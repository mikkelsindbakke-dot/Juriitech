"""
FastAPI-bro til eksisterende Python-PAX-kode.

Denne service eksponerer ai_engine.py, embeddings.py, processor.py,
anonymisering_pdf.py m.fl. som HTTP-endpoints, så Next.js-versionen
af PAX (i pax-next/) kan kalde dem uden at vi skal port'e den
juridiske domæne-logik til TypeScript.

Designprincipper:
  - INGEN ændring af eksisterende Python-kode (ai_engine.py m.fl.).
  - Kun lokalt under migration. IKKE deployet til Fly.io.
  - Importerer fra parent-mappen via sys.path-hack øverst i filen.
  - CORS tillader kun localhost:3000 (Next.js dev-server).

Kør lokalt:
  cd /Users/mikkelhansen/Desktop/Projekter/juridisk_assistent
  uvicorn api.main:app --reload --port 8000
"""

import os
import sys

# Tilføj parent-mappen til sys.path så vi kan importere ai_engine,
# embeddings, processor m.fl. uden at flytte dem.
_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

# Indlæs .env (DB + ENCRYPTION_KEY) og pax-next/.env.local (Supabase) så
# uvicorn ikke kræver eksplicit env-export før den starter. Aliasér
# NEXT_PUBLIC_*-varianterne så auth.py (der forventer SUPABASE_URL uden
# prefix) finder dem.
try:
    from dotenv import load_dotenv as _load_dotenv  # noqa: E402
    _load_dotenv(os.path.join(_PARENT, ".env"))
    _load_dotenv(os.path.join(_PARENT, "pax-next", ".env.local"), override=False)
    for _src, _dst in (
        ("NEXT_PUBLIC_SUPABASE_URL", "SUPABASE_URL"),
        ("NEXT_PUBLIC_SUPABASE_ANON_KEY", "SUPABASE_ANON_KEY"),
    ):
        if os.getenv(_src) and not os.getenv(_dst):
            os.environ[_dst] = os.getenv(_src)
except Exception as _e:
    print(f"DEBUG: dotenv-load fejlede (ikke kritisk): {_e}")

from typing import List, Optional  # noqa: E402

from fastapi import (  # noqa: E402
    Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402


# ─────────── SENTRY ERROR-MONITORING ───────────
# Initialiseres FØR FastAPI() så crashes under app-opstart også fanges.
# DSN læses fra SENTRY_DSN miljøvariabel. Hvis den mangler, springes
# init over så lokal udvikling stadig virker (graceful no-op).
#
# PII-scrubberen er bit-præcist samme felt-liste som Streamlit-PAX
# (app.py). Når Streamlit slukkes, mister vi al observability uden
# denne dækning af FastAPI-laget.

_PII_FELT_NAVNE = frozenset({
    "aktuel_sag", "sagsakter", "sagsakter_filer", "filer",
    "fil_bytes", "bytes", "raw_bytes", "pdf_bytes",
    "tekst", "indhold", "klage", "klage_tekst", "sag_tekst",
    "klager_navn", "klagers_navn", "email", "fulde_navn",
    "auto_vurdering_tekst", "seneste_svarbrev", "seneste_anonymisering",
    "seneste_tjekliste", "sagsresume", "chat_historik",
    "state_json", "aktiv_sag_state", "snapshot",
    "spoergsmaal", "ekstra_instrukser",
    "password", "access_token", "refresh_token", "api_key",
    # FastAPI-specifikke felter med bytes/PII
    "data", "form", "body", "markdown",
})


def _scrub_pii(node, _depth=0):
    """
    Rekursiv PII-scrubber til Sentry-events. Erstatter værdier af
    følsomme felter med "[REDACTED]" og trunkerer lange strenge.
    Max-dybde 8 så vi ikke rammer rekursions-grænse på cykliske
    referencer eller meget dybe pydantic-modeller.

    Spejler app.py:_scrub_pii så scrubbing er konsistent på tværs af
    Streamlit og FastAPI-stacken.
    """
    if _depth > 8:
        return "[REDACTED:max-depth]"
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if isinstance(k, str) and k.lower() in _PII_FELT_NAVNE:
                out[k] = "[REDACTED]"
            else:
                out[k] = _scrub_pii(v, _depth + 1)
        return out
    if isinstance(node, (list, tuple)):
        scrubbed = [_scrub_pii(item, _depth + 1) for item in node]
        return type(node)(scrubbed) if not isinstance(node, tuple) else tuple(scrubbed)
    if isinstance(node, bytes):
        return f"[REDACTED:bytes len={len(node)}]"
    if isinstance(node, str) and len(node) > 500:
        return node[:200] + f"...[TRUNCATED len={len(node)}]"
    return node


def _sentry_before_send(event, hint):
    """
    Renser Sentry-event for PII før det forlader processen. Spejler
    app.py:_sentry_before_send (Streamlit-stack) — samme strategi
    overalt så vi ikke utilsigtet lækker PII fra FastAPI-laget.
    """
    try:
        for exc in (event.get("exception") or {}).get("values") or []:
            for frame in (exc.get("stacktrace") or {}).get("frames") or []:
                if frame.get("vars"):
                    frame["vars"] = _scrub_pii(frame["vars"])
        if event.get("extra"):
            event["extra"] = _scrub_pii(event["extra"])
        if event.get("contexts"):
            event["contexts"] = _scrub_pii(event["contexts"])
        req = event.get("request") or {}
        if req.get("data"):
            req["data"] = _scrub_pii(req["data"])
    except Exception as e:
        print(f"DEBUG: Sentry PII-scrubber fejlede: {e}")
    return event


def _init_sentry():
    sentry_dsn = os.getenv("SENTRY_DSN", "")
    if not sentry_dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        sentry_sdk.init(
            dsn=sentry_dsn,
            send_default_pii=False,
            before_send=_sentry_before_send,
            traces_sample_rate=0.1,
            environment=os.getenv("SENTRY_ENV", "production"),
            release=os.getenv("SENTRY_RELEASE", "juriitech-pax-api@dev"),
            integrations=[
                FastApiIntegration(),
                StarletteIntegration(),
            ],
        )
        print("DEBUG: Sentry initialiseret for FastAPI")
        return True
    except Exception as e:
        print(f"DEBUG: Sentry init for FastAPI fejlede (ikke kritisk): {e}")
        return False


_SENTRY_AKTIV = _init_sentry()


# ─────────── ANTHROPIC OVERLOAD-MAPPING ───────────
#
# Når ai_engine-funktioner ramler ind i Anthropic 529 (overloaded), bør
# vi returnere HTTP 503 i stedet for 500/422 — så frontend's p-retry
# kører automatisk og brugeren ikke ser en fejl.
#
# ai_engine._kald_anthropic_robust prøver allerede 3 gange med backoff
# før den propagerer 529. Hvis vi når her er Anthropic varigt nede.
def _er_overload_fejl(e: Exception) -> bool:
    msg = str(e)
    return (
        "529" in msg
        or "Overloaded" in msg
        or "overloaded_error" in msg.lower()
    )


def _raise_503_hvis_overload(e: Exception) -> None:
    """Hjælper: hvis exception er en Anthropic-overload eller circuit-
    breaker er åben, raise HTTP 503 så frontend's p-retry tager over.
    Ellers gør ingenting (kalderen håndterer fejlen som normalt 500)."""
    # Circuit-breaker giver en custom exception fra ai_engine
    try:
        from ai_engine import CircuitBreakerOpenError
        if isinstance(e, CircuitBreakerOpenError):
            raise HTTPException(
                status_code=503,
                detail=(
                    "AI er midlertidigt overbelastet. "
                    "Vi har kortvarigt slået retry'es fra — prøv igen "
                    "om ~1 minut."
                ),
            )
    except ImportError:
        pass
    if _er_overload_fejl(e):
        raise HTTPException(
            status_code=503,
            detail=(
                "AI er midlertidigt overbelastet. "
                "Prøv igen om et øjeblik — der retries automatisk."
            ),
        )


# ─────────── SLA-LOGNING ───────────
#
# Hver AI-endpoint-request logger én række til request_log med:
#   - latency_ms, model, input_tokens, output_tokens
#   - success/failure + error-kategori
#   - tenant_id (for per-tenant audit-trail)
#
# Bruges til at svare på "var oppetiden 99,9%?" og "hvor mange tokens
# bruger vi pr. måned pr. tenant?".
import uuid
import time as _time

# Hvilke endpoints der SLA-logges. Health-tjek, admin-tools m.fl. logges
# IKKE — det er kun de AI-tunge user-facing requests vi har brug for
# audit-trail på.
_SLA_LOG_ENDPOINTS = {
    "/api/foerstevurdering",
    "/api/svarbrev",
    "/api/tjekliste",
    "/api/sagsmetadata",
    "/api/anonymiser",
}


def _kategoriser_fejl(e: Exception) -> str:
    """Mapper exception til en kanonisk error-kategori for request_log."""
    msg = str(e).lower()
    try:
        from ai_engine import CircuitBreakerOpenError
        if isinstance(e, CircuitBreakerOpenError):
            return "circuit_breaker"
    except ImportError:
        pass
    if _er_overload_fejl(e):
        return "overload"
    if isinstance(e, HTTPException):
        if e.status_code == 503:
            return "overload"
        if e.status_code == 422:
            return "validation"
        if 400 <= e.status_code < 500:
            return "client_error"
        return "server_error"
    if "timeout" in msg or "timed out" in msg:
        return "timeout"
    if "json" in msg or "parse" in msg or "decode" in msg:
        return "parse"
    if "max_tokens" in msg or "truncat" in msg:
        return "truncation"
    return "other"


app = FastAPI(
    title="juriitech PAX API",
    description="Bro mellem Next.js-frontend og eksisterende Python-AI-kode.",
    version="0.1.0",
)


# ─────────── GDPR AUDIT-LOG HELPERS ───────────
# Skriver én række til gdpr_audit_log pr. persondata-relevant handling
# (upload, analyse, eksport, anonymisering, sletning). Bruges af GDPR
# art. 30 (oversigt over behandlingsaktiviteter) og art. 32 (sikkerhed).
#
# Fail-safe: hvis log-skrivning fejler, undertrykkes det — brugeren
# oplever ALDRIG en fejl pga. audit. Sentry fanger evt. DB-problemer.

def _hent_audit_kontekst(request: Request) -> dict:
    """Plukker tenant_id, user_id, user_email og ip ud af request.state.

    Returnerer dict med felterne — eller None-værdier hvis auth-dependency
    ikke har sat dem (kan ske ved AUTH_BYPASS-mode eller før dependency
    har kørt). I så fald skipper audit-skrivning helt.
    """
    try:
        tenant = getattr(request.state, "tenant", None) or {}
        user = getattr(request.state, "user", None) or {}
        db_user = user.get("db_user") if isinstance(user, dict) else {}
        if not isinstance(db_user, dict):
            db_user = {}
        # IP-adresse — request.client kan være None bag visse proxies
        ip = None
        try:
            if request.client and request.client.host:
                ip = request.client.host
            # Fly.io proxy sender ægte client-IP i Fly-Client-IP header
            forwarded = request.headers.get("fly-client-ip") or request.headers.get(
                "x-forwarded-for"
            )
            if forwarded:
                ip = forwarded.split(",")[0].strip()
        except Exception:
            pass
        return {
            "tenant_id": tenant.get("id") if isinstance(tenant, dict) else None,
            "user_id": db_user.get("id"),
            "user_email": db_user.get("email") or (user.get("email") if isinstance(user, dict) else None),
            "ip_adresse": ip,
        }
    except Exception:
        return {"tenant_id": None, "user_id": None, "user_email": None, "ip_adresse": None}


def _audit_request(
    request: Request,
    handling: str,
    sag_id=None,
    metadata: dict = None,
) -> None:
    """Convenience-wrapper: pluk kontekst fra request og skriv audit-log.

    Bruges fra endpoints:
        _audit_request(request, "upload", sag_id=filnavn, metadata={"bytes": n})

    Hvis tenant_id ikke kan udledes (fx AUTH_BYPASS-mode), springer vi
    audit-skrivning over uden at fejle. Det er korrekt: i bypass-mode er
    der ingen rigtig bruger at logge alligevel.
    """
    ctx = _hent_audit_kontekst(request)
    if not ctx.get("tenant_id"):
        return
    try:
        from database import skriv_gdpr_audit
        skriv_gdpr_audit(
            handling=handling,
            tenant_id=ctx["tenant_id"],
            sag_id=sag_id,
            user_id=ctx.get("user_id"),
            user_email=ctx.get("user_email"),
            ip_adresse=ctx.get("ip_adresse"),
            metadata=metadata,
        )
    except Exception as e:
        # Audit må ALDRIG blokere request. Suppress.
        print(f"DEBUG: _audit_request fejlede (ikke kritisk): {e}")


@app.on_event("startup")
async def _init_request_log_tabel():
    """Sikrer at SLA-logning-tabellen findes inden første request rammer."""
    try:
        from database import ensure_request_log_tabel
        ensure_request_log_tabel()
    except Exception as e:
        print(f"DEBUG: request_log init fejlede (ikke kritisk): {e}")


# ─────────── GDPR AUTO-ANONYMISERINGS-SCHEDULER ───────────
#
# Tidligere skulle GDPR-pipelinen køre via en separat Fly cron-machine,
# men det blev aldrig aktiveret efter migrationen til Next.js. I stedet
# kører vi nu BackgroundScheduler INDE i FastAPI-processen — én gang i
# timen kalder den trigger_auto_anonymisering der:
#
#   1. Anonymiserer mine_dokumenter med anonymiserings_status='aktiv'
#      og anonymiseres_efter < NOW() (AI-baseret PII-redaktion)
#   2. Anonymiserer analyse_arkiv (AI-redaktion af genererede tekster)
#   3. Sletter gemte_sager med slet_efter < NOW() (90-dages TTL)
#
# BackgroundScheduler kører i sin egen tråd → blokerer ikke event-loop.
# Idempotent: pipelinen filtrerer på status, så dobbelt-eksekvering er
# sikker. Uvicorn-deploy kører kun 1 worker (default), så ingen risiko
# for parallel-kørsel.
_gdpr_scheduler = None


@app.on_event("startup")
async def _start_gdpr_scheduler():
    """Starter timer-cyklus for GDPR auto-anonymisering."""
    global _gdpr_scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        _gdpr_scheduler = BackgroundScheduler(timezone="Europe/Copenhagen")
        _gdpr_scheduler.add_job(
            _koer_gdpr_pipeline,
            "interval",
            hours=1,
            id="gdpr_auto_anonymisering",
            replace_existing=True,
            # next_run_time=None → første kørsel sker efter 1 time, ikke
            # ved boot. Forhindrer dobbelt-trigger ved hurtig redeploy.
        )
        _gdpr_scheduler.start()
        print(
            "DEBUG: GDPR auto-anonymisering scheduler aktiveret "
            "(hver time)"
        )
    except Exception as e:
        print(f"DEBUG: GDPR scheduler init fejlede: {e}")


@app.on_event("shutdown")
async def _stop_gdpr_scheduler():
    """Stop scheduler pænt ved shutdown så ikke-færdige jobs får finally."""
    global _gdpr_scheduler
    if _gdpr_scheduler:
        try:
            _gdpr_scheduler.shutdown(wait=False)
        except Exception as e:
            print(f"DEBUG: scheduler shutdown fejlede: {e}")


def _koer_gdpr_pipeline():
    """Wrapper omkring trigger_auto_anonymisering med fejlhåndtering.
    Kører i BackgroundScheduler's tråd, IKKE event-loop."""
    try:
        from gdpr_pipeline import trigger_auto_anonymisering
        resultat = trigger_auto_anonymisering(maks_per_kørsel=20)
        print(f"DEBUG: GDPR-cyklus færdig: {resultat}")
    except Exception as e:
        print(f"DEBUG: GDPR-cyklus fejlede: {e}")
        try:
            if _SENTRY_AKTIV:
                import sentry_sdk
                sentry_sdk.capture_exception(e)
        except Exception:
            pass


@app.post("/api/admin/gdpr-tick")
async def admin_gdpr_tick(
    x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
    dry_run: bool = False,
):
    """Manuelt trigger af GDPR-pipelinen. Beskyttet af ADMIN_KEY-header.
    Bruges til (1) initial backfill efter første deploy og (2) ad-hoc
    debugging når scheduler ikke har ramt endnu.

    Eksempel:
        curl -X POST https://pax.juriitech.com/api/admin/gdpr-tick \\
             -H "X-Admin-Key: ${ADMIN_KEY}"

    Sæt dry_run=true for at se hvad pipelinen VILLE gøre uden faktisk
    at skrive til DB."""
    admin_key = os.getenv("ADMIN_KEY", "").strip()
    if not admin_key:
        raise HTTPException(
            status_code=500,
            detail="ADMIN_KEY ikke konfigureret som Fly-secret",
        )
    if not x_admin_key or x_admin_key != admin_key:
        raise HTTPException(status_code=403, detail="Ugyldig admin-nøgle")

    try:
        from gdpr_pipeline import trigger_auto_anonymisering
        resultat = trigger_auto_anonymisering(
            maks_per_kørsel=20, dry_run=dry_run
        )
        return {"ok": True, "resultat": resultat}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"GDPR-pipeline fejlede: {e}"
        )

# CORS: tillad kun Next.js dev-serveren at kalde os under udvikling.
# Når vi deployer rigtigt (step 8+), opdateres denne liste.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    # "*" inkluderer ikke Authorization explicit i alle browsere; vi
    # lister den eksplicit så preflight ikke afviser Bearer-tokenet.
    allow_headers=["*", "Authorization"],
)


# ─────────── SLA-LOGNING MIDDLEWARE ───────────
#
# Wrapper hver AI-request med start-timer + token-tracker. Efter
# response logges latency, token-forbrug, success/failure og fejl-
# kategori til request_log-tabellen. Fail-safe: hvis log fejler
# undertrykkes det — bruger oplever ALDRIG en fejl pga. SLA-logging.
@app.middleware("http")
async def sla_logging_middleware(request: Request, call_next):
    path = request.url.path
    if path not in _SLA_LOG_ENDPOINTS:
        return await call_next(request)

    from ai_engine import reset_token_usage, hent_token_usage
    from database import log_request

    request_id = str(uuid.uuid4())[:12]
    start_t = _time.monotonic()
    reset_token_usage()

    success = False
    http_status = 500
    error_kat: Optional[str] = None
    error_det: Optional[str] = None
    response = None
    try:
        response = await call_next(request)
        http_status = response.status_code
        success = 200 <= http_status < 400
        if not success:
            error_kat = (
                "client_error" if 400 <= http_status < 500 else "server_error"
            )
        return response
    except Exception as e:
        http_status = 500
        success = False
        error_kat = _kategoriser_fejl(e)
        error_det = str(e)[:500]
        raise
    finally:
        latency_ms = int((_time.monotonic() - start_t) * 1000)
        usage = hent_token_usage() or {}
        tenant_id = None
        try:
            tenant_state = getattr(request.state, "tenant", None)
            if isinstance(tenant_state, dict):
                tenant_id = tenant_state.get("id")
        except Exception:
            pass
        try:
            log_request(
                request_id=request_id,
                tenant_id=tenant_id,
                endpoint=path,
                model="claude-sonnet-4-6",
                input_tokens=usage.get("input"),
                output_tokens=usage.get("output"),
                latency_ms=latency_ms,
                success=success,
                http_status=http_status,
                error_kategori=error_kat,
                error_detail=error_det,
                truncation_detekteret=bool(usage.get("truncation")),
            )
        except Exception as _log_err:
            print(f"DEBUG: SLA-log fejlede (ikke kritisk): {_log_err}")


# ─────────── MULTI-TENANT AUTH-DEPENDENCY ───────────
# KRITISK: uden denne dependency rammer ALLE FastAPI-requests TUI-
# fallback i selskab_profiler / database. Det betyder Apollo/Spies/
# test-quicktour-brugere ville få TUI-branded svarbreve, og at
# tenant-isolation i DB-queries ville lække data på tværs af tenants.
#
# Flow:
#   1. Læs "Authorization: Bearer <jwt>" header (Supabase access_token)
#   2. Validér tokenet via Supabase Admin (auth.get_user) — kan ikke
#      forfalskes, signaturen verificeres mod Supabase JWT-secret
#   3. Slå brugeren op i vores users-tabel via supabase_user_id
#   4. Slå tenanten op via tenant_id → få slug + profil-dict
#   5. Sæt BÅDE selskab_profiler-ContextVar OG database-ContextVar for
#      hele request-lifetimen. Ryddes i finally-blok.
#
# Hvis tokenet mangler eller er ugyldigt: 401. Hvis brugeren findes i
# Supabase men ikke i vores DB: 403 (ikke inviteret). Hvis tenant
# mangler: 500 (data-inkonsistens — bør aldrig ske).
#
# Bevidst valg: vi VALIDERER tokenet på hver request frem for at
# cache. Cache ville være hurtigere men kompliceret korrekt — Supabase
# har internt cache, og kaldet er ~30-100ms = trivielt sammenlignet
# med de 30-90 sek AI-kald varer.

# Cache af tenant-lookup per supabase_user_id pr. proces. Tenant-relationen
# ændrer sig sjældent, og en udløbet cache koster maks at en bruger får
# sin gamle tenant indtil processen restarter (eller cachen ryddes).
_TENANT_CACHE: dict = {}


def _valider_jwt_og_hent_user(jwt: str):
    """
    Validér Supabase JWT og returnér user-dict {supabase_user_id, email}.

    Bruger Supabase Admin SDK's auth.get_user(jwt) der verificerer
    signaturen og udløbstiden mod Supabase Auth-serveren. Kan ikke
    forfalskes — det er sikkerheds-anker for tenant-routing.
    """
    try:
        # auth.py har allerede en lazy-init admin-klient — genbrug den.
        from auth import _get_admin_client
        admin = _get_admin_client()
        if admin is None:
            return None, "SUPABASE_SERVICE_KEY mangler — kan ikke validere JWT"
        # Selvom det hedder admin-klient, kalder vi auth.get_user(jwt) som
        # er en standard-method der ikke kræver admin-rettigheder — vi
        # bruger bare admin-klienten fordi den allerede er init'eret.
        res = admin.auth.get_user(jwt)
        if not res or not getattr(res, "user", None):
            return None, "JWT validerede ikke til en bruger"
        u = res.user
        return {
            "supabase_user_id": str(u.id),
            "email": (u.email or "").lower(),
        }, None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _slaa_tenant_op(supabase_user_id: str):
    """
    Slå (db_user, tenant) op på supabase_user_id. Returnerer tuple
    (user_dict, tenant_dict) eller (None, None) hvis brugeren ikke
    findes i vores users-tabel.

    Cachet i _TENANT_CACHE pr. supabase_user_id for at undgå 2 DB-kald
    pr. request.
    """
    cached = _TENANT_CACHE.get(supabase_user_id)
    if cached:
        return cached
    try:
        from database import hent_user_by_supabase_id, hent_tenant_by_id
        db_user = hent_user_by_supabase_id(supabase_user_id)
        if not db_user:
            return None, None
        tenant = hent_tenant_by_id(db_user.get("tenant_id"))
        if not tenant:
            return db_user, None
        _TENANT_CACHE[supabase_user_id] = (db_user, tenant)
        return db_user, tenant
    except Exception as e:
        print(f"DEBUG: _slaa_tenant_op fejlede: {e}")
        return None, None


def ryd_tenant_cache(supabase_user_id: str = None):
    """
    Tøm tenant-cachen. Bruges fx hvis admin flytter en bruger til en
    anden tenant — næste request henter friske data fra DB.
    """
    global _TENANT_CACHE
    if supabase_user_id:
        _TENANT_CACHE.pop(supabase_user_id, None)
    else:
        _TENANT_CACHE = {}


async def aktiv_tenant(
    request: Request,
    authorization: Optional[str] = Header(default=None),
):
    """
    FastAPI-dependency der sikrer at requesten kører med korrekt tenant-
    context. Læser Bearer JWT, validerer mod Supabase, slår tenant op,
    og sætter både selskab_profiler.ContextVar og database.ContextVar.

    AUTH_BYPASS-mode: hvis miljøvariablen PAX_API_AUTH_BYPASS=1 er sat
    (KUN til lokal udvikling), springer vi auth over og bruger TUI som
    default tenant. Det undgår at lokal pax-next-dev-flow er blokeret
    af mangelfuld Supabase-konfiguration. Må ALDRIG sættes i produktion.

    Bruges som:
        @app.post("/api/foo")
        async def foo(_=Depends(aktiv_tenant), ...):
            ...
    """
    bypass = os.getenv("PAX_API_AUTH_BYPASS", "").strip() in ("1", "true", "yes")

    # ───── Læs Bearer-token ─────
    jwt = None
    if authorization and authorization.lower().startswith("bearer "):
        jwt = authorization[7:].strip()

    if not jwt:
        if bypass:
            # Sæt TUI som default i bypass-mode
            from database import saet_aktiv_tenant_id, reset_aktiv_tenant_id, hent_tenant_by_slug
            from selskab_profiler import (
                saet_aktiv_profil, reset_aktiv_profil, ryd_cache,
            )
            ryd_cache()  # tving frisk DB-opslag
            tui = hent_tenant_by_slug("tui")
            if not tui:
                raise HTTPException(
                    status_code=500,
                    detail="AUTH_BYPASS aktiv men TUI-tenant findes ikke i DB",
                )
            tok_id = saet_aktiv_tenant_id(tui["id"])
            tok_pf = saet_aktiv_profil(tui)
            request.state.tenant = tui
            request.state.user = {"email": "bypass@local"}
            try:
                yield
            finally:
                reset_aktiv_tenant_id(tok_id)
                reset_aktiv_profil(tok_pf)
            return

        raise HTTPException(
            status_code=401,
            detail="Mangler Authorization-header med Bearer-token",
        )

    # ───── Validér JWT ─────
    user, fejl = _valider_jwt_og_hent_user(jwt)
    if not user:
        raise HTTPException(
            status_code=401,
            detail=f"Ugyldigt eller udløbet token: {fejl or 'ukendt grund'}",
        )

    # ───── Slå tenant op ─────
    db_user, tenant = _slaa_tenant_op(user["supabase_user_id"])
    if not db_user:
        raise HTTPException(
            status_code=403,
            detail=(
                "Du er logget ind via Supabase, men din konto er ikke "
                "knyttet til en tenant i PAX. Kontakt en administrator."
            ),
        )
    if not tenant:
        raise HTTPException(
            status_code=500,
            detail=(
                "Din konto er ikke knyttet til en gyldig tenant "
                "(data-inkonsistens). Kontakt en administrator."
            ),
        )

    # ───── ADMIN-IMPERSONERING via pax_admin_viewing_tenant cookie ─────
    # Next.js har en tenant-switcher der lader admins "se som" en anden
    # tenant. Den sætter cookie 'pax_admin_viewing_tenant=<tenant_id>'.
    # For Next.js queries respekteres denne i hentBrugerMedTenant() →
    # effektiv_tenant_id. Men FastAPI's aktiv_tenant brugte historisk
    # KUN JWT'ens user → user.tenant_id. Resultat: når admin har valgt
    # 'view as FjordTravel' i UI'en, og kalder /api/svarbrev, fik AI'en
    # admin'ens RIGTIGE tenant (med dansk sprog), ikke FjordTravel.
    #
    # Fix: hvis bruger er admin OG cookien er sat til en gyldig tenant,
    # bruger vi den i stedet. Ikke-admins ignoreres (defensiv vs
    # cookie-tampering). Hvis cookien peger på en ikke-eksisterende
    # tenant, falder vi tilbage til admin's egen tenant.
    if db_user.get("role") == "admin":
        try:
            override_raw = request.cookies.get("pax_admin_viewing_tenant")
            if override_raw:
                override_id = int(override_raw)
                if override_id != tenant["id"]:
                    from database import hent_tenant_by_id
                    override_tenant = hent_tenant_by_id(override_id)
                    if override_tenant:
                        print(
                            f"DEBUG: aktiv_tenant — admin '{db_user.get('email')}' "
                            f"har 'view as'-cookie sat til tenant {override_id} "
                            f"({override_tenant.get('slug')}); bruger den i "
                            f"stedet for admin's egen tenant {tenant['id']}"
                        )
                        tenant = override_tenant
        except (ValueError, TypeError) as _e:
            print(f"DEBUG: aktiv_tenant — ignorerer ugyldig view-as-cookie: {_e}")

    # ───── Sæt ContextVars for hele request-lifetimen ─────
    from database import saet_aktiv_tenant_id, reset_aktiv_tenant_id
    from selskab_profiler import saet_aktiv_profil, reset_aktiv_profil

    tok_id = saet_aktiv_tenant_id(tenant["id"])
    tok_pf = saet_aktiv_profil(tenant)

    # Gør tenant + user tilgængelig på request.state så endpoints kan
    # logge/læse uden at slå op igen.
    request.state.tenant = tenant
    request.state.user = {**user, "db_user": db_user}

    try:
        yield
    finally:
        reset_aktiv_tenant_id(tok_id)
        reset_aktiv_profil(tok_pf)


# ─────────── AUTH-AUDIT (Next.js rapporterer login/logout) ───────────
#
# Supabase Auth foregår direkte mellem browser og Supabase — vi har
# ikke server-side adgang til selve credentials-flowet. For at fange
# login/logout-events kalder Next.js disse endpoints lige efter
# Supabase har bekræftet handlingen. Endpoints validerer JWT'en via
# samme aktiv_tenant-dependency, så vi har user_id + tenant_id + IP
# automatisk.
#
# Hvis Next.js glemmer at kalde (eller netværket dropper), mister vi
# kun den ene audit-row — selve login fungerer stadig. Det er accepteret
# tab, fordi audit er supplerende dokumentation, ikke en sikkerheds-
# kontrol (sikkerheden ligger i Supabase Auth + JWT-validering).

@app.post("/api/auth/log-login")
async def log_login_event(request: Request, _=Depends(aktiv_tenant)):
    """Skriver login_success til gdpr_audit_log. Kaldes af Next.js
    umiddelbart efter Supabase Auth har returneret en gyldig session."""
    _audit_request(
        request,
        handling="login_success",
        sag_id=None,
        metadata={"klient": "next.js"},
    )
    return {"ok": True}


@app.post("/api/auth/log-logout")
async def log_logout_event(request: Request, _=Depends(aktiv_tenant)):
    """Skriver logout til gdpr_audit_log. Kaldes af Next.js FØR den
    rydder Supabase-sessionen (ellers fejler aktiv_tenant fordi der
    ikke er noget gyldigt JWT mere)."""
    _audit_request(
        request,
        handling="logout",
        sag_id=None,
        metadata={"klient": "next.js"},
    )
    return {"ok": True}


# ─────────── ADMIN: GDPR-AUDIT-LOG-VISNING ───────────
#
# Returnerer audit-log-rækker for revisor/compliance-fremvisning.
# Kun admin-brugere må kalde endpointet — håndhæves via aktiv_tenant
# (sikrer JWT) + ekstra role-check her. Filtrerer ALTID på admin'ens
# egen tenant (cross-tenant-adgang er ikke understøttet).

@app.get("/api/admin/audit-log")
async def admin_audit_log(
    request: Request,
    handling: str = "",
    user_id: int = 0,
    sag_id: str = "",
    limit: int = 200,
    _=Depends(aktiv_tenant),
):
    """Returnerer seneste audit-log-rækker for caller's egen tenant.

    Query-params:
        handling: filtrer på handling-type (eks. 'login_success', 'eksport')
        user_id: filtrer på specifik bruger
        sag_id: filtrer på specifik sag/dokument
        limit: maks antal rækker (default 200, max 2000)

    Kun caller med role='admin' får adgang. Andre roller får 403.
    """
    user = getattr(request.state, "user", None) or {}
    db_user = user.get("db_user") if isinstance(user, dict) else None
    if not db_user or db_user.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Adgang nægtet — kun administratorer kan hente audit-log.",
        )

    tenant = getattr(request.state, "tenant", None) or {}
    tenant_id = tenant.get("id") if isinstance(tenant, dict) else None
    if not tenant_id:
        raise HTTPException(status_code=500, detail="Tenant-context mangler")

    from database import hent_gdpr_audit_log

    limit = max(1, min(int(limit or 200), 2000))
    rows = hent_gdpr_audit_log(
        tenant_id=tenant_id,
        handling=handling or None,
        user_id=int(user_id) if user_id else None,
        sag_id=sag_id or None,
        limit=limit,
    )
    return {"rows": rows, "antal": len(rows)}


@app.get("/api/health")
def health():
    """
    Sundhedstjek. Verificerer at FastAPI kører OG at den faktisk
    kan importere de eksisterende AI-moduler — så vi tidligt fanger
    path- eller dependency-problemer.
    """
    moduler_status = {}
    for navn in ["ai_engine", "embeddings", "processor", "anonymisering_pdf",
                 "database", "selskab_profiler"]:
        try:
            __import__(navn)
            moduler_status[navn] = "ok"
        except Exception as e:
            moduler_status[navn] = f"FEJL: {type(e).__name__}: {e}"

    alle_ok = all(v == "ok" for v in moduler_status.values())
    return {
        "ok": alle_ok,
        "service": "juriitech-pax-api",
        "version": "0.1.0",
        "python_path_root": _PARENT,
        "moduler": moduler_status,
    }


def _probe_anthropic_access() -> tuple[bool, str | None]:
    """
    Verificerer at Anthropic-API'en er tilgængelig før vi starter den
    dyre 30-90-sekunders pipeline. Sender et minimalt 1-token kald
    (~1 sek, koster næsten ingen tokens). Hvis credits er løbet tør,
    API-nøglen er ugyldig, eller vi er rate-limit'ed, fejler probe'n
    ØJEBLIKKELIGT så brugeren får besked på sekunder i stedet for at
    vente på en pipeline der alligevel ender i fejl efter 5 minutter
    (med retries).

    Returnerer (ok, brugervenlig fejlbesked).
    """
    try:
        import anthropic
    except ImportError:
        return True, None  # Ikke installeret = ingen probe (lad pipelinen prøve)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return False, (
            "ANTHROPIC_API_KEY er ikke sat på serveren. "
            "Kontakt administrator."
        )

    try:
        # Vi bruger samme model som pipelinen, så probe'n verificerer
        # adgang til den specifikke model. max_tokens=1 holder kaldet
        # billigt (~1 sekund, < 0.01 cent).
        from ai_engine import MODEL as _PIPELINE_MODEL
        client = anthropic.Anthropic(api_key=api_key)
        client.messages.create(
            model=_PIPELINE_MODEL,
            max_tokens=1,
            messages=[{"role": "user", "content": "ping"}],
        )
        return True, None
    except Exception as e:
        # Anthropic-SDK'ens exceptions har sigende navne — vi matcher på
        # type og besked-substring så vi giver brugeren konkrete next steps.
        msg = str(e).lower()
        cls = type(e).__name__

        if "credit" in msg or "balance" in msg or "billing" in msg:
            return False, (
                "Anthropic-credits er løbet tør. "
                "Tjek balancen på console.anthropic.com/settings/billing "
                "og top op før du prøver igen."
            )
        if cls == "AuthenticationError" or "authentication" in msg or "api key" in msg:
            return False, (
                "Anthropic API-nøglen er ugyldig eller udløbet. "
                "Kontakt administrator."
            )
        if cls == "RateLimitError" or "rate limit" in msg or "429" in msg:
            return False, (
                "Anthropic API er midlertidigt overbelastet (rate limit). "
                "Vent 1-2 minutter og prøv igen."
            )
        if cls == "PermissionDeniedError" or "permission" in msg:
            return False, (
                "Anthropic API afviser kaldet (permission denied). "
                "Tjek at API-nøglen har adgang til de modeller vi bruger."
            )
        # Ukendt fejl — lad pipelinen prøve, men log
        print(f"DEBUG: Anthropic probe fejlede ({cls}: {e}) — fortsætter alligevel")
        return True, None


async def _laes_uploads_med_zip_udpakning(filer: List[UploadFile]):
    """
    Læser uploads til (filnavn, bytes)-tupler og pakker zip-filer ud
    inline. Returnerer en flad liste — kalderen ser ingen forskel på
    om en fil kom direkte fra brugeren eller fra en zip.

    Bruger samme udpak_zip_til_filer-funktion som Streamlit-PAX, så
    udpaknings-adfærden er bit-præcist ens (springer __MACOSX, skjulte
    filer og mapper over).
    """
    from processor import udpak_zip_til_filer  # lazy import

    flad_liste = []  # liste af (filnavn, bytes)
    zip_fejl = []  # list[(filnavn, fejlbesked)] — alle zip-fejl samles
    for fil in filer:
        navn = fil.filename or "ukendt"
        data = await fil.read()
        if navn.lower().endswith(".zip"):
            udpakket, fejl = udpak_zip_til_filer(data)
            if fejl:
                zip_fejl.append((navn, fejl))
            for u_navn, u_data in udpakket:
                flad_liste.append((u_navn, u_data))
        else:
            flad_liste.append((navn, data))

    # Hvis nogen zip-fil fejlede helt (typisk pga. password/AES), så
    # afvis hele uploaden — for et juridisk værktøj er det farligere at
    # arbejde videre på en delvis sag end at bede brugeren udpakke
    # manuelt. Brugeren får en præcis besked med konkret handling.
    if zip_fejl:
        if len(zip_fejl) == 1:
            navn, fejl = zip_fejl[0]
            besked = f'"{navn}": {fejl}'
        else:
            linjer = [f'• "{n}": {f}' for n, f in zip_fejl]
            besked = "Flere zip-filer kunne ikke åbnes:\n" + "\n".join(linjer)
        raise HTTPException(status_code=422, detail=besked)

    return flad_liste


@app.post("/api/parse-fil")
async def parse_fil(
    request: Request,
    filer: List[UploadFile] = File(...),
    _=Depends(aktiv_tenant),
):
    """
    Tager én eller flere uploadede filer og returnerer struktureret
    parse-resultat per fil. Bruger eksisterende
    processor._laes_fra_bytes — samme funktion som Streamlit-PAX bruger
    bag scenen, så parse-output er bit-præcist det samme.

    Bytes i resultatet sendes IKKE tilbage i JSON (de kan være store).
    Vi returnerer kun:
      - filnavn, type, rolle, media_type, evt. aarsag
      - antal_bytes (størrelse-info så frontend kan vise)
      - tekst_uddrag (første 500 tegn til preview)
      - tekst_total_laengde (total antal tegn udtrukket)
    """
    from processor import _laes_fra_bytes  # lazy import for testbarhed

    flade_filer = await _laes_uploads_med_zip_udpakning(filer)

    resultater = []
    for navn, data in flade_filer:
        result = _laes_fra_bytes(navn, data)
        tekst = result.get("tekst") or ""
        resultater.append({
            "filnavn": result.get("filnavn"),
            "type": result.get("type"),
            "rolle": result.get("rolle"),
            "media_type": result.get("media_type"),
            "aarsag": result.get("aarsag"),
            "antal_bytes": len(data),
            "tekst_total_laengde": len(tekst),
            "tekst_uddrag": tekst[:500],
        })

    # GDPR audit: registrer uploadet (filnavne + bytes — IKKE indhold).
    # Bruges til art. 30 "hvilke persondata er indkommet hvornår".
    _audit_request(
        request,
        handling="upload",
        sag_id=(resultater[0].get("filnavn") if resultater else None),
        metadata={
            "antal_filer": len(resultater),
            "filnavne": [r.get("filnavn") for r in resultater][:20],
            "total_bytes": sum(r.get("antal_bytes") or 0 for r in resultater),
        },
    )

    return {"filer": resultater, "antal": len(resultater)}


@app.post("/api/foerstevurdering")
async def foerstevurdering(
    request: Request,
    filer: List[UploadFile] = File(...),
    sagsakter: str = Form(""),
    _=Depends(aktiv_tenant),
):
    """
    Orkestrerer hele førstevurderings-flowet ved at kalde de eksisterende
    Python-funktioner uændret:

      1. processor._laes_fra_bytes — parse uploadede filer
      2. ai_engine.udled_alle_klagepunkter — verificeret klagepunkt-liste
      3. ai_engine.udled_tidsforhold — reklamationsrettidighed
      4. ai_engine.udled_foerstevurdering_struktureret — 6-sektion JSON-analyse
         (returnerer også relevante tidligere afgørelser via RAG)

    Returnerer alt i én JSON. Tager 30-90 sekunder pga. AI-kald +
    embedding-opslag i 500+ sager. Kalder mod prod-Supabase READ-ONLY
    (vidensbanken). Bruger Anthropic-credits.

    Bytes i sag-filerne sendes IKKE tilbage i JSON (kun metadata).
    """
    from processor import _laes_fra_bytes
    from ai_engine import (
        udled_alle_klagepunkter,
        udled_tidsforhold,
        udled_foerstevurdering_struktureret,
    )

    # ---------- 0. Anthropic-probe (fail-fast) ----------
    # Verificer at AI-API'en er tilgængelig FØR vi bruger 60-90 sekunder
    # på den fulde pipeline. Hvis credits er væk eller nøglen er
    # ugyldig, får brugeren besked på ~1 sekund i stedet for ~5 minutter
    # (frontend retry'er 5xx tre gange med eksponentielt backoff).
    ok, fejl = _probe_anthropic_access()
    if not ok:
        raise HTTPException(status_code=422, detail=fejl or "AI ikke tilgængelig")

    # ---------- 1. Parse files ----------
    flade_filer = await _laes_uploads_med_zip_udpakning(filer)
    parsed_filer = [_laes_fra_bytes(navn, data) for navn, data in flade_filer]
    sag = {"filer": parsed_filer}

    # Saml liste over filer der ikke kunne læses — sendes med tilbage så
    # frontenden kan vise en neutral info-besked. Analysen fortsætter
    # uændret med de øvrige filer (processor markerer ulæselige som
    # type="fil_ikke_laest"; ai_engine springer dem over).
    ulaeselige_filer = [
        {
            "filnavn": f.get("filnavn") or "(ukendt fil)",
            "aarsag": f.get("aarsag") or "Filen kunne ikke læses",
        }
        for f in parsed_filer
        if f.get("type") == "fil_ikke_laest"
    ]

    # ---------- 2. Verified klagepunkter ----------
    try:
        klagepunkter = udled_alle_klagepunkter(
            sag=sag,
            sagsakter_tekst=sagsakter,
        ) or []
    except Exception as e:
        _raise_503_hvis_overload(e)
        raise HTTPException(
            status_code=500,
            detail=f"udled_alle_klagepunkter fejlede: {e}",
        )

    # ---------- 3. Tidsforhold (reklamationsrettidighed) ----------
    try:
        tidsforhold = udled_tidsforhold(
            sag=sag,
            sagsakter_tekst=sagsakter,
        ) or {}
    except Exception as e:
        _raise_503_hvis_overload(e)
        print(f"DEBUG: udled_tidsforhold fejlede ({e}) — fortsætter uden")
        tidsforhold = {}

    # Berig tidsforhold med antal nætter beregnet fra rejseperiode-strengen
    # — så frontend kan vise "Rejseperiode: ... (14 nætter)" uden at
    # implementere dato-parsing i TypeScript. Streamlit-PAX gør det samme.
    try:
        from ai_engine import _beregn_antal_naetter as _bn
        rp = (tidsforhold or {}).get("rejseperiode") or ""
        if rp:
            n = _bn(rp)
            if n and n >= 1:
                tidsforhold["antal_naetter"] = n
    except Exception as e:
        print(f"DEBUG: antal_naetter-beregning fejlede ({e}) — springer over")

    # ---------- 4. Byg facit-blokke ----------
    klagepunkter_facit = ""
    if klagepunkter:
        klagepunkter_facit = (
            "VERIFICERET LISTE OVER ALLE KLAGEPUNKTER (udtrukket separat):\n"
            + "".join(f"  {i + 1}. {kp}\n" for i, kp in enumerate(klagepunkter))
            + f"\nTotal: {len(klagepunkter)} klagepunkter.\n\n"
        )

    tidsforhold_facit = ""
    if (
        tidsforhold
        and tidsforhold.get("har_problematisk_forsinkelse")
        and not tidsforhold.get("kunne_ikke_udledes")
    ):
        tidsforhold_facit = (
            "VERIFICERET TIDSFORHOLD — REKLAMATIONSRETTIDIGHED:\n"
            + (
                f"  Samlet: {tidsforhold.get('samlet_vurdering', '')}\n\n"
                if tidsforhold.get("samlet_vurdering")
                else ""
            )
            + "".join(
                f"  • {obs}\n"
                for obs in (tidsforhold.get("konkrete_observationer") or [])
            )
        )

    # ---------- 5. Hovedanalyse ----------
    try:
        analyse_dict, rel_sager = udled_foerstevurdering_struktureret(
            sag=sag,
            sagsakter=sagsakter,
            sagsakter_filer=[],
            klagepunkter_facit=klagepunkter_facit,
            tidsforhold_facit=tidsforhold_facit,
            klagepunkter_liste=klagepunkter,
        )
    except Exception as e:
        _raise_503_hvis_overload(e)
        raise HTTPException(
            status_code=500,
            detail=f"udled_foerstevurdering_struktureret fejlede: {e}",
        )

    if analyse_dict is None:
        # 422 (ikke 5xx) — så frontend ikke retry'er det samme i 5 minutter.
        # Probe'n øverst har allerede verificeret at API'en er nåelig, så
        # når vi havner her er det enten tool-use parse-fejl, max-tokens
        # afkortet uden continuation, eller en mid-pipeline credits-
        # exhaustion. Alle tre er deterministiske — retry hjælper ikke.
        raise HTTPException(
            status_code=422,
            detail=(
                "AI returnerede tomt svar på analysen. "
                "Det skyldes typisk en af disse: (1) Anthropic-credits "
                "løb tør under analysen — tjek "
                "console.anthropic.com/settings/billing. "
                "(2) Sagen er for stor for én AI-omgang — prøv at fjerne "
                "store irrelevante bilag (videoer, store billeder) eller "
                "split sagen op. (3) En transient parsefejl — prøv igen "
                "om et minut."
            ),
        )

    # ---------- 6. Strip bytes/embedding fra rel_sager til JSON ----------
    #
    # Relevans-filtrering: i stedet for ALTID at vise 5 sager bruger vi
    # rerank-scoren til at vise 2-5 — afhængigt af hvor mange der reelt
    # matcher godt. Voyage rerank-2 scorer 0-1 hvor højere = bedre.
    #
    # Threshold = 0.30: konservativt valg. Under det er matches typisk
    # svage og forvirrer mere end de hjælper. Hvis kun 0-1 sager er over
    # tærsklen, viser vi alligevel min 2 (så brugeren har sammenligning)
    # og markerer match_kvalitet="begrænset" så UI'en kan vise advarsel.
    RELEVANS_TAERSKEL = 0.30
    MIN_VISTE_SAGER = 2
    MAX_VISTE_SAGER = 5

    def _strip_bytes(s):
        return {
            k: v
            for k, v in s.items()
            if k not in ("embedding", "fil_bytes")
            and not isinstance(v, bytes)
        }

    # rel_sager er en kombineret liste af afgørelser (først) + vilkår +
    # lovgivning. Filter til kun afgørelser — det er det brugeren ser som
    # "tidligere kendelser". Vilkår/lov er allerede brugt af AI'en i
    # vidensbanken, men hører ikke hjemme i sagskort-listen.
    afgoerelser_only = [
        s for s in (rel_sager or [])
        if (s.get("dokumenttype") or "").lower() == "afgoerelse"
    ]

    # Sortér efter similarity desc (skal allerede være sorteret fra
    # rerank, men double-check så vi ikke afhænger af kald-ordning)
    afgoerelser_only.sort(
        key=lambda s: float(s.get("similarity") or 0.0), reverse=True,
    )

    stærke_matches = [
        s for s in afgoerelser_only
        if float(s.get("similarity") or 0.0) >= RELEVANS_TAERSKEL
    ]

    if len(stærke_matches) >= MIN_VISTE_SAGER:
        # Mindst MIN_VISTE_SAGER stærke matches — vis op til MAX_VISTE_SAGER
        valgte = stærke_matches[:MAX_VISTE_SAGER]
        match_kvalitet = "god"
    else:
        # 0-1 stærke matches: vis alligevel top MIN_VISTE_SAGER (eller
        # færre hvis der bare ikke er flere afgørelser overhovedet), men
        # markér at match-kvaliteten er begrænset
        valgte = afgoerelser_only[:MIN_VISTE_SAGER]
        match_kvalitet = "begrænset" if valgte else "ingen"

    rel_sager_clean = [_strip_bytes(s) for s in valgte]

    # Log til SLA-overvågning: hvor ofte rammer vi "begrænset"-state?
    top_score = (
        float(afgoerelser_only[0].get("similarity") or 0.0)
        if afgoerelser_only else 0.0
    )
    print(
        f"DEBUG: RAG-filter — match_kvalitet={match_kvalitet}, "
        f"top_score={top_score:.3f}, "
        f"vist={len(rel_sager_clean)}, "
        f"tærskel={RELEVANS_TAERSKEL}"
    )

    # ---------- 7. Match-metadata til visningskort ----------
    # opsummer_matches_til_visning er et separat AI-kald der pr. sag
    # producerer struktureret metadata (sagsnummer, udfald, klagers krav,
    # tilkendt beløb, match-begrundelser). Streamlit-PAX bruger det til
    # de visuelle sagskort.
    match_info = []
    if rel_sager_clean:
        try:
            from ai_engine import (
                opsummer_matches_til_visning,
                par_filtrer_relevante_og_matches,
            )
            match_info = opsummer_matches_til_visning(
                uploadet_sag=sag,
                relevante_sager=rel_sager_clean,
            ) or []
            # Drop sager hvor udfaldet ikke kunne udledes (de tilbyder
            # ingen prejudikatværdi til juristen) og cap til top 3.
            # rel_sager_clean og match_info filtreres parallelt så
            # frontend-pairingen [i] forbliver konsistent.
            rel_sager_clean, match_info = par_filtrer_relevante_og_matches(
                rel_sager_clean, match_info, max_n=3,
            )
        except Exception as e:
            print(f"DEBUG: opsummer_matches_til_visning fejlede ({e}) — fortsætter uden")
            match_info = []

    # ---------- 8. Struktureret sagsresumé ----------
    # Driver den 2-kolonne "Resumé"-pillar i UI'et: emne + klagepunkter
    # + klagers krav + selskabets håndtering + forventet udfald. Bygger
    # ovenpå den allerede genererede analyse, så det er hurtigt.
    sagsresume = None
    try:
        from ai_engine import udled_sagsresume_strukturelt
        # Saml analyse-tekst som funktionen forventer (markdown af alle
        # sektioner). Vi kan rekonstruere det fra analyse_dict.
        analyse_tekst_dele = []
        for nøgle, label in [
            ("klagens_kernepunkter", "Klagens kernepunkter"),
            ("yderligere_klagepunkter_og_detaljer", "Yderligere klagepunkter"),
            ("rejseselskabets_stillingtagen_indtil_nu", "Rejseselskabets stillingtagen indtil nu"),
            ("kort_juridisk_vurdering", "Kort juridisk vurdering"),
            ("konklusion_en_linje", "Konklusion"),
        ]:
            v = analyse_dict.get(nøgle)
            if not v:
                continue
            if isinstance(v, list):
                analyse_tekst_dele.append(f"## {label}\n" + "\n".join(f"- {p}" for p in v))
            else:
                analyse_tekst_dele.append(f"## {label}\n{v}")
        analyse_tekst = "\n\n".join(analyse_tekst_dele)
        if analyse_tekst:
            sagsresume = udled_sagsresume_strukturelt(
                analyse_tekst=analyse_tekst,
                sagsakter_tekst=sagsakter,
                tidsforhold=tidsforhold,
            )
    except Exception as e:
        print(f"DEBUG: udled_sagsresume_strukturelt fejlede ({e}) — fortsætter uden")
        sagsresume = None

    # ---------- 9. Paragraf-hallucinations-check ----------
    # Saml AI-genereret tekst og scan for pakkerejselov-§-citationer der
    # ikke findes i den faktiske lov. Returneres i payload — kun admin
    # ser advarslen i UI'et (frontend filtrerer). Fail open: hvis listen
    # ikke kan bygges, springes valideringen over.
    paragraf_advarsler = []
    try:
        from ai_engine import valider_paragraf_citationer
        analyse_tekst_for_check = " ".join(
            [
                str(analyse_dict.get(k, ""))
                if not isinstance(analyse_dict.get(k), list)
                else " ".join(analyse_dict.get(k, []))
                for k in (
                    "klagens_kernepunkter",
                    "yderligere_klagepunkter_og_detaljer",
                    "rejseselskabets_stillingtagen_indtil_nu",
                    "kort_juridisk_vurdering",
                    "konklusion_en_linje",
                )
            ]
        )
        paragraf_advarsler = valider_paragraf_citationer(
            analyse_tekst_for_check
        ) or []
        if paragraf_advarsler:
            print(
                f"WARN: Førstevurdering citerer ugyldige pakkerejselov-"
                f"paragraffer: {paragraf_advarsler}"
            )
    except Exception as e:
        print(f"DEBUG: paragraf-validering fejlede ({e}) — fortsætter uden")
        paragraf_advarsler = []

    # GDPR audit: analyse er den primære persondata-behandling.
    # Metadata bevidst MINIMAL — vi gemmer ikke selve analyse-teksten,
    # kun aggregater (antal/længde) der kan forsvare retention-bevisbyrden.
    _audit_request(
        request,
        handling="analyse",
        sag_id=(parsed_filer[0].get("filnavn") if parsed_filer else None),
        metadata={
            "antal_filer": len(parsed_filer),
            "antal_klagepunkter": len(klagepunkter),
            "antal_relevante_sager": len(rel_sager_clean),
            "har_sagsakter": bool(sagsakter and sagsakter.strip()),
        },
    )

    # ---------- Forudsigelses-feedback-løkke (bagvedliggende) ----------
    # FIRE-AND-FORGET: gem PAX' forudsigelse så vi senere kan måle hvor
    # præcist den ramte den faktiske nævnsafgørelse. Helt usynligt for
    # brugeren. Pakket i try/except + log_forudsigelse er selv fail-safe,
    # så dette trin kan ALDRIG blokere eller fejle analysen.
    try:
        from ai_engine import _regex_find_sagsnummer
        from database import log_forudsigelse, hent_aktiv_tenant_id
        _sagsnr = _regex_find_sagsnummer(sag, sagsakter or "")
        log_forudsigelse(
            sagsnummer=_sagsnr,
            tenant_id=hent_aktiv_tenant_id(),
            sandsynlighedsvurdering=analyse_dict.get("sandsynlighedsvurdering"),
            konklusion=analyse_dict.get("konklusion_en_linje"),
        )
    except Exception as _fe:
        print(f"DEBUG: forudsigelses-capture sprang over ({_fe})")

    return {
        "klagepunkter": klagepunkter,
        "tidsforhold": tidsforhold,
        "analyse": analyse_dict,
        "relevante_sager": rel_sager_clean,
        "match_info": match_info,
        "match_kvalitet": match_kvalitet,
        "sagsresume": sagsresume,
        "ulaeselige_filer": ulaeselige_filer,
        "paragraf_advarsler": paragraf_advarsler,
        "metadata": {
            "antal_filer": len(parsed_filer),
            "antal_klagepunkter": len(klagepunkter),
            "antal_relevante_sager": len(rel_sager_clean),
            "antal_ulaeselige": len(ulaeselige_filer),
            "antal_paragraf_advarsler": len(paragraf_advarsler),
        },
    }


@app.post("/api/sagsmetadata")
async def sagsmetadata(
    filer: List[UploadFile] = File(...),
    sagsakter: str = Form(""),
    _=Depends(aktiv_tenant),
):
    """
    Auto-udtræk af sagsnummer + klagers fulde navn fra uploadede filer.
    Bruges til at præ-udfylde Brevhoved-felterne i svarbrev-formularen.

    Lille hurtigt AI-kald (~5-10 sek). Frontenden kan cache resultatet
    pr. sag-signatur så vi kun kalder én gang.
    """
    from processor import _laes_fra_bytes
    from ai_engine import udled_sagsmetadata

    flade_filer = await _laes_uploads_med_zip_udpakning(filer)
    parsed_filer = [_laes_fra_bytes(navn, data) for navn, data in flade_filer]
    sag = {"filer": parsed_filer}

    try:
        meta = udled_sagsmetadata(sag=sag, sagsakter_tekst=sagsakter) or {}
    except Exception as e:
        _raise_503_hvis_overload(e)
        print(f"DEBUG: udled_sagsmetadata fejlede: {e}")
        meta = {"sagsnummer": "", "klagers_navn": ""}

    return {
        "sagsnummer": meta.get("sagsnummer", ""),
        "klagers_navn": meta.get("klagers_navn", ""),
    }


@app.post("/api/svarbrev")
async def svarbrev(
    request: Request,
    filer: List[UploadFile] = File(...),
    sagsakter: str = Form(""),
    ekstra_instrukser_json: str = Form("[]"),
    inkluder_kildehenvisninger: bool = Form(False),
    verificerede_klagepunkter_json: str = Form("null"),
    tidsforhold_json: str = Form("null"),
    sagsnummer: str = Form(""),
    klagers_navn: str = Form(""),
    hoeringssvar_nr: int = Form(1),
    bilag_liste_json: str = Form("[]"),
    _=Depends(aktiv_tenant),
):
    """
    Genererer komplet udkast til svarbrev. Kalder eksisterende
    ai_engine.generer_svarbrev_til_sag uændret.

    Hvis verificerede_klagepunkter + tidsforhold sendes med (fra et
    tidligere /api/foerstevurdering-kald), genbruges de — det sparer
    2 AI-kald. Ellers udleder svarbrev-funktionen dem selv internt.

    Tager 30-60 sekunder pr. kald. Bruger Anthropic-credits.
    """
    import json

    from processor import _laes_fra_bytes
    from ai_engine import generer_svarbrev_til_sag

    # Anthropic-probe (fail-fast) — se /api/foerstevurdering for begrundelse
    ok, fejl = _probe_anthropic_access()
    if not ok:
        raise HTTPException(status_code=422, detail=fejl or "AI ikke tilgængelig")

    # ---------- Parse files ----------
    flade_filer = await _laes_uploads_med_zip_udpakning(filer)
    parsed_filer = [_laes_fra_bytes(navn, data) for navn, data in flade_filer]
    sag = {"filer": parsed_filer}

    # ---------- Decode JSON-Form-felter ----------
    try:
        ekstra_instrukser = json.loads(ekstra_instrukser_json) or []
        if not isinstance(ekstra_instrukser, list):
            ekstra_instrukser = []
    except Exception:
        ekstra_instrukser = []

    try:
        verificerede_klagepunkter = json.loads(verificerede_klagepunkter_json)
        if verificerede_klagepunkter and not isinstance(
            verificerede_klagepunkter, list
        ):
            verificerede_klagepunkter = None
    except Exception:
        verificerede_klagepunkter = None

    try:
        tidsforhold_dict = json.loads(tidsforhold_json)
        if tidsforhold_dict and not isinstance(tidsforhold_dict, dict):
            tidsforhold_dict = None
    except Exception:
        tidsforhold_dict = None

    # ---------- Byg ekstra_instrukser-tekst ----------
    instrukser_tekst = ""
    if ekstra_instrukser:
        instrukser_tekst = "\n".join(
            f"- {instr}" for instr in ekstra_instrukser if instr
        )

    # ---------- Generer svarbrev ----------
    try:
        svarbrev_tekst = generer_svarbrev_til_sag(
            sag=sag,
            sagsakter=sagsakter,
            ekstra_instrukser=instrukser_tekst or None,
            inkluder_kildehenvisninger=inkluder_kildehenvisninger,
            verificerede_klagepunkter=verificerede_klagepunkter,
            tidsforhold=tidsforhold_dict,
        )
    except Exception as e:
        _raise_503_hvis_overload(e)
        raise HTTPException(
            status_code=500,
            detail=f"generer_svarbrev_til_sag fejlede: {e}",
        )

    if not svarbrev_tekst or not svarbrev_tekst.strip():
        raise HTTPException(
            status_code=422,
            detail=(
                "AI returnerede tomt svarbrev. "
                "Tjek om Anthropic-credits er løbet tør på "
                "console.anthropic.com/settings/billing, eller prøv at "
                "fjerne store bilag og generere igen."
            ),
        )

    # ---------- Generer DOCX med brevhoved + bilag-liste ----------
    # Streamlit-PAX bruger svarbrev_til_docx der bygger en pæn brev-
    # opsætning med selskabs-logo, by/dato, "Vedr."-linje og bilag-
    # oversigt nederst. Returneres som base64 så frontenden kan tilbyde
    # download direkte uden et separat API-kald.
    import base64
    docx_b64 = ""
    docx_fejl = None
    try:
        bilag_liste = json.loads(bilag_liste_json) or []
        if not isinstance(bilag_liste, list):
            bilag_liste = []
    except Exception:
        bilag_liste = []

    try:
        from eksport import svarbrev_til_docx
        klage_filnavn = None
        for f in parsed_filer:
            if f.get("rolle") == "klageskema":
                klage_filnavn = f.get("filnavn")
                if klage_filnavn:
                    break
        if not klage_filnavn and parsed_filer:
            klage_filnavn = parsed_filer[0].get("filnavn")

        docx_bytes = svarbrev_til_docx(
            svarbrev=svarbrev_tekst,
            klage_filnavn=klage_filnavn or "svarbrev.pdf",
            sagsnummer=sagsnummer.strip(),
            klagers_navn=klagers_navn.strip(),
            hoeringssvar_nr=hoeringssvar_nr if hoeringssvar_nr in (1, 2, 3) else 1,
            bilag_liste=bilag_liste,
        )
        docx_b64 = base64.b64encode(docx_bytes).decode("ascii")
    except Exception as e:
        print(f"DEBUG: svarbrev_til_docx fejlede ({e}) — returnerer kun markdown")
        docx_fejl = str(e)

    # Hallucinations-check: scan svarbrev-teksten for §-citationer der
    # ikke findes i pakkerejseloven. Vises kun for admin i UI'et.
    paragraf_advarsler = []
    try:
        from ai_engine import valider_paragraf_citationer
        paragraf_advarsler = valider_paragraf_citationer(svarbrev_tekst) or []
        if paragraf_advarsler:
            print(
                f"WARN: Svarbrev citerer ugyldige pakkerejselov-paragraffer: "
                f"{paragraf_advarsler}"
            )
    except Exception as e:
        print(f"DEBUG: svarbrev paragraf-validering fejlede ({e})")

    # GDPR audit: svarbrev = juridisk vurdering + eksport i én operation
    _audit_request(
        request,
        handling="eksport",
        sag_id=sagsnummer.strip() or (parsed_filer[0].get("filnavn") if parsed_filer else None),
        metadata={
            "type": "svarbrev",
            "antal_filer": len(parsed_filer),
            "antal_bilag": len(bilag_liste),
            "hoeringssvar_nr": hoeringssvar_nr,
            "har_klagers_navn": bool(klagers_navn.strip()),
            "tegn": len(svarbrev_tekst),
        },
    )

    return {
        "svarbrev": svarbrev_tekst,
        "docx_base64": docx_b64,
        "docx_fejl": docx_fejl,
        "paragraf_advarsler": paragraf_advarsler,
        "metadata": {
            "antal_filer": len(parsed_filer),
            "antal_instrukser": len(ekstra_instrukser),
            "inkluder_kildehenvisninger": inkluder_kildehenvisninger,
            "sagsnummer": sagsnummer.strip(),
            "klagers_navn": klagers_navn.strip(),
            "hoeringssvar_nr": hoeringssvar_nr,
            "antal_bilag": len(bilag_liste),
            "tegn": len(svarbrev_tekst),
            "antal_paragraf_advarsler": len(paragraf_advarsler),
        },
    }


@app.post("/api/anonymiser")
async def anonymiser(
    request: Request,
    filer: List[UploadFile] = File(...),
    klager_navne_json: str = Form("[]"),
    _=Depends(aktiv_tenant),
):
    """
    Anonymisering af bilag — understøtter PDF (ægte sort-bjælke-redaction)
    og DOCX (tekst-erstatning med █-blokke). Router pr. fil-extension.

    Regler (defineret i Python-modulet):
      - Klagers navne (i klager_navne_json) bevares fuldt
      - Andre fornavne beholdes, efternavne sorbjælkes
      - Email: lokal del sorbjælkes, domæne bevares
      - Telefon: områdekode bevares, resten sorbjælkes
      - CPR: fuldt sorbjælkes
      - Adresse: gade+husnr sorbjælkes, postnr+by bevares

    Returnerer per fil:
      - status: 'ok' | 'scannet' | 'fejl_aaben' | 'fejl_redaktion'
                | 'ikke_understoettet' | 'exception'
      - anonymiseret_pdf_base64: base64-encoded redacted output (kun ved 'ok')
        — feltnavnet er historisk; indholdet kan også være DOCX-bytes
      - output_extension: 'pdf' | 'docx' (kun ved 'ok')
      - bemaerkning: forklarende tekst

    Bytes base64-encodes så de kan transporteres i JSON.
    """
    import base64
    import json

    from anonymisering_pdf import anonymiser_pdf_fil
    from anonymisering_docx import anonymiser_docx_fil

    try:
        klager_navne = json.loads(klager_navne_json) or []
        if not isinstance(klager_navne, list):
            klager_navne = []
    except Exception:
        klager_navne = []

    flade_filer = await _laes_uploads_med_zip_udpakning(filer)

    resultater = []
    for filnavn, data in flade_filer:
        navn_lower = filnavn.lower()
        if navn_lower.endswith(".pdf"):
            anonymiser_fn = anonymiser_pdf_fil
            output_ext = "pdf"
            format_label = "PDF"
        elif navn_lower.endswith(".docx"):
            anonymiser_fn = anonymiser_docx_fil
            output_ext = "docx"
            format_label = "DOCX"
        else:
            resultater.append({
                "filnavn": filnavn,
                "status": "ikke_understoettet",
                "anonymiseret_pdf_base64": None,
                "output_extension": None,
                "antal_bytes_input": len(data),
                "antal_bytes_output": 0,
                "bemaerkning": (
                    "Kun PDF og DOCX understøttes af automatisk anonymisering"
                ),
            })
            continue

        try:
            output_bytes, status = anonymiser_fn(data, klager_navne)
        except Exception as e:
            resultater.append({
                "filnavn": filnavn,
                "status": "exception",
                "anonymiseret_pdf_base64": None,
                "output_extension": None,
                "antal_bytes_input": len(data),
                "antal_bytes_output": 0,
                "bemaerkning": f"{type(e).__name__}: {e}",
            })
            continue

        bemaerkning_map = {
            "ok": (
                "Sort-bjælke-anonymiseret PDF med bevaret layout"
                if output_ext == "pdf"
                else "Anonymiseret DOCX — følsom tekst erstattet med █-blokke"
            ),
            "scannet": "Scannet PDF (intet tekst-lag) — sort-bjælke ikke muligt",
            "fejl_aaben": f"{format_label} kunne ikke åbnes",
            "fejl_redaktion": "Redaction fejlede internt",
        }

        resultater.append({
            "filnavn": filnavn,
            "status": status,
            "anonymiseret_pdf_base64": (
                base64.b64encode(output_bytes).decode("ascii")
                if output_bytes and status == "ok"
                else None
            ),
            "output_extension": output_ext if status == "ok" else None,
            "antal_bytes_input": len(data),
            "antal_bytes_output": len(output_bytes) if output_bytes else 0,
            "bemaerkning": bemaerkning_map.get(status, status),
        })

    antal_ok = sum(1 for r in resultater if r["status"] == "ok")

    # GDPR audit: bilag anonymiseret er en KEY persondata-handling
    # (data minimisation art. 5.1.c — vi reducerer PII inden vi viser/sender)
    _audit_request(
        request,
        handling="anonymisering",
        sag_id=(resultater[0].get("filnavn") if resultater else None),
        metadata={
            "antal_input": len(filer),
            "antal_anonymiseret_ok": antal_ok,
            "filnavne": [r.get("filnavn") for r in resultater][:20],
        },
    )

    return {
        "filer": resultater,
        "metadata": {
            "antal_input": len(filer),
            "antal_anonymiseret_ok": antal_ok,
            "klager_navne": klager_navne,
        },
    }


@app.post("/api/tjekliste")
async def tjekliste(
    request: Request,
    filer: List[UploadFile] = File(...),
    _=Depends(aktiv_tenant),
):
    """
    Genererer struktureret tjekliste over hvad Nævnet har bedt om i
    høringsbrevet, og hvad der er dækket/ikke dækket af de uploadede
    bilag. Kalder eksisterende ai_engine.generer_tjekliste uændret.

    Returnerer markdown-tekst som typisk indeholder:
      - Liste af ønskede oplysninger
      - Status per punkt (✓ dækket / ✗ mangler)
      - Konkrete bilag der dækker hvert punkt

    Tager ~30 sek. Bruger Anthropic-credits.
    """
    from processor import _laes_fra_bytes
    from ai_engine import generer_tjekliste

    # Anthropic-probe (fail-fast) — se /api/foerstevurdering for begrundelse
    ok, fejl = _probe_anthropic_access()
    if not ok:
        raise HTTPException(status_code=422, detail=fejl or "AI ikke tilgængelig")

    flade_filer = await _laes_uploads_med_zip_udpakning(filer)
    parsed_filer = [_laes_fra_bytes(navn, data) for navn, data in flade_filer]
    sag = {"filer": parsed_filer}

    try:
        tjekliste_md = generer_tjekliste(sag=sag)
    except Exception as e:
        _raise_503_hvis_overload(e)
        raise HTTPException(
            status_code=500,
            detail=f"generer_tjekliste fejlede: {e}",
        )

    if not tjekliste_md or not tjekliste_md.strip():
        raise HTTPException(
            status_code=422,
            detail=(
                "AI returnerede tom tjekliste. "
                "Tjek om Anthropic-credits er løbet tør på "
                "console.anthropic.com/settings/billing, eller prøv igen."
            ),
        )

    _audit_request(
        request,
        handling="analyse",
        sag_id=(parsed_filer[0].get("filnavn") if parsed_filer else None),
        metadata={
            "type": "tjekliste",
            "antal_filer": len(parsed_filer),
            "tegn": len(tjekliste_md),
        },
    )

    return {
        "tjekliste": tjekliste_md,
        "metadata": {
            "antal_filer": len(parsed_filer),
            "tegn": len(tjekliste_md),
        },
    }


# ─────────── DEBUG: AKTIV TENANT ───────────
# Til verificering at multi-tenant routing virker korrekt. Endpoint
# returnerer hvilken tenant requestet rammer — uvurderligt under
# debug af "hvorfor får denne bruger TUI-branded svarbreve"-bugs.
# Eksponeres KUN i ikke-prod (PAX_API_ENV != production). Skjules
# automatisk i produktion for ikke at lække tenant-eksistens-info.

@app.get("/api/_debug/aktiv-tenant")
async def debug_aktiv_tenant(
    request: Request,
    _=Depends(aktiv_tenant),
):
    """
    Returnerer den aktive tenant for den autentificerede bruger.
    Bruges af E2E-tests + manuel verificering. Returnerer 404 i prod.
    """
    env = os.getenv("PAX_API_ENV", "dev").lower()
    if env == "production":
        raise HTTPException(status_code=404, detail="Not found")

    tenant = getattr(request.state, "tenant", None) or {}
    user = getattr(request.state, "user", None) or {}

    # Slug er det vigtigste — det er nøglen vi router branding/AI på.
    # ID kommer med så test-scripts kan korrelere mod migration-output.
    return {
        "slug": tenant.get("slug"),
        "navn": tenant.get("navn"),
        "tenant_id": tenant.get("id"),
        "by": tenant.get("by"),
        "sagsbehandler": tenant.get("sagsbehandler"),
        "lov_navn": tenant.get("lov_navn"),
        "klageorgan_navn": tenant.get("klageorgan_navn"),
        "bruger_email": user.get("email"),
    }


# ─────────── ANALYSE-EKSPORT (DOCX / PDF) ───────────
# Streamlit-PAX lader brugeren downloade selve analysens tekst som
# Word eller PDF (separat fra svarbrevet). Pax-next havde tidligere
# kun "Kopiér"-knap. Dette endpoint genererer eksport-bytes via
# eksisterende eksport.markdown_til_*_bytes — samme rendering som
# Streamlit, så Word/PDF-output er bit-præcist det samme.

@app.post("/api/analyse-eksport")
async def analyse_eksport(
    request: Request,
    _=Depends(aktiv_tenant),
):
    """
    Tager analyse-markdown + format ("docx" eller "pdf") og returnerer
    eksport-fil som base64. Returner:
      - filnavn (suggested), mime, base64
    Frontenden bygger Blob og trigger download via samme mønster som
    anonymiseringssektion (base64TilBlob).

    Brug JSON body i stedet for multipart fordi vi ikke transporterer
    filer — kun markdown-tekst + metadata.
    """
    import base64
    import re as _re

    # Læs JSON-body manuelt (vi har ikke pydantic-model — det er en lille
    # request og vi vil ikke betale boilerplate-omkostningen).
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ugyldigt JSON: {e}")

    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body skal være et JSON-objekt")

    markdown = (body.get("markdown") or "").strip()
    fmt = (body.get("format") or "").strip().lower()
    sagsnr = (body.get("sagsnr") or "").strip()
    selskab = (body.get("selskab") or "").strip()

    if not markdown:
        raise HTTPException(status_code=400, detail="Felt 'markdown' mangler eller er tom")
    if fmt not in ("docx", "pdf"):
        raise HTTPException(
            status_code=400,
            detail="Felt 'format' skal være enten 'docx' eller 'pdf'",
        )

    # ───── Byg titel + undertitel ─────
    titel = "Førstevurdering"
    undertitel_dele = []
    if sagsnr:
        undertitel_dele.append(f"Sagsnummer: {sagsnr}")
    if selskab:
        undertitel_dele.append(selskab)
    # Tilføj dags dato — så eksporten kan tidsstemples i arkivet
    from datetime import date
    undertitel_dele.append(date.today().strftime("%d-%m-%Y"))
    undertitel = " · ".join(undertitel_dele)

    # ───── Generer bytes ─────
    try:
        if fmt == "docx":
            from eksport import markdown_til_docx_bytes
            data = markdown_til_docx_bytes(
                markdown, titel=titel, undertitel=undertitel,
            )
            mime = (
                "application/vnd.openxmlformats-"
                "officedocument.wordprocessingml.document"
            )
            ext = "docx"
        else:
            from eksport import markdown_til_pdf_bytes
            data = markdown_til_pdf_bytes(
                markdown, titel=titel, undertitel=undertitel,
            )
            mime = "application/pdf"
            ext = "pdf"
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Eksport fejlede: {type(e).__name__}: {e}",
        )

    # ───── Filnavn ─────
    # Slugger sagsnr — fjerner mellemrum og specialtegn så filnavnet er
    # cross-platform sikkert. Falder tilbage til "analyse" hvis tomt.
    if sagsnr:
        base = _re.sub(r"[^A-Za-z0-9_\-]+", "_", sagsnr).strip("_") or "analyse"
        filnavn = f"foerstevurdering_{base}.{ext}"
    else:
        filnavn = f"foerstevurdering.{ext}"

    _audit_request(
        request,
        handling="eksport",
        sag_id=sagsnr or None,
        metadata={
            "type": "analyse",
            "format": fmt,
            "antal_bytes": len(data),
            "antal_tegn_markdown": len(markdown),
        },
    )

    return {
        "filnavn": filnavn,
        "mime": mime,
        "base64": base64.b64encode(data).decode("ascii"),
        "metadata": {
            "format": fmt,
            "antal_bytes": len(data),
            "antal_tegn_markdown": len(markdown),
        },
    }
