"""
Load-test for juriitech PAX produktion.

Simulerer 5-10 samtidige brugere der uploader en testsag og kører fuld
førstevurderings-analyse. Måler:
  - Success rate
  - p50/p95/p99 latency
  - Fejl-kategorier (timeout, 4xx, 5xx, netværk)
  - Hvilke endpoints fejler
  - Anthropic-credit-forbrug (estimat)

USAGE:
    # Default: brug service_role_key til at minte session uden password.
    # Kræver at SUPABASE_SERVICE_KEY findes i pax-next/.env.local (det gør den).
    export PAX_LOADTEST_EMAIL="juriitech@juriitech.com"

    # Standard kørsel: 5 samtidige brugere
    python3 scripts/load_test.py

    # Mere aggressiv: 10 samtidige
    python3 scripts/load_test.py --concurrency 10

    # Kun 1 bruger til sanity-check
    python3 scripts/load_test.py --concurrency 1

    # Alternativt: brug password direkte hvis du foretrækker
    PAX_LOADTEST_PASSWORD="..." python3 scripts/load_test.py

OPRYDNING:
    Testsager uploaded under load-testen har samme anonymiserings-status
    som almindelige sager — auto-anonymisering rydder dem inden for 24
    timer. Hvis du vil rydde med det samme, brug /admin-siden eller kør
    gdpr_pipeline.trigger_auto_anonymisering manuelt.

OMKOSTNING:
    Hver fuld analyse koster ~$0.30-0.50 i Anthropic-credits + lidt
    Voyage embedding. 10 samtidige analyser = ~$3-5 pr. testkørsel.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import statistics
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import httpx
except ImportError:
    print("FEJL: httpx mangler. Installer med: pip install 'httpx[http2]'")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────
# KONFIGURATION
# ─────────────────────────────────────────────────────────────────

PROD_URL = os.getenv("PAX_LOADTEST_URL", "https://pax.juriitech.com")
SUPABASE_URL = "https://sebsjjsfxlegspqturxl.supabase.co"
SUPABASE_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNlYnNqanNmeGxlZ3NwcXR1cnhsIiwicm9sZSI6ImFub24i"
    "LCJpYXQiOjE3NzcyMjExOTQsImV4cCI6MjA5Mjc5NzE5NH0._6LDeO-2FXTjJSEeau179os39edXyRqnIcVVvBVk3nQ"
)
TEST_SAGER_DIR = Path(__file__).resolve().parent.parent / "pax-next" / "public" / "test-sager"

# To-trins flow: submit + poll
SUBMIT_ENDPOINT = "/api/jobs/foerstevurdering"
STATUS_ENDPOINT = "/api/jobs"  # GET /api/jobs/{job_id}
# Total timeout pr. analyse — kø-ventetid kan være lang ved høj load.
# Med concurrency=2 på worker + 5 samtidige jobs hvor hver tager 5-7 min
# i parallel: sidste job i kø kan tage 15-18 min. 20 min er generøst.
ANALYSE_TIMEOUT = 1200.0
# Polling-interval matcher hvad frontend bruger
POLL_INTERVAL = 3.0


# ─────────────────────────────────────────────────────────────────
# DATAKLASSER
# ─────────────────────────────────────────────────────────────────

@dataclass
class Resultat:
    worker_id: int
    sag_mappe: str
    success: bool
    latency_s: float
    http_status: Optional[int] = None
    error_kategori: Optional[str] = None  # "timeout", "network", "4xx", "5xx", "schema", "other"
    error_besked: Optional[str] = None
    proxy_status: Optional[int] = None  # _proxy_status hvis present
    started_at: float = field(default_factory=time.monotonic)
    antal_klagepunkter: Optional[int] = None
    antal_relevante_sager: Optional[int] = None


# ─────────────────────────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────────────────────────

import re as _re


async def hent_jwt_via_password(email: str, password: str) -> str:
    """Login via Supabase Auth API med email+password. Kan fejle pga.
    rate-limit hvis flere mislykkede forsøg er blevet lavet."""
    url = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            url,
            headers=headers,
            json={"email": email, "password": password},
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Supabase login fejlede ({resp.status_code}): {resp.text[:200]}"
            )
        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise RuntimeError(f"Login OK men ingen access_token i svar: {data}")
        return token


async def hent_jwt_via_magic_link(email: str, service_role_key: str) -> str:
    """Login uden password ved at:
      1. Generere magic-link via admin API (kræver service_role_key)
      2. Forløse linket via GET /auth/v1/verify
      3. Parse access_token fra redirect-URL'en

    Undgår password-rate-limits og kræver intet bruger-password.
    """
    headers_admin = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Content-Type": "application/json",
    }
    headers_anon = {"apikey": SUPABASE_ANON_KEY}

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
        # 1. Generér magic-link
        resp = await client.post(
            f"{SUPABASE_URL}/auth/v1/admin/generate_link",
            headers=headers_admin,
            json={"type": "magiclink", "email": email},
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"admin/generate_link fejlede ({resp.status_code}): "
                f"{resp.text[:200]}"
            )
        link_data = resp.json()
        hashed_token = link_data.get("hashed_token")
        if not hashed_token:
            raise RuntimeError(
                f"hashed_token mangler i generate_link-svar: {link_data}"
            )

        # 2. Forløs linket via GET /verify — returnerer redirect med
        # access_token i URL-fragmentet (#access_token=...)
        resp2 = await client.get(
            f"{SUPABASE_URL}/auth/v1/verify",
            headers=headers_anon,
            params={"token": hashed_token, "type": "magiclink"},
        )
        # Forventet: 303 See Other med Location-header der peger på
        # vores site med token i fragmentet.
        location = resp2.headers.get("location") or resp2.text
        # Parse access_token fra URL-fragmentet
        match = _re.search(r"access_token=([A-Za-z0-9._\-]+)", location)
        if not match:
            raise RuntimeError(
                f"Kunne ikke parse access_token fra verify-svar: "
                f"status={resp2.status_code}, body={location[:200]}"
            )
        return match.group(1)


async def hent_jwt(email: str) -> str:
    """Default auth-strategi: foretrækker magic-link via service_role_key
    (ingen password, ingen rate-limits). Falder tilbage til password
    hvis PAX_LOADTEST_PASSWORD er sat eller service_role_key mangler.
    """
    password = os.getenv("PAX_LOADTEST_PASSWORD")
    if password:
        print("  Auth-metode: password (PAX_LOADTEST_PASSWORD er sat)")
        return await hent_jwt_via_password(email, password)

    service_key = (
        os.getenv("SUPABASE_SERVICE_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    )
    if not service_key:
        # Sidste fallback: prøv at læse fra pax-next/.env.local
        env_local = (
            Path(__file__).resolve().parent.parent
            / "pax-next" / ".env.local"
        )
        if env_local.exists():
            for linje in env_local.read_text().splitlines():
                if linje.startswith("SUPABASE_SERVICE_KEY="):
                    service_key = linje.split("=", 1)[1].strip()
                    break

    if service_key:
        print("  Auth-metode: magic-link via service_role_key (intet password)")
        return await hent_jwt_via_magic_link(email, service_key)

    raise RuntimeError(
        "Hverken PAX_LOADTEST_PASSWORD eller SUPABASE_SERVICE_KEY er sat. "
        "Sæt en af dem og prøv igen."
    )


# ─────────────────────────────────────────────────────────────────
# UDFØRELSE
# ─────────────────────────────────────────────────────────────────

def vaelg_testsag() -> Path:
    """Plukker en tilfældig testsag. 5 sager findes — vi roterer
    så ikke alle workers rammer samme RAG-cache-hit."""
    mapper = sorted([p for p in TEST_SAGER_DIR.iterdir() if p.is_dir()])
    if not mapper:
        raise RuntimeError(f"Ingen testsager fundet i {TEST_SAGER_DIR}")
    return random.choice(mapper)


def kategoriser_fejl(exc: BaseException, http_status: Optional[int]) -> str:
    """Mapper exception eller status til kanonisk kategori."""
    if isinstance(exc, asyncio.TimeoutError) or isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError)):
        return "network"
    if http_status is not None:
        if 400 <= http_status < 500:
            return "4xx"
        if 500 <= http_status < 600:
            return "5xx"
    return "other"


async def kør_én_analyse(
    worker_id: int,
    jwt: str,
    semafor: asyncio.Semaphore,
    ny_input: bool = False,
    fast_sag_navn: Optional[str] = None,
) -> Resultat:
    """Én komplet analyse-flow: login → upload → vent på svar → returner.

    Hvis fast_sag_navn er sat, bruges netop den sag (matchende sag pr.
    test-bruger). Ellers plukkes tilfældigt.
    """
    async with semafor:
        if fast_sag_navn:
            sag = TEST_SAGER_DIR / fast_sag_navn
            if not sag.is_dir():
                return Resultat(
                    worker_id=worker_id,
                    sag_mappe=fast_sag_navn,
                    success=False,
                    latency_s=0.0,
                    error_kategori="other",
                    error_besked=f"Fast sag ikke fundet: {sag}",
                )
        else:
            sag = vaelg_testsag()
        files_data = []
        try:
            for fil in sorted(sag.glob("*.pdf")):
                files_data.append(
                    (
                        "filer",
                        (fil.name, fil.read_bytes(), "application/pdf"),
                    )
                )
        except Exception as e:
            return Resultat(
                worker_id=worker_id,
                sag_mappe=sag.name,
                success=False,
                latency_s=0.0,
                error_kategori="other",
                error_besked=f"Kunne ikke læse testsag: {e}",
            )

        headers = {
            "Authorization": f"Bearer {jwt}",
        }
        # Tilføj random suffix til sagsakter hvis vi bypasses idempotens-cachen.
        # Suffix-byter er en lille kommentar AI'en ignorerer, men idempotency-
        # hash-funktionen ser det som unikt input → tvinger nyt job.
        sagsakter_text = ""
        if ny_input:
            import uuid as _uuid
            sagsakter_text = f"\n\n[loadtest-nonce: {_uuid.uuid4().hex[:16]}]"
        data = {"sagsakter": sagsakter_text}

        start = time.monotonic()
        http_status: Optional[int] = None

        try:
            async with httpx.AsyncClient(timeout=30.0, http2=True) as client:
                # ─── Step 1: submit job ───
                submit_resp = await client.post(
                    f"{PROD_URL}{SUBMIT_ENDPOINT}",
                    headers=headers,
                    files=files_data,
                    data=data,
                )
                http_status = submit_resp.status_code

                if submit_resp.status_code != 200:
                    return Resultat(
                        worker_id=worker_id,
                        sag_mappe=sag.name,
                        success=False,
                        latency_s=time.monotonic() - start,
                        http_status=submit_resp.status_code,
                        error_kategori=kategoriser_fejl(
                            Exception(), submit_resp.status_code
                        ),
                        error_besked=f"submit fejlede: {submit_resp.text[:150]}",
                    )

                submit_data = submit_resp.json()
                job_id = submit_data.get("job_id")
                if not job_id:
                    return Resultat(
                        worker_id=worker_id,
                        sag_mappe=sag.name,
                        success=False,
                        latency_s=time.monotonic() - start,
                        http_status=200,
                        error_kategori="schema",
                        error_besked="Manglende job_id i submit-svar",
                    )

                # ─── Step 2: poll status indtil completed/failed/timeout ───
                async with httpx.AsyncClient(timeout=15.0, http2=True) as poll_client:
                    while True:
                        if time.monotonic() - start > ANALYSE_TIMEOUT:
                            return Resultat(
                                worker_id=worker_id,
                                sag_mappe=sag.name,
                                success=False,
                                latency_s=time.monotonic() - start,
                                http_status=None,
                                error_kategori="timeout",
                                error_besked=f"Job {job_id[:8]} timeout i poll-loop",
                            )

                        await asyncio.sleep(POLL_INTERVAL)

                        status_resp = await poll_client.get(
                            f"{PROD_URL}{STATUS_ENDPOINT}/{job_id}",
                            headers=headers,
                        )
                        if status_resp.status_code != 200:
                            # 5xx → fortsæt polling, 4xx → fejl
                            if status_resp.status_code >= 500:
                                continue
                            return Resultat(
                                worker_id=worker_id,
                                sag_mappe=sag.name,
                                success=False,
                                latency_s=time.monotonic() - start,
                                http_status=status_resp.status_code,
                                error_kategori="4xx",
                                error_besked=f"poll: {status_resp.text[:150]}",
                            )

                        sd = status_resp.json()
                        status = sd.get("status")
                        if status == "completed":
                            resultat = sd.get("resultat") or {}
                            meta = resultat.get("metadata") or {}
                            return Resultat(
                                worker_id=worker_id,
                                sag_mappe=sag.name,
                                success=True,
                                latency_s=time.monotonic() - start,
                                http_status=200,
                                antal_klagepunkter=meta.get("antal_klagepunkter"),
                                antal_relevante_sager=meta.get("antal_relevante_sager"),
                            )
                        if status == "failed":
                            return Resultat(
                                worker_id=worker_id,
                                sag_mappe=sag.name,
                                success=False,
                                latency_s=time.monotonic() - start,
                                http_status=200,
                                error_kategori=sd.get("fejl_kategori") or "other",
                                error_besked=(sd.get("fejl_besked") or "")[:150],
                            )
                        # pending / running → fortsæt
        except Exception as e:
            return Resultat(
                worker_id=worker_id,
                sag_mappe=sag.name,
                success=False,
                latency_s=time.monotonic() - start,
                http_status=http_status,
                error_kategori=kategoriser_fejl(e, http_status),
                error_besked=f"{type(e).__name__}: {str(e)[:150]}",
            )


# ─────────────────────────────────────────────────────────────────
# RAPPORT
# ─────────────────────────────────────────────────────────────────

def percentil(data: list[float], p: float) -> float:
    if not data:
        return 0.0
    if len(data) == 1:
        return data[0]
    sorteret = sorted(data)
    k = (len(sorteret) - 1) * p
    f = int(k)
    c = min(f + 1, len(sorteret) - 1)
    return sorteret[f] + (sorteret[c] - sorteret[f]) * (k - f)


def print_rapport(resultater: list[Resultat], duration_s: float) -> None:
    n = len(resultater)
    successes = [r for r in resultater if r.success]
    failures = [r for r in resultater if not r.success]

    success_rate = len(successes) / n * 100 if n else 0.0

    print("\n" + "═" * 70)
    print(f"  LOAD-TEST RAPPORT — {n} requests over {duration_s:.1f}s")
    print("═" * 70)
    print(f"  Success: {len(successes)}/{n} ({success_rate:.1f}%)")
    print(f"  Fejl:    {len(failures)}/{n} ({100 - success_rate:.1f}%)")

    if successes:
        latenser = [r.latency_s for r in successes]
        print("\n  Latency (kun successes):")
        print(f"    min:  {min(latenser):.1f}s")
        print(f"    p50:  {percentil(latenser, 0.50):.1f}s")
        print(f"    p95:  {percentil(latenser, 0.95):.1f}s")
        print(f"    p99:  {percentil(latenser, 0.99):.1f}s")
        print(f"    max:  {max(latenser):.1f}s")
        print(f"    mean: {statistics.mean(latenser):.1f}s")

    if failures:
        print("\n  Fejl-kategorier:")
        kat_tæller = Counter(r.error_kategori for r in failures)
        for kat, antal in kat_tæller.most_common():
            print(f"    {kat:12s} {antal}")

        print("\n  Fejl-eksempler (top 5):")
        for r in failures[:5]:
            status = (
                f"HTTP {r.http_status}"
                + (f" (proxy_status={r.proxy_status})" if r.proxy_status else "")
                if r.http_status
                else "intet svar"
            )
            print(
                f"    worker={r.worker_id} sag={r.sag_mappe}\n"
                f"      {status} · {r.error_kategori}\n"
                f"      → {(r.error_besked or '')[:150]}"
            )

    if successes:
        kp_data = [r.antal_klagepunkter for r in successes if r.antal_klagepunkter]
        rs_data = [r.antal_relevante_sager for r in successes if r.antal_relevante_sager]
        if kp_data:
            print(f"\n  AI-output sanity:")
            print(f"    antal_klagepunkter (mean): {statistics.mean(kp_data):.1f}")
        if rs_data:
            print(f"    antal_relevante_sager (mean): {statistics.mean(rs_data):.1f}")

    print("\n" + "═" * 70)
    print(f"  Estimeret omkostning: ${len(successes) * 0.40:.2f} Anthropic-credits")
    print("═" * 70 + "\n")


# ─────────────────────────────────────────────────────────────────
# ENTRYPOINT
# ─────────────────────────────────────────────────────────────────

async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=5,
                        help="Antal samtidige analyser (default 5)")
    parser.add_argument("--total", type=int, default=None,
                        help="Total antal analyser (default = concurrency)")
    parser.add_argument("--ny-input", action="store_true",
                        help="Tilføj random salt til sagsakter så idempotens-cache bypasses")
    parser.add_argument("--samme-bruger", action="store_true",
                        help="Brug samme email til alle workers (legacy mode)")
    args = parser.parse_args()

    total = args.total or args.concurrency
    concurrency = args.concurrency

    # ─── Multi-bruger mode (default): én test-bruger pr. worker ───
    # Dette er det realistiske scenarie — forskellige kunder med forskellige
    # logins der submitter samtidigt. Læser test-brugere fra config-fil og
    # par'er hver worker med en bruger + dennes matchende test-sag.
    config_path = Path(__file__).resolve().parent.parent / "test-brugere-config.json"
    use_multi = not args.samme_bruger and config_path.exists()

    worker_emails: list[str]
    worker_sager: list[Optional[str]]
    if use_multi:
        with open(config_path, "r", encoding="utf-8") as f:
            test_config = json.load(f)
        test_brugere = test_config.get("brugere", [])
        if len(test_brugere) < total:
            print(
                f"FEJL: Test-config har {len(test_brugere)} brugere, men "
                f"--concurrency={total} kræver mindst så mange. Reducér "
                f"concurrency eller opret flere test-brugere."
            )
            return 1
        valgte = test_brugere[:total]
        worker_emails = [b["email"] for b in valgte]
        worker_sager = [b.get("matchende_test_sag") for b in valgte]
        auth_beskrivelse = (
            f"multi-user ({len(valgte)} unikke test-brugere — realistisk scenarie)"
        )
    else:
        default_email = os.getenv("PAX_LOADTEST_EMAIL", "juriitech@juriitech.com")
        worker_emails = [default_email] * total
        worker_sager = [None] * total
        auth_beskrivelse = f"single-user ({default_email})"

    print(f"Load-test mod {PROD_URL}")
    print(f"  Concurrency: {concurrency}")
    print(f"  Total requests: {total}")
    print(f"  Submit endpoint: {SUBMIT_ENDPOINT} → poll {STATUS_ENDPOINT}/[id]")
    print(f"  Timeout per analyse: {ANALYSE_TIMEOUT}s")
    print(f"  Auth: {auth_beskrivelse}")
    print(f"  Bypass idempotens-cache: {args.ny_input}")

    print("\n[1/3] Logger ind via Supabase ...")
    jwts: list[str] = []
    try:
        # Mint JWT for hver unik email (ikke pr. worker — for emails der
        # deler bruger kan vi genbruge JWT'en).
        unique_emails = list(dict.fromkeys(worker_emails))
        email_to_jwt: dict[str, str] = {}
        for em in unique_emails:
            email_to_jwt[em] = await hent_jwt(em)
            print(f"  ✓ JWT mintet for {em} ({len(email_to_jwt[em])} tegn)")
        jwts = [email_to_jwt[em] for em in worker_emails]
    except Exception as e:
        print(f"FEJL ved login: {e}")
        return 1

    print(f"\n[2/3] Starter {total} parallelle analyser ({concurrency} samtidige) ...")
    semafor = asyncio.Semaphore(concurrency)
    start = time.monotonic()

    tasks = [
        asyncio.create_task(
            kør_én_analyse(
                worker_id=i,
                jwt=jwts[i],
                semafor=semafor,
                ny_input=args.ny_input,
                fast_sag_navn=worker_sager[i],
            )
        )
        for i in range(total)
    ]

    # Progress-print mens vi venter
    completed: list[Resultat] = []
    for fut in asyncio.as_completed(tasks):
        r = await fut
        completed.append(r)
        symbol = "✓" if r.success else "✗"
        ms = int(r.latency_s * 1000)
        print(
            f"  {symbol} worker={r.worker_id:2d} sag={r.sag_mappe:25s} "
            f"latency={ms:6d}ms status={r.http_status or 'X':<4} "
            f"{r.error_kategori or ''}"
        )

    duration = time.monotonic() - start
    print(f"\n[3/3] Færdig på {duration:.1f}s")

    print_rapport(completed, duration)
    return 0 if all(r.success for r in completed) else 2


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\nAfbrudt af bruger.")
        sys.exit(130)
