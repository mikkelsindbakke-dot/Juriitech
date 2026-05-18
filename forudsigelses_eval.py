"""
forudsigelses_eval — bagvedliggende feedback-løkke for PAX.

FORMÅL: gøre PAX målbart klogere over tid uden at røre den eksisterende
opsætning og uden at noget bliver synligt for brugeren.

Sådan virker det:
  1. Når PAX laver en førstevurdering, gemmer database.log_forudsigelse()
     PAX' forudsigelse (3 sandsynligheder + konklusion) sammen med
     sagsnummeret i tabellen 'forudsigelses_log'.
  2. Senere offentliggør Nævnet den faktiske afgørelse, og scraperen
     henter den ind i vidensbanken (mine_dokumenter, dokumenttype=
     'afgoerelse').
  3. Dette script ('match'-mode) matcher gemte forudsigelser mod de
     faktiske afgørelser via sagsnummeret og noterer om PAX ramte rigtigt.
  4. 'rapport'-mode printer en nøjagtigheds-statistik til udvikleren.

Intet af dette er synligt for sagsbehandlere. Capture-trinnet er
fire-and-forget (kan aldrig blokere eller fejle en analyse). Matching
og rapportering kører som offline-scripts udvikleren selv starter:

    python3 forudsigelses_eval.py match     # match nye afgørelser
    python3 forudsigelses_eval.py rapport   # vis nøjagtigheds-statistik
"""
import re
import sys


# ─────────────────────────────────────────────────────────────────
# RENE HJÆLPEFUNKTIONER (deterministiske, fuldt unit-testede)
# ─────────────────────────────────────────────────────────────────

# Et sagsnummer er 2-4 cifre efterfulgt af mindst én gruppe mere,
# adskilt af bindestreg/punktum/skråstreg. Dækker både norsk
# ('2026-00660') og dansk ('25-1234', '25-109-8024327').
_SAGSNUMMER_RE = re.compile(r"\d{2,4}(?:[-./]\d{2,8})+")


def normaliser_sagsnummer(raw):
    """
    Normaliserer et sagsnummer til en kanonisk form der kan sammenlignes
    på tværs af upload-tidspunkt og publiceret afgørelse.

    Fjerner .pdf-suffix, anchor-ord ('Sag nr.', 'Sagsnummer:' osv.) og
    whitespace, og udtrækker selve nummer-tokenet. Returnerer tom streng
    hvis intet sagsnummer-mønster findes.
    """
    if not raw:
        return ""
    t = str(raw).strip()
    # Fjern .pdf-endelse (case-insensitivt)
    t = re.sub(r"\.pdf$", "", t, flags=re.IGNORECASE)
    m = _SAGSNUMMER_RE.search(t)
    return m.group(0) if m else ""


def normaliser_udfald(raw):
    """
    Mapper et fritekst-udfald (fra PAX eller fra en scrapet afgørelse)
    til én kanonisk værdi: 'fuld_medhold' | 'delvist_medhold' |
    'afvist' | 'ukendt'.

    Rækkefølgen er bevidst: 'delvis'/'delvist' tjekkes FØR 'medhold'
    (fordi 'delvis medhold' indeholder 'medhold'), og afvisnings-
    signaler tjekkes før 'medhold' (fordi 'ikke medhold' indeholder det).
    """
    if not raw:
        return "ukendt"
    t = str(raw).strip().lower()
    if not t or t == "ukendt":
        return "ukendt"
    if "delvis" in t or "delvist" in t:
        return "delvist_medhold"
    if (
        "ikke medhold" in t
        or "afvist" in t
        or "afvises" in t
        or "frifind" in t
        or "ikke til følge" in t
        or "ikke tages til følge" in t
    ):
        return "afvist"
    if "medhold" in t or "fuld" in t or "fullt" in t:
        return "fuld_medhold"
    return "ukendt"


def pax_argmax_bucket(fuld, delvist, afvisning):
    """
    Returnerer den udfalds-kategori PAX vurderede mest sandsynlig ud fra
    de tre procent-tal. Tie-break-rækkefølge: fuld > delvist > afvist.
    None behandles som 0.
    """
    f = fuld or 0
    d = delvist or 0
    a = afvisning or 0
    if f >= d and f >= a:
        return "fuld_medhold"
    if d >= a:
        return "delvist_medhold"
    return "afvist"


def beregn_traf_rigtigt(pax_bucket, faktisk_udfald):
    """
    Afgør om PAX' mest sandsynlige bud ramte den faktiske afgørelse.
    Returnerer None hvis det faktiske udfald er 'ukendt' (kan ikke score).
    """
    if not faktisk_udfald or faktisk_udfald == "ukendt":
        return None
    return pax_bucket == faktisk_udfald


# Udtræk 'Udfall:'/'Udfald:'-headeren fra en scrapet afgørelses indhold.
# Scraperen lægger en struktureret header øverst: "Saksnummer: ... Dato:
# ... Tjenesteyter: ... Udfall: Ikke medhold Sammendrag: ...".
_UDFALD_HEADER_RE = re.compile(
    r"\bUdfal[dl]\s*:\s*(.+?)(?:\s+(?:Sammendrag|Sammenfatning)\s*:|\n|$)",
    re.IGNORECASE,
)


def udtraek_udfald_fra_afgoerelse(indhold):
    """
    Udtrækker det faktiske udfald fra en scrapet afgørelses indhold.

    Bruger primært den strukturerede 'Udfall:'/'Udfald:'-header som
    scraperen lægger øverst. Returnerer en kanonisk udfalds-værdi
    (via normaliser_udfald) eller 'ukendt' hvis headeren mangler.
    """
    if not indhold:
        return "ukendt"
    m = _UDFALD_HEADER_RE.search(indhold)
    if m:
        return normaliser_udfald(m.group(1))
    return "ukendt"


# Udtræk 'Saksnummer:'/'Sagsnummer:'-headeren fra en afgørelses indhold —
# brugt som sekundær match-nøgle hvis filnavnet ikke bærer sagsnummeret.
_SAKSNUMMER_HEADER_RE = re.compile(
    r"\bSa[gk]snummer\s*:\s*(\S+)", re.IGNORECASE
)


def udtraek_sagsnummer_fra_afgoerelse(indhold):
    """Udtrækker sagsnummeret fra en afgørelses 'Saksnummer:'-header
    (normaliseret). Tom streng hvis headeren mangler."""
    if not indhold:
        return ""
    m = _SAKSNUMMER_HEADER_RE.search(indhold)
    return normaliser_sagsnummer(m.group(1)) if m else ""


# ─────────────────────────────────────────────────────────────────
# MATCHING + RAPPORT (offline — kører kun når udvikleren starter scriptet)
# ─────────────────────────────────────────────────────────────────

def _db_connect():
    """Direkte psycopg2-forbindelse til offline-brug. Scripts har ingen
    request-kontekst, så vi behøver ikke database._connect()'s RLS-setup."""
    import os
    import psycopg2
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL ikke sat")
    return psycopg2.connect(db_url)


def match_alle():
    """
    'match'-mode: matcher endnu-ikke-matchede forudsigelser mod de
    afgørelser nævnet har offentliggjort siden sidst.

    For hver umatchet række i forudsigelses_log: slå op om der findes en
    scrapet afgørelse (mine_dokumenter, dokumenttype='afgoerelse') med
    samme sagsnummer. Hvis ja: udtræk det faktiske udfald, beregn om PAX
    ramte rigtigt, og opdatér rækken.

    Returnerer (antal_matchet, antal_umatchede_tilbage).
    """
    conn = _db_connect()
    try:
        cur = conn.cursor()

        # Byg opslags-tabel: sagsnummer_norm → (dokument_id, indhold-header).
        # Indekseret på BÅDE filnavn og 'Saksnummer:'-headeren for robusthed.
        cur.execute(
            "SELECT id, filnavn, LEFT(indhold, 600) "
            "FROM mine_dokumenter WHERE dokumenttype = 'afgoerelse'"
        )
        afgoerelser = {}
        for doc_id, filnavn, header in cur.fetchall():
            header = header or ""
            for noegle in (
                normaliser_sagsnummer(filnavn or ""),
                udtraek_sagsnummer_fra_afgoerelse(header),
            ):
                if noegle and noegle not in afgoerelser:
                    afgoerelser[noegle] = (doc_id, header)

        # Hent umatchede forudsigelser.
        cur.execute(
            "SELECT id, sagsnummer_norm, pax_bucket "
            "FROM forudsigelses_log WHERE faktisk_udfald IS NULL"
        )
        umatchede = cur.fetchall()

        matchet = 0
        for pred_id, sagsnr_norm, pax_bucket in umatchede:
            fund = afgoerelser.get(sagsnr_norm)
            if not fund:
                continue
            doc_id, header = fund
            faktisk = udtraek_udfald_fra_afgoerelse(header)
            traf = beregn_traf_rigtigt(pax_bucket or "", faktisk)
            cur.execute(
                "UPDATE forudsigelses_log SET faktisk_udfald = %s, "
                "faktisk_dokument_id = %s, traf_rigtigt = %s, "
                "matchet_tidspunkt = NOW() WHERE id = %s",
                (faktisk, doc_id, traf, pred_id),
            )
            matchet += 1

        conn.commit()
        cur.execute(
            "SELECT COUNT(*) FROM forudsigelses_log WHERE faktisk_udfald IS NULL"
        )
        tilbage = cur.fetchone()[0]
        cur.close()
        return matchet, tilbage
    finally:
        conn.close()


def byg_rapport():
    """
    'rapport'-mode: printer en nøjagtigheds-statistik over PAX'
    forudsigelser til udvikleren. Ren konsol-output — intet gemmes,
    intet vises til brugere.
    """
    conn = _db_connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM forudsigelses_log")
        i_alt = cur.fetchone()[0]
        cur.execute(
            "SELECT COUNT(*) FROM forudsigelses_log "
            "WHERE faktisk_udfald IS NOT NULL"
        )
        matchet = cur.fetchone()[0]
        cur.execute(
            "SELECT COUNT(*) FROM forudsigelses_log "
            "WHERE traf_rigtigt IS NOT NULL"
        )
        scorbare = cur.fetchone()[0]
        cur.execute(
            "SELECT COUNT(*) FROM forudsigelses_log WHERE traf_rigtigt = TRUE"
        )
        ramt = cur.fetchone()[0]

        print("=" * 56)
        print("  PAX FORUDSIGELSES-NØJAGTIGHED")
        print("=" * 56)
        print(f"  Gemte forudsigelser i alt:      {i_alt}")
        print(f"  Matchet med en afgørelse:       {matchet}")
        print(f"  Scorbare (kendt faktisk udfald): {scorbare}")
        if scorbare:
            pct = 100.0 * ramt / scorbare
            print(f"\n  SAMLET TRÆFSIKKERHED: {pct:.1f}%  ({ramt} af {scorbare})")
        else:
            print("\n  (Ingen scorbare endnu — kør 'match' når nævnet "
                  "har offentliggjort afgørelser.)")

        # Pr. bucket PAX forudsagde
        cur.execute(
            "SELECT pax_bucket, "
            "  COUNT(*) FILTER (WHERE traf_rigtigt IS NOT NULL), "
            "  COUNT(*) FILTER (WHERE traf_rigtigt = TRUE) "
            "FROM forudsigelses_log "
            "WHERE traf_rigtigt IS NOT NULL "
            "GROUP BY pax_bucket ORDER BY pax_bucket"
        )
        bucket_rows = cur.fetchall()
        if bucket_rows:
            print("\n  Pr. udfald PAX forudsagde (træf / scorbare):")
            for bucket, n, r in bucket_rows:
                p = f"{100.0 * r / n:.0f}%" if n else "-"
                print(f"    {bucket:18s} {r}/{n}   ({p})")

        # Konfusionsmatrix: PAX forudsagde → faktisk
        cur.execute(
            "SELECT pax_bucket, faktisk_udfald, COUNT(*) "
            "FROM forudsigelses_log WHERE traf_rigtigt IS NOT NULL "
            "GROUP BY pax_bucket, faktisk_udfald "
            "ORDER BY pax_bucket, faktisk_udfald"
        )
        konf = cur.fetchall()
        if konf:
            print("\n  Konfusion (PAX forudsagde → faktisk udfald):")
            for pax_b, faktisk, n in konf:
                markor = "✓" if pax_b == faktisk else "✗"
                print(f"    {markor} {pax_b:18s} → {faktisk:18s} {n}")
        print("=" * 56)
        cur.close()
    finally:
        conn.close()


def main():
    """CLI: 'match' matcher nye afgørelser, 'rapport' viser statistik."""
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "match":
        matchet, tilbage = match_alle()
        print(
            f"✓ Match færdig: {matchet} nye forudsigelser matchet mod "
            f"afgørelser. {tilbage} venter stadig på offentliggørelse."
        )
    elif mode == "rapport":
        byg_rapport()
    else:
        print("Brug: python3 forudsigelses_eval.py [match|rapport]")
        print("  match    — match gemte forudsigelser mod nye afgørelser")
        print("  rapport  — vis PAX' nøjagtigheds-statistik")
        sys.exit(1)


if __name__ == "__main__":
    main()
