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

  2. Vores users-tabel (Supabase Postgres) — kobler Supabase-Auth-user
     til tenant_id (TUI/Spies/Apollo) + role (admin/jurist) + business
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


def _generate_temp_password(length=14):
    """
    Genererer et sikkert midlertidigt password til en ny bruger.
    Bruger Python's secrets-modul (kryptografisk sikker tilfældighed)
    med en blanding af store/små bogstaver, tal og symboler. Garanterer
    mindst ét tegn fra hver klasse for at matche typiske password-policy.
    """
    import secrets
    import string

    bogstaver_store = string.ascii_uppercase
    bogstaver_smaa = string.ascii_lowercase
    tal = string.digits
    symboler = "!@#$%&*"
    alle_tegn = bogstaver_store + bogstaver_smaa + tal + symboler

    # Sikr mindst ét fra hver klasse
    pw_chars = [
        secrets.choice(bogstaver_store),
        secrets.choice(bogstaver_smaa),
        secrets.choice(tal),
        secrets.choice(symboler),
    ]
    # Fyld op til length med tilfældige tegn
    pw_chars += [secrets.choice(alle_tegn) for _ in range(length - 4)]
    # Bland rækkefølgen så de garanterede tegn ikke altid står først
    secrets.SystemRandom().shuffle(pw_chars)
    return "".join(pw_chars)


def admin_invite_user(email, tenant_id, role="jurist", fulde_navn=""):
    """
    Inviterer en ny bruger via email — den ANBEFALEDE måde.

    Process:
      1. Validerer input
      2. Tjekker at email ikke allerede findes i vores users-tabel
      3. Opretter row i vores users-tabel UDEN supabase_user_id
         (linkes ved første login når brugeren klikker invite-link)
      4. Beder Supabase om at sende invite-email til brugeren med et
         link til vores set_password-side

    Brugeren modtager en email, klikker linket, sættes ind på
    set_password-siden, vælger sin egen adgangskode, og logges ind.
    Linket indeholder et token_hash som verify_otp validerer.

    KRÆVER: Supabase email-templates skal være konfigureret til at bruge
    URL-format: {{ .SiteURL }}?token_hash={{ .TokenHash }}&type=invite
    Se docs/CLAUDE.md for præcis HTML.

    Returnerer (success: bool, fejlmeddelelse: str | None).
    """
    if not email or not email.strip():
        return False, "Email er påkrævet."
    email = email.strip().lower()

    if not tenant_id:
        return False, "Tenant er påkrævet."

    if role not in ("admin", "jurist"):
        return False, f"Ugyldig rolle: {role!r}."

    # Tjek om brugeren allerede findes i vores users-tabel
    from database import hent_user_by_email, opret_user
    eksisterende = hent_user_by_email(email)
    if eksisterende:
        return False, (
            f"{email} er allerede oprettet "
            f"(tenant_id={eksisterende['tenant_id']}, "
            f"role={eksisterende['role']})."
        )

    # Opret row i vores users-tabel UDEN supabase_user_id.
    # _link_supabase_to_db_user vil finde rækken via email ved invite-flowet
    # og linke UUID når brugeren sætter password.
    user_db_id = opret_user(
        email=email,
        tenant_id=tenant_id,
        role=role,
        fulde_navn=fulde_navn,
    )
    if not user_db_id:
        return False, "Kunne ikke oprette bruger-row i databasen."

    # Bed Supabase sende invite-email
    admin_client = _get_admin_client()
    if not admin_client:
        return False, (
            "Bruger oprettet i DB, men SUPABASE_SERVICE_KEY mangler så "
            "invite-email ikke kunne sendes."
        )

    try:
        admin_client.auth.admin.invite_user_by_email(email)
        return True, None
    except Exception as e:
        msg = str(e).lower()
        if "already" in msg and ("registered" in msg or "exists" in msg):
            # Brugeren har allerede en Supabase Auth-konto.
            # Send dem en password-reset i stedet, så de kan sætte ny pw.
            try:
                admin_client.auth.reset_password_for_email(email)
                return True, (
                    f"{email} havde allerede en Supabase-konto. Vi har "
                    "sendt dem et password-reset-link i stedet. De kan "
                    "klikke på linket og vælge en ny adgangskode."
                )
            except Exception:
                return False, (
                    f"{email} har allerede en Supabase-konto, og vi kunne "
                    "ikke sende reset-link. Slet brugeren manuelt i "
                    "Supabase Dashboard og prøv igen."
                )
        return False, f"Bruger oprettet i DB, men invite-email fejlede: {e}"


def admin_create_user(email, tenant_id, role="jurist", fulde_navn=""):
    """
    Opretter en ny bruger med et automatisk genereret midlertidigt
    password. Admin skal manuelt videregive passwordet til brugeren
    via en sikker kanal (Signal, telefonisk, etc. — IKKE email).

    Forskellen fra magic-link invite: ingen URL-token-håndtering,
    intet ekstra trin med "Glemt adgangskode" for første login.
    Brugeren kan logge ind med email + temp password med det samme.

    Process:
      1. Validerer input + tjekker at email ikke allerede findes
      2. Genererer secure 14-tegns temp password
      3. Opretter brugeren i Supabase Auth med email_confirm=True
         (springer email-verifikation over — admin har already
         vouchet for emailen)
      4. Opretter row i vores users-tabel med supabase_user_id
         (linkningen sker MED DET SAMME, ikke ved første login)
      5. Returnerer det genererede password til admin

    Returnerer (success: bool, fejlmeddelelse: str | None,
                temp_password: str | None).
    """
    if not email or not email.strip():
        return False, "Email er påkrævet.", None
    email = email.strip().lower()

    if not tenant_id:
        return False, "Tenant er påkrævet.", None

    if role not in ("admin", "jurist"):
        return False, f"Ugyldig rolle: {role!r}.", None

    # Tjek om brugeren allerede findes i vores users-tabel
    from database import hent_user_by_email, opret_user
    eksisterende = hent_user_by_email(email)
    if eksisterende:
        return False, (
            f"{email} er allerede oprettet "
            f"(tenant_id={eksisterende['tenant_id']}, "
            f"role={eksisterende['role']})."
        ), None

    # Generer temp password
    temp_pw = _generate_temp_password()

    # Opret bruger i Supabase Auth
    admin_client = _get_admin_client()
    if not admin_client:
        return False, (
            "SUPABASE_SERVICE_KEY mangler — kan ikke oprette bruger "
            "i Supabase Auth. Tjek fly secrets."
        ), None

    try:
        result = admin_client.auth.admin.create_user({
            "email": email,
            "password": temp_pw,
            "email_confirm": True,  # Skip email-verifikation
            "user_metadata": {
                "fulde_navn": fulde_navn or "",
            },
        })
        sup_user = result.user
        sup_user_id = getattr(sup_user, "id", None) or sup_user.get("id")
    except Exception as e:
        msg = str(e).lower()
        if "already" in msg and ("registered" in msg or "exists" in msg):
            return False, (
                f"{email} har allerede en konto i Supabase Auth (men "
                "ikke i vores users-tabel). Slet brugeren i Supabase "
                "Dashboard → Authentication → Users først, eller gå "
                "via 'reset password' for at få adgang."
            ), None
        return False, f"Supabase create_user fejlede: {e}", None

    # Opret row i vores users-tabel — link straks med supabase_user_id
    user_db_id = opret_user(
        email=email,
        tenant_id=tenant_id,
        role=role,
        fulde_navn=fulde_navn,
        supabase_user_id=sup_user_id,
    )
    if not user_db_id:
        return False, (
            "Bruger oprettet i Supabase, men kunne ikke oprettes i "
            "vores DB. Slet brugeren manuelt i Supabase Dashboard og "
            "prøv igen."
        ), None

    return True, None, temp_pw


def admin_delete_user(user_id):
    """
    Sletter en bruger BÅDE i Supabase Auth og i vores users-tabel.

    Sikkerheds-spær (returnerer fejl uden at slette noget):
      - Brugeren findes ikke
      - Brugeren er den nuværende administrator (du må ikke slette dig
        selv — log ud i stedet)
      - Brugeren er den sidste admin på platformen (ville låse alle
        ude af admin-siden)

    Process:
      1. Slå brugeren op i vores DB (få supabase_user_id + role + email)
      2. Kør sikkerheds-checks
      3. Slet i Supabase Auth (hvis supabase_user_id findes)
      4. Slet i vores users-tabel
      5. Returnér succes

    Bemærk: Hvis Supabase-sletningen fejler, slettes den ikke i vores
    DB heller — så vi undgår "halvt slettede" brugere der findes i
    vores tabel men ikke har en Auth-konto. Den eneste undtagelse er
    hvis Supabase-kontoen ALLEREDE er væk (admin har slettet den
    manuelt) — så fortsætter vi med DB-sletningen.

    Returnerer (success: bool, fejlmeddelelse: str | None).
    """
    from database import (
        hent_user_by_id,
        slet_user,
        tael_admins,
    )

    # Step 1: slå op
    db_user = hent_user_by_id(user_id)
    if not db_user:
        return False, f"Bruger med id={user_id} findes ikke."

    # Step 2: spær — må ikke slette sig selv
    aktuel = current_user()
    if aktuel and aktuel.get("id") == db_user["id"]:
        return False, (
            "Du kan ikke slette din egen konto her. Hvis du vil logge "
            "ud, brug 'Log ud'-knappen i sidebaren."
        )

    # Step 2b: spær — må ikke slette sidste admin
    if db_user["role"] == "admin" and tael_admins() <= 1:
        return False, (
            "Du kan ikke slette den sidste administrator. Opret først "
            "en anden admin før du sletter denne."
        )

    # Step 3: slet i Supabase Auth (hvis vi har deres UUID)
    sup_uuid = db_user.get("supabase_user_id")
    if sup_uuid:
        admin_client = _get_admin_client()
        if admin_client is None:
            return False, (
                "SUPABASE_SERVICE_KEY mangler — kan ikke slette i Supabase "
                "Auth. Slet i Supabase Dashboard → Users og prøv igen."
            )
        try:
            admin_client.auth.admin.delete_user(sup_uuid)
        except Exception as e:
            msg = str(e).lower()
            # "User not found" / 404 — Supabase-kontoen er allerede væk
            # (admin har slettet manuelt). Vi fortsætter med DB-sletning.
            if "not found" in msg or "404" in msg or "no rows" in msg:
                print(
                    f"DEBUG: Supabase-konto for {db_user['email']} var "
                    "allerede væk — fortsætter med DB-sletning."
                )
            else:
                return False, (
                    f"Supabase-sletning fejlede: {e}. "
                    "Bruger IKKE slettet i vores DB."
                )

    # Step 4: slet i vores users-tabel
    if not slet_user(db_user["id"]):
        return False, (
            f"Slettet i Supabase Auth, men sletning i vores DB fejlede. "
            f"Slet manuelt med: DELETE FROM users WHERE id={db_user['id']}"
        )

    return True, None


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
