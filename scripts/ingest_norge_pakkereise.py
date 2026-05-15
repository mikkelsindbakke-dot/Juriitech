"""
ingest_norge_pakkereise.py

Læser PDFs fra data_imports/norge_afgoerelser/pakkereise/, ekstraherer
metadata + tekst, embedder via Voyage, og INSERT'er i mine_dokumenter
med land='NO' + is_public=TRUE.

SIKKERHED FOR DANSK PAX:
- Scriptet ROR ALDRIG eksisterende rækker (kun INSERT)
- Alle nye rækker tagges land='NO' — kan ikke ses af danske tenants
  pga. RAG-filterets WHERE land = caller_tenant.land
- Hvis scriptet kører to gange på samme PDF, deduperes via filnavn-check
- Hvis embedding fejler, gemmes sagen alligevel (uden embedding) så vi
  kan re-embedde senere — RAG springer rækker uden embedding over

KØRSEL:
  # Tør-kørsel (vis hvad der ville ske):
  python3 scripts/ingest_norge_pakkereise.py

  # Faktisk ingest:
  python3 scripts/ingest_norge_pakkereise.py --execute

  # Med batch-cap (test):
  python3 scripts/ingest_norge_pakkereise.py --execute --max 5

OBS: Forventer at migration_land_kolonne.py er kørt så land-kolonnen findes.
"""

import argparse
import os
import re
import sys
from pathlib import Path
from datetime import datetime

ROD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROD)

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(ROD, ".env"))
load_dotenv(os.path.join(ROD, "pax-next", ".env.local"), override=False)

from pypdf import PdfReader  # noqa: E402
from database import _connect  # noqa: E402
from embeddings import embed_dokument  # noqa: E402

INPUT_DIR = Path(ROD) / "data_imports" / "norge_afgoerelser" / "pakkereise"
PROCESSED_DIR = Path(ROD) / "data_imports" / "norge_afgoerelser" / "processed"


# ─────────────────────────────────────────────────────────────────
# PARSING — udled metadata fra PDF-indhold
# ─────────────────────────────────────────────────────────────────

# Mønstre der matcher Pakkereisenemndas standard-format:
#   "Saksnummer\n2026-00581"
#   "Dato\n07.05.2026"
#   "Tjenesteytere\nVing Norge AS"
SAKSNUMMER_RE = re.compile(
    r"Saksnummer\s*[\r\n]+\s*(\d{4}-\d+)", re.IGNORECASE
)
DATO_RE = re.compile(
    r"Dato\s*[\r\n]+\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})", re.IGNORECASE
)
TJENESTEYTER_RE = re.compile(
    r"Tjenesteytere?\s*[\r\n]+\s*([^\r\n]+)", re.IGNORECASE
)
SAMMENDRAG_RE = re.compile(
    r"Sammendrag\s*[\r\n]+\s*([^\r\n]+(?:\s+[^\r\n]+)?)", re.IGNORECASE
)

# Udfald-detektion: Pakkereisenemnda's standard-format er at det FINALE
# udfald står efter "Vedtak"-overskriften i slutningen af PDF'en. Format:
#   "Pakkereisenemnda anbefaler at klager [ikke|delvis] gis medhold."
#
# Vi søger i de sidste ~1500 tegn for at undgå at fange tidligere
# omtaler i teksten (fx "klager gis ikke medhold" i selve sagsfremstillingen
# der modsiger den endelige afgørelse). Vedtak-sektionen er ALTID til sidst.
UDFALD_MOENSTRE = [
    # Mest specifikke først — "ikke gis medhold" matcher før "gis medhold"
    (r"anbefaler\s+at\s+klager\s+ikke\s+gis\s+medhold", "Ikke medhold"),
    (r"anbefaler\s+at\s+klager\s+gis\s+delvis\s+medhold", "Delvis medhold"),
    (r"anbefaler\s+at\s+klager\s+gis\s+medhold", "Medhold"),
    # Backup-mønstre hvis "anbefaler"-formulering ikke bruges
    (r"klagen\s+tas\s+ikke\s+til\s+f.lge", "Ikke medhold"),
    (r"klagen\s+f.rer\s+ikke\s+fram", "Ikke medhold"),
    (r"klager\s+gis\s+delvis\s+medhold", "Delvis medhold"),
    (r"klager\s+gis\s+medhold", "Medhold"),
    (r"klagen\s+tas\s+til\s+f.lge", "Medhold"),
    # Saker avvist uden realitetsbehandling (typisk pga. bevisspørsmål
    # der kræver muntlig forhandling). Klager får intet, så det rangerer
    # som "Avvist" — en variant af Ikke medhold men mere præcis.
    (r"saken\s+avvises", "Avvist"),
]


def parse_pdf(sti: Path) -> dict:
    """Parser én PDF og returnerer struktureret metadata + fuld tekst."""
    reader = PdfReader(str(sti))
    fuld_tekst = ""
    for side in reader.pages:
        try:
            fuld_tekst += side.extract_text() + "\n"
        except Exception:
            continue

    # Saksnummer (kritisk — bruges som id)
    saksnummer = None
    m = SAKSNUMMER_RE.search(fuld_tekst)
    if m:
        saksnummer = m.group(1).strip()

    # Dato
    dato = None
    m = DATO_RE.search(fuld_tekst)
    if m:
        dato = m.group(1).strip()

    # Tjenesteyter
    tjenesteyter = None
    m = TJENESTEYTER_RE.search(fuld_tekst)
    if m:
        tjenesteyter = m.group(1).strip()

    # Sammendrag
    sammendrag = None
    m = SAMMENDRAG_RE.search(fuld_tekst)
    if m:
        sammendrag = m.group(1).strip()

    # Udfald — søg KUN i de sidste ~1500 tegn (Vedtak-sektion). Det
    # forhindrer false positives fra tidligere omtaler i sagsfremstillingen.
    udfald = None
    sidste_del = fuld_tekst[-1500:].lower() if len(fuld_tekst) > 1500 else fuld_tekst.lower()
    for moenster, label in UDFALD_MOENSTRE:
        if re.search(moenster, sidste_del):
            udfald = label
            break

    return {
        "filnavn_original": sti.name,
        "saksnummer": saksnummer,
        "dato": dato,
        "tjenesteyter": tjenesteyter,
        "sammendrag": sammendrag,
        "udfald": udfald,
        "fuld_tekst": fuld_tekst.strip(),
        "antal_tegn": len(fuld_tekst),
        "antal_sider": len(reader.pages),
    }


# ─────────────────────────────────────────────────────────────────
# INGEST — gem i database
# ─────────────────────────────────────────────────────────────────

def findes_allerede(cur, filnavn: str) -> bool:
    """Tjek om en sag med dette filnavn allerede er ingested."""
    cur.execute(
        "SELECT 1 FROM mine_dokumenter WHERE filnavn = %s LIMIT 1",
        (filnavn,),
    )
    return cur.fetchone() is not None


def gem_i_db(cur, sag: dict, embedding) -> int:
    """INSERT'er sagen i mine_dokumenter med land='NO'. Returnerer id."""
    # Vi bruger saksnummer.pdf som filnavn hvis tilgængeligt, ellers original
    if sag["saksnummer"]:
        filnavn = f"{sag['saksnummer']}.pdf"
    else:
        filnavn = sag["filnavn_original"]

    # Header der prepender struktureret metadata til teksten — gør RAG
    # i stand til at finde sagerne via tjenesteyter/udfald-keywords.
    header = (
        f"Saksnummer: {sag['saksnummer'] or 'ukendt'}\n"
        f"Dato: {sag['dato'] or 'ukendt'}\n"
        f"Tjenesteyter: {sag['tjenesteyter'] or 'ukendt'}\n"
        f"Udfall: {sag['udfald'] or 'ukendt'}\n"
        f"Sammendrag: {sag['sammendrag'] or '(ingen)'}\n\n"
        f"---FULL AFGØRELSE NEDENFOR---\n\n"
    )
    indhold = header + sag["fuld_tekst"]

    # Specifik kilde-URL pr. sag — stable URL der direkte returnerer PDF'en.
    # Mønstret er afdækket via inspektion af eksisterende rækker. Hvis vi
    # ikke har saksnummer (fallback), bruger vi den generiske URL.
    if sag["saksnummer"]:
        kilde_url = (
            "https://reiselivsforum.no/digiforms/sessionInitializer?"
            f"processName=vedtak_PDF_Process&case={sag['saksnummer']}"
        )
    else:
        kilde_url = "https://reiselivsforum.no/web/dommer_og_avgjoerelser/"

    cur.execute(
        """
        INSERT INTO mine_dokumenter
            (filnavn, indhold, dokumenttype, embedding,
             kilde_url, tenant_id, is_public, land,
             er_krypteret, oprettet_dato)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        RETURNING id
        """,
        (
            filnavn,
            indhold,
            "afgoerelse",
            embedding,  # None hvis embedding fejlede
            kilde_url,
            None,           # tenant_id NULL — det er PUBLIC data
            True,           # is_public — synlig for alle norske tenants
            "NO",           # land — afgør hvilke tenants der ser den
            False,          # er_krypteret — public docs krypteres ikke
        ),
    )
    return cur.fetchone()[0]


# ─────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--execute", action="store_true",
        help="Faktisk INSERT i databasen. Uden flag: kun parsing + rapport.",
    )
    parser.add_argument(
        "--max", type=int, default=None,
        help="Maks antal sager at behandle (til test). Default: alle.",
    )
    args = parser.parse_args()

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(
        [p for p in INPUT_DIR.glob("*.pdf") if not p.name.startswith(".")]
    )
    if args.max:
        pdfs = pdfs[: args.max]
    if not pdfs:
        print(f"Ingen PDFs i {INPUT_DIR}")
        return

    print("=" * 70)
    print(f"INGEST: {len(pdfs)} PDFs fra {INPUT_DIR}")
    print(f"Mode: {'EXECUTE' if args.execute else 'TØR-KØRSEL'}")
    print("=" * 70)

    # Hvis execute: forbind til DB
    conn = cur = None
    if args.execute:
        conn = _connect()
        cur = conn.cursor()

    succes = 0
    fejlet = 0
    sprunget = 0

    for i, pdf_sti in enumerate(pdfs, 1):
        print(f"\n[{i}/{len(pdfs)}] {pdf_sti.name}")
        try:
            sag = parse_pdf(pdf_sti)
        except Exception as e:
            print(f"  ✗ Parse-fejl: {e}")
            fejlet += 1
            continue

        # Rapport
        print(f"  Saksnummer:    {sag['saksnummer'] or '(MANGLER)'}")
        print(f"  Dato:          {sag['dato'] or '(MANGLER)'}")
        print(f"  Tjenesteyter:  {sag['tjenesteyter'] or '(MANGLER)'}")
        print(f"  Udfald:        {sag['udfald'] or '(IKKE DETEKTERET)'}")
        print(f"  Tekst:         {sag['antal_tegn']} tegn, {sag['antal_sider']} sider")
        if sag["sammendrag"]:
            print(f"  Sammendrag:    {sag['sammendrag'][:80]}...")

        if not args.execute:
            continue

        # Tjek om allerede ingested (baseret på saksnummer-filnavn)
        target_filnavn = (
            f"{sag['saksnummer']}.pdf"
            if sag["saksnummer"] else pdf_sti.name
        )
        if findes_allerede(cur, target_filnavn):
            print(f"  ⊙ Allerede ingested ({target_filnavn}) — springer over")
            sprunget += 1
            # Flyt til processed alligevel
            try:
                pdf_sti.rename(PROCESSED_DIR / pdf_sti.name)
            except Exception:
                pass
            continue

        # Embed
        try:
            print(f"  → Embedder via Voyage ...")
            embedding = embed_dokument(sag["fuld_tekst"])
            if embedding is None:
                print(f"    ⚠ Embedding returnerede None — gemmer uden")
        except Exception as e:
            print(f"    ⚠ Embedding-fejl: {e} — gemmer uden embedding")
            embedding = None

        # Gem
        try:
            doc_id = gem_i_db(cur, sag, embedding)
            conn.commit()
            print(f"  ✓ Gemt som id={doc_id} med land='NO'")
            # Flyt til processed-mappen
            pdf_sti.rename(PROCESSED_DIR / pdf_sti.name)
            succes += 1
        except Exception as e:
            conn.rollback()
            print(f"  ✗ DB-fejl: {e}")
            fejlet += 1

    if cur:
        cur.close()
    if conn:
        conn.close()

    print("\n" + "=" * 70)
    print("RAPPORT")
    print("=" * 70)
    print(f"  Behandlet: {len(pdfs)}")
    print(f"  Succes:    {succes}")
    print(f"  Sprunget:  {sprunget} (allerede i DB)")
    print(f"  Fejlet:    {fejlet}")
    if args.execute and succes:
        print(f"\nNorske afgørelser kan nu findes via RAG når en tenant med")
        print(f"land='NO' er aktiv. Dansk PAX er upåvirket.")


if __name__ == "__main__":
    main()
