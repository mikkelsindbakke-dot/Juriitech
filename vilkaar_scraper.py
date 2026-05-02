"""
Generaliseret rejsevilkår-scraper.

Tager én kilde-URL fra et hvilket som helst rejseselskab og scraper deres
juridiske indhold (vilkår, persondata, klageforhold, ansvar osv.). Tagger
alt med korrekt tenant_id og is_public=False så indholdet ender i den
rigtige tenants private vidensbank — ALDRIG synligt for andre tenants.

Bruges af admin-siden ('Scrape vilkår nu'-knappen på Tenants-fanen) når
en ny tenant onboardes. Kan også køres direkte fra terminalen:

    python3 vilkaar_scraper.py --tenant-slug apollo \\
        --kilde-url https://www.apollorejser.dk/rejsevilkaar/

Sikkerhed:
  - Holder sig STRENGT inden for kilde-URL'ens base-domæne (ingen
    cross-domain crawling)
  - Følger kun links der matcher juridiske keywords (vilkår, regler,
    persondata, klage, ansvar osv.)
  - Udelukker destinations/rejsepakke-sider via blacklist
  - Idempotent: spring URL'er over der allerede er i databasen
  - Tagger ALTID med tenant_id (eksplicit param, ikke fallback)

Forskel fra tui_scraper.py: Universel — virker for alle selskaber. TUI's
specifikke scraper er beholdt som-er for bagudkompatibilitet, men nye
selskaber bør køre via denne fil.
"""

import re
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from database import gem_sag_i_db, url_findes, hent_tenant_by_slug
from embeddings import embed_dokument


# Keywords der indikerer juridisk/kontraktuelt indhold. Matches
# case-insensitivt mod URL-sti og link-tekst.
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
    # Engelsk fallback (mange selskaber er internationale)
    "terms", "conditions", "privacy",
    "rules", "guidelines",
]

# URL-mønstre vi udelukker selv hvis de skulle ramme et keyword
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
        "JuridiskAssistent/1.0 (intern juridisk analyse for "
        "kontraktpartner; kontakt: mikkelsindbakke@gmail.com)"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "da-DK,da;q=0.9,en;q=0.6",
}
REQUEST_TIMEOUT = 30
DELAY_MELLEM_SIDER = 1.5

DEFAULT_MAX_DYBDE = 2
DEFAULT_MAX_SIDER = 40
MIN_TEKSTLAENGDE = 300


def _udled_base_domain(kilde_url: str) -> str:
    """Trækker base-domænet ud af en URL.
    'https://www.apollorejser.dk/rejsevilkaar/' → 'apollorejser.dk'
    'https://tui.dk/' → 'tui.dk'
    """
    netloc = urlparse(kilde_url).netloc.lower().split(":")[0]
    # Fjern 'www.' præfiks så vi accepterer både apex og www-subdomain
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc


def _er_samme_domæne(url: str, base_domain: str) -> bool:
    """True hvis URL er på base_domain eller ægte subdomæne."""
    try:
        netloc = urlparse(url).netloc.lower().split(":")[0]
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc == base_domain or netloc.endswith("." + base_domain)
    except Exception:
        return False


def _er_juridisk_keyword(url: str, linktekst: str = "") -> bool:
    """True hvis URL eller linktekst matcher mindst ét juridisk keyword."""
    needle = (urlparse(url).path + " " + (linktekst or "")).lower()
    needle_ascii = (
        needle.replace("æ", "ae").replace("ø", "oe").replace("å", "aa")
    )
    return any(kw in needle or kw in needle_ascii for kw in JURIDISKE_KEYWORDS)


def _er_blacklistet(url: str) -> bool:
    """Filtrerer destinations/rejsepakke-sider fra."""
    path = urlparse(url).path.lower()
    return any(m in path or m in url.lower() for m in UDELUK_MOENSTRE)


def _normaliser_url(url: str) -> str:
    """Fjerner fragments og trailing slashes for stabil dedup."""
    try:
        p = urlparse(url)
        url = p._replace(fragment="").geturl()
        if url.endswith("/") and url.count("/") > 3:
            url = url.rstrip("/")
        return url
    except Exception:
        return url


def _hent_html(url: str):
    """Henter HTML, returnerer BeautifulSoup eller None ved fejl."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        ctype = r.headers.get("Content-Type", "").lower()
        if "html" not in ctype:
            return None
        if r.encoding and r.encoding.lower() in ("iso-8859-1", "latin-1", "ascii"):
            r.encoding = r.apparent_encoding or "utf-8"
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"   ⚠️  Kunne ikke hente {url}: {e}")
        return None


def _find_juridiske_links(soup, side_url: str, base_domain: str):
    """Returnerer absolutte URL'er på siden der matcher juridiske keywords
    og er på samme base-domain."""
    fundne = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("mailto:", "javascript:", "#", "tel:")):
            continue
        absolut = _normaliser_url(urljoin(side_url, href))
        if not _er_samme_domæne(absolut, base_domain):
            continue
        if _er_blacklistet(absolut):
            continue
        linktekst = a.get_text(strip=True) or ""
        if _er_juridisk_keyword(absolut, linktekst):
            fundne.add(absolut)
    return fundne


def _udtraek_hovedtekst(soup) -> str:
    """Udtrækker hovedteksten — fjerner navigation, footer, scripts osv."""
    for tag in soup.find_all(
        ["script", "style", "nav", "header", "footer", "aside", "noscript"]
    ):
        tag.decompose()

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

    tekst = main.get_text(separator="\n", strip=True)
    tekst = re.sub(r"\n\s*\n+", "\n\n", tekst)
    return tekst.strip()


def _udled_titel(soup) -> str | None:
    t = soup.find("title")
    if t and t.get_text(strip=True):
        return t.get_text(strip=True)
    h = soup.find("h1")
    if h and h.get_text(strip=True):
        return h.get_text(strip=True)
    return None


def _filnavn_fra_url(url: str, tenant_slug: str, titel: str | None = None) -> str:
    """Pænt filnavn til DB. Prefix med tenant_slug så de er nemme at identificere."""
    path = urlparse(url).path.strip("/") or "rod"
    basis = re.sub(r"[^A-Za-z0-9_\-æøåÆØÅ]", "_", path.replace("/", "_")) or "rod"
    if titel:
        kort = re.sub(r"[^A-Za-z0-9_\-æøåÆØÅ ]", "", titel)[:60].strip()
        return f"{tenant_slug}_{basis}__{kort}.html"
    return f"{tenant_slug}_{basis}.html"


def scrape_vilkaar(
    tenant_id: int,
    tenant_slug: str,
    kilde_url: str,
    max_sider: int = DEFAULT_MAX_SIDER,
    max_dybde: int = DEFAULT_MAX_DYBDE,
    progress_callback=None,
) -> dict:
    """
    Scraper alle juridiske sider fra kilde_url's domæne og gemmer dem som
    dokumenttype='vilkaar' med tenant_id=tenant_id, is_public=False.

    Argumenter:
        tenant_id        — DB-id på den tenant der ejer disse vilkår
        tenant_slug      — slug, bruges som filnavn-prefix
        kilde_url        — URL at starte BFS fra (typisk selskabets vilkår-side)
        max_sider        — øvre grænse for antal sider besøgt (anti-runaway)
        max_dybde        — link-dybde fra startpunkt
        progress_callback — funktion der kaldes med (besked: str) ved hvert
                            trin. Bruges til Streamlit-progress-visning.

    Returnerer dict med statistik:
        {besogte, gemt, allerede_i_db, for_kort_tekst, fejlede}
    """
    def log(msg):
        print(msg)
        if progress_callback:
            try:
                progress_callback(msg)
            except Exception:
                pass

    base_domain = _udled_base_domain(kilde_url)
    log(f"🌍 Scraper {base_domain} for tenant '{tenant_slug}' (id={tenant_id})")
    log(f"   Startpunkt: {kilde_url}")
    log(f"   Max sider: {max_sider}, max dybde: {max_dybde}")

    stats = {
        "besogte": 0,
        "gemt": 0,
        "allerede_i_db": 0,
        "for_kort_tekst": 0,
        "fejlede": 0,
    }

    kø = [(kilde_url, 0)]
    besogte_urls = set()
    kø_set = {kilde_url}

    while kø and stats["besogte"] < max_sider:
        url, dybde = kø.pop(0)
        url = _normaliser_url(url)

        if url in besogte_urls or dybde > max_dybde:
            continue

        besogte_urls.add(url)
        stats["besogte"] += 1
        log(f"[{stats['besogte']}/{max_sider}] dybde={dybde}  {url}")

        soup = _hent_html(url)
        if soup is None:
            stats["fejlede"] += 1
            time.sleep(DELAY_MELLEM_SIDER)
            continue

        # Opdag flere juridiske links til næste dybde
        if dybde < max_dybde:
            for nyt in _find_juridiske_links(soup, url, base_domain):
                if nyt not in besogte_urls and nyt not in kø_set:
                    kø.append((nyt, dybde + 1))
                    kø_set.add(nyt)

        # Gem siden hvis den ser juridisk ud
        titel = _udled_titel(soup)
        if not _er_juridisk_keyword(url, titel or ""):
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
            log(f"   ℹ️  Kun {len(tekst)} tegn — for kort")
            time.sleep(DELAY_MELLEM_SIDER)
            continue

        filnavn = _filnavn_fra_url(url, tenant_slug, titel)
        embedding = embed_dokument(tekst)

        try:
            gem_sag_i_db(
                filnavn=filnavn,
                tekst=tekst,
                dokumenttype="vilkaar",
                embedding=embedding,
                kilde_url=url,
                tenant_id=tenant_id,  # EKSPLICIT — ingen fallback
                is_public=False,       # ALTID privat for tenant
            )
            stats["gemt"] += 1
            log(
                f"   ✅ gemt ({len(tekst)} tegn"
                + (", embedded" if embedding else ", uden embedding")
                + f") — {titel or filnavn}"
            )
        except Exception as e:
            stats["fejlede"] += 1
            log(f"   ⚠️  Kunne ikke gemme: {e}")

        time.sleep(DELAY_MELLEM_SIDER)

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

    p = argparse.ArgumentParser(
        description="Generaliseret rejsevilkår-scraper for enhver tenant"
    )
    p.add_argument("--tenant-slug", required=True,
                   help="Slug på tenanten (fx 'tui', 'apollo')")
    p.add_argument("--kilde-url", required=True,
                   help="URL at starte BFS fra (typisk selskabets vilkår-side)")
    p.add_argument("--max", type=int, default=DEFAULT_MAX_SIDER,
                   help=f"Max antal sider (default {DEFAULT_MAX_SIDER})")
    p.add_argument("--max-dybde", type=int, default=DEFAULT_MAX_DYBDE,
                   help=f"Max link-dybde (default {DEFAULT_MAX_DYBDE})")
    args = p.parse_args()

    tenant = hent_tenant_by_slug(args.tenant_slug)
    if not tenant:
        print(f"❌ Tenant '{args.tenant_slug}' findes ikke i databasen.")
        raise SystemExit(1)

    scrape_vilkaar(
        tenant_id=tenant["id"],
        tenant_slug=tenant["slug"],
        kilde_url=args.kilde_url,
        max_sider=args.max,
        max_dybde=args.max_dybde,
    )
