"""
Authentication-lag til juriitech PAX.

Denne fil håndterer alt omkring login/logout og bro'en mellem Supabase
Auth (eksternt auth-system) og vores egen users-tabel (intern bruger-
data inkl. tenant_id og rolle).

═══════════════════════════════════════════════════════════════
ARKITEKTUR
═══════════════════════════════════════════════════════════════

Der er TO bruger-systemer i spil, og de skal være synkroniserede:

  1. Supabase Auth (externt) — håndterer email + password, JWT-tokens,
     password-reset-emails, magic-links, email-verifikation. Ingen
     forretningsdata.

  2. Vores users-tabel (Neon Postgres) — kobler Supabase-user til
     tenant_id (TUI/Spies/Apollo) + role (admin/jurist) + business
     metadata. Ingen credentials.

Bro'en: vores users-row har et felt 'supabase_user_id' der peger på
Supabase Auth's UUID. Når en bruger logger ind, slår vi op i vores
tabel for at finde deres tenant og rolle.

═══════════════════════════════════════════════════════════════
LOGIN-FLOW
═══════════════════════════════════════════════════════════════

  1. Bruger åbner pax.juriitech.com
  2. app.py tjekker is_logged_in() — falsy → render_login_page()
  3. Bruger indtaster email + password → klikker "Log ind"
  4. login_with_password() kalder Supabase, modtager JWT + user
  5. _link_supabase_to_db_user() finder/opdaterer vores users-row:
     - Hvis row med supabase_user_id findes → brug den
     - Ellers slå op på email; hvis fundet → opdatér med UUID
       (det her er invitation-flowet: admin har pre-oprettet rækken)
     - Hvis ingen match overhovedet → afvis login (ikke inviteret)
  6. st.session_state.user sættes med {tenant_id, role, email, ...}
  7. st.rerun() — næste sideopdatering tjekker is_logged_in()=True
     og lader brugeren komme videre

═══════════════════════════════════════════════════════════════
SESSION-PERSISTENS
═══════════════════════════════════════════════════════════════

Streamlit's session_state er per-bruger og overlever side-skift, men
forsvinder når browser-tabben lukkes. Det er fint for B2 — brugeren
logger bare ind igen næste gang. I B4 kan vi tilføje "Husk mig" via
cookies eller refresh-token-håndtering.
"""

import os
import streamlit as st


# ───────────────────────────────────────────────────────────────
# SUPABASE-KLIENT
# Lazy init så manglende env-vars ikke crasher app-import.
# ───────────────────────────────────────────────────────────────

_client = None
_client_init_fejlet = False


def _get_supabase_client():
    """
    Returnér Supabase-klienten. Initialiserer den lazily ved første
    brug. Returnerer None hvis env-vars mangler eller init fejler —
    kalderen skal håndtere None med en pæn fejlmeddelelse.
    """
    global _client, _client_init_fejlet
    if _client is not None:
        return _client
    if _client_init_fejlet:
        return None

    url = os.getenv("SUPABASE_URL")
    anon_key = os.getenv("SUPABASE_ANON_KEY")
    if not url or not anon_key:
        print(
            "DEBUG: SUPABASE_URL eller SUPABASE_ANON_KEY mangler — "
            "auth deaktiveret. Sæt dem via 'fly secrets set'."
        )
        _client_init_fejlet = True
        return None
    try:
        from supabase import create_client
        _client = create_client(url, anon_key)
        return _client
    except Exception as e:
        print(f"DEBUG: Supabase-klient kunne ikke initialiseres: {e}")
        _client_init_fejlet = True
        return None


# ───────────────────────────────────────────────────────────────
# SESSION-STATE-HJÆLPERE
# ───────────────────────────────────────────────────────────────

def is_logged_in():
    """True hvis der er en autentificeret bruger i session_state."""
    user = st.session_state.get("user")
    return bool(user and user.get("tenant_id"))


def current_user():
    """Returnerer current user dict eller None."""
    return st.session_state.get("user")


def current_tenant_id():
    """Convenience: returnerer current user's tenant_id eller None."""
    user = current_user()
    return user.get("tenant_id") if user else None


def is_admin():
    """True hvis logged-in bruger har rolle='admin'."""
    user = current_user()
    return bool(user and user.get("role") == "admin")


# ───────────────────────────────────────────────────────────────
# BRO TIL VORES DATABASE
# ───────────────────────────────────────────────────────────────

def _link_supabase_to_db_user(supabase_user):
    """
    Finder eller opdaterer en users-row i vores DB baseret på
    Supabase-user. Returnerer dict med {tenant_id, role, email,
    fulde_navn} eller None hvis brugeren ikke er inviteret.

    Logik:
      1. Slå op via supabase_user_id (returkunde) → brug direkte
      2. Slå op via email (første-gangs login efter invitation)
         → opdatér med supabase_user_id, returnér
      3. Ingen match → returnér None (ikke inviteret)
    """
    if not supabase_user:
        return None

    from database import (
        hent_user_by_supabase_id,
        hent_user_by_email,
        opdater_user_supabase_id,
    )

    sup_id = getattr(supabase_user, "id", None) or supabase_user.get("id")
    email = (
        getattr(supabase_user, "email", None)
        or supabase_user.get("email", "")
    )
    if not sup_id or not email:
        return None

    # Trin 1: returkunde — har vi allerede koblet UUID?
    db_user = hent_user_by_supabase_id(sup_id)
    if db_user:
        return db_user

    # Trin 2: første-gangs login efter invitation — slå op via email
    db_user = hent_user_by_email(email)
    if db_user:
        # Linkning: opdatér rækken med Supabase-UUID så fremtidige
        # logins går via trin 1 (hurtigere + ikke afhængig af email).
        opdater_user_supabase_id(db_user["id"], sup_id)
        db_user["supabase_user_id"] = str(sup_id)
        return db_user

    # Trin 3: ikke inviteret
    print(
        f"DEBUG: Login afvist — {email} findes i Supabase men ikke i "
        "vores users-tabel. Brugeren er ikke inviteret af admin."
    )
    return None


# ───────────────────────────────────────────────────────────────
# LOGIN/LOGOUT
# ───────────────────────────────────────────────────────────────

def login_with_password(email, password):
    """
    Logger en bruger ind med email + password via Supabase Auth.

    Returnerer (success: bool, fejlmeddelelse: str | None).
    Ved succes er st.session_state.user sat og st.rerun() kan kaldes.
    """
    if not email or not password:
        return False, "Indtast både email og adgangskode."

    client = _get_supabase_client()
    if client is None:
        return False, (
            "Login-systemet er ikke konfigureret korrekt. Kontakt admin."
        )

    try:
        resp = client.auth.sign_in_with_password({
            "email": email.strip().lower(),
            "password": password,
        })
        sup_user = resp.user
        sup_session = resp.session
    except Exception as e:
        # Supabase returnerer typisk "Invalid login credentials" eller
        # "Email not confirmed" — vi viser en pæn dansk besked.
        msg = str(e).lower()
        if "invalid login" in msg or "invalid credentials" in msg:
            return False, "Forkert email eller adgangskode."
        if "email not confirmed" in msg:
            return False, (
                "Din email er ikke bekræftet endnu. Tjek din indbakke "
                "for verifikations-mail."
            )
        return False, f"Login fejlede: {e}"

    if not sup_user:
        return False, "Login fejlede: ingen bruger returneret fra Supabase."

    # Bro til vores users-tabel
    db_user = _link_supabase_to_db_user(sup_user)
    if not db_user:
        return False, (
            f"Din konto ({email}) er ikke tilknyttet et selskab. "
            "Bed din administrator om at invitere dig først."
        )

    # Sæt session_state — herefter er is_logged_in() = True
    st.session_state.user = {
        "id": db_user["id"],
        "supabase_user_id": db_user["supabase_user_id"],
        "tenant_id": db_user["tenant_id"],
        "email": db_user["email"],
        "fulde_navn": db_user.get("fulde_navn", ""),
        "role": db_user.get("role", "jurist"),
    }
    # Gem også selve Supabase-session så vi kan refresh tokens senere
    if sup_session:
        st.session_state.supabase_session = {
            "access_token": getattr(sup_session, "access_token", None),
            "refresh_token": getattr(sup_session, "refresh_token", None),
        }
    return True, None


def send_password_reset(email):
    """
    Sender en password-reset-mail via Supabase. Returnerer
    (success, fejlmeddelelse).
    """
    if not email:
        return False, "Indtast din email-adresse."
    client = _get_supabase_client()
    if client is None:
        return False, "Login-systemet er ikke konfigureret."
    try:
        client.auth.reset_password_for_email(email.strip().lower())
        return True, None
    except Exception as e:
        return False, f"Kunne ikke sende reset-mail: {e}"


def logout():
    """Rydder session_state og logger brugeren ud af Supabase."""
    client = _get_supabase_client()
    if client:
        try:
            client.auth.sign_out()
        except Exception as e:
            print(f"DEBUG: Supabase sign_out fejlede (ikke kritisk): {e}")
    # Ryd Streamlit-session
    for key in ("user", "supabase_session"):
        if key in st.session_state:
            del st.session_state[key]


# ───────────────────────────────────────────────────────────────
# ADMIN-OPERATIONER (Phase B4)
# ───────────────────────────────────────────────────────────────
# Disse funktioner bruger SUPABASE_SERVICE_KEY til at udføre operationer
# der KUN må køres af administrators — fx invitere nye brugere, slette
# brugere fra Supabase Auth osv. Service-key giver fuld adgang og må
# ALDRIG eksponeres via UI eller logs.

_admin_client = None
_admin_client_init_fejlet = False


def _get_admin_client():
    """
    Returnér Supabase-klient med SERVICE_KEY (admin-privileges).
    Lazy init. Returnerer None hvis SERVICE_KEY mangler.
    """
    global _admin_client, _admin_client_init_fejlet
    if _admin_client is not None:
        return _admin_client
    if _admin_client_init_fejlet:
        return None

    url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not service_key:
        print(
            "DEBUG: SUPABASE_URL eller SUPABASE_SERVICE_KEY mangler — "
            "admin-operationer deaktiveret."
        )
        _admin_client_init_fejlet = True
        return None
    try:
        from supabase import create_client
        _admin_client = create_client(url, service_key)
        return _admin_client
    except Exception as e:
        print(f"DEBUG: Supabase admin-klient kunne ikke initialiseres: {e}")
        _admin_client_init_fejlet = True
        return None


def admin_invite_user(email, tenant_id, role="jurist", fulde_navn=""):
    """
    Inviterer en ny bruger:
      1. Validerer at email ikke allerede findes i vores users-tabel
      2. Opretter row i users-tabel (uden supabase_user_id endnu —
         den linkes automatisk ved første login via invitation-mail)
      3. Sender Supabase magic-link invitation til email'en

    Når brugeren modtager mail'en og klikker linket, sætter de et
    password og logger ind. Vores login-flow finder dem via email,
    linker UUID, og giver dem adgang.

    Returnerer (success: bool, fejlmeddelelse: str | None).
    """
    if not email or not email.strip():
        return False, "Email er påkrævet."
    email = email.strip().lower()

    if not tenant_id:
        return False, "Tenant er påkrævet."

    if role not in ("admin", "jurist"):
        return False, f"Ugyldig rolle: {role!r} (skal være 'admin' eller 'jurist')."

    # Tjek om brugeren allerede er inviteret
    from database import hent_user_by_email, opret_user
    eksisterende = hent_user_by_email(email)
    if eksisterende:
        return False, (
            f"{email} er allerede oprettet i users-tabellen "
            f"(tenant_id={eksisterende['tenant_id']}, "
            f"role={eksisterende['role']}). "
            f"Brug edit-funktionen i stedet, eller slet først."
        )

    # Opret row i vores DB
    user_db_id = opret_user(
        email=email,
        tenant_id=tenant_id,
        role=role,
        fulde_navn=fulde_navn,
    )
    if not user_db_id:
        return False, "Kunne ikke oprette bruger-row i databasen."

    # Send Supabase invitation
    admin_client = _get_admin_client()
    if not admin_client:
        return False, (
            "Bruger oprettet i DB, men SUPABASE_SERVICE_KEY mangler så "
            "invitation-mail ikke kunne sendes. Tjek fly secrets."
        )

    try:
        admin_client.auth.admin.invite_user_by_email(email)
        return True, None
    except Exception as e:
        msg = str(e)
        # Hvis brugeren allerede findes i Supabase Auth (måske admin
        # oprettede dem manuelt før), er det ok — de skal bare logge
        # ind med det password de allerede har.
        if "already" in msg.lower() and "registered" in msg.lower():
            return True, (
                "Bruger oprettet i DB. Bemærk: Supabase Auth siger at "
                f"{email} allerede har en konto — de skal logge ind med "
                "deres eksisterende password (eller bruge "
                "'Glemt adgangskode?' for at nulstille)."
            )
        return False, f"Bruger oprettet i DB, men Supabase invitation fejlede: {e}"


# ───────────────────────────────────────────────────────────────
# UI-KOMPONENTER
# ───────────────────────────────────────────────────────────────

def render_login_page():
    """
    Renderer login-siden. Bruges som gate i app.py når brugeren
    ikke er logget ind.
    """
    # Centeret card-layout
    _, midt, _ = st.columns([1, 2, 1])
    with midt:
        st.markdown("# juriitech PAX")
        st.markdown(
            "<p style='color: #6B7280; margin-top: -8px; "
            "font-size: 1.05rem;'>Log ind for at fortsætte</p>",
            unsafe_allow_html=True,
        )
        st.write("")

        with st.form("login_form", clear_on_submit=False):
            email = st.text_input(
                "Email",
                placeholder="navn@firma.dk",
                key="login_email",
            )
            password = st.text_input(
                "Adgangskode",
                type="password",
                key="login_password",
            )
            login_knap = st.form_submit_button(
                "Log ind",
                type="primary",
                use_container_width=True,
            )

        if login_knap:
            with st.spinner("Logger ind..."):
                ok, fejl = login_with_password(email, password)
            if ok:
                st.rerun()
            else:
                st.error(fejl or "Login fejlede.")

        st.write("")
        with st.expander("Glemt adgangskode?"):
            reset_email = st.text_input(
                "Email til password-reset",
                key="reset_email",
                placeholder="navn@firma.dk",
            )
            if st.button(
                "Send reset-link",
                key="send_reset",
                use_container_width=True,
            ):
                with st.spinner("Sender reset-mail..."):
                    ok, fejl = send_password_reset(reset_email)
                if ok:
                    st.success(
                        f"Reset-link sendt til {reset_email}. "
                        "Tjek din indbakke."
                    )
                else:
                    st.error(fejl or "Kunne ikke sende reset-mail.")

        st.write("")
        st.caption(
            "Har du ikke en konto? Kontakt din administrator for at "
            "blive inviteret."
        )


def render_logout_button(placement="sidebar"):
    """
    Renderer en lille logout-knap + bruger-info. Default placering
    er sidebaren (st.sidebar). Sættes til 'main' for at lægge i hoved-
    indholdet i stedet.
    """
    user = current_user()
    if not user:
        return

    target = st.sidebar if placement == "sidebar" else st

    target.markdown("---")
    target.caption(f"Logget ind som **{user.get('email', '')}**")
    if user.get("role") == "admin":
        target.caption("🛡️ Administrator")
    if target.button("Log ud", key="logout_btn", use_container_width=True):
        logout()
        st.rerun()
