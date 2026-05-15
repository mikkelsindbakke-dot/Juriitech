"""
scrape_lovdata_artikkel.py

Scraper informative artikler fra Lovdata.no (fx /artikkel/pakkereiser/5166)
og gemmer dem som juridisk kontekst for norske tenants. I modsætning til
norsk_pakkereiselov_scraper.py der henter selve lov-paragrafferne, henter
denne KOMMENTARER og artikler der forklarer lovens praktiske anvendelse.

Gemmes med:
  - dokumenttype='lovgivning' (genbruger eksisterende type for at indgå
    i RAG på lige fod med pakkereiseloven)
  - land='NO'
  - is_public=TRUE (synlig for alle norske tenants)
  - filnavn-prefix: 'lovdata_artikkel_<id>'

Idempotent — dedup på filnavn.

KØRSEL:
    python3 scripts/scrape_lovdata_artikkel.py <artikkel-url> [<artikkel-url> ...]

Eksempel:
    python3 scripts/scrape_lovdata_artikkel.py \\
        https://lovdata.no/artikkel/pakkereiser/5166
"""

import re
import sys
from pathlib import Path

ROD = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROD))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROD / ".env")
load_dotenv(ROD / "pax-next" / ".env.local", override=False)

import requests  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402

from database import gem_sag_i_db, sag_findes  # noqa: E402
from embeddings import embed_dokument  # noqa: E402


HEADERS = {
    "User-Agent": (
        "juriitech-pax-bot/1.0 (mikkelsindbakke@gmail.com; "
        "juridisk research, contact for issues)"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "no-NO,no;q=0.9,nb;q=0.8",
}
REQUEST_TIMEOUT = 30


def _artikkel_id(url: str) -> str:
    """Udled artikkel-ID fra URL'en (sidste segment, evt. uden trailing /)."""
    m = re.search(r"/artikkel/[^/]+/(\d+)", url)
    if m:
        return m.group(1)
    # Fallback: brug sidste path-segment
    return url.rstrip("/").split("/")[-1]


def _hent_html(url: str):
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"  ⚠ Kunne ikke hente {url}: {e}")
        return None


def _udtraek_tekst(soup) -> tuple[str, str]:
    """
    Returnerer (titel, brødtekst). Lovdata-artikler har en standard-struktur
    med <h1>artikel-titel</h1> et sted i hovedindholdet. Vi henter alt fra
    h1'en og fremad, men begrænser os til article/main-tag hvis muligt.
    """
    if soup is None:
        return "", ""

    main = soup.find("main") or soup.find("article") or soup.body
    if main is None:
        return "", ""

    # Find første h1 i main der ikke er "Hovedmeny", "Del artikkel" osv.
    titel = ""
    for h1 in main.find_all("h1"):
        t = h1.get_text(strip=True)
        if t and t not in ("Hovedmeny", "Del artikkel", "Brukerveiledning"):
            titel = t
            break

    # Fjern støj — navigation, footer, share-buttons
    for selector in ["nav", "footer", "header", "aside", "script", "style"]:
        for tag in main.find_all(selector):
            tag.decompose()
    # Konkrete støj-elementer Lovdata bruger
    for cls in ["share", "delknapper", "brukerveiledning"]:
        for tag in main.find_all(class_=cls):
            tag.decompose()

    # Hent ren tekst
    brodtekst = main.get_text(separator="\n", strip=True)
    # Slå multiple linjeskift sammen
    brodtekst = re.sub(r"\n{3,}", "\n\n", brodtekst)
    return titel, brodtekst


def scrape_artikkel(url: str) -> bool:
    """Returnerer True hvis ny artikkel gemt, False ved fejl/duplikat."""
    print(f"\n→ Henter {url}")
    soup = _hent_html(url)
    if soup is None:
        return False

    titel, tekst = _udtraek_tekst(soup)
    if len(tekst) < 200:
        print(f"  ⚠ For lidt tekst ({len(tekst)} tegn) — springer over")
        return False

    art_id = _artikkel_id(url)
    filnavn = f"lovdata_artikkel_{art_id}.txt"

    if sag_findes(filnavn):
        print(f"  ✓ {filnavn} findes allerede — springer over")
        return False

    fuld_tekst = f"{titel}\n\n{tekst}" if titel else tekst
    print(f"  Titel:   {titel[:60]}")
    print(f"  Længde:  {len(fuld_tekst)} tegn")

    embedding = embed_dokument(fuld_tekst)

    try:
        gem_sag_i_db(
            filnavn=filnavn,
            tekst=fuld_tekst,
            dokumenttype="lovgivning",
            embedding=embedding,
            kilde_url=url,
            is_public=True,
            tenant_id=None,
            land="NO",
        )
        print(f"  ✅ Gemt som {filnavn} (land=NO, is_public=TRUE)")
        return True
    except Exception as e:
        print(f"  ❌ Kunne ikke gemme: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    urls = sys.argv[1:]
    print(f"=" * 70)
    print(f"SCRAPE Lovdata-artikler — {len(urls)} URL(s)")
    print(f"=" * 70)

    gemt = 0
    for url in urls:
        if scrape_artikkel(url):
            gemt += 1

    print(f"\n→ Gemt {gemt}/{len(urls)} nye artikler")
    sys.exit(0 if gemt > 0 or len(urls) == 0 else 1)


if __name__ == "__main__":
    main()
