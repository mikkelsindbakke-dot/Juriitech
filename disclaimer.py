"""
Disclaimer-side: information til brugeren om at programmet er AI-baseret,
samt hvordan kildehenvisninger gør det nemt at verificere AI'ens påstande.
"""

import streamlit as st


# Admin-flag sat af app.py
ER_ADMIN = st.session_state.get("er_admin", False)


# ---------- SKJUL DELINGS-MENU FOR IKKE-ADMINS ----------
if not ER_ADMIN:
    st.markdown(
        """
        <style>
        #MainMenu {visibility: hidden !important;}
        [data-testid="stToolbar"] {visibility: hidden !important;}
        [data-testid="stDeployButton"] {display: none !important;}
        footer {visibility: hidden !important;}
        .viewerBadge_container__1QSob { display: none !important; }
        [data-testid="manage-app-button"] { display: none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------- STYLING ----------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700&display=swap');
    html, body, .stApp, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        -webkit-font-smoothing: antialiased;
    }
    h1 a, h2 a, h3 a, h4 a,
    [data-testid="stHeaderActionElements"],
    [data-testid="stHeading"] a {
        display: none !important;
    }
    h1, h2, h3, h4 {
        font-family: 'Source Serif 4', Georgia, serif !important;
        font-weight: 600 !important;
        letter-spacing: -0.015em !important;
    }
    section[data-testid="stSidebar"] {
        backdrop-filter: saturate(180%) blur(24px) !important;
        -webkit-backdrop-filter: saturate(180%) blur(24px) !important;
        background-color: rgba(250, 250, 252, 0.72) !important;
        border-right: 1px solid rgba(0, 0, 0, 0.06) !important;
    }
    @media (prefers-color-scheme: dark) {
        section[data-testid="stSidebar"] {
            background-color: rgba(25, 27, 32, 0.72) !important;
        }
    }
    .main .block-container {
        padding-top: 3rem !important;
        max-width: 900px !important;
    }
    .stMarkdown p, .stMarkdown li, p, li {
        line-height: 1.7 !important;
    }
    [data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 10px !important;
        padding: 1.5rem !important;
        margin-bottom: 1rem !important;
        border: 1px solid rgba(127, 127, 127, 0.14) !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------- INDHOLD ----------

st.title("Disclaimer: læs inden brug")

st.markdown(
    """
    **juriitech PAX** er et digitalt værktøj, der bruger kunstig intelligens
    (AI) til at analysere klagesager fra Pakkerejse-Ankenævnet og foreslå
    juridiske vurderinger og svarbreve. Programmet er bygget fra bunden som
    et specialiseret værktøj til rejsebranchen.

    juriitech PAX er udviklet af **juriitech** — en virksomhed der bygger
    specialiserede AI-værktøjer til juridiske nicheområder. "PAX" refererer
    til at dette produkt er skræddersyet til pakkerejsesager. Fremtidige
    produkter fra juriitech vil have deres egne modelnavne efter samme
    princip.
    """
)

with st.container(border=True):
    st.markdown(
        """
        ### Hvad programmet gør

        juriitech PAX hjælper din arbejdsgang ved at:

        - læse sagens dokumenter (høringsbrev, klageskema, bilag)
        - finde de 3-5 mest relevante tidligere afgørelser fra Ankenævnet
        - generere en struktureret førstevurdering med sandsynlighedsestimat
        - udarbejde et komplet udkast til svarbrev
        - anonymisere bilag efter Ankenævnets retningslinjer
        - arkivere alle analyser så de er nemme at finde igen
        """
    )

with st.container(border=True):
    st.markdown(
        """
        ### Om AI og præcision

        AI-modeller er ekstremt dygtige, men **ikke ufejlbarlige**. Selv
        de bedste modeller kan i sjældne tilfælde:

        - misforstå en juridisk nuance
        - overse et bilag i en kompleks sag
        - sammenblande lignende sagstyper
        - fejltolke et beløb eller en dato

        Derfor **skal alle resultater fra juriitech PAX gennemlæses og
        verificeres af en jurist**, før de bruges i en formel sammenhæng.
        Programmet er et beslutningsstøtteværktøj — ikke en erstatning for
        juridisk dømmekraft.
        """
    )

with st.container(border=True):
    st.markdown(
        """
        ### Kildehenvisninger — sådan tjekker du AI'ens påstande

        For at gøre verificering så hurtig som muligt, er juriitech PAX trænet
        til at **angive kilden umiddelbart efter hver påstand**. Hver gang
        programmet fremsætter et faktum, en pris, en dato eller en juridisk
        konklusion, står der en kildehenvisning i kantet parentes lige
        efter. Fx:

        > Klageren rejste til Rhodos den 10. august 2024 [Bilag 03, s. 1] og
        > reklamerede over rengøringsstandard på værelset [Klageskema, s. 2].
        > I tilsvarende sager har Nævnet afvist klagen, når rejseselskabet
        > tilbød afhjælpning på stedet [Afgørelse 19-1467 (2019)].

        På den måde kan du som jurist lynhurtigt finde den konkrete linje i
        det konkrete bilag, og verificere at AI'en har forstået materialet
        korrekt.

        De tre hovedtyper af kilder, programmet henviser til:

        - **[Bilag XX, s. Y]** — sagens egne bilag fra klagesagen
        - **[Afgørelse YY-NNNN (ÅÅÅÅ)]** — tidligere afgørelser fra
          Pakkerejse-Ankenævnet
        - **[Rejsevilkår, punkt X.Y]** — et rejseselskabs egne rejsevilkår,
          såfremt disse er hentet af juriitech PAX
        """
    )

with st.container(border=True):
    st.markdown(
        """
        ### Din rolle som bruger

        Når du bruger juriitech PAX, bør du:

        1. Læse AI'ens vurdering kritisk og se den som et **udkast**, ikke et facit
        2. Stikprøvekontrollere kildehenvisningerne — især de centrale argumenter
        3. Bruge din egen juridiske dømmekraft som den endelige filter
        4. Være særligt opmærksom hvis sagen afviger fra normale mønstre

        Når disse forholdsregler tages, er juriitech PAX et værdifuldt værktøj
        der kan spare dig mange timers manuelt læsearbejde — men det
        endelige juridiske ansvar ligger altid hos dig.
        """
    )

st.caption(
    "juriitech PAX er under løbende udvikling. Har du observationer eller "
    "forslag til forbedringer, er feedback meget velkommen."
)
