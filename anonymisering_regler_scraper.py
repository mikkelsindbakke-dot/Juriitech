"""
Anonymiseringsregler-scraper.

Henter de officielle regler og vejledninger om anonymisering og
pseudonymisering fra fire autoritative kilder og lægger dem i juriitech
PAX's vidensbank som dokumenttype='anonymisering_regler'. Kilder:

  1. Datatilsynet — Pseudonymisering og anonymisering (katalog over
     foranstaltninger)
  2. Datatilsynet — Myter om GDPR
  3. Jurabibliotek — artikel om anonymisering (2024)
  4. EU Article 29 Working Party — WP216 Opinion 05/2014 on Anonymisation
     Techniques (PDF)

Indholdet hentes ÉN gang og bliver en fast del af modellens "hjerne" via
vidensbanken — brugeren skal ikke gøre noget aktivt for at få det ind.
Scraperen er idempotent: eksisterende chunks re-downloades ikke.

Bruges via app.py's auto-load ved start-up, eller manuelt:
    python3 anonymisering_regler_scraper.py
"""

import io
import re
import time

import requests
from bs4 import BeautifulSoup

from database import gem_sag_i_db, sag_findes
from embeddings import embed_dokument


# ---------- KONFIGURATION ----------

HTTP_HEADERS = {
    "User-Agent": (
        "JuriitechPAX/1.0 (juridisk AI-assistent; "
        "kontakt: mikkelsindbakke@gmail.com)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/pdf",
    "Accept-Language": "da-DK,da;q=0.9,en-US;q=0.7,en;q=0.5",
}
REQUEST_TIMEOUT = 45

# Hver kilde er en dict med url, type (html|pdf), kort-navn (brugt som
# filnavn-præfix) og en menneskevenlig titel.
KILDER = [
    {
        "url": (
            "https://www.datatilsynet.dk/regler-og-vejledning/"
            "behandlingssikkerhed/katalog-over-foranstaltninger/"
            "pseudonymisering-og-anonymisering"
        ),
        "type": "html",
        "kort_navn": "datatilsynet_pseudonymisering_og_anonymisering",
        "titel": (
            "Datatilsynet — Pseudonymisering og anonymisering "
            "(katalog over foranstaltninger)"
        ),
    },
    {
        "url": "https://www.datatilsynet.dk/regler-og-vejledning/myter-om-gdpr",
        "type": "html",
        "kort_navn": "datatilsynet_myter_om_gdpr",
        "titel": "Datatilsynet — Myter om GDPR",
    },
    {
        "url": "https://www.jurabibliotek.dk/view/journals/jur/2024/1/article-p1926.xml",
        "type": "html",
        "kort_navn": "jurabibliotek_anonymisering_2024",
        "titel": "Jurabibliotek — Artikel om anonymisering (2024)",
    },
    {
        "url": (
            "https://ec.europa.eu/justice/article-29/documentation/"
            "opinion-recommendation/files/2014/wp216_en.pdf"
        ),
        "type": "pdf",
        "kort_navn": "article29_wp216_anonymisation_techniques",
        "titel": (
            "EU Article 29 Working Party — WP216 "
            "Opinion 05/2014 on Anonymisation Techniques"
        ),
    },
]

# Maks-længde pr. chunk (tegn). Længere kilder deles op i chunks så de er
# praktiske at embedde og hente via RAG. ~6000 tegn er ca. 1500 tokens og
# fanger en tematisk sammenhængende sektion.
MAX_CHUNK_LEN = 6000
MIN_CHUNK_LEN = 300  # ignorér ultra-korte fragmenter


# ---------- HJÆLPERE ----------

def _log(msg, cb=None):
    print(msg)
    if cb:
        try:
            cb(msg)
        except Exception:
            pass


def _hent_raa(url):
    """Returnerer (bytes, content_type) eller (None, None)."""
    try:
        r = requests.get(url, headers=HTTP_HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.content, r.headers.get("Content-Type", "").lower()
    except Exception as e:
        print(f"   ⚠️ Kunne ikke hente {url}: {e}")
        return None, None


def _udtraek_html_tekst(html_bytes):
    """Renser HTML for navigation/scripts/footers og returnerer ren tekst."""
    if not html_bytes:
        return ""
    try:
        soup = BeautifulSoup(html_bytes, "html.parser")
    except Exception:
        return ""

    # Find hovedindhold
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find(id="content")
        or soup.find(id="main")
        or soup.find(class_=re.compile(r"(content|article|main|body)", re.I))
        or soup.body
    )
    if main is None:
        return ""

    for tag in main.find_all([
        "script", "style", "nav", "header", "footer",
        "aside", "noscript", "form", "iframe",
    ]):
        tag.decompose()

    tekst = main.get_text(separator="\n", strip=True)
    # Kollaps multiple linjeskift
    tekst = re.sub(r"\n\s*\n+", "\n\n", tekst)
    return tekst.strip()


def _udtraek_pdf_tekst(pdf_bytes):
    """Udtrækker tekst fra PDF-bytes. Returnerer ren tekst eller ''."""
    if not pdf_bytes:
        return ""
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        sider = []
        for side in reader.pages:
            try:
                sider.append(side.extract_text() or "")
            except Exception:
                sider.append("")
        tekst = "\n\n".join(sider)
        tekst = re.sub(r"\n\s*\n+", "\n\n", tekst)
        return tekst.strip()
    except Exception as e:
        print(f"   ⚠️ Kunne ikke parse PDF: {e}")
        return ""


def _del_i_chunks(tekst, max_len=MAX_CHUNK_LEN):
    """
    Deler en lang tekst i chunks der brydes på afsnit-grænser når det er
    muligt. Bevarer afsnitsstrukturen og sikrer ingen chunk overstiger
    max_len markant.
    """
    if not tekst:
        return []

    tekst = tekst.strip()
    if len(tekst) <= max_len:
        return [tekst] if len(tekst) >= MIN_CHUNK_LEN else []

    chunks = []
    afsnit = re.split(r"\n\s*\n", tekst)
    aktuel = []
    aktuel_laengde = 0

    for a in afsnit:
        a = a.strip()
        if not a:
            continue
        ny_laengde = aktuel_laengde + len(a) + 2
        if ny_laengde > max_len and aktuel:
            chunks.append("\n\n".join(aktuel).strip())
            aktuel = [a]
            aktuel_laengde = len(a)
        else:
            aktuel.append(a)
            aktuel_laengde = ny_laengde

    if aktuel:
        chunks.append("\n\n".join(aktuel).strip())

    # Hvis et enkelt afsnit stadig er for langt, hård-skær det
    endelig = []
    for c in chunks:
        if len(c) <= max_len * 1.3:
            endelig.append(c)
        else:
            for i in range(0, len(c), max_len):
                stykke = c[i:i + max_len].strip()
                if len(stykke) >= MIN_CHUNK_LEN:
                    endelig.append(stykke)

    return [c for c in endelig if len(c) >= MIN_CHUNK_LEN]


def _gem_chunks_i_db(chunks, kort_navn, titel, kilde_url, log_cb=None):
    """Embedder og gemmer hver chunk. Returnerer stats-dict."""
    stats = {"gemt": 0, "fejlede": 0, "sprunget_over": 0, "fundet": len(chunks)}

    for i, chunk in enumerate(chunks, 1):
        # Prefix chunk med titlen så modellen altid ved hvilken kilde den læser
        fuld_tekst = f"[KILDE: {titel}]\n\n{chunk}"

        filnavn = f"{kort_navn}_del{i:02d}.txt"

        if sag_findes(filnavn):
            stats["sprunget_over"] += 1
            continue

        embedding = embed_dokument(fuld_tekst)

        try:
            gem_sag_i_db(
                filnavn=filnavn,
                tekst=fuld_tekst,
                dokumenttype="anonymisering_regler",
                embedding=embedding,
                kilde_url=kilde_url,
            )
            stats["gemt"] += 1
            _log(
                f"   ✅ {filnavn} gemt ({len(fuld_tekst)} tegn, "
                f"embedded: {'ja' if embedding else 'nej'})",
                log_cb,
            )
        except Exception as e:
            _log(f"   ⚠️ Kunne ikke gemme {filnavn}: {e}", log_cb)
            stats["fejlede"] += 1

    return stats


# ---------- HOVEDFUNKTION ----------

def scrape_og_gem_anonymiseringsregler(progress_callback=None):
    """
    Henter alle fire kilder, udtrækker tekst, chunker og gemmer i db.

    Idempotent — filer der allerede findes springes over. Fejler stille
    ved netværksproblemer så app-start aldrig blokeres.

    Returnerer total-stats.
    """
    total = {"gemt": 0, "fejlede": 0, "sprunget_over": 0, "fundet": 0}

    for kilde in KILDER:
        _log(f"\n🔎 Henter: {kilde['titel']}", progress_callback)
        _log(f"   URL: {kilde['url']}", progress_callback)

        raa, content_type = _hent_raa(kilde["url"])
        if raa is None:
            _log("   ⚠️ Sprunget over (ingen respons)", progress_callback)
            continue

        # Vælg parser ud fra deklareret type (med fallback til content-type)
        er_pdf = kilde["type"] == "pdf" or (
            content_type and "pdf" in content_type
        )

        if er_pdf:
            tekst = _udtraek_pdf_tekst(raa)
        else:
            tekst = _udtraek_html_tekst(raa)

        if not tekst:
            _log(
                "   ⚠️ Ingen tekst udtrukket — sprunget over",
                progress_callback,
            )
            continue

        _log(f"   Udtrak {len(tekst)} tegn", progress_callback)

        chunks = _del_i_chunks(tekst)
        _log(f"   Delt i {len(chunks)} chunks", progress_callback)

        if not chunks:
            continue

        stats = _gem_chunks_i_db(
            chunks,
            kort_navn=kilde["kort_navn"],
            titel=kilde["titel"],
            kilde_url=kilde["url"],
            log_cb=progress_callback,
        )

        for k in ("gemt", "fejlede", "sprunget_over", "fundet"):
            total[k] += stats.get(k, 0)

        # Vær flink ved serverne
        time.sleep(1)

    _log(
        f"\n✅ Færdig. Gemt: {total['gemt']}, "
        f"sprunget over: {total['sprunget_over']}, "
        f"fejlede: {total['fejlede']}",
        progress_callback,
    )
    return total


if __name__ == "__main__":
    scrape_og_gem_anonymiseringsregler()
