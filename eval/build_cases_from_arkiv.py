"""
Bygger eval-cases fra din analyse_arkiv.

Trækker N distinkte sager fra den aktive tenant's arkiv, ekstraherer
første-klagepunkter-sektionen som query, og citerede præcedenser som
expected_filenames. Skriver resultatet i det format run_eval.py forventer.

KØRSEL:
    python3 eval/build_cases_from_arkiv.py            # 10 cases → eval/cases.json
    python3 eval/build_cases_from_arkiv.py --n 20     # 20 cases
    python3 eval/build_cases_from_arkiv.py --output eval/cases-tui.json
    python3 eval/build_cases_from_arkiv.py --force    # overwrite eksisterende
    python3 eval/build_cases_from_arkiv.py --tenant-slug apollo

PRIVACY:
    Output-fil er per default eval/cases.json som er gitignored.
    Hvis du overrider med --output, så pas på filnavnet ikke matcher
    et versioneret mønster (kun cases.example.json + cases.json/cases-*.json
    pattern er sikre — alt andet kan ende i git).

REPRODUCERBART:
    Kør scriptet igen om en uge eller måned for at refresh cases med
    nyere sager fra dit arkiv. Eksisterende cases.json overskrives ikke
    medmindre du sender --force.

DEDUP-STRATEGI:
    To analyser regnes for samme case hvis de citerer NØJAGTIG samme
    sæt af præcedenser. Det er en grov heuristik, men tilstrækkelig
    til at fange gen-runs af samme klage.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv()

import psycopg2  # noqa: E402

EVAL_DIR = PROJECT_ROOT / "eval"
DEFAULT_OUTPUT = EVAL_DIR / "cases.json"

# Match Claude's standard reference-format: [Afgørelse 22-885 (2022)] eller
# [Afgørelse 2015.0220 (2015)]. Året er valgfrit.
REF_PATTERN = re.compile(
    r"\[Afg[øo]relse[s]?\s+([\d\.\-]+)(?:\s*\(\d{4}\))?\]",
    re.IGNORECASE,
)


def hent_tenant_id(conn, slug: str | None) -> tuple[int, str]:
    """Returnerer (tenant_id, tenant_slug). Hvis slug=None bruges TUI som default."""
    cur = conn.cursor()
    target_slug = slug or "tui"
    cur.execute("SELECT id, slug FROM tenants WHERE slug = %s", (target_slug,))
    row = cur.fetchone()
    cur.close()
    if not row:
        print(f"❌ Tenant med slug '{target_slug}' findes ikke.")
        sys.exit(1)
    return row[0], row[1]


def hent_tilgængelige_filnavne(conn, tenant_id: int) -> set[str]:
    """
    Returnerer alle filnavne i mine_dokumenter der er synlige for denne tenant
    (egne private docs + alle is_public). Bruges til at validere at citerede
    præcedenser faktisk findes i vidensbanken.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT filnavn FROM mine_dokumenter
        WHERE filnavn IS NOT NULL
          AND (is_public = TRUE OR tenant_id = %s)
        """,
        (tenant_id,),
    )
    filnavne = {r[0] for r in cur.fetchall()}
    cur.close()
    return filnavne


def map_sagsnummer_til_filnavn(sagsnummer: str, kendte_filnavne: set[str]) -> str | None:
    """
    Mapper et sagsnummer som '22-885' eller '2015.0220' til den faktiske
    filnavn i mine_dokumenter. Prøver flere konventioner:
        '22-885'      → '22-885.pdf', '22-885.docx', '22-885.doc', osv.
        '2015.0220'   → '2015.0220.pdf' osv.
    Returnerer den FØRSTE match — typisk findes hvert sagsnummer kun
    i én version i vidensbanken.
    """
    # Prøv kendte extensions i prioritet
    for ext in (".pdf", ".docx", ".doc", ".PDF", ".DOCX", ""):
        kandidat = f"{sagsnummer}{ext}"
        if kandidat in kendte_filnavne:
            return kandidat
    # Fallback: case-insensitiv match på sagsnummer som prefix
    lower_prefix = sagsnummer.lower()
    for fn in kendte_filnavne:
        fn_lower = fn.lower()
        # Match hvis filnavnet starter med sagsnummer fulgt af '.' eller '-' eller slut
        if fn_lower.startswith(lower_prefix):
            rest = fn_lower[len(lower_prefix):]
            if not rest or rest[0] in ".-_":
                return fn
    return None


def udtræk_klagepunkter(indhold: str) -> str:
    """
    Trækker indholdet af '1. Klagens kernepunkter'-sektionen ud, som vi
    bruger som query. Hvis sektionen ikke findes (fx svarbrev eller
    tjekliste), returnér første 500 tegn af indhold som fallback.
    """
    m = re.search(
        r"\*\*1\.\s+Klagens?\s+kernepunkter?\*\*\s*(.+?)(?=\*\*[2-9]\.)",
        indhold or "",
        re.DOTALL,
    )
    if m:
        # Strip whitespace og collaps lange newlines
        tekst = m.group(1).strip()
        # Behold bullets men skær ned til ~1500 tegn så querien er fokuseret
        if len(tekst) > 1500:
            tekst = tekst[:1500].rstrip() + " [...]"
        return tekst
    return (indhold or "").strip()[:1500]


def lav_id(klagepunkter: str, idx: int) -> str:
    """Lav et kort stikordsnavn til case-id baseret på første ord af første bullet."""
    # Find første '- '-bullet
    m = re.search(r"-\s+(?:Klagepunkt\s+\d+:\s*)?([^\n]+)", klagepunkter)
    if not m:
        return f"sag-{idx:02d}"
    første_linje = m.group(1).lower()
    # Tag de første 3 meningsfulde ord
    ord_liste = re.findall(r"[a-zæøå]{3,}", første_linje)
    stop = {"klager", "tui", "fejlagtigt", "har", "været", "blev", "er", "med", "for", "ved", "som", "der", "den"}
    nøgle = [o for o in ord_liste if o not in stop][:3]
    if not nøgle:
        return f"sag-{idx:02d}"
    return f"{idx:02d}-" + "-".join(nøgle)


def byg_cases(conn, tenant_id: int, n: int) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, type, klage_filnavn, oprettet_dato, indhold
        FROM analyse_arkiv
        WHERE tenant_id = %s
          AND type = 'analyse'
        ORDER BY oprettet_dato DESC
        """,
        (tenant_id,),
    )
    rows = cur.fetchall()
    cur.close()

    kendte_filnavne = hent_tilgængelige_filnavne(conn, tenant_id)
    print(f"📚 {len(kendte_filnavne)} filnavne tilgængelige i tenant's vidensbank")

    cases: list[dict] = []
    seen_refsets: set[frozenset[str]] = set()
    sprunget_uden_refs = 0
    sprunget_uden_match = 0

    for aid, atype, kfn, dato, indhold in rows:
        sagsnumre = set(REF_PATTERN.findall(indhold or ""))
        if not sagsnumre:
            sprunget_uden_refs += 1
            continue
        refset = frozenset(sagsnumre)
        if refset in seen_refsets:
            continue

        # Map sagsnumre → faktiske filnavne
        expected = []
        manglende = []
        for sn in sorted(sagsnumre):
            fn = map_sagsnummer_til_filnavn(sn, kendte_filnavne)
            if fn:
                expected.append(fn)
            else:
                manglende.append(sn)
        if not expected:
            sprunget_uden_match += 1
            continue

        seen_refsets.add(refset)
        klagepunkter = udtræk_klagepunkter(indhold)
        case_id = lav_id(klagepunkter, len(cases) + 1)

        case = {
            "id": case_id,
            "description": (
                f"Trukket fra analyse #{aid} ({dato.strftime('%Y-%m-%d')}). "
                f"Klage_filnavn: {kfn or '(ingen)'}."
            ),
            "query": klagepunkter,
            "expected_filenames": expected,
            "notes": (
                f"Auto-genereret fra analyse_arkiv. Citerede sagsnumre i AI-vurdering: "
                f"{sorted(sagsnumre)}."
                + (f" Ikke fundet som filnavn: {manglende}." if manglende else "")
            ),
            "_meta": {
                "kilde_analyse_id": aid,
                "kilde_analyse_dato": dato.isoformat(),
                "klage_filnavn": kfn,
            },
        }
        cases.append(case)
        if len(cases) >= n:
            break

    print(
        f"📊 {len(cases)} unikke cases bygget. "
        f"Sprunget {sprunget_uden_refs} uden citationer, "
        f"{sprunget_uden_match} hvor ingen citationer kunne mappes til filnavn."
    )
    return cases


def main():
    parser = argparse.ArgumentParser(
        description="Byg eval-cases fra analyse_arkiv (privat, tenant-isoleret)"
    )
    parser.add_argument("--n", type=int, default=10,
                        help="Antal unikke cases der skal trækkes (default 10)")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT),
                        help="Output-fil. Default eval/cases.json (gitignored).")
    parser.add_argument("--force", action="store_true",
                        help="Overskriv eksisterende output-fil uden at spørge")
    parser.add_argument("--tenant-slug", type=str, default=None,
                        help="Filter på tenant slug (default: 'tui'). "
                             "Brug 'apollo' eller 'spies' for andre tenants.")
    args = parser.parse_args()

    output_path = Path(args.output)

    # Privacy-check: advar hvis output-filen ligner et navn der KUNNE være versioneret
    if output_path.name == "cases.example.json":
        print("❌ Output må IKKE være cases.example.json — den er en versioneret template.")
        print("   Brug eval/cases.json eller eval/cases-<tenant>.json i stedet.")
        sys.exit(1)

    if output_path.exists() and not args.force:
        print(f"❌ {output_path} findes allerede. Brug --force for at overskrive.")
        sys.exit(1)

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("❌ DATABASE_URL ikke sat i .env")
        sys.exit(1)

    conn = psycopg2.connect(db_url)
    try:
        tenant_id, tenant_slug = hent_tenant_id(conn, args.tenant_slug)
        print(f"🏢 Tenant: {tenant_slug} (id={tenant_id})")

        cases = byg_cases(conn, tenant_id, args.n)
        if not cases:
            print("⚠️  Ingen brugbare cases fundet. Afbryder uden at skrive output.")
            sys.exit(1)

        output_data = {
            "_kommentar": (
                f"Auto-genereret fra analyse_arkiv via build_cases_from_arkiv.py "
                f"({len(cases)} cases for tenant '{tenant_slug}'). "
                "Privat klient-data — gitignored. Kør scriptet igen for at refresh."
            ),
            "version": "1",
            "tenant_slug": tenant_slug,
            "cases": cases,
        }

        with output_path.open("w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        print(f"✅ Skrevet til {output_path}")
        print(f"   Næste skridt: python3 eval/run_eval.py")
        if output_path == DEFAULT_OUTPUT:
            print("   (cases.json er gitignored — dine private cases ender ikke i git)")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
