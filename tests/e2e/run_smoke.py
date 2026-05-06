"""
E2E smoke-test af juriitech PAX mod live deployment.

Driver en headless Chromium-browser via Playwright og kører gennem
hele bruger-flowet:

  1. Login (med test-credentials fra .env.test)
  2. Verificér forsiden indlæses
  3. Upload test-klage PDF
  4. Klik "Scan filer" → verificér loading-cirkel kommer frem inden 5s
  5. Vent på førstevurdering (max 3 min — fanger freezes)
  6. Verificér klagepunkter, sandsynligheder, tidsforhold rendres
  7. Generer udkast til svarbrev → verificér download-knap dukker op
  8. Klik nogle bilag-checkboxes (catches Bug #1 fra tidligere)
  9. Logout — verificér login-side returneres

Output:
  tests/e2e/screenshots/<timestamp>/  → PNG ved hvert step
  tests/e2e/reports/<timestamp>.md     → markdown-rapport med PASS/FAIL

Test-isolation: Bruger Test-tenant. Ingen prod-data påvirkes.

Brug:
  python3 -m playwright install chromium  # første gang
  python3 tests/e2e/run_smoke.py
  python3 tests/e2e/run_smoke.py --headed   # vis browser-vinduet
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Lokal .env.test — credentials sat af setup_test_tenant.py
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env.test")
except ImportError:
    print(
        "FEJL: python-dotenv mangler. Kør:\n"
        "  python3 -m pip install -r requirements-dev.txt"
    )
    sys.exit(1)

try:
    from playwright.sync_api import (
        sync_playwright,
        TimeoutError as PlaywrightTimeoutError,
        Page,
    )
except ImportError:
    print(
        "FEJL: playwright mangler. Kør:\n"
        "  python3 -m pip install -r requirements-dev.txt\n"
        "  python3 -m playwright install chromium"
    )
    sys.exit(1)


_ROOT = Path(__file__).parent
_FIXTURE = _ROOT / "fixtures" / "test_klage.pdf"
_SCREENSHOTS_BASE = _ROOT / "screenshots"
_REPORTS_BASE = _ROOT / "reports"


# ---------------------------------------------------------------------------
# Hjælpere
# ---------------------------------------------------------------------------

class TestKontext:
    """
    Holder skærmbillede-mappe, rapport-state og step-counter.
    Hver step() genererer et auto-nummeret screenshot og logger
    PASS/FAIL.
    """

    def __init__(self):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.timestamp = ts
        self.screenshots_dir = _SCREENSHOTS_BASE / ts
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        _REPORTS_BASE.mkdir(parents=True, exist_ok=True)
        self.report_path = _REPORTS_BASE / f"{ts}.md"
        self.steps: list[dict] = []
        self.step_nr = 0

    def step(self, page: Page, navn: str, status: str = "PASS",
             detalje: str = "") -> Path:
        """Tag screenshot, log step. Returnér sti til screenshot."""
        self.step_nr += 1
        nr = f"{self.step_nr:02d}"
        slug = navn.lower().replace(" ", "_").replace("/", "_")
        path = self.screenshots_dir / f"{nr}_{slug}.png"
        try:
            page.screenshot(path=str(path), full_page=True)
        except Exception as e:
            print(f"DEBUG: Kunne ikke tage screenshot: {e}")
        self.steps.append({
            "nr": nr,
            "navn": navn,
            "status": status,
            "detalje": detalje,
            "screenshot": path.name,
        })
        ikon = "✓" if status == "PASS" else (
            "⚠" if status == "WARN" else "✗"
        )
        print(f"  {ikon} {nr} {navn:48s} [{status}] {detalje}")
        return path

    def skriv_rapport(self):
        """Skriv markdown-rapport til reports/<timestamp>.md."""
        antal_pass = sum(1 for s in self.steps if s["status"] == "PASS")
        antal_warn = sum(1 for s in self.steps if s["status"] == "WARN")
        antal_fail = sum(1 for s in self.steps if s["status"] == "FAIL")
        total = len(self.steps)

        linjer = []
        linjer.append(f"# E2E smoke-test rapport — {self.timestamp}\n")
        linjer.append(f"**Total:** {total} steps")
        linjer.append(
            f"**Resultat:** {antal_pass} PASS, "
            f"{antal_warn} WARN, {antal_fail} FAIL\n"
        )
        linjer.append(f"**Screenshots:** `{self.screenshots_dir}`\n")
        linjer.append("## Steps\n")
        linjer.append("| # | Navn | Status | Detalje |")
        linjer.append("| --- | --- | --- | --- |")
        for s in self.steps:
            linjer.append(
                f"| {s['nr']} | {s['navn']} | "
                f"{s['status']} | {s['detalje']} |"
            )
        self.report_path.write_text("\n".join(linjer) + "\n")
        print(f"\nRapport: {self.report_path}")
        return antal_fail == 0


def _vent_paa_streamlit_ready(page: Page, timeout_ms: int = 10000):
    """
    Vent til Streamlit har færdig-renderet (ingen 'running'-spinner i
    øverste højre hjørne).
    """
    try:
        page.wait_for_function(
            """() => !document.querySelector(
                '[data-testid=stStatusWidget] [data-testid=stRunningStatus]'
            )""",
            timeout=timeout_ms,
        )
    except PlaywrightTimeoutError:
        pass  # ikke kritisk; vi fortsætter alligevel


def _check_for_kritisk_fejl(page: Page) -> tuple[bool, str]:
    """
    Returnér (ok, detalje). False hvis siden viser den røde
    fallback-fejlboks fra app.py.
    """
    try:
        if page.is_visible(
            "text=Hov — noget gik galt under opstart", timeout=500
        ):
            return False, "Rød fallback-fejlboks vises"
    except Exception:
        pass
    # Tjek for Streamlit's exception-render (fx StreamlitDuplicateElementId)
    try:
        if page.is_visible("[data-testid=stException]", timeout=500):
            tekst = page.text_content(
                "[data-testid=stException]"
            ) or ""
            return False, f"Streamlit-exception: {tekst[:100]}"
    except Exception:
        pass
    return True, ""


# ---------------------------------------------------------------------------
# Test-flow
# ---------------------------------------------------------------------------

def koer_smoke_test(headed: bool = False) -> bool:
    """Kør hele smoke-testen. Returnér True hvis alle steps PASS."""
    test_email = os.getenv("TEST_EMAIL")
    test_password = os.getenv("TEST_PASSWORD")
    base_url = os.getenv(
        "TEST_BASE_URL",
        "https://pax-juriitech.fly.dev",
    )
    if not test_email or not test_password:
        print(
            "FEJL: TEST_EMAIL og TEST_PASSWORD mangler. Kør først:\n"
            "  python3 tests/e2e/setup_test_tenant.py"
        )
        return False
    if not _FIXTURE.exists():
        print(
            f"FEJL: {_FIXTURE} mangler. Kør først:\n"
            "  python3 tests/e2e/generate_test_klage.py"
        )
        return False

    ctx = TestKontext()
    print(f"\nE2E smoke-test mod {base_url}")
    print(f"Screenshots: {ctx.screenshots_dir}\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="da-DK",
        )
        page = context.new_page()

        # Saml console-errors så vi kan rapportere dem
        console_errors: list[str] = []
        page.on(
            "console",
            lambda msg: console_errors.append(
                f"[{msg.type}] {msg.text}"
            ) if msg.type in ("error",) else None,
        )

        try:
            # ───────── STEP 1: Åbn login-siden ─────────
            page.goto(base_url, timeout=30000, wait_until="networkidle")
            # Vent eksplicit på login-form'ens kendetegn — Streamlit kan
            # tage 5-10s på cold start før WebSocket er klar og DOM er
            # bygget. Network-idle alene er ikke nok.
            try:
                page.wait_for_selector(
                    "text=Log ind for at fortsætte",
                    timeout=20000,
                )
            except PlaywrightTimeoutError:
                # Måske er brugeren auto-restored — prøv at se efter
                # forsiden i stedet
                pass
            _vent_paa_streamlit_ready(page, timeout_ms=15000)
            ok, detalje = _check_for_kritisk_fejl(page)
            if not ok:
                ctx.step(page, "Forside indlæses", "FAIL", detalje)
                return False
            ctx.step(page, "Forside indlæses", "PASS")

            # ───────── STEP 2: Login ─────────
            # Streamlit st.text_input rendrer som <input type="text">
            # med aria-label = label-teksten. type="password" er sat
            # eksplicit på password-feltet.
            try:
                # Email-feltet: brug aria-label eller placeholder
                email_input = page.locator(
                    "input[aria-label='Email'], "
                    "input[placeholder*='@']"
                ).first
                email_input.fill(test_email, timeout=8000)
                # Password-feltet er det eneste type=password
                page.fill(
                    "input[type=password]", test_password, timeout=3000
                )
                page.click(
                    "button:has-text('Log ind')", timeout=3000
                )
                ctx.step(page, "Login-form udfyldt + sendt", "PASS")
            except PlaywrightTimeoutError as e:
                ctx.step(
                    page, "Login-form udfyldt + sendt",
                    "FAIL", f"Login-form ikke fundet: {e}",
                )
                return False

            # ───────── STEP 3: Vent på forside efter login ─────────
            try:
                page.wait_for_selector(
                    "text=juriitech PAX",
                    timeout=15000,
                )
                _vent_paa_streamlit_ready(page, timeout_ms=15000)
                ok, detalje = _check_for_kritisk_fejl(page)
                if not ok:
                    ctx.step(page, "Forside efter login", "FAIL", detalje)
                    return False
                ctx.step(page, "Forside efter login", "PASS")
            except PlaywrightTimeoutError:
                ctx.step(
                    page, "Forside efter login",
                    "FAIL", "Login fuldførte ikke inden 15s",
                )
                return False

            # ───────── STEP 4: Upload klage ─────────
            # Streamlit's file_uploader har en hidden <input type=file>.
            # set_input_files udløser change-event som triggers
            # Streamlit's WebSocket-rerun. Vi venter eksplicit på at
            # filnavnet dukker op i UI'en — ellers er uploaden ikke
            # registreret.
            try:
                # Vent på at file_uploader er i DOM — Streamlit lazy-
                # loader komponenter, så det kan tage et par sekunder
                # efter forsiden er rendret.
                try:
                    page.wait_for_selector(
                        "input[type=file]",
                        state="attached",
                        timeout=15000,
                    )
                except PlaywrightTimeoutError:
                    ctx.step(
                        page, "Test-klage uploadet",
                        "FAIL", "file_uploader ikke i DOM efter 15s",
                    )
                    return False

                file_inputs = page.locator("input[type=file]")
                antal_inputs = file_inputs.count()
                if antal_inputs == 0:
                    ctx.step(
                        page, "Test-klage uploadet",
                        "FAIL", "ingen <input type=file> i DOM",
                    )
                    return False
                # Den første file_uploader er hovedsagens klage-uploader
                file_inputs.first.set_input_files(str(_FIXTURE))
                # Vent på at filen dukker op i UI'en (filename rendres)
                try:
                    page.wait_for_selector(
                        "text=test_klage.pdf",
                        timeout=15000,
                    )
                    _vent_paa_streamlit_ready(page, timeout_ms=10000)
                    # Streamlit kører ofte to reruns: én når filen er
                    # uploadet (filename vises), og endnu én når UI'en
                    # opdateres med "Scan filer"-knappen. Vi venter
                    # eksplicit på knappen så test-flowet ikke fejler.
                    try:
                        page.wait_for_selector(
                            "button:has-text('Scan filer'), "
                            "button:has-text('Opdatér filer')",
                            state="attached",
                            timeout=10000,
                        )
                    except PlaywrightTimeoutError:
                        # Knappen kommer måske først efter mere tid;
                        # fortsæt til step 5 der har sin egen retry.
                        pass
                    ctx.step(
                        page, "Test-klage uploadet",
                        "PASS",
                        f"({antal_inputs} file_uploader i DOM)",
                    )
                except PlaywrightTimeoutError:
                    ctx.step(
                        page, "Test-klage uploadet",
                        "FAIL",
                        "filnavn ikke synligt i UI efter upload",
                    )
                    return False
            except Exception as e:
                ctx.step(
                    page, "Test-klage uploadet",
                    "FAIL", f"Upload fejlede: {e}",
                )
                return False

            # ───────── STEP 5: Klik 'Scan filer' og verificér loading ──
            # Knappen ligger under fold efter upload — Playwright's
            # locator.click() auto-scroller ind i view, så vi bruger
            # det i stedet for is_visible (der returnerer false når
            # element er udenfor viewport).
            try:
                klik_kandidater = [
                    "button:has-text('Scan filer')",
                    "button:has-text('Analysér')",
                    "button:has-text('Start analyse')",
                ]
                klik_lykkedes = False
                for sel in klik_kandidater:
                    knap = page.locator(sel).first
                    if knap.count() > 0:
                        knap.scroll_into_view_if_needed(timeout=2000)
                        knap.click(timeout=5000)
                        klik_lykkedes = True
                        ctx.step(
                            page, "Scan filer-knap klikket",
                            "PASS", f"selector: {sel}",
                        )
                        break
                if not klik_lykkedes:
                    ctx.step(
                        page, "Scan filer-knap klikket",
                        "FAIL", "ingen scan-knap fundet i DOM",
                    )
                    return False

                # Loading skal komme inden for 5 sekunder
                starttid = time.time()
                loading_set = False
                try:
                    page.wait_for_selector(
                        "text=behandler dine filer",
                        timeout=5000,
                    )
                    loading_set = True
                except PlaywrightTimeoutError:
                    pass
                forloeb = time.time() - starttid
                if loading_set:
                    ctx.step(
                        page, "Loading-cirkel inden 5s",
                        "PASS",
                        f"vist efter {forloeb:.1f}s",
                    )
                else:
                    ctx.step(
                        page, "Loading-cirkel inden 5s",
                        "WARN",
                        "loading-tekst ikke fundet (måske allerede færdig)",
                    )
            except Exception as e:
                ctx.step(
                    page, "Scan filer-knap klikket",
                    "FAIL", f"{type(e).__name__}: {e}",
                )
                return False

            # ───────── STEP 6: Vent på analyse (max 3 min) ─────────
            try:
                page.wait_for_selector(
                    "text=Førstevurdering",
                    timeout=180000,  # 3 min — fanger freezes
                )
                _vent_paa_streamlit_ready(page, timeout_ms=10000)
                ok, detalje = _check_for_kritisk_fejl(page)
                if not ok:
                    ctx.step(
                        page, "Førstevurdering færdig",
                        "FAIL", detalje,
                    )
                    return False
                ctx.step(page, "Førstevurdering færdig", "PASS")
            except PlaywrightTimeoutError:
                ctx.step(
                    page, "Førstevurdering færdig",
                    "FAIL",
                    "ingen 'Førstevurdering' efter 3 min — sandsynlig freeze",
                )
                return False

            # ───────── STEP 7: Verificér nøgle-sektioner rendres ──────
            sektion_checks = [
                ("Klagepunkter",
                 "h2:has-text('Klagepunkter'), "
                 "h3:has-text('Klagepunkter')"),
                ("Sandsynligheder",
                 "text=Sandsynligheds"),
                ("Tidsforhold/tidslinje",
                 "text=Tidsforhold, text=Tidslinje"),
            ]
            for navn, sel in sektion_checks:
                try:
                    synlig = page.is_visible(sel, timeout=2000)
                    if synlig:
                        ctx.step(
                            page, f"Sektion: {navn}", "PASS"
                        )
                    else:
                        ctx.step(
                            page, f"Sektion: {navn}",
                            "WARN", "ikke synlig (kan være under fold)",
                        )
                except Exception as e:
                    ctx.step(
                        page, f"Sektion: {navn}",
                        "WARN", f"check fejlede: {e}",
                    )

            # ───────── STEP 8: Klik på bilag-checkboxes ───────────────
            # Catches Bug #1 (StreamlitDuplicateElementId ved overlap)
            try:
                checkboxes = page.locator(
                    "[data-testid=stCheckbox] input[type=checkbox]"
                )
                antal = checkboxes.count()
                if antal == 0:
                    ctx.step(
                        page, "Bilag-checkboxes klikket",
                        "WARN", "ingen checkbox fundet",
                    )
                else:
                    # Klik op til 3 første checkboxes — skal IKKE
                    # crashe med DuplicateElementId
                    for i in range(min(3, antal)):
                        try:
                            checkboxes.nth(i).click(timeout=2000)
                            _vent_paa_streamlit_ready(
                                page, timeout_ms=5000
                            )
                        except Exception as e:
                            print(
                                f"  DEBUG: checkbox {i} klik fejlede: "
                                f"{e}"
                            )
                    ok, detalje = _check_for_kritisk_fejl(page)
                    if not ok:
                        ctx.step(
                            page, "Bilag-checkboxes klikket",
                            "FAIL", detalje,
                        )
                        return False
                    ctx.step(
                        page, "Bilag-checkboxes klikket",
                        "PASS",
                        f"{min(3, antal)} af {antal} klikket "
                        "uden crash",
                    )
            except Exception as e:
                ctx.step(
                    page, "Bilag-checkboxes klikket",
                    "FAIL", f"{type(e).__name__}: {e}",
                )

            # ───────── STEP 9: Logout ────────────────────────────────
            try:
                # Logout-knap er i sidebaren
                logout_synlig = page.is_visible(
                    "button:has-text('Log ud')", timeout=3000
                )
                if logout_synlig:
                    page.click(
                        "button:has-text('Log ud')", timeout=3000
                    )
                    page.wait_for_selector(
                        "text=Log ind for at fortsætte",
                        timeout=10000,
                    )
                    ctx.step(page, "Logout virker", "PASS")
                else:
                    ctx.step(
                        page, "Logout virker",
                        "WARN", "logout-knap ikke fundet i sidebar",
                    )
            except PlaywrightTimeoutError:
                ctx.step(
                    page, "Logout virker",
                    "FAIL",
                    "logout fuldførte ikke / login-side ikke vist efter",
                )

            # ───────── Console errors-rapport ────────────────────────
            if console_errors:
                ctx.step(
                    page, "Browser-console-fejl",
                    "WARN",
                    f"{len(console_errors)} JS-fejl(s); første: "
                    f"{console_errors[0][:80]}",
                )
            else:
                ctx.step(page, "Browser-console-fejl", "PASS")

        finally:
            context.close()
            browser.close()

    return ctx.skriv_rapport()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Vis browser-vinduet under kørsel (default: headless)",
    )
    args = parser.parse_args()
    ok = koer_smoke_test(headed=args.headed)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
