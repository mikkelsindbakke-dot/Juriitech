"""
Sæt password-side. Brugere lander her efter at have klikket på et
invite-link (fra admin) eller password-reset-link (fra "Glemt
adgangskode?") i deres email.

URL-format (sat via Supabase email-templates):
    https://pax.juriitech.com/?token_hash=...&type=invite|recovery

Flow:
  1. Læs token_hash + type fra URL query params
  2. Vis "sæt password + bekræft password" form
  3. Ved submit:
     a. Kald supabase.auth.verify_otp({token_hash, type})
        — det verificerer tokenet og opretter en session
     b. Kald supabase.auth.update_user({password: ny_pw})
        — sætter brugerens password i Supabase
     c. Slå op i vores users-tabel via _link_supabase_to_db_user
        — finder rækken admin oprettede ved invite, linker UUID
     d. Sæt st.session_state.user → brugeren er logget ind
     e. Ryd token fra URL og kør st.rerun() → forsiden vises

Modulet eksporterer kun render() — kaldes fra app.py som standalone-side
udenfor st.navigation (siden vises kun ved invite/recovery flows, ikke
i den almindelige navigation).
"""

import streamlit as st
import auth


# De 30 mest almindelige svage adgangskoder. Ren blacklist — bruges kun
# ved oprettelse for at afvise åbenlyst usikre kombinationer.
_SVAGE_PASSWORDS = {
    "12345678", "123456789", "1234567890", "qwerty12", "qwertyui",
    "qwerty123", "password", "password1", "password12", "password123",
    "passw0rd", "passw0rd1", "abc12345", "abcd1234", "letmein1",
    "welcome1", "welcome12", "welcome123", "admin123", "admin1234",
    "test1234", "test12345", "iloveyou1", "monkey123", "dragon123",
    "master123", "shadow123", "sunshine1", "princess1", "football1",
}


def _valider_password_styrke(pw):
    """
    Returnerer (ok: bool, fejlmeddelelse: str | None).
    Mindste-krav til styrke: 8 tegn + både bogstav og tal + ikke i
    blacklist over almindelige svage adgangskoder.
    """
    if len(pw) < 8:
        return False, (
            "Adgangskoden skal være mindst 8 tegn. Vælg gerne en længere "
            "kode for ekstra sikkerhed."
        )
    if pw.lower() in _SVAGE_PASSWORDS:
        return False, (
            "Den adgangskode er på listen over almindelige svage "
            "adgangskoder. Vælg en mere unik kombination."
        )
    har_bogstav = any(c.isalpha() for c in pw)
    har_tal = any(c.isdigit() for c in pw)
    if not (har_bogstav and har_tal):
        return False, (
            "Adgangskoden skal indeholde både bogstaver og tal."
        )
    return True, None


def render():
    """Render set-password siden. Kaldes fra app.py."""
    qp = st.query_params
    token_hash = qp.get("token_hash") or ""
    type_param = qp.get("type") or ""

    # Defensiv check
    if not token_hash:
        st.error(
            "Manglende token i link. Bed din administrator om at sende "
            "en ny invitation."
        )
        return
    if type_param not in ("invite", "recovery", "email", "magiclink"):
        st.error(f"Ukendt link-type: '{type_param}'. Kontakt support.")
        return

    auth._inject_auth_chrome_css()
    # Centeret card-layout (samme stil som login-side)
    _, midt, _ = st.columns([1, 2, 1])
    with midt:
        st.markdown("# juriitech PAX")

        if type_param in ("invite", "magiclink"):
            st.markdown(
                "<p style='color: #6B7280; margin-top: -8px; "
                "font-size: 1.05rem;'>Velkommen — vælg din adgangskode</p>",
                unsafe_allow_html=True,
            )
            st.write("")
            st.info(
                "Du er blevet inviteret af din administrator. Vælg en "
                "stærk adgangskode (mindst 8 tegn) for at oprette din "
                "konto. Du bruger den til at logge ind fremover."
            )
        else:  # recovery
            st.markdown(
                "<p style='color: #6B7280; margin-top: -8px; "
                "font-size: 1.05rem;'>Nulstil din adgangskode</p>",
                unsafe_allow_html=True,
            )
            st.write("")

        st.write("")

        with st.form("set_password_form", clear_on_submit=False):
            pw1 = st.text_input(
                "Ny adgangskode",
                type="password",
                placeholder="Mindst 8 tegn",
                key="set_pw1",
            )
            pw2 = st.text_input(
                "Bekræft adgangskode",
                type="password",
                placeholder="Skriv samme adgangskode igen",
                key="set_pw2",
            )
            submit = st.form_submit_button(
                "Gem og log ind",
                type="primary",
                use_container_width=True,
            )

        if submit:
            # Validering
            if not pw1 or not pw2:
                st.error("Indtast adgangskoden begge steder.")
                return
            if pw1 != pw2:
                st.error(
                    "De to adgangskoder er ikke ens. Skriv den samme "
                    "adgangskode i begge felter."
                )
                return
            ok_styrke, styrke_fejl = _valider_password_styrke(pw1)
            if not ok_styrke:
                st.error(styrke_fejl)
                return

            # Forsøg at sætte password via Supabase
            with st.spinner("Opretter din konto..."):
                ok, fejl = _verify_and_set_password(
                    token_hash=token_hash,
                    type_param=type_param,
                    new_password=pw1,
                )

            if ok:
                # Ryd token fra URL så det ikke ligger i browser-history
                st.query_params.clear()
                st.success(
                    "✅ Din adgangskode er gemt — du er logget ind. "
                    "Du sendes til forsiden..."
                )
                st.rerun()
            else:
                st.error(fejl or "Noget gik galt. Prøv igen.")


def _verify_and_set_password(token_hash, type_param, new_password):
    """
    Intern hjælper: verify token → opret session → opdatér password →
    slå op i vores users-tabel → sæt st.session_state.user.

    Returnerer (success: bool, fejl: str | None).
    """
    client = auth._get_supabase_client()
    if client is None:
        return False, "Login-systemet er ikke konfigureret. Kontakt admin."

    # Step 1: Verify OTP token (opretter session i Supabase-klienten)
    try:
        verify_response = client.auth.verify_otp({
            "token_hash": token_hash,
            "type": type_param,
        })
        sup_user = verify_response.user
        sup_session = verify_response.session
    except Exception as e:
        msg = str(e).lower()
        if "expired" in msg or "invalid" in msg:
            return False, (
                "Linket er udløbet eller ugyldigt. Bed din administrator "
                "om at sende en ny invitation."
            )
        return False, f"Token-verifikation fejlede: {e}"

    if not sup_user:
        return False, "Ingen bruger returneret fra Supabase."

    # Step 2: Opdatér password på den nu-loggede-ind bruger
    try:
        client.auth.update_user({"password": new_password})
    except Exception as e:
        return False, f"Kunne ikke gemme adgangskode: {e}"

    # Step 3: Slå op / link til vores users-tabel
    db_user = auth._link_supabase_to_db_user(sup_user)
    if not db_user:
        return False, (
            f"Din konto ({sup_user.email}) findes nu i Supabase, men er "
            "ikke tilknyttet et selskab i vores database. Bed admin om "
            "at oprette dig korrekt."
        )

    # Step 4: Sæt session_state — brugeren er nu logged in
    st.session_state.user = {
        "id": db_user["id"],
        "supabase_user_id": db_user["supabase_user_id"],
        "tenant_id": db_user["tenant_id"],
        "email": db_user["email"],
        "fulde_navn": db_user.get("fulde_navn", ""),
        "role": db_user.get("role", "jurist"),
    }
    if sup_session:
        st.session_state.supabase_session = {
            "access_token": getattr(sup_session, "access_token", None),
            "refresh_token": getattr(sup_session, "refresh_token", None),
        }

    return True, None
