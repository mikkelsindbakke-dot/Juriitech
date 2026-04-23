"""
TUI.dk scraper — henter kun juridisk relevant indhold fra tui.dk.

Scraperen følger kun links hvis URL eller linktekst indeholder et af de
juridiske keywords (vilkår, regler, betingelser, procedurer, policy,
persondata osv.). Den henter den rå HTML, udtrækker hovedteksten, og
gemmer den i databasen som dokumenttype='vilkaar' med en embedding.

Scraperen tager IKKE destinationer, rejsepakker eller markedsføringsindhold.

Køres enten fra Streamlit-knappen eller direkte fra terminalen:
    python3 tui_scraper.py
"""

import re
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from database import gem_sag_i_db, url_findes
from embeddings import embed_dokument


# Rod-domæne vi holder os til — vi følger aldrig links udenfor dette
BASE_DOMAIN = "tui.dk"

# Startpunkter: forsiden + kendte sider hvor juridisk indhold typisk findes.
# Hvis tui.dk flytter tingene rundt, finder scraperen alligevel de relevante
# sider via keyword-filtrering på alle fundne links.
ENTRY_POINTS = [
    "https://www.tui.dk/",
    "https://www.tui.dk/rejsevilkar/",
    "https://www.tui.dk/rejseinformation/",
    "https://www.tui.dk/kundeservice/",
    "https://www.tui.dk/om-tui/",
]

# Keywords der indikerer juridisk/kontraktuelt indhold. Vi kigger efter
# disse både i URL-stien og i linkets synlige tekst.
# Brug kun lowercase (vi matcher case-insensitive).
JURIDISKE_KEYWORDS = [
    # Kernen — vilkår og regler
    "vilkar", "vilkår", "vilkaar",
    "betingelser", "bestemmelser",
    "regler", "regulativ",
    "retningslinjer", "retningslinje",
    "procedurer", "procedure",
    # Politikker
    "policy", "politik",
    "persondata", "privatliv", "privatlivs",
    "cookies", "cookiepolitik",
    # Klage- og ændringsforhold
    "reklamation", "klage", "klager",
    "aflysning", "annullering",
    "aendring", "ændring",
    "erstatning", "refusion",
    # Ansvar og forbehold
    "ansvar", "ansvarsfraskrivelse", "forbehold",
    "force-majeure", "force_majeure",
    # Rejsespecifikt
    "pas", "visum", "visa",
    "forsikring", "rejseforsikring",
    "sikkerhed", "sikkerhedsinformation",
    "pakkerejse",
    # Engelsk fallback (TUI er international)
    "terms", "conditions", "privacy", "policy",
    "rules", "guidelines",
]

# Vi udelukker visse URL-mønstre der næsten aldrig er juridiske, selv hvis
# de skulle ramme et keyword ved et tilfælde (fx "regler for familierejse"
# i marketingmateriale).
UDELUK_MOENSTRE = [
    "/destinationer/", "/rejsemaal/", "/rejsemal/",
    "/hoteller/", "/hotel/",
    "/fly/", "/flyrejser/",
    "/tilbud/", "/kampagner/",
    "/blog/", "/inspiration/",
    "?sortering=", "?sort=",
    "/søg/", "/search/",
]

HEADERS = {
    "User-Agent": (
        "JuridiskAssistent/1.0 (intern juridisk analyse af "
        "arbejdsgiverens egne vilkår; kontakt: mikkelsindbakke@gmail.com)"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "da-DK,da;q=0.9,en;q=0.6",
}
REQUEST_TIMEOUT = 30
DELAY_MELLEM_SIDER = 1.5

# Grænse for rekursionsdybde fra entry points — beskytter mod at ende i
# hele sitet hvis filteret svigter.
MAX_DYBDE = 2

# Minimum antal tegn vi forventer at finde på en reel juridisk side.
# Kortere sider er typisk navigation/redirects og gemmes ikke.
MIN_TEKSTLAENGDE = 300


def _er_samme_domæne(url):
    """
    Returnerer True KUN hvis URL'en er på tui.dk eller et ægte subdomæne
    (fx www.tui.dk eller presse.tui.dk). Afviser bevidst falske match som
    'fake-tui.dk' der teknisk 'ender på' tui.dk men er et helt andet domæne.
    """
    try:
        netloc = urlparse(url).netloc.lower()
        # Fjern evt. port (fx :443)
        netloc = netloc.split(":")[0]
        return netloc == BASE_DOMAIN or netloc.endswith("." + BASE_DOMAIN)
    except Exception:
        return False


def _er_juridisk_keyword_i_url(url, linktekst=""):
    """
    Returnerer True hvis URL'en ELLER linkets synlige tekst indeholder
    mindst ét af de juridiske keywords.
    """
    needle = (urlparse(url).path + " " + (linktekst or "")).lower()
    # Normalisér danske bogstaver så vi fanger både 'vilkar' og 'vilkår'
    needle_ascii = (
        needle.replace("æ", "ae").replace("ø", "oe").replace("å", "aa")
    )
    for kw in JURIDISKE_KEYWORDS:
        if kw in needle or kw in needle_ascii:
            return True
    return False


def _er_blacklistet(url):
    """Filtrerer destinations/rejsepakke-sider fra, selv hvis de ramte et keyword."""
    path = urlparse(url).path.lower()
    for mønster in UDELUK_MOENSTRE:
        if mønster in path or mønster in url.lower():
            return True
    return False


def _normaliser_url(url):
    """Fjerner fragments (#...) og trailing-slashes så dedup virker."""
    try:
        p = urlparse(url)
        # Drop fragment
        url = p._replace(fragment="").geturl()
        # Drop trailing slash (men ikke på selve rod-URL'en)
        if url.endswith("/") and url.count("/") > 3:
            url = url.rstrip("/")
        return url
    except Exception:
        return url


def _hent_html(url):
    """Henter HTML, returnerer BeautifulSoup eller None.
    Sikrer at encoding håndteres korrekt — requests' default detektion er
    nogle gange forkert og giver mojibake i danske tegn."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        ctype = r.headers.get("Content-Type", "").lower()
        if "html" not in ctype:
            return None
        # Hvis requests har gættet latin-1/iso-8859-1 (default for HTTP hvis
        # intet er sat), skift til den faktiske encoding fra indholdet
        if r.encoding and r.encoding.lower() in ("iso-8859-1", "latin-1", "ascii"):
            r.encoding = r.apparent_encoding or "utf-8"
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"   ⚠️  Kunne ikke hente {url}: {e}")
        return None


def _find_juridiske_links(soup, side_url):
    """Returnerer sæt af absolutte URL'er på siden der matcher juridiske keywords."""
    fundne = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("mailto:", "javascript:", "#", "tel:")):
            continue
        absolut = urljoin(side_url, href)
        absolut = _normaliser_url(absolut)
        if not _er_samme_domæne(absolut):
            continue
        if _er_blacklistet(absolut):
            continue
        linktekst = a.get_text(strip=True) or ""
        if _er_juridisk_keyword_i_url(absolut, linktekst):
            fundne.add(absolut)
    return fundne


def _udtraek_hovedtekst(soup):
    """
    Udtrækker hovedteksten fra en HTML-side. Fjerner navigation, footer,
    scripts osv. og holder kun det reelle indhold.
    """
    # Fjern elementer der aldrig er hovedindhold
    for tag in soup.find_all(["script", "style", "nav", "header", "footer", "aside", "noscript"]):
        tag.decompose()

    # Prøv at finde det mest sandsynlige "main content"-element
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find(id="content")
        or soup.find(id="main")
        or soup.find(class_=re.compile(r"(content|main|article|indhold)", re.I))
        or soup.body
    )
    if main is None:
        return ""

    # Hent tekst med reasonable separators så afsnit ikke klumper sammen
    tekst = main.get_text(separator="\n", strip=True)

    # Fjern dobbelte blanke linjer
    tekst = re.sub(r"\n\s*\n+", "\n\n", tekst)
    return tekst.strip()


def _udled_titel(soup):
    """Hent sidens <title> eller <h1> som titel — bruges som 'filnavn' i DB."""
    t = soup.find("title")
    if t and t.get_text(strip=True):
        return t.get_text(strip=True)
    h = soup.find("h1")
    if h and h.get_text(strip=True):
        return h.get_text(strip=True)
    return None


def _filnavn_fra_url(url, titel=None):
    """Udleder et pænt 'filnavn' til DB'en fra URL'en (+ evt. titel)."""
    path = urlparse(url).path.strip("/") or "rod"
    basis = path.replace("/", "_") or "rod"
    basis = re.sub(r"[^A-Za-z0-9_\-æøåÆØÅ]", "_", basis)
    if titel:
        kort_titel = re.sub(r"[^A-Za-z0-9_\-æøåÆØÅ ]", "", titel)[:60].strip()
        return f"tui_{basis}__{kort_titel}.html"
    return f"tui_{basis}.html"


def scrape_tui_vilkaar(max_sider=40, progress_callback=None):
    """
    Hovedfunktion. Går i gang ved entry points, følger juridisk-matchende
    links i op til MAX_DYBDE niveauer, udtrækker tekst, embedder og gemmer.

    Returnerer dict med statistik.
    """
    def log(msg):
        print(msg)
        if progress_callback:
            try:
                progress_callback(msg)
            except Exception:
                pass

    stats = {
        "besogte": 0,
        "gemt": 0,
        "allerede_i_db": 0,
        "for_kort_tekst": 0,
        "fejlede": 0,
    }

    # BFS fra entry points — (url, dybde)
    kø = [(u, 0) for u in ENTRY_POINTS]
    besogte_urls = set()

    while kø and stats["besogte"] < max_sider:
        url, dybde = kø.pop(0)
        url = _normaliser_url(url)

        if url in besogte_urls:
            continue
        if dybde > MAX_DYBDE:
            continue

        besogte_urls.add(url)
        stats["besogte"] += 1

        log(f"[{stats['besogte']}/{max_sider}] dybde={dybde}  {url}")

        soup = _hent_html(url)
        if soup is None:
            stats["fejlede"] += 1
            time.sleep(DELAY_MELLEM_SIDER)
            continue

        # 1. Opdag flere juridiske links fra denne side (til næste dybde)
        if dybde < MAX_DYBDE:
            nye_links = _find_juridiske_links(soup, url)
            for nyt in nye_links:
                if nyt not in besogte_urls:
                    kø.append((nyt, dybde + 1))

        # 2. Gem siden selv — men kun hvis den ser juridisk ud
        #    (entry points gemmer vi ikke hvis de ikke matcher et keyword)
        titel = _udled_titel(soup)
        er_juridisk_side = _er_juridisk_keyword_i_url(url, titel or "")

        if not er_juridisk_side:
            # Entry point-siden gemmes ikke hvis den ikke ramte et keyword —
            # vi brugte den kun som link-kilde. Det er normalt for forsiden.
            time.sleep(DELAY_MELLEM_SIDER)
            continue

        if url_findes(url):
            stats["allerede_i_db"] += 1
            log("   ℹ️  Allerede i databasen — springer over")
            time.sleep(DELAY_MELLEM_SIDER)
            continue

        tekst = _udtraek_hovedtekst(soup)

        if len(tekst) < MIN_TEKSTLAENGDE:
            stats["for_kort_tekst"] += 1
            log(f"   ℹ️  Kun {len(tekst)} tegn — for kort til at være relevant")
            time.sleep(DELAY_MELLEM_SIDER)
            continue

        # 3. Embed + gem
        filnavn = _filnavn_fra_url(url, titel)
        embedding = embed_dokument(tekst)

        try:
            gem_sag_i_db(
                filnavn=filnavn,
                tekst=tekst,
                dokumenttype="vilkaar",
                embedding=embedding,
                kilde_url=url,
            )
            stats["gemt"] += 1
            log(
                f"   ✅ gemt ({len(tekst)} tegn"
                + (", embedded" if embedding else ", uden embedding")
                + f")  — {titel or filnavn}"
            )
        except Exception as e:
            stats["fejlede"] += 1
            log(f"   ⚠️  Kunne ikke gemme: {e}")

        time.sleep(DELAY_MELLEM_SIDER)

    # Opsummering
    log("")
    log("=" * 50)
    log(
        f"Færdig. Besøgte: {stats['besogte']}, gemt: {stats['gemt']}, "
        f"allerede i db: {stats['allerede_i_db']}, "
        f"for kort: {stats['for_kort_tekst']}, fejlede: {stats['fejlede']}."
    )
    log("=" * 50)
    return stats


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Scraper til juridisk indhold på tui.dk")
    p.add_argument(
        "--max",
        type=int,
        default=40,
        help="Max antal sider der besøges (standard: 40)",
    )
    args = p.parse_args()
    scrape_tui_vilkaar(max_sider=args.max)
