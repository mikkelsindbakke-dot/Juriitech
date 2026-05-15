"""
Norsk pakkereiselov-scraper.

Henter "Lov om pakkereiser og reisegaranti mv. (pakkereiseloven)"
(LOV-2018-06-15-32) fra Lovdata.no og splitter den i paragraffer.

Lovdata har en clean HTML-struktur med <div class="paragraf"> pr.
paragraf — meget enklere at parse end den danske scraper.

Hver paragraf gemmes som dokumenttype='lovgivning', is_public=True,
land='NO'. Det betyder:
  - Synlig for ALLE norske tenants (FjordTravel og fremtidige)
  - USYNLIG for danske tenants (land='DK' filtrerer den væk)

Idempotent: kan køres igen uden duplikater (dedup på filnavn).

KØRSEL:
    python3 norsk_pakkereiselov_scraper.py

POLITE SCRAPING:
- User-Agent: juriitech-pax-bot (mikkelsindbakke@gmail.com)
- Én HTTP-request total (loven er én side på Lovdata)
- 1 sek delay før evt. retry
"""

import re
import sys
import time

import requests
from bs4 import BeautifulSoup

from database import gem_sag_i_db, sag_findes
from embeddings import embed_dokument


LOVDATA_URL = "https://lovdata.no/dokument/NL/lov/2018-06-15-32"

HEADERS = {
    "User-Agent": (
        "juriitech-pax-bot/1.0 (mikkelsindbakke@gmail.com; "
        "juridisk research, contact for issues)"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "no-NO,no;q=0.9,nb;q=0.8",
}
REQUEST_TIMEOUT = 30


def _hent_lovdata():
    """Henter lovens HTML fra Lovdata.no. Returnerer BeautifulSoup eller None."""
    try:
        r = requests.get(LOVDATA_URL, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        if r.encoding and r.encoding.lower() in ("iso-8859-1", "latin-1", "ascii"):
            r.encoding = r.apparent_encoding or "utf-8"
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"  ⚠ Kunne ikke hente {LOVDATA_URL}: {e}")
        return None


def _udtraek_paragraffer(soup):
    """
    Returnerer liste af dicts: [{paragraf_nr, overskrift, tekst}, ...].

    Lovdata strukturerer hver paragraf som <div class="paragraf"> med
    headeren først (§ X. Overskrift) og indholdet derefter. Vi splitter
    headeren ud og fjerner trailing "🔗 Del paragraf"-link.
    """
    if soup is None:
        return []

    paragrafs = soup.select("div.paragraf")
    if not paragrafs:
        return []

    resultater = []
    for div in paragrafs:
        raa_tekst = div.get_text(separator=" ", strip=True)
        # Fjern trailing del-link
        raa_tekst = re.sub(r"\s*🔗?\s*Del paragraf\s*$", "", raa_tekst).strip()
        if not raa_tekst:
            continue

        # Match "§ NN. Overskrift Indhold..." — Lovdata har punktum efter nr
        m = re.match(r"§\s*(\d+[a-zA-Z]?)\.\s*([^.]+?)\s+(.+)", raa_tekst, re.DOTALL)
        if m:
            nr = m.group(1).strip()
            overskrift = m.group(2).strip()
            indhold = m.group(3).strip()
        else:
            # Fallback: prøv kun nummer + resten
            m2 = re.match(r"§\s*(\d+[a-zA-Z]?)\.?\s+(.+)", raa_tekst, re.DOTALL)
            if not m2:
                continue
            nr = m2.group(1).strip()
            overskrift = ""
            indhold = m2.group(2).strip()

        # Sammensæt for RAG: header + indhold så embedding fanger paragraf-titel
        fuld_tekst = f"§ {nr}. {overskrift}\n\n{indhold}".strip()

        # Minimum-længde for at undgå tomme/falske matches
        if len(fuld_tekst) < 40:
            continue

        resultater.append({
            "paragraf_nr": nr,
            "overskrift": overskrift,
            "tekst": fuld_tekst,
        })

    return resultater


def scrape_og_gem_norsk_pakkereiselov():
    """Hovedfunktion. Henter, parser, embedder, gemmer."""
    print("=" * 70)
    print("SCRAPE NORSK PAKKEREISELOVEN (LOV-2018-06-15-32)")
    print(f"Kilde: {LOVDATA_URL}")
    print("=" * 70)

    soup = _hent_lovdata()
    if soup is None:
        time.sleep(1)
        soup = _hent_lovdata()  # Én retry
    if soup is None:
        print("❌ Kunne ikke hente loven fra Lovdata.no")
        return {"gemt": 0, "fejlede": 0, "sprunget_over": 0, "fundet": 0}

    print(f"✓ Hentet HTML fra Lovdata.no")

    paragraffer = _udtraek_paragraffer(soup)
    print(f"✓ Identificerede {len(paragraffer)} paragraffer")
    if not paragraffer:
        print("❌ Ingen paragraffer fundet — Lovdata har måske ændret struktur")
        return {"gemt": 0, "fejlede": 0, "sprunget_over": 0, "fundet": 0}

    stats = {"gemt": 0, "fejlede": 0, "sprunget_over": 0, "fundet": len(paragraffer)}

    print()
    for p in paragraffer:
        filnavn = f"pakkereiseloven_no_§{p['paragraf_nr']}.txt"
        kilde = f"{LOVDATA_URL}#§{p['paragraf_nr']}"

        if sag_findes(filnavn):
            stats["sprunget_over"] += 1
            print(f"  § {p['paragraf_nr']:>3s}  — allerede i DB, springer over")
            continue

        embedding = embed_dokument(p["tekst"])

        try:
            gem_sag_i_db(
                filnavn=filnavn,
                tekst=p["tekst"],
                dokumenttype="lovgivning",
                embedding=embedding,
                kilde_url=kilde,
                is_public=True,
                tenant_id=None,
                land="NO",  # KRITISK: ellers ender den som dansk
            )
            stats["gemt"] += 1
            embed_status = "✓" if embedding else "✗ (ingen embedding)"
            print(
                f"  § {p['paragraf_nr']:>3s}  {p['overskrift'][:50]:50s} "
                f"{len(p['tekst']):>5d} tegn  {embed_status}"
            )
        except Exception as e:
            stats["fejlede"] += 1
            print(f"  § {p['paragraf_nr']:>3s}  ❌ fejlede: {e}")

    print()
    print("=" * 70)
    print("RAPPORT")
    print("=" * 70)
    print(f"  Paragraffer fundet:   {stats['fundet']}")
    print(f"  Gemt nye:             {stats['gemt']}")
    print(f"  Sprunget (i DB):      {stats['sprunget_over']}")
    print(f"  Fejlede:              {stats['fejlede']}")
    print()
    print("Norsk pakkereiseloven er nu tilgængelig for norske tenants.")
    return stats


if __name__ == "__main__":
    sys.exit(0 if scrape_og_gem_norsk_pakkereiselov()["fejlede"] == 0 else 1)
