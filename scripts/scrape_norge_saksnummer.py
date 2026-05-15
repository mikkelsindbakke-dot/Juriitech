"""
scrape_norge_saksnummer.py

Henter saksnummer for ALLE Pakkereise-afgørelser fra reiselivsforum.no
ved at åbne siden i en headless browser, applicere filter, og iterere
gennem alle sider.

OUTPUT: data_imports/norge_afgoerelser/saksnummer_pakkereise.txt
        (én saksnummer pr. linje)

Når denne fil er genereret, kan download_norge_pdfs.py downloade
hver PDF via den stabile URL-mønster:
  https://reiselivsforum.no/digiforms/sessionInitializer?processName=vedtak_PDF_Process&case=XXX

POLITE SCRAPING:
- User-Agent: juriitech-pax-bot (mikkelsindbakke@gmail.com)
- 2-4 sek delay pr. side-skift
- Stopper hvis siden returnerer fejl
- Kører headless så det ikke forstyrrer

KØRSEL:
  # Få første side kun (test):
  python3 scripts/scrape_norge_saksnummer.py --max-pages 1

  # Hent alle Pakkereise-sager (kører ~20-30 min):
  python3 scripts/scrape_norge_saksnummer.py --max-pages 200

  # Med visible browser (debug):
  python3 scripts/scrape_norge_saksnummer.py --max-pages 1 --headed
"""

import argparse
import os
import random
import sys
import time
from pathlib import Path

ROD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROD)

from playwright.sync_api import sync_playwright  # noqa: E402

LISTING_URL = (
    "https://reiselivsforum.no/web/dommer_og_avgjoerelser/htmlViewer"
    "?documentName=dommer_og_avgjoerelser"
)

OUTPUT_FIL = (
    Path(ROD) / "data_imports" / "norge_afgoerelser" / "saksnummer_pakkereise.txt"
)


def scrape_saksnummer(max_pages: int, headed: bool = False) -> list[tuple]:
    """
    Returnerer liste af (saksnummer, tjenesteyter, udfall) tuples for
    alle Pakkereise-sager på de første max_pages sider.
    """
    alle_sager = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=not headed,
            args=[
                "--no-sandbox",
            ],
        )
        context = browser.new_context(
            user_agent=(
                "juriitech-pax-bot/1.0 (mikkelsindbakke@gmail.com; "
                "juridisk research)"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        print(f"→ Åbner {LISTING_URL}")
        page.goto(LISTING_URL, wait_until="networkidle", timeout=30_000)
        time.sleep(2)

        # Vis filter og vælg Pakkereise
        print("→ Klikker 'VIS FILTER' og vælger 'Pakkereise' ...")
        try:
            page.click("#vis_filter")
            time.sleep(1.5)
        except Exception as e:
            print(f"  ⚠ Kunne ikke klikke VIS FILTER: {e}")

        # Filter-knappen er en select-element eller checkbox — find Pakkereise
        try:
            # Prøv at klikke på Pakkereise-label/checkbox
            page.get_by_text("Pakkereise", exact=True).first.click()
            time.sleep(0.5)
            # Klik SØK eller tilsvarende submit-knap for at applicere filter
            page.locator("#knapp_search, button:has-text('SØK')").first.click()
            time.sleep(2.5)
        except Exception as e:
            print(f"  ⚠ Kunne ikke applicere Pakkereise-filter: {e}")
            print("  Fortsætter alligevel — vi filtrerer på klient-siden.")

        for side_nr in range(1, max_pages + 1):
            print(f"\n→ Side {side_nr} ...")
            time.sleep(random.uniform(1.5, 3.0))  # høflig forsinkelse

            # Find alle rækker — for hver række: saksnr + nemnd + tjenesteyter + udfald
            rows = page.locator("tr").all()
            sider_pakkereise_før = sum(1 for s in alle_sager if s)

            # Vi parser via JS-evaluering for at få alle felter på én gang
            row_data = page.evaluate("""
                () => {
                  const rows = [];
                  document.querySelectorAll('tr').forEach(tr => {
                    const sn = tr.querySelector('.col_saksnr div');
                    const nm = tr.querySelector('.col_nemnd_for div');
                    const tj = tr.querySelector('.col_tjenesteyter div');
                    const uf = tr.querySelector('.col_utfall_for_klager div');
                    if (sn && nm && /^\\d{4}-\\d+/.test(sn.textContent)) {
                      rows.push({
                        saksnr: sn.textContent.trim(),
                        nemnd: nm.textContent.trim(),
                        tjenesteyter: tj ? tj.textContent.trim() : '',
                        udfall: uf ? uf.textContent.trim() : '',
                      });
                    }
                  });
                  return rows;
                }
            """)

            pakkereise_paa_siden = [r for r in row_data if r["nemnd"] == "Pakkereise"]
            print(
                f"  Total rækker: {len(row_data)}, "
                f"deraf Pakkereise: {len(pakkereise_paa_siden)}"
            )

            for r in pakkereise_paa_siden:
                alle_sager.append(
                    (r["saksnr"], r["tjenesteyter"], r["udfall"])
                )

            # Klik Neste side
            if side_nr < max_pages:
                try:
                    neste = page.locator("button:has-text('Neste side')").first
                    if not neste.is_visible():
                        print("  Ingen 'Neste side'-knap mere — stopper.")
                        break
                    neste.click()
                    time.sleep(random.uniform(2.0, 4.0))
                except Exception as e:
                    print(f"  ⚠ Kunne ikke klikke Neste: {e} — stopper.")
                    break

        browser.close()

    return alle_sager


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--max-pages", type=int, default=10,
        help="Maks antal sider at scrape (50 sager pr. side). Default: 10",
    )
    parser.add_argument(
        "--headed", action="store_true",
        help="Vis browser-vinduet (debug).",
    )
    args = parser.parse_args()

    OUTPUT_FIL.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print(f"SCRAPE saksnummer (op til {args.max_pages} sider á 50 rækker)")
    print(f"Mål: ekstrahér KUN Pakkereise-sager")
    print("=" * 70)

    sager = scrape_saksnummer(args.max_pages, args.headed)

    print(f"\n→ Skriver {len(sager)} Pakkereise-saksnummer til {OUTPUT_FIL}")
    with open(OUTPUT_FIL, "w") as f:
        f.write("# saksnummer | tjenesteyter | udfald\n")
        for sn, tj, uf in sager:
            f.write(f"{sn}\t{tj}\t{uf}\n")

    print("\n" + "=" * 70)
    print(f"✓ FÆRDIG — {len(sager)} Pakkereise-sager fundet")
    print(f"  Output: {OUTPUT_FIL}")
    print("=" * 70)
    print(
        "\nNæste skridt: kør scripts/download_norge_pdfs.py for at hente "
        "PDFs via stabile URL'er."
    )


if __name__ == "__main__":
    main()
