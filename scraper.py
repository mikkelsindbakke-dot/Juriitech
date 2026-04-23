"""
Scraper til pakkerejseankenaevnet.dk/kendelser/

Henter offentligt tilgængelige kendelser (PDF) fra ankenævnets arkiv,
dedupper mod eksisterende sager i databasen, downloader nye, udtrækker
teksten, embedder og gemmer. Respekterer siden med pænt interval mellem
kald og standard User-Agent.

Køres enten fra Streamlit-knappen eller direkte fra terminalen:
    python3 scraper.py
"""

import time
import io
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from database import gem_sag_i_db, url_findes, sag_findes
from embeddings import embed_dokument
from processor import laes_pdf_tekst


BASE_URL = "https://pakkerejseankenaevnet.dk/kendelser/"

# Pæn opførsel: sig hvem vi er, vent lidt mellem kald, og giv op hvis
# serveren svarer langsomt.
HEADERS = {
    "User-Agent": (
        "JuridiskAssistent/1.0 (intern analyse af offentlige kendelser; "
        "kontakt: mikkelsindbakke@gmail.com)"
    )
}
REQUEST_TIMEOUT = 30  # sekunder
DELAY_MELLEM_PDF = 1.5  # sekunder mellem hver PDF-download
DELAY_MELLEM_SIDER = 2.0  # sekunder mellem hver listeside

# Hvis en PDF er under dette antal tegn efter tekstudtræk, antager vi den
# er scannet — vi gemmer den alligevel med et placeholder, så man kan se
# at den findes, men Claude kan senere læse den via vision ved behov.
SCANNET_TAERSKEL = 100


def _hent_side(url):
    """Henter en HTML-side og returnerer BeautifulSoup-objektet, eller None ved fejl."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"   ⚠️  Kunne ikke hente {url}: {e}")
        return None


def _find_pdf_links(soup, side_url):
    """
    Finder alle <a href=...>-links på siden der peger på PDF-filer.
    Returnerer liste af (absolut_url, synlig_titel)-tupler, deduppet på URL.
    """
    fundne = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href:
            continue
        # Hop over mailto/javascript/anchor-links
        if href.startswith(("mailto:", "javascript:", "#", "tel:")):
            continue
        absolut = urljoin(side_url, href)
        path_del = urlparse(absolut).path.lower()
        if path_del.endswith(".pdf"):
            titel = a.get_text(strip=True) or None
            if absolut not in fundne:
                fundne[absolut] = titel
    return list(fundne.items())


def _find_naeste_side(soup, aktuel_url):
    """
    Prøver at finde et 'næste side'-link via almindelige mønstre.
    Returnerer absolut URL eller None hvis der ikke er flere sider.
    """
    kandidater = []

    # 1. Links med rel="next" (standardmønster)
    for a in soup.find_all("a", href=True, rel=True):
        rel = a.get("rel") or []
        if "next" in [r.lower() for r in rel]:
            kandidater.append(a["href"])

    # 2. Links hvis tekst indeholder "næste", ">", "»"
    for a in soup.find_all("a", href=True):
        tekst = (a.get_text(strip=True) or "").lower()
        if tekst in ("næste", "næste »", "næste side", ">", "»", "next"):
            kandidater.append(a["href"])

    # 3. aria-label / title
    for a in soup.find_all("a", href=True):
        etiket = (a.get("aria-label", "") + " " + a.get("title", "")).lower()
        if "næste" in etiket or "next" in etiket:
            kandidater.append(a["href"])

    for href in kandidater:
        absolut = urljoin(aktuel_url, href)
        if absolut != aktuel_url:
            return absolut
    return None


def _hent_pdf_bytes(pdf_url):
    """Downloader en PDF og returnerer bytes, eller None ved fejl."""
    try:
        r = requests.get(pdf_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        # Basic sanity check — PDF'er starter altid med '%PDF'
        if not r.content.startswith(b"%PDF"):
            return None
        return r.content
    except Exception as e:
        print(f"   ⚠️  Kunne ikke downloade {pdf_url}: {e}")
        return None


def _udled_filnavn(pdf_url, titel=None):
    """Udleder et fornuftigt filnavn fra URL'en (eller titlen som fallback)."""
    path = urlparse(pdf_url).path
    basis = path.rsplit("/", 1)[-1] or "ukendt.pdf"
    # Sanitér så det ikke indeholder underlige tegn
    basis = re.sub(r"[^A-Za-z0-9_.\-]", "_", basis)
    return basis


def tael_alle_kendelser_paa_siden(max_sider=20):
    """
    Dry-run: tæller hvor mange PDF-links der findes på tværs af alle listesider
    (op til max_sider for at undgå uendelige loops). Returnerer (antal, liste).
    """
    alle_links = {}
    side_url = BASE_URL
    besoegte = set()

    for _ in range(max_sider):
        if side_url in besoegte:
            break
        besoegte.add(side_url)

        soup = _hent_side(side_url)
        if soup is None:
            break

        for pdf_url, titel in _find_pdf_links(soup, side_url):
            alle_links[pdf_url] = titel

        naeste = _find_naeste_side(soup, side_url)
        if not naeste:
            break
        side_url = naeste
        time.sleep(DELAY_MELLEM_SIDER)

    return len(alle_links), list(alle_links.items())


def scrape_nye_sager(max_sager=50, progress_callback=None, max_sider=20):
    """
    Hovedfunktion. Gennemgår listesiderne, identificerer nye PDF'er (ikke
    allerede i databasen baseret på kilde_url eller filnavn), downloader
    op til max_sager, udtrækker tekst, embedder, og gemmer.

    progress_callback(msg) kaldes løbende så UI'en kan opdatere.
    Returnerer en dict med statistik: {"fundet_paa_siden", "nye", "gemt",
    "fejlede", "scannede", "sprunget_over"}.
    """

    def log(msg):
        print(msg)
        if progress_callback:
            try:
                progress_callback(msg)
            except Exception:
                pass

    stats = {
        "fundet_paa_siden": 0,
        "allerede_i_db": 0,
        "forsoegt_gemt": 0,
        "gemt": 0,
        "fejlede": 0,
        "scannede": 0,
    }

    # 1. Find alle PDF-links (inkl. paginering)
    log("🔎 Henter oversigt fra pakkerejseankenaevnet.dk...")
    antal_total, alle_links = tael_alle_kendelser_paa_siden(max_sider=max_sider)
    stats["fundet_paa_siden"] = antal_total
    log(f"   Fandt {antal_total} PDF-links i alt på arkivet.")

    if antal_total == 0:
        log("⚠️  Ingen PDF-links fundet — sidestrukturen er muligvis ændret.")
        return stats

    # 2. Filtrér dem der allerede er i databasen
    nye = []
    for pdf_url, titel in alle_links:
        filnavn = _udled_filnavn(pdf_url, titel)
        if url_findes(pdf_url) or sag_findes(filnavn):
            stats["allerede_i_db"] += 1
            continue
        nye.append((pdf_url, titel, filnavn))

    log(
        f"   {stats['allerede_i_db']} var allerede i databasen. "
        f"{len(nye)} er nye."
    )

    if not nye:
        log("✅ Intet nyt at hente — databasen er up-to-date.")
        return stats

    # 3. Loft: processer kun de første max_sager
    if max_sager and len(nye) > max_sager:
        log(
            f"   Der er {len(nye)} nye sager i alt — henter de første "
            f"{max_sager} nu (resten ved næste kørsel)."
        )
        nye = nye[:max_sager]
    else:
        log(f"   Henter alle {len(nye)} nye sager.")

    # 4. Download + udtræk tekst + embed + gem
    for i, (pdf_url, titel, filnavn) in enumerate(nye, 1):
        log(f"[{i}/{len(nye)}] {filnavn}")
        stats["forsoegt_gemt"] += 1

        # 4a. Download
        pdf_bytes = _hent_pdf_bytes(pdf_url)
        if pdf_bytes is None:
            stats["fejlede"] += 1
            time.sleep(DELAY_MELLEM_PDF)
            continue

        # 4b. Udtræk tekst
        try:
            tekst = laes_pdf_tekst(io.BytesIO(pdf_bytes))
        except Exception as e:
            log(f"   ⚠️  Tekstudtræk fejlede: {e}")
            tekst = ""

        if len(tekst.strip()) < SCANNET_TAERSKEL:
            # Scannet PDF — vi gemmer et placeholder så sagen kan findes igen,
            # men tekstudtræk kræver Claudes vision (sker ved spørgsmål).
            log("   ℹ️  PDF'en er scannet — gemmer uden tekstudtræk")
            stats["scannede"] += 1
            tekst = (
                f"[Scannet afgørelse fra {pdf_url} — tekst ikke udtrukket lokalt. "
                f"Analyseres via vision ved forespørgsel.]"
            )
            embedding = None  # ingen meningsfuld embedding uden rigtig tekst
        else:
            # 4c. Generer embedding
            embedding = embed_dokument(tekst)

        # 4d. Gem i databasen
        try:
            gem_sag_i_db(
                filnavn=filnavn,
                tekst=tekst,
                dokumenttype="afgoerelse",
                embedding=embedding,
                kilde_url=pdf_url,
            )
            stats["gemt"] += 1
            log(
                f"   ✅ gemt"
                + (f" ({len(tekst)} tegn, embedded)" if embedding else " (uden embedding)")
            )
        except Exception as e:
            log(f"   ⚠️  Kunne ikke gemme i database: {e}")
            stats["fejlede"] += 1

        time.sleep(DELAY_MELLEM_PDF)

    # 5. Opsummering
    log("")
    log("=" * 50)
    log(f"Færdig. Gemt: {stats['gemt']}, fejlede: {stats['fejlede']}, "
        f"scannede: {stats['scannede']}.")
    resterende = antal_total - stats["allerede_i_db"] - stats["gemt"]
    if resterende > 0:
        log(f"Der er stadig {resterende} nye sager på siden. Kør igen for at hente flere.")
    log("=" * 50)

    return stats


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Scraper til pakkerejseankenaevnet.dk")
    p.add_argument(
        "--max",
        type=int,
        default=50,
        help="Max antal sager der hentes pr. kørsel (standard: 50)",
    )
    p.add_argument(
        "--tael-kun",
        action="store_true",
        help="Kun tæl hvor mange der findes — download ikke noget",
    )
    args = p.parse_args()

    if args.tael_kun:
        antal, _ = tael_alle_kendelser_paa_siden()
        print(f"Der findes {antal} PDF-kendelser på siden.")
    else:
        scrape_nye_sager(max_sager=args.max)
