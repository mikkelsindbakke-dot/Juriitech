"""
download_norge_pdfs.py

Henter PDF-afgørelser fra reiselivsforum.no via stabile URL'er:
  https://reiselivsforum.no/digiforms/sessionInitializer
    ?processName=vedtak_PDF_Process&case=<SAKSNR>

INPUT: data_imports/norge_afgoerelser/saksnummer_pakkereise.txt
        (produceret af scrape_norge_saksnummer.py)

OUTPUT: data_imports/norge_afgoerelser/pakkereise/<SAKSNR>.pdf
        (klar til ingest_norge_pakkereise.py)

POLITE DOWNLOADS:
- User-Agent: juriitech-pax-bot (mikkelsindbakke@gmail.com)
- 1-3 sek random delay mellem hver download
- Stopper hvis vi rammer fejl-grænse (5 fejl i træk = noget er galt)
- Skipper sager der allerede er downloaded
- Logger til stdout så vi kan følge med

KØRSEL:
  # Test med 5 sager:
  python3 scripts/download_norge_pdfs.py --max 5

  # Hent alle saksnummer fra listen:
  python3 scripts/download_norge_pdfs.py

  # Re-download (overskriv eksisterende):
  python3 scripts/download_norge_pdfs.py --force
"""

import argparse
import os
import random
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests

ROD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

INPUT_FIL = (
    Path(ROD) / "data_imports" / "norge_afgoerelser" / "saksnummer_pakkereise.txt"
)
OUTPUT_DIR = (
    Path(ROD) / "data_imports" / "norge_afgoerelser" / "pakkereise"
)

PDF_URL_TEMPLATE = (
    "https://reiselivsforum.no/digiforms/sessionInitializer"
    "?processName=vedtak_PDF_Process&case={saksnr}"
)

USER_AGENT = (
    "juriitech-pax-bot/1.0 (mikkelsindbakke@gmail.com; "
    "juridisk research, contact for issues)"
)


def laes_saksnummer_liste(sti: Path) -> list[str]:
    """Læs saksnummer-listen fra fil (TSV med #-kommentarer)."""
    if not sti.exists():
        print(f"FEJL: {sti} findes ikke. Kør scrape_norge_saksnummer.py først.")
        sys.exit(1)
    saksnr = []
    with open(sti) as f:
        for linje in f:
            linje = linje.strip()
            if not linje or linje.startswith("#"):
                continue
            sn = linje.split("\t")[0].strip()
            if sn and "-" in sn:
                saksnr.append(sn)
    return saksnr


def download_pdf(session: requests.Session, saksnr: str,
                 output_dir: Path) -> tuple[bool, str]:
    """
    Download én PDF. Returnerer (success, fejl-besked).
    """
    target = output_dir / f"{saksnr}.pdf"
    url = PDF_URL_TEMPLATE.format(saksnr=quote(saksnr))

    try:
        resp = session.get(url, timeout=30, stream=True)
        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code}"

        ct = resp.headers.get("content-type", "")
        if "pdf" not in ct.lower():
            return False, f"Forkert content-type: {ct}"

        target.write_bytes(resp.content)

        # Sanity-tjek: må ikke være 0 bytes
        if target.stat().st_size < 1000:
            target.unlink(missing_ok=True)
            return False, f"PDF for lille ({target.stat().st_size} bytes)"

        return True, ""
    except Exception as e:
        return False, str(e)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--max", type=int, default=None,
        help="Maks antal at downloade (test). Default: alle.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overskriv eksisterende PDFs.",
    )
    parser.add_argument(
        "--delay-min", type=float, default=1.0,
        help="Min delay mellem requests i sek.",
    )
    parser.add_argument(
        "--delay-max", type=float, default=3.0,
        help="Max delay mellem requests i sek.",
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    saksnummer = laes_saksnummer_liste(INPUT_FIL)
    if args.max:
        saksnummer = saksnummer[: args.max]

    print("=" * 70)
    print(f"DOWNLOAD {len(saksnummer)} norske afgørelser fra reiselivsforum.no")
    print(f"Target: {OUTPUT_DIR}")
    print(f"User-Agent: {USER_AGENT}")
    print(f"Delay: {args.delay_min}-{args.delay_max} sek mellem requests")
    print("=" * 70)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    succes = 0
    sprunget = 0
    fejlet = 0
    fejl_i_traek = 0

    for i, sn in enumerate(saksnummer, 1):
        target = OUTPUT_DIR / f"{sn}.pdf"

        if target.exists() and not args.force:
            print(f"[{i}/{len(saksnummer)}] {sn} — eksisterer, springer over")
            sprunget += 1
            continue

        print(f"[{i}/{len(saksnummer)}] {sn} ...", end=" ", flush=True)
        ok, fejl = download_pdf(session, sn, OUTPUT_DIR)

        if ok:
            print(f"✓ {target.stat().st_size:,} bytes")
            succes += 1
            fejl_i_traek = 0
        else:
            print(f"✗ {fejl}")
            fejlet += 1
            fejl_i_traek += 1

        # Stop hvis vi rammer mange fejl i træk — siden er måske nede
        if fejl_i_traek >= 5:
            print(
                "\n⚠ 5 fejl i træk — stopper for at undgå at hamre siden. "
                "Kør igen om lidt for at fortsætte."
            )
            break

        # Høflig delay
        time.sleep(random.uniform(args.delay_min, args.delay_max))

    print("\n" + "=" * 70)
    print("RAPPORT")
    print("=" * 70)
    print(f"  Total:    {len(saksnummer)}")
    print(f"  Succes:   {succes}")
    print(f"  Sprunget: {sprunget} (allerede downloaded)")
    print(f"  Fejlet:   {fejlet}")

    if succes:
        print(
            f"\nNæste skridt: kør 'python3 scripts/ingest_norge_pakkereise.py "
            "--execute' for at parse + embed + INSERT i mine_dokumenter."
        )


if __name__ == "__main__":
    main()
