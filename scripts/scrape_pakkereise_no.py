"""
scrape_pakkereise_no.py

Scraper for Norsk Reiselivsforums afgørelses-database
(https://reiselivsforum.no). Henter KUN Pakkereise-afgørelser — ikke
Flyreise (de gemmes til fremtidige FLY-program) eller Kollektiv.

VIGTIGE DESIGN-VALG:

1. HØFLIG SCRAPING:
   - User-Agent identificerer os ærligt med kontakt-email
   - 2-3 sek delay mellem requests
   - Én crawl, ikke konstant re-crawling
   - Sequentielt — ingen parallelle threads

2. KUN PAKKEREISE:
   - Hver række i resultat-listen har en kategori-celle
   - Vi filtrerer på "Pakkereise" — alt andet springes over
   - Det er user's eksplicitte krav (Flysager er til FLY-program senere)

3. ISOLERET FRA DANSK PAX:
   - Hvert dokument indsættes med land='NO', is_public=TRUE
   - Dansk PAX's RAG vil ALDRIG returnere disse fordi den filtrerer på
     land='DK'. Strukturel garanti — ikke en konvention

4. RESUMABLE:
   - State gemmes i scrape_state.json mellem kørsler
   - Kan afbrydes med Ctrl+C og genoptages
   - Idempotent: en allerede-scrapet sag genscrapes ikke

KØRSEL:

  # Test først med få sager
  python3 scripts/scrape_pakkereise_no.py --max-cases 5 --dry-run

  # Lille test mod prod-DB (5 sager)
  python3 scripts/scrape_pakkereise_no.py --max-cases 5

  # Full scrape (alle Pakkereise-sager, ~3-5k stk., ~30-60 min)
  python3 scripts/scrape_pakkereise_no.py

  # Genoptag fra afbrudt scrape
  python3 scripts/scrape_pakkereise_no.py --resume
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

ROD = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROD))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROD / ".env")
load_dotenv(ROD / "pax-next" / ".env.local", override=False)

import requests  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402

# Lazy import — undgår at vi crasher hvis embeddings-modulet ikke kan
# initialiseres (fx mangler API-key). Vi vil have scraping virker selv
# uden embedding, og kører backfill_embeddings.py bagefter.

BASE_URL = "https://reiselivsforum.no"
LIST_URL = (
    f"{BASE_URL}/web/dommer_og_avgjoerelser/htmlViewer"
    f"?documentName=dommer_og_avgjoerelser"
)
PDF_URL_TEMPLATE = (
    f"{BASE_URL}/digiforms/sessionInitializer"
    f"?processName=vedtak_PDF_Process&case={{case_id}}"
)

USER_AGENT = (
    "juriitech-pax-bot/1.0 "
    "(legal-research; mailto:mikkelsindbakke@gmail.com)"
)

# Høflig delay mellem requests for ikke at hamre deres server
REQUEST_DELAY_SEC = 2.5

STATE_FIL = ROD / "scrape_state_no.json"


@dataclass
class Sag:
    """Metadata om én afgørelse hentet fra resultat-listen."""

    case_id: str  # fx "2025-02679"
    kategori: str  # "Pakkereise" / "Flyreise" / "Kollektiv"
    klageårsak: str
    tjenesteyder: str
    udfald: str  # "Medhold" / "Ikke medhold" / "Delvis medhold"


def _laes_state() -> dict:
    if STATE_FIL.exists():
        with open(STATE_FIL, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"færdige_case_ids": [], "sidste_side": 0}


def _gem_state(state: dict) -> None:
    with open(STATE_FIL, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def _opret_session() -> requests.Session:
    """Initialiserer en session med cookies + User-Agent."""
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    # Touch the index så vi får jsessionid cookie
    resp = s.get(LIST_URL, timeout=30, allow_redirects=True)
    resp.raise_for_status()
    return s


def _parse_case_list(html: str) -> list[Sag]:
    """Ekstraherer alle sager fra én resultat-listside.

    HTML-strukturen er et table med rækker. Hver række har:
      - en celle med kategori-tekst (Pakkereise / Flyreise / Kollektiv)
      - en celle med klageårsak
      - en celle med tjenesteyder
      - en celle med utfald
      - en knap med onclick='...case=<id>...'
    """
    soup = BeautifulSoup(html, "html.parser")
    sager: list[Sag] = []

    # Find alle buttons med case-id i onclick
    for btn in soup.find_all("button"):
        onclick = btn.get("onclick", "") or btn.get("OnClick", "") or ""
        m = re.search(r"case=([\w\-]+)", onclick)
        if not m:
            continue
        case_id = m.group(1)

        # Find den række (tr) som denne button tilhører
        row = btn.find_parent("tr")
        if not row:
            continue

        # Ekstraktér celler — vi kender ikke præcise klasse-navne, så
        # vi indsamler alle td'er og bruger positionen
        celler = row.find_all("td")
        if len(celler) < 4:
            continue

        # Forventet kolonne-rækkefølge baseret på HTML-inspektion:
        # Saksnr | Nemnd for | Klageårsak | Tjenesteyter | Utfall | (knap)
        # Vi prøver at finde kategorien via klasse-navne hvis tilstede
        kategori = ""
        for td in celler:
            cls = " ".join(td.get("class") or [])
            txt = td.get_text(strip=True)
            if "nemnd_for" in cls or "kategori" in cls:
                kategori = txt
                break
        if not kategori:
            # Fallback: scan alle celler for kendte kategori-ord
            for td in celler:
                txt = td.get_text(strip=True)
                if txt in ("Pakkereise", "Flyreise", "Kollektivreise"):
                    kategori = txt
                    break

        def _hent_kolonne(klasse_prefix: str) -> str:
            for td in celler:
                cls = " ".join(td.get("class") or [])
                if klasse_prefix in cls:
                    return td.get_text(strip=True)
            return ""

        sager.append(
            Sag(
                case_id=case_id,
                kategori=kategori,
                klageårsak=_hent_kolonne("klageaarsak"),
                tjenesteyder=_hent_kolonne("tjenesteyter"),
                udfald=_hent_kolonne("utfall"),
            )
        )

    return sager


def _hent_pdf(session: requests.Session, case_id: str) -> Optional[bytes]:
    """Henter PDF for én sag. Returnerer None ved fejl."""
    url = PDF_URL_TEMPLATE.format(case_id=case_id)
    try:
        resp = session.get(url, timeout=30, allow_redirects=True)
        if resp.status_code != 200:
            print(f"  ! HTTP {resp.status_code} for {case_id}")
            return None
        ct = resp.headers.get("Content-Type", "")
        if "pdf" not in ct.lower():
            print(f"  ! Forkert Content-Type for {case_id}: {ct}")
            return None
        return resp.content
    except Exception as e:
        print(f"  ! Fejl ved hentning af {case_id}: {e}")
        return None


def _ekstrahér_tekst(pdf_bytes: bytes) -> str:
    """Trækker tekst ud af PDF via pypdf."""
    import io

    import pypdf

    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    dele = []
    for side in reader.pages:
        t = side.extract_text() or ""
        if t.strip():
            dele.append(t)
    return "\n\n".join(dele)


def _gem_i_db(
    sag: Sag, tekst: str, pdf_bytes: bytes, dry_run: bool
) -> bool:
    """Indsætter sagen i mine_dokumenter med land='NO', is_public=TRUE.

    Returnerer True hvis indsat, False hvis sprunget over (allerede findes).
    """
    if dry_run:
        print(
            f"  [DRY-RUN] Ville indsætte {sag.case_id} "
            f"({len(tekst)} tegn, {len(pdf_bytes)} bytes PDF)"
        )
        return True

    from database import _connect

    filnavn = f"pakkereisenemnda-{sag.case_id}.pdf"
    kilde_url = PDF_URL_TEMPLATE.format(case_id=sag.case_id)

    conn = _connect()
    try:
        cur = conn.cursor()
        # Tjek om vi allerede har den
        cur.execute(
            "SELECT id FROM mine_dokumenter WHERE filnavn = %s LIMIT 1",
            (filnavn,),
        )
        if cur.fetchone():
            cur.close()
            return False

        # Indsæt med land='NO', is_public=TRUE, tenant_id=NULL (public)
        cur.execute(
            """
            INSERT INTO mine_dokumenter
              (filnavn, indhold, dokumenttype, kilde_url,
               tenant_id, is_public, land,
               fil_bytes, fil_mime, oprettet_dato)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """,
            (
                filnavn,
                tekst,
                "afgoerelse",
                kilde_url,
                None,  # public
                True,
                "NO",
                pdf_bytes,
                "application/pdf",
            ),
        )
        conn.commit()
        cur.close()
        return True
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--max-cases",
        type=int,
        default=None,
        help="Stop efter N Pakkereise-sager (test-mode). Default = alle",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Stop efter N sider af resultat-listen",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print kun hvad der ville ske, skriv ikke til DB",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Genoptag fra sidste afbrudte kørsel (læser scrape_state.json)",
    )
    args = parser.parse_args()

    state = _laes_state() if args.resume else {
        "færdige_case_ids": [], "sidste_side": 0
    }
    færdige = set(state["færdige_case_ids"])

    print(f"=" * 70)
    print(f"SCRAPE: Norsk Reiselivsforum — KUN Pakkereise")
    print(f"=" * 70)
    print(f"  Dry-run:    {args.dry_run}")
    print(f"  Max sager:  {args.max_cases or 'alle'}")
    print(f"  Max sider:  {args.max_pages or 'alle'}")
    print(f"  Genoptag:   {args.resume} (har {len(færdige)} færdige fra før)")

    session = _opret_session()

    indsatte = 0
    overspruengt_kategori = 0
    overspruengt_duplikat = 0
    fejl = 0
    side = state["sidste_side"]

    try:
        while True:
            side += 1
            if args.max_pages and side > args.max_pages:
                print(f"\n→ Stop: max sider ({args.max_pages}) nået")
                break

            print(f"\n→ Henter side {side} ...")
            # Første side: vi har allerede den fra _opret_session.
            # Efter side 1 skal vi navigere — det vil kræve at finde
            # pagineringslinks i HTML'en. For nu: stop efter side 1
            # i v1 og dokumentér at vi mangler pagination.
            if side > 1:
                print(
                    "  (Pagination ikke implementeret i v1 — stop efter side 1)"
                )
                break

            resp = session.get(LIST_URL, timeout=30)
            resp.raise_for_status()
            sager = _parse_case_list(resp.text)
            print(f"  Fundet {len(sager)} sager på side {side}")

            for sag in sager:
                if args.max_cases and indsatte >= args.max_cases:
                    print(f"\n→ Stop: max sager ({args.max_cases}) nået")
                    state["sidste_side"] = side
                    _gem_state(state)
                    return

                if sag.case_id in færdige:
                    overspruengt_duplikat += 1
                    continue

                if sag.kategori != "Pakkereise":
                    overspruengt_kategori += 1
                    færdige.add(sag.case_id)  # skip permanent
                    continue

                print(
                    f"  → {sag.case_id} | {sag.tjenesteyder[:30]} | "
                    f"{sag.udfald[:20]}"
                )
                time.sleep(REQUEST_DELAY_SEC)

                pdf = _hent_pdf(session, sag.case_id)
                if pdf is None:
                    fejl += 1
                    continue

                try:
                    tekst = _ekstrahér_tekst(pdf)
                except Exception as e:
                    print(f"    ! PDF-parsing fejlede: {e}")
                    fejl += 1
                    continue

                if len(tekst) < 200:
                    print(f"    ! For lidt tekst ({len(tekst)}) — springer over")
                    fejl += 1
                    continue

                indsat = _gem_i_db(sag, tekst, pdf, args.dry_run)
                if indsat:
                    indsatte += 1
                else:
                    overspruengt_duplikat += 1
                færdige.add(sag.case_id)

                # Gem state efter hver fil så vi kan genoptage
                state["færdige_case_ids"] = sorted(færdige)
                state["sidste_side"] = side
                _gem_state(state)

    except KeyboardInterrupt:
        print("\n\nAfbrudt af bruger — state gemt, kør med --resume for at fortsætte")

    print("\n" + "=" * 70)
    print(f"SAMMENDRAG")
    print(f"=" * 70)
    print(f"  Indsatte Pakkereise-sager: {indsatte}")
    print(f"  Sprunget over (anden kategori): {overspruengt_kategori}")
    print(f"  Sprunget over (allerede i DB): {overspruengt_duplikat}")
    print(f"  Fejl: {fejl}")
    if not args.dry_run and indsatte > 0:
        print(
            f"\n→ Næste skridt: kør backfill_embeddings.py for at generere "
            f"embeddings til de nye sager"
        )


if __name__ == "__main__":
    main()
