"""
Pakkerejselov-scraper.

Henter pakkerejseloven (lov nr. 1666 af 26. december 2017) fra
danskelove.dk og splitter den i paragraffer (§ 1, § 2, ...), embedder
hver paragraf og gemmer dem i databasen som dokumenttype='lovgivning'.

Brug:
    python3 pakkerejselov_scraper.py

Eller fra admin-panelet i juriitech PAX via en knap.

Scraperen er idempotent — eksisterende paragraffer re-downloades ikke
(dedup på filnavn).
"""

import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from database import gem_sag_i_db, sag_findes
from embeddings import embed_dokument


# Vi foretrækker danskelove.dk som er lettere at parse end retsinformation.dk
STANDARD_KILDER = [
    "https://danskelove.dk/pakkerejseloven",
    # Fallback til officiel kilde
    "https://www.retsinformation.dk/eli/lta/2017/1666",
]

HEADERS = {
    "User-Agent": (
        "JuriitechPAX/1.0 (juridisk AI-assistent; "
        "kontakt: mikkelsindbakke@gmail.com)"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "da-DK,da;q=0.9",
}
REQUEST_TIMEOUT = 30


def _hent_side(url):
    """Henter en HTML-side og returnerer BeautifulSoup-objekt + kilde-URL."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        # Forbedret encoding-håndtering
        if r.encoding and r.encoding.lower() in ("iso-8859-1", "latin-1", "ascii"):
            r.encoding = r.apparent_encoding or "utf-8"
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"   ⚠️ Kunne ikke hente {url}: {e}")
        return None


def _udtraek_hovedtekst(soup):
    """Udtrækker lovens hovedtekst, renset for navigation/footer/scripts."""
    if soup is None:
        return ""

    # Prøv forskellige mønstre — fald tilbage til body
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find(id="content")
        or soup.find(id="main")
        or soup.find(class_=re.compile(r"(content|article|main|lov|paragraf)", re.I))
        or soup.body
    )
    if main is None:
        return ""

    # Fjern navigation, footer osv.
    for tag in main.find_all(["script", "style", "nav", "header", "footer", "aside", "noscript"]):
        tag.decompose()

    tekst = main.get_text(separator="\n", strip=True)
    tekst = re.sub(r"\n\s*\n+", "\n\n", tekst)
    return tekst.strip()


def _split_i_paragraffer(fuld_tekst):
    """
    Deler lovens tekst i paragraffer ved at finde '§ X.'-mønstre.
    Returnerer liste af dicts: {paragraf_nr, tekst}.
    """
    if not fuld_tekst:
        return []

    # Match § NN. eller § NNa. i starten af en sætning/linje
    pattern = re.compile(
        r"§\s*(\d+[a-zA-Z]?)\.?\s",
        re.MULTILINE,
    )

    matches = list(pattern.finditer(fuld_tekst))
    if not matches:
        return []

    paragraffer = []
    for i, m in enumerate(matches):
        nr = m.group(1).strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(fuld_tekst)
        tekst = fuld_tekst[start:end].strip()

        # Minimum-længde for at undgå falske positives
        if len(tekst) >= 40:
            paragraffer.append({
                "paragraf_nr": nr,
                "tekst": tekst,
            })

    return paragraffer


def scrape_og_gem_pakkerejseloven(progress_callback=None, kilde_url=None):
    """
    Hovedfunktion. Henter loven, splitter i paragraffer, embedder og gemmer.

    Returnerer dict med statistik.
    """
    def log(msg):
        print(msg)
        if progress_callback:
            try:
                progress_callback(msg)
            except Exception:
                pass

    stats = {"gemt": 0, "fejlede": 0, "sprunget_over": 0, "fundet": 0}

    # Prøv kilder i prioriteret rækkefølge
    kilder = [kilde_url] if kilde_url else STANDARD_KILDER
    soup = None
    anvendt_url = None
    for url in kilder:
        log(f"🔎 Prøver at hente pakkerejseloven fra {url}...")
        soup = _hent_side(url)
        if soup is not None:
            anvendt_url = url
            break
        time.sleep(1)

    if soup is None:
        log("❌ Kunne ikke hente loven fra nogen af kilderne.")
        return stats

    log(f"   Hentede HTML fra {anvendt_url}")

    fuld_tekst = _udtraek_hovedtekst(soup)
    if not fuld_tekst:
        log("❌ Kunne ikke udtrække tekst fra siden.")
        return stats

    log(f"   Udtrak {len(fuld_tekst)} tegn fra siden")

    paragraffer = _split_i_paragraffer(fuld_tekst)
    stats["fundet"] = len(paragraffer)
    log(f"   Identificerede {len(paragraffer)} paragraffer")

    if not paragraffer:
        log(
            "⚠️ Ingen paragraffer fundet — siden har muligvis en anden "
            "struktur end forventet. Tjek at URL'en peger på selve "
            "lovteksten."
        )
        return stats

    for p in paragraffer:
        filnavn = f"pakkerejseloven_§{p['paragraf_nr']}.txt"
        kilde = f"{anvendt_url}#§{p['paragraf_nr']}"

        if sag_findes(filnavn):
            stats["sprunget_over"] += 1
            continue

        embedding = embed_dokument(p["tekst"])

        try:
            gem_sag_i_db(
                filnavn=filnavn,
                tekst=p["tekst"],
                dokumenttype="lovgivning",
                embedding=embedding,
                kilde_url=kilde,
            )
            stats["gemt"] += 1
            log(
                f"   ✅ § {p['paragraf_nr']} gemt ({len(p['tekst'])} tegn, "
                f"embedded: {'ja' if embedding else 'nej'})"
            )
        except Exception as e:
            log(f"   ⚠️ Kunne ikke gemme § {p['paragraf_nr']}: {e}")
            stats["fejlede"] += 1

    log(
        f"\n✅ Færdig. Gemt: {stats['gemt']}, "
        f"sprunget over (allerede i db): {stats['sprunget_over']}, "
        f"fejlede: {stats['fejlede']}"
    )
    return stats


if __name__ == "__main__":
    scrape_og_gem_pakkerejseloven()
