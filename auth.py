"""
Auth-modul for juriitech PAX.

Wrapper omkring Supabase Auth — håndterer login, logout, session-tjek
og henter den aktuelle bruger. Bruges af alle Streamlit-sider for at
beskytte indhold mod ikke-loggede brugere.

KRITISK PRINCIP:
Denne modul ÆNDRER IKKE selve PAX-funktionaliteten. Den TILFØJER bare
et lag af bruger-tjek på toppen af eksisterende sider.

Workflow:
  1. Bruger åbner pax.juriitech.com
  2. login_required() tjekker om de er logget ind
  3. Hvis ja: PAX-indhold vises som normalt
  4. Hvis nej: redirect til login-side
"""

import os
import streamlit as st


# ---------- LAZY KLIENT-INITIALISERING ----------
# Vi initialiserer IKKE Supabase-klienten ved modul-import — det
# matcher mønsteret fra embeddings.py og ai_engine.py. Hvis SUPABASE-
# nøglerne mangler eller er ugyldige, fejler kun auth-funktionerne, ikke
# hele appen.
_supabase_klient = None
_klient_init_fejlet = False


def get_supabase_client():
    """Returnér Supabase-klienten. Initialiserer den lazily på første
    kald. Returnerer None hvis konfiguration mangler eller init fejler.
    """
    global _supabase_klient, _klient_init_fejlet

    if _supabase_klient is not None:
        return _supabase_klient
    if _klient_init_fejlet:
        return None

    try:
        # Læs fra Streamlit secrets (production) eller env (lokal)
        url = ""
        anon_key = ""
        try:
            url = st.secrets.get("SUPABASE_URL", "") or ""
            anon_key = st.secrets.get("SUPABASE_ANON_KEY", "") or ""
        except Exception:
            pass
        if not url:
            url = os.getenv("SUPABASE_URL", "")
        if not anon_key:
            anon_key = os.getenv("SUPABASE_ANON_KEY", "")

        if not url or not anon_key:
            print(
                "DEBUG: SUPABASE_URL eller SUPABASE_ANON_KEY mangler — "
                "auth deaktiveret."
            )
            _klient_init_fejlet = True
            return None

        from supabase import create_client
        _supabase_klient = create_client(url, anon_key)
        return _supabase_klient
    except Exception as e:
        print(f"DEBUG: Supabase-klient kunne ikke oprettes: {e}")
        _klient_init_fejlet = True
        return None


# ---------- SESSION HJÆLPERE ----------

def er_logget_ind() -> bool:
    """True hvis brugeren har en aktiv session i st.session_state."""
    return bool(st.session_state.get("auth_user"))


def hent_aktuel_bruger():
    """Returnér den loggede bruger (dict med email, id osv.) eller None."""
    return st.session_state.get("auth_user")


def hent_aktuel_email() -> str:
    """Returnér emailen for den loggede bruger eller tom streng."""
    bruger = hent_aktuel_bruger()
    if bruger and isinstance(bruger, dict):
        return bruger.get("email", "")
    return ""


# ---------- LOGIN / LOGOUT ----------

def log_ind(email: str, password: str) -> tuple[bool, str]:
    """Forsøg at logge brugeren ind med email + password.
    Returnerer (succes: bool, fejlbesked: str).
    Hvis succes, gemmes session-data i st.session_state['auth_user'].
    """
    klient = get_supabase_client()
    if klient is None:
        return False, (
            "Login-systemet er ikke konfigureret korrekt. "
            "Kontakt support@juriitech.com."
        )

    if not email or not password:
        return False, "Indtast både email og password."

    try:
        respons = klient.auth.sign_in_with_password({
            "email": email.strip().lower(),
            "password": password,
        })
        # Gem brugeren + session i Streamlit state
        if respons and respons.user:
            st.session_state["auth_user"] = {
                "id": respons.user.id,
                "email": respons.user.email,
                "metadata": respons.user.user_metadata or {},
            }
            # Gem session-token til evt. fremtidige API-kald
            if respons.session:
                st.session_state["auth_session"] = {
                    "access_token": respons.session.access_token,
                    "refresh_token": respons.session.refresh_token,
                }
            return True, ""
        return False, "Login mislykkedes — ukendt fejl."
    except Exception as e:
        # Konvertér Supabase-fejl til brugervenlig dansk besked
        fejl_str = str(e).lower()
        if "invalid login" in fejl_str or "invalid_credentials" in fejl_str:
            return False, "Forkert email eller password."
        if "email not confirmed" in fejl_str:
            return False, (
                "Email er ikke bekræftet endnu. Tjek din indbakke for "
                "bekræftelses-mail."
            )
        if "rate limit" in fejl_str:
            return False, (
                "For mange login-forsøg. Vent et par minutter og prøv igen."
            )
        return False, f"Login fejlede: {e}"


def log_ud():
    """Log brugeren ud — ryd session state."""
    klient = get_supabase_client()
    if klient is not None:
        try:
            klient.auth.sign_out()
        except Exception:
            pass  # Ignorér fejl ved logout — vi rydder state alligevel

    # Ryd ALT bruger-relateret state
    for key in list(st.session_state.keys()):
        if key.startswith("auth_"):
            del st.session_state[key]


def send_password_reset(email: str) -> tuple[bool, str]:
    """Send 'glemt password'-email til brugeren via Supabase.
    Returnerer (succes, fejlbesked)."""
    klient = get_supabase_client()
    if klient is None:
        return False, "Login-systemet er ikke konfigureret korrekt."
    if not email:
        return False, "Indtast din email."

    try:
        klient.auth.reset_password_for_email(email.strip().lower())
        return True, ""
    except Exception as e:
        return False, f"Kunne ikke sende reset-mail: {e}"


# ---------- LOGIN UI ----------

def vis_login_side():
    """Renderer login-siden — vises når brugeren ikke er logget ind.
    Skjuler standard-navigation og viser et centreret login-kort i
    juriitech-brand-stil. Kald st.stop() bagefter for at forhindre at
    resten af app'en renderes.
    """
    # Skjul standard sidebar/navigation
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] { display: none !important; }
        [data-testid="collapsedControl"] { display: none !important; }
        .main .block-container {
            padding-top: 4rem !important;
            max-width: 480px !important;
        }
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Source+Serif+4:wght@600;700&display=swap');
        body, .stApp { font-family: 'Inter', sans-serif !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # juriitech-wordmark (samme stil som forsiden)
    st.markdown(
        """
        <div style="text-align: center; margin-bottom: 32px;">
            <div style="font-family: 'Source Serif 4', Georgia, serif;
                font-size: 2.4rem; font-weight: 700; letter-spacing: -0.025em;">
                <span style="color: #6E74F0;">j</span><span style="color: #111827;">uriitech</span>
            </div>
            <div style="color: #6B7280; font-size: 0.95rem; margin-top: 4px;">
                Log ind for at fortsætte
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # State til at vise password-reset i stedet for login
    if "_vis_glemt_password" not in st.session_state:
        st.session_state._vis_glemt_password = False

    if st.session_state._vis_glemt_password:
        _vis_password_reset_form()
    else:
        _vis_login_form()


def _vis_login_form():
    """Login-form med email + password."""
    with st.form("login_form", clear_on_submit=False):
        email = st.text_input(
            "Email",
            placeholder="navn@selskab.dk",
            autocomplete="email",
        )
        password = st.text_input(
            "Password",
            type="password",
            autocomplete="current-password",
        )
        submitted = st.form_submit_button(
            "Log ind",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        with st.spinner("Logger ind..."):
            ok, fejl = log_ind(email, password)
        if ok:
            st.success("Velkommen tilbage!")
            st.rerun()
        else:
            st.error(fejl)

    # Glemt password-link
    if st.button(
        "Glemt password?",
        type="tertiary",
        key="glemt_password_btn",
    ):
        st.session_state._vis_glemt_password = True
        st.rerun()

    # Hjælpe-tekst nederst
    st.markdown(
        """
        <div style="text-align: center; margin-top: 32px;
            color: #9CA3AF; font-size: 0.85rem;">
            Har du brug for adgang? Skriv til
            <a href="mailto:support@juriitech.com"
               style="color: #6366F1; text-decoration: none;">
                support@juriitech.com
            </a>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _vis_password_reset_form():
    """Form til at sende glemt-password mail."""
    st.markdown(
        "Indtast din email — så sender vi dig et link til at "
        "nulstille dit password."
    )
    with st.form("reset_form"):
        email = st.text_input("Email", placeholder="navn@selskab.dk")
        submitted = st.form_submit_button(
            "Send reset-link",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        ok, fejl = send_password_reset(email)
        if ok:
            st.success(
                "Reset-link er sendt. Tjek din indbakke (og evt. spam-"
                "mappen). Linket virker i 1 time."
            )
        else:
            st.error(fejl)

    if st.button(
        "← Tilbage til login",
        type="tertiary",
        key="tilbage_til_login_btn",
    ):
        st.session_state._vis_glemt_password = False
        st.rerun()


# ---------- LOGOUT-KNAP I SIDEBAR ----------

def render_logout_i_sidebar():
    """Tilføj brugerinfo + logout-knap nederst i sidebaren.
    Kaldes fra app.py når brugeren ER logget ind.
    """
    email = hent_aktuel_email()
    if not email:
        return

    with st.sidebar:
        st.markdown(
            f"""
            <div style="padding: 12px 14px; margin-top: 12px;
                background: rgba(99, 102, 241, 0.05);
                border-radius: 10px;
                border: 1px solid rgba(99, 102, 241, 0.12);">
                <div style="font-size: 0.78rem; color: #6B7280;
                    font-weight: 500; margin-bottom: 2px;">
                    LOGGET IND SOM
                </div>
                <div style="color: #111827; font-size: 0.92rem;
                    font-weight: 600; word-break: break-all;">
                    {email}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button(
            "Log ud",
            key="logout_btn",
            use_container_width=True,
        ):
            log_ud()
            st.rerun()
