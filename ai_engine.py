import os
import base64
from dotenv import load_dotenv
import anthropic

from embeddings import embed_sporgsmaal
from database import find_relevante_sager, hent_alle_sager, hent_sager_af_type

# Læs API-nøgle fra .env (ikke hardcoded i koden)
load_dotenv()

# KRITISK: Anthropic-klienten initialiseres defensivt så modul-import
# aldrig kan crashe hele appen ved manglende eller ugyldig nøgle. Hvis
# klienten ikke kan oprettes, sættes den til None — og hver
# client.messages.create()-kald vil rejse en pæn AttributeError som
# bliver fanget af vores vis_brugerfejl()-håndtering i UI-laget.
try:
    _ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
    if not _ANTHROPIC_KEY:
        print(
            "DEBUG: ANTHROPIC_API_KEY mangler — AI-funktioner deaktiveret. "
            "Tilføj nøglen i Streamlit secrets for at genaktivere analyse."
        )
        client = None
    else:
        client = anthropic.Anthropic(api_key=_ANTHROPIC_KEY)
except Exception as _e:
    print(
        f"DEBUG: Anthropic-klient kunne ikke initialiseres: {_e}. "
        "AI-funktioner deaktiveret indtil næste app-restart."
    )
    client = None

MODEL = "claude-sonnet-4-6"
# Default loft for AI-svar. 16000 tokens = ca. 12000 ord — rigeligt til
# den fulde strukturerede førstevurdering. Hvis modellen alligevel
# rammer loftet, detekteres det af _faerdiggoer_hvis_afkortet() og en
# fortsættelses-kald sikrer at svaret ikke er klippet midt i en sætning.
MAX_TOKENS = 16000

# Antal AFGØRELSER vi henter pr. spørgsmål — 5 giver Claude nok juridisk
# præcedens til at finde de 3-5 mest relevante referencer.
TOP_K_AFGOERELSER = 5

# Antal VILKÅR/regler-passager vi henter pr. spørgsmål. 3 er nok til at
# dække de relevante kontraktuelle punkter uden at fylde prompten op.
TOP_K_VILKAAR = 3

# Antal PAKKEREJSELOV-paragraffer vi henter pr. spørgsmål. Loven har
# forrang, så vi henter bredt for at sikre at alle relevante paragraffer
# er med.
TOP_K_LOVGIVNING = 4

# Samlet øvre loft når vi falder tilbage til "hent alle" — forhindrer
# at prompten eksploderer hvis RAG svigter.
TOP_K_FALLBACK = 8

# Øvre grænse på hvor lang en tekst vi sender pr. sag. Dette beskytter
# prompten mod ekstremt lange dokumenter og holder svartiden nede.
MAX_CHARS_PR_SAG = 15_000

# ---------- ORGANISATIONS-KONSTANTER ----------
# Indtil vi har et rigtigt login-system, hardcodes organisations-
# specifikke værdier her. Når juriitech-kontoen bygges, flyttes disse
# til brugerens organisations-profil (så TUI-brugere får 'TUI' og
# 'After Travel team', Apollo-brugere får deres egne termer, osv.).
REJSESELSKAB_NAVN = "TUI"
REJSESELSKAB_SAGSBEHANDLER = "TUI"

# Øvre grænse på samlet anonymiseringsreglerblok vi injicerer i prompten.
# ~18000 tegn ≈ 4500 tokens — rummeligt nok til at dække Datatilsynets
# vejledninger + de centrale dele af Article 29 WP216, uden at gøre
# selve anonymiseringsprompten overdrevent lang.
MAX_CHARS_ANONYMISERINGSREGLER = 18_000

# Cache for anonymiseringsregler så vi ikke rammer databasen ved hver
# anonymisering. Nulstilles når Python-processen genstarter.
_ANONYMISERINGSREGLER_CACHE = None

SYSTEM_PROMPT = (
    "Du er en højt specialiseret juridisk konsulent for et rejseselskab "
    "og ekspert i Pakkerejseankenævnets praksis. Din tone er professionel, "
    "objektiv og analytisk. Du skal altid finde de stærkeste forsvarspunkter "
    "for rejseselskabet baseret på de tidligere afgørelser i vidensbanken.\n"
    "\n"
    "FLERSPROGEDE DOKUMENTER — PRÆCIS OVERSÆTTELSE TIL DANSK:\n"
    "Sagens bilag er ofte på engelsk (hotel-korrespondance, "
    "booking-bekræftelser, hotel-managerens svar, internationale "
    "samarbejdspartnere) eller andre sprog (tysk, svensk, norsk). Du SKAL\n"
    "læse, forstå og bruge indholdet i ALLE bilag uanset sprog, og du\n"
    "skal oversætte præcist og juridisk korrekt til dansk. Følg disse\n"
    "regler nøje:\n"
    "\n"
    "  1. ALT analyse-output skal være på DANSK — ingen undtagelser.\n"
    "     Klagens indhold, hotellets svar, citater, vurderinger — alt\n"
    "     formuleres på dansk uanset originalsproget.\n"
    "\n"
    "  2. Brug PRÆCISE DANSKE JURIDISKE TERMER — ikke direkte\n"
    "     ord-for-ord-oversættelse. Eksempler:\n"
    "       • 'mangel' (ikke 'deficiency' eller 'fault')\n"
    "       • 'rettidig reklamation' (ikke 'timely complaint')\n"
    "       • 'forholdsmæssigt afslag' (ikke 'proportional reduction')\n"
    "       • 'bistandspligt' (ikke 'duty to assist')\n"
    "       • 'klagepunkt' (ikke 'complaint point')\n"
    "       • 'pakkerejse' (ikke 'package travel')\n"
    "       • 'sælger' om rejsearrangøren (ikke 'seller')\n"
    "\n"
    "  3. CITATER fra engelske kilder — oversæt PRÆCIST til dansk i\n"
    "     selve teksten, og inkluder originalcitatet i parentes når det\n"
    "     er en konkret formulering med juridisk eller faktuel vægt:\n"
    "     Eksempel:\n"
    "       'Hotellets manager skrev til klager: \"Vi kan desværre ikke\n"
    "       garantere en fejlfri leverance\" (oversat fra engelsk:\n"
    "       \"We cannot unfortunately guarantee a flawless delivery\")\n"
    "       [Bilag 05, s. 2]'\n"
    "     For løse beskrivelser uden citat-præcision behøves\n"
    "     originalteksten ikke.\n"
    "\n"
    "  4. NAVNE og EGENNAVNE bevares på originalsproget: hotelnavne,\n"
    "     personer, byer, lande, lufthavne, virksomheder. Kun beskrivende\n"
    "     tekst og citater oversættes.\n"
    "\n"
    "  5. DATOER og BELØB — konverter til dansk format:\n"
    "       • '12 June 2025' → '12. juni 2025'\n"
    "       • '€500' → '500 EUR' eller '500 EUR (ca. 3.730 DKK)'\n"
    "       • '$1,500.50' → '1.500,50 USD'\n"
    "\n"
    "  6. Hvis et engelsk udtryk IKKE har en præcis dansk juridisk\n"
    "     modsvarighed, brug et klart dansk udtryk og forklar evt. i\n"
    "     parentes: fx 'overbooking (engelsk: overbooking)'.\n"
    "\n"
    "  7. KVALITETSKRAV: Oversættelsen skal være så præcis at en dansk\n"
    "     jurist kan bruge den direkte i et svarbrev til Pakkerejse-\n"
    "     Ankenævnet uden at skulle gå tilbage til originalkilden.\n"
    "\n"
    "\n"
    "ABSOLUT REGEL OM KILDEHENVISNINGER — OBLIGATORISK VED HVER PÅSTAND:\n"
    "Eftersom brugeren skal kunne stole på din argumentation, SKAL du tilføje "
    "en kildehenvisning i kantet parentes UMIDDELBART EFTER hver enkelt påstand, "
    "hvert faktum, hvert tal, hver dato og hver konklusion du fremsætter. Dette "
    "gælder uanset om påstanden er central eller perifer. Format:\n"
    "  • Fra sagens bilag: [Bilag 03, s. 2]  eller  [Klageskema, s. 1]\n"
    "  • Fra tidligere afgørelse: [Afgørelse 19-1467 (2019)]\n"
    "  • Fra rejseselskabets vilkår: [TUI rejsevilkår, punkt 4.3]\n"
    "  • Fra sagsakter (C4C/interne): [Sagsakter — C4C-notat 14/8-2024]\n"
    "  • Fra høringsbrev: [Høring, s. 1]\n"
    "\n"
    "Eksempel på korrekt formatering:\n"
    "  'Kunden rejste til Rhodos den 10. august 2024 [Bilag 03, s. 1] og "
    "klagede over rengøringsstandard på værelset [Klageskema, s. 2]. "
    "Rejseselskabet tilbød værelsesskift dag 2 [Sagsakter — C4C-notat "
    "14/8-2024], hvilket i tilsvarende sager har været tilstrækkeligt til "
    "at afvise klagen [Afgørelse 19-1467 (2019)].'\n"
    "\n"
    "Hvis du ikke kan finde en konkret kilde til en påstand, må du IKKE "
    "fremsætte påstanden. Skriv i stedet: '[Kilde ikke fundet i materialet — "
    "skal verificeres af sagsbehandler]'.\n"
    "\n"
    "Du må ALDRIG trække på almen juridisk viden uden for vidensbanken, og "
    "du må ALDRIG opdigte afgørelser, bilagsnumre, sidetal eller datoer. Hvis "
    "du ikke kender sidetallet, skriv fx [Bilag 05, sidetal ikke angivet] — "
    "men opfind aldrig et sidetal.\n"
    "\n"
    "VIDENSBANKEN indeholder fire typer dokumenter:\n"
    "  - AFGØRELSE: en tidligere kendelse fra Pakkerejseankenævnet, hvor "
    "udfaldet (fuld medhold / delvist medhold / afvist) og beløb fremgår af teksten. "
    "Disse er din juridiske præcedens.\n"
    "  - KLAGE: en indkommen klage, der IKKE er afgjort endnu. Her kender vi "
    "kravet, men ikke udfaldet. Brug kun KLAGER som kontekst/fingerpeg om "
    "hvilke typer sager rejseselskabet har haft — ALDRIG som juridisk præcedens.\n"
    "  - REJSESELSKABETS VILKÅR: rejsebetingelser, regler, retningslinjer og "
    "procedurer hentet direkte fra rejseselskabets egen hjemmeside. Dette er "
    "kontraktgrundlaget mellem rejseselskabet og kunden og skal bruges aktivt "
    "i argumentationen — 'ifølge punkt X i rejsevilkårene ...'.\n"
    "  - PAKKEREJSELOVEN: paragraffer fra den danske pakkerejselov (lov nr. 1666 "
    "af 2017). Dette er det lovmæssige fundament for alle pakkerejsesager i "
    "Danmark. Henvis konkret til paragraffer hvor relevant — fx '§ 19 om mangler' "
    "eller '§ 22 om forholdsmæssigt afslag'. Loven har forrang over vilkår."
)


def _format_dato(dato):
    if dato is None:
        return "ukendt dato"
    try:
        return dato.strftime("%d-%m-%Y")
    except Exception:
        return str(dato)


def _trim(tekst):
    if tekst is None:
        return ""
    if len(tekst) > MAX_CHARS_PR_SAG:
        return tekst[:MAX_CHARS_PR_SAG] + "\n[...tekst forkortet...]"
    return tekst


def udtraek_sagen_angaar(tekst, max_chars=2000):
    """
    Trækker den juridisk MEST sigende del af en Pakkerejse-Ankenævn-
    afgørelse ud — typisk titel + 'Klagen angår'/'Sagen angår'-afsnit
    + de første par paragraffer af nævnets bemærkninger.

    Bruges som FOKUSERET input når vi sammenligner en ny sag med
    tidligere afgørelser — frem for at sende 5500 rå tegn med
    procedurel støj (datoer, adresser, sagsbehandler-navne osv.) sender
    vi de tegn der faktisk fortæller hvad sagen ER om.

    Robust mod variationer i scrapet markdown:
      - Finder titel-linjer (caps, kort, øverst i dokumentet)
      - Søger efter 'Klagen angår', 'Sagen angår', 'Klagepunkter',
        'Hovedspørgsmål' eller lignende anchor-ord
      - Inkluderer 1-2 paragraffer EFTER hvert anchor
      - Falder tilbage til de første ~1500 tegn hvis ingen anchor findes

    Returnerer en streng på max ~max_chars tegn — tilstrækkeligt til
    at AI'en kan vurdere relevans uden at blive overvældet af støj.
    """
    import re as _re

    if not tekst:
        return ""

    tekst = tekst.strip()
    if len(tekst) <= max_chars:
        # Allerede kort nok — returnér uændret
        return tekst

    dele = []

    # ---------- 1. TITEL ----------
    # De første 5-10 ikke-tomme linjer indeholder typisk titel + sagsnr.
    # Vi tager de første linjer indtil vi finder en der ligner brødtekst.
    titel_linjer = []
    for linje in tekst.split("\n")[:20]:
        s = linje.strip()
        if not s:
            continue
        # Brødtekst-detektor: hvis linjen er meget lang ELLER slutter med
        # punktum + lille bogstav, er det sandsynligvis et sætningsfragment
        if len(s) > 200 or _re.search(r"[a-zæøå]\.\s+[a-zæøå]", s):
            break
        titel_linjer.append(s)
        if len(titel_linjer) >= 5:
            break
    if titel_linjer:
        dele.append("=== TITEL / OVERSKRIFT ===\n" + "\n".join(titel_linjer))

    # ---------- 2. ANCHOR-AFSNIT ----------
    # Find afsnit der starter med specifikke nøgleord — disse er de
    # juridisk mest sigende dele af afgørelsen.
    ANCHORS = [
        r"Klagen\s+angår",
        r"Sagen\s+angår",
        r"Hoved\s*spørgsmål(et)?",
        r"Klagens?\s+kernepunkt(er)?",
        r"Klage(?:r|n)?s?\s+påstand",
        r"Klagepunkt(er)?",
        r"Nævnets?\s+bemærkninger?\s+og\s+afgørelse",
        r"Konklusion",
    ]
    for anchor in ANCHORS:
        # Match anchor + alt frem til næste blank linje + max 800 tegn
        match = _re.search(
            anchor + r"[:\s]*\n*([\s\S]{1,800}?)(?=\n\s*\n|\Z)",
            tekst,
            _re.IGNORECASE,
        )
        if match:
            anchor_navn = _re.search(anchor, match.group(0), _re.IGNORECASE)
            anchor_safe = (
                anchor_navn.group(0).strip() if anchor_navn else "Anchor"
            )
            indhold = match.group(1).strip()
            if indhold and len(indhold) > 30:
                dele.append(
                    f"=== {anchor_safe.upper()} ===\n{indhold}"
                )

    # ---------- 3. FALLBACK hvis ingen anchors fundet ----------
    if len(dele) <= 1:  # kun titel, eller intet
        # Tag de første ~1200 tegn af brødteksten
        body_start = "\n".join(tekst.split("\n")[len(titel_linjer):])
        dele.append("=== UDDRAG ===\n" + body_start[:1200])

    samlet = "\n\n".join(dele)

    # Cap til max_chars
    if len(samlet) > max_chars:
        samlet = samlet[:max_chars - 3] + "..."

    return samlet


def _byg_vidensbank_tekst(sager):
    """
    Bygger én tekstblok med de udvalgte relevante sager, med tydelig markering
    af dokumenttype (AFGØRELSE / KLAGE / VILKÅR) så Claude kan skelne.

    'sager' er en liste af dicts: {"filnavn", "indhold", "oprettet_dato",
    "dokumenttype", "kilde_url" (valgfri), "similarity" (valgfri)}.
    """
    blokke = []
    for sag in sager:
        filnavn = sag.get("filnavn") or "ukendt_fil"
        indhold = _trim(sag.get("indhold") or "")
        dato = _format_dato(sag.get("oprettet_dato"))
        doktype = sag.get("dokumenttype") or "afgoerelse"
        kilde = sag.get("kilde_url")

        if doktype == "klage":
            label = "KLAGE (ikke afgjort endnu)"
        elif doktype == "vilkaar":
            label = "REJSESELSKABETS VILKÅR"
        elif doktype == "lovgivning":
            label = "PAKKEREJSELOVEN"
        else:
            label = "AFGØRELSE"

        # Vis evt. similarity-score så Claude ved hvor godt denne sag matcher
        sim = sag.get("similarity")
        header_dele = [f"=== {label}", f"Filnavn: {filnavn}", f"Gemt: {dato}"]
        if sim is not None:
            header_dele.append(f"Relevans: {sim:.2f}")
        if kilde:
            header_dele.append(f"Kilde: {kilde}")
        header_dele.append("===")
        header = " | ".join(header_dele)

        blokke.append(f"{header}\n{indhold}")
    return "\n\n".join(blokke)


def _opgave_tekst():
    """
    Den strukturerede opgaveformulering som vi beder Claude følge.
    Kræver eksplicit et udfalds- og beløbs-linje lige under hver reference.
    """
    return (
        "OPGAVE — strukturér dit svar sådan her:\n\n"
        "1. RELEVANTE REFERENCER\n"
        "   Identificér de 3-5 mest relevante sager fra vidensbanken. For HVER reference "
        "skal du bruge dette nøjagtige format (markdown):\n"
        "\n"
        "   **[filnavn] ([dato eller år])**\n"
        "   [UDFALDS-LINJE — se nedenstående regler]\n"
        "   [1-2 sætninger om hvorfor denne sag er relevant]\n"
        "\n"
        "   UDFALDS-LINJEN skal være én af disse præcise formater, baseret på hvad "
        "dokumentet viser:\n"
        "     • 'Fuld medhold af krav på X kr.'\n"
        "     • 'Delvist medhold på Y kr. af samlet krav på X kr.'\n"
        "     • 'Afvist samlet krav på X kr.'\n"
        "     • 'Under behandling — ikke afgjort endnu. Krav: X kr.' "
        "(bruges KUN for dokumenter markeret som KLAGE i vidensbanken)\n"
        "\n"
        "   Eksempler på korrekte reference-blokke:\n"
        "\n"
        "   **19-1467.docx (2019)**\n"
        "   Fuld medhold af krav på 15.000 kr.\n"
        "   Sagen omhandler samme type indlogeringsmangler som nærværende sag.\n"
        "\n"
        "   **afgoerelse_2022_05.pdf (maj 2022)**\n"
        "   Delvist medhold på 2.500 kr. af samlet krav på 10.000 kr.\n"
        "   Tilsvarende faktum om forsinket fly pga. strejke.\n"
        "\n"
        "   **21-0834.pdf (2021)**\n"
        "   Afvist samlet krav på 20.000 kr.\n"
        "   Nævnet anså forholdet for usædvanlig omstændighed, hvilket også er relevant her.\n"
        "\n"
        "   Læs dokumentindholdet grundigt for at finde det præcise beløb og udfald. "
        "Hvis beløbet ikke fremgår eksplicit af teksten, skriv 'beløb fremgår ikke' i stedet for X.\n"
        "\n"
        "2. JURIDISK ARGUMENTATION\n"
        "   Opstil de stærkeste argumenter for rejseselskabets forsvar baseret på "
        "referencerne ovenfor. Henvis eksplicit til filnavn og år (fx '(19-1467, 2019)').\n\n"
        "3. SANDSYNLIGHEDSVURDERING\n"
        "   Giv et estimat for tre mulige udfald baseret UDELUKKENDE på vidensbanken. "
        "Procentsatserne SKAL summe til 100%.\n\n"
        "   Brug præcis dette format (markdown):\n"
        "\n"
        "   - **Fuld medhold til klager:** X%\n"
        "     Begrundelse: [1-2 sætninger med henvisning til konkrete afgørelser]\n"
        "\n"
        "   - **Delvist medhold til klager:** Y%\n"
        "     Begrundelse: [1-2 sætninger med henvisning til konkrete afgørelser]\n"
        "\n"
        "   - **Afvisning af klagen (fuld medhold til rejseselskabet):** Z%\n"
        "     Begrundelse: [1-2 sætninger med henvisning til konkrete afgørelser]\n"
        "\n"
        "   VIGTIGT: Hvert procenttal skal kunne forsvares ud fra mønstre i "
        "vidensbanken — hvor mange tilsvarende sager gav hvilket udfald. Hvis "
        "vidensbanken ikke har tilstrækkeligt grundlag (fx kun 1-2 tilsvarende "
        "afgørelser), skal du skrive 'Lavt grundlag' ud for det udfald hvor "
        "grundlaget er tyndt.\n\n"
        "4. KONKLUSION I ÉN LINJE\n"
        "   En enkelt sætning der opsummerer det mest sandsynlige udfald og "
        "rejseselskabets anbefalede strategi."
    )


def _hent_relevante_eller_fald_tilbage(soge_tekst, udeluk_filnavn=None):
    """
    Finder relevante sager via embedding-søgning og kombinerer fire typer:
      - De TOP_K_AFGOERELSER mest relevante AFGØRELSER (juridisk præcedens)
      - De TOP_K_VILKAAR mest relevante VILKÅR-passager (kontraktgrundlaget)
      - De TOP_K_LOVGIVNING mest relevante PAKKEREJSELOV-paragraffer
      - KLAGER bliver ikke hentet separat (klager er kun kontekst)

    Returnerer en kombineret liste. Hvis Voyage er nede eller ingen
    embeddings findes, falder vi tilbage til at sende et begrænset udvalg
    af alle sager, så systemet aldrig står helt stille.
    """
    sporgsmaal_emb = embed_sporgsmaal(soge_tekst)
    if sporgsmaal_emb is not None:
        afgoerelser = find_relevante_sager(
            sporgsmaal_emb,
            top_k=TOP_K_AFGOERELSER,
            udeluk_filnavn=udeluk_filnavn,
            dokumenttype="afgoerelse",
        )
        vilkaar = find_relevante_sager(
            sporgsmaal_emb,
            top_k=TOP_K_VILKAAR,
            udeluk_filnavn=udeluk_filnavn,
            dokumenttype="vilkaar",
        )
        lovgivning = find_relevante_sager(
            sporgsmaal_emb,
            top_k=TOP_K_LOVGIVNING,
            udeluk_filnavn=udeluk_filnavn,
            dokumenttype="lovgivning",
        )
        kombineret = afgoerelser + vilkaar + lovgivning
        if kombineret:
            return kombineret, "rag"

    # Fallback: hent et begrænset udvalg fra alle sager. Dette er langsommere
    # men sikrer at systemet virker selv hvis embeddings fejler.
    print("DEBUG: RAG-søgning gav intet resultat — falder tilbage til alle sager")
    alle = hent_alle_sager()
    if udeluk_filnavn:
        alle = [s for s in alle if s.get("filnavn") != udeluk_filnavn]
    return alle[:TOP_K_FALLBACK], "fallback"


def _faerdiggoer_hvis_afkortet(
    response,
    system_prompt,
    messages,
    max_tokens=None,
    max_rounds=3,
):
    """
    Tjekker om et svar fra Anthropic er blevet afkortet (stop_reason ==
    'max_tokens'). Hvis ja, laves ét eller flere fortsættelses-kald hvor
    modellen bliver bedt om at skrive videre, indtil svaret er komplet
    eller vi har ramt max_rounds.

    Returnerer den samlede tekst — altid afsluttet med en hel sætning.

    response:      det initielle message-response fra client.messages.create
    system_prompt: samme system-prompt som i det initielle kald
    messages:      samme messages-liste som i det initielle kald
    max_tokens:    max_tokens for hvert fortsættelses-kald (default MAX_TOKENS)
    max_rounds:    maksimalt antal fortsættelser (sikkerhedsnet)
    """
    if max_tokens is None:
        max_tokens = MAX_TOKENS

    try:
        samlet_tekst = response.content[0].text
    except Exception:
        return ""

    stop = getattr(response, "stop_reason", None)
    runder = 0

    while stop == "max_tokens" and runder < max_rounds:
        runder += 1
        print(
            f"DEBUG: Svar afkortet (runde {runder}) — fortsætter via "
            "continuation-kald"
        )
        try:
            # Byg nye messages der inkluderer det delvise svar som
            # assistant-turn og beder modellen om at fortsætte
            # præcis hvor den slap. Vi tilføjer ikke et nyt bruger-
            # spørgsmål — Anthropic forstår 'prefill'-mønstret.
            fortsaet_msgs = list(messages) + [
                {"role": "assistant", "content": samlet_tekst},
            ]
            fortsaettelse = client.messages.create(
                model=MODEL,
                max_tokens=max_tokens,
                temperature=0,
                system=system_prompt,
                messages=fortsaet_msgs,
            )
            ekstra = fortsaettelse.content[0].text or ""
            if not ekstra.strip():
                break
            samlet_tekst += ekstra
            stop = getattr(fortsaettelse, "stop_reason", None)
        except Exception as e:
            print(f"DEBUG: Continuation-kald fejlede: {e}")
            break

    return samlet_tekst


def spoerg_ai(spoergsmaal, sager=None):
    """
    Stil et spørgsmål mod vidensbanken uden nogen ny klage vedhæftet.

    'sager'-parameteren bevares for bagudkompatibilitet men ignoreres nu —
    vi finder selv de relevante sager via embedding-søgning.
    """
    try:
        relevante, mode = _hent_relevante_eller_fald_tilbage(spoergsmaal)

        if not relevante:
            return (
                "Vidensbanken er tom eller ingen sager kunne findes. "
                "Upload først nogle tidligere afgørelser i sidebaren."
            )

        vidensbank = _byg_vidensbank_tekst(relevante)

        user_content = (
            f"VIDENSBANK (de {len(relevante)} mest relevante sager for dit spørgsmål):\n"
            f"{vidensbank}\n\n"
            f"SPØRGSMÅL:\n{spoergsmaal}\n\n"
            f"{_opgave_tekst()}"
        )

        messages = [{"role": "user", "content": user_content}]
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            temperature=0,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        return _faerdiggoer_hvis_afkortet(
            response, SYSTEM_PROMPT, messages,
        )

    except Exception as e:
        return f"Fejl i forbindelsen til juriitech PAX: {str(e)}"


def _hent_anonymiseringsregler_tekst(max_tegn=MAX_CHARS_ANONYMISERINGSREGLER):
    """
    Henter ALLE anonymiseringsregler fra vidensbanken og returnerer dem
    som én konkateneret tekst der kan injiceres i anonymiserings-prompter.

    Disse stammer fra de fire autoritative kilder der auto-loades ved
    app-start (Datatilsynet x2, Jurabibliotek, EU Article 29 WP216) og er
    dermed en fast del af modellens forståelse — IKKE noget brugeren
    behøver scrape eller uploade.

    Resultatet caches i memory så vi ikke rammer databasen ved hver
    anonymisering. Returnerer tom streng hvis reglerne mangler (så
    anonymisering stadig virker, bare uden ekstern kontekst).
    """
    global _ANONYMISERINGSREGLER_CACHE
    if _ANONYMISERINGSREGLER_CACHE is not None:
        return _ANONYMISERINGSREGLER_CACHE

    try:
        chunks = hent_sager_af_type("anonymisering_regler")
    except Exception as e:
        print(f"DEBUG: Kunne ikke hente anonymiseringsregler: {e}")
        _ANONYMISERINGSREGLER_CACHE = ""
        return ""

    if not chunks:
        _ANONYMISERINGSREGLER_CACHE = ""
        return ""

    dele = []
    samlet_laengde = 0
    for c in chunks:
        indhold = (c.get("indhold") or "").strip()
        if not indhold:
            continue
        kilde = c.get("kilde_url") or ""
        blok_header = f"\n--- {c.get('filnavn','')} ({kilde}) ---\n"
        blok = blok_header + indhold
        if samlet_laengde + len(blok) > max_tegn:
            # Inkludér kun det der er plads til, så prompten aldrig
            # sprænger max-tokens
            resterende = max_tegn - samlet_laengde
            if resterende > 500:
                dele.append(blok[:resterende] + "\n[...afkortet...]")
            break
        dele.append(blok)
        samlet_laengde += len(blok)

    samlet = (
        "AUTORITATIVE ANONYMISERINGSREGLER (fast del af din træning — "
        "disse skal du altid følge):\n"
        + "\n".join(dele)
        + "\n\n--- SLUT PÅ AUTORITATIVE REGLER ---\n"
    )
    _ANONYMISERINGSREGLER_CACHE = samlet
    return samlet


ANONYMISERING_PROMPT = """
Du forbereder dokumenter (bilag) som TUI sender til
Pakkerejse-Ankenævnet sammen med svarbrevet. Disse bilag bruges som
dokumentation, og reglerne for hvad der må fremgå er ANDERLEDES end
for selve svarbrevet.

VIGTIGT: Dette er IKKE den samme anonymisering som svarbrevet. Følg
PRÆCIS de regler der står her — de overstyrer eventuelle generelle
anonymiseringsregler du måtte have lært andetsteds. Specifikt:
klagers grundlæggende kontaktoplysninger MÅ fremgå i bilag.

REGLER DU SKAL FØLGE:

1. KLAGER (kunden der har klaget) — INFORMATION BEVARES:
   - Klagers navn må gerne fremgå (skriv det som det står)
   - Klagers e-mailadresse må gerne fremgå
   - Klagers telefonnummer må gerne fremgå
   - Klagers postadresse må gerne fremgå
   - Klagers booking-/kundenummer må gerne fremgå
   - MEN følgende fjernes ALTID for klager:
     • CPR-numre → "[CPR fjernet]"
     • Bankoplysninger / kontonumre → "[bankoplysninger fjernet]"
     • Følsomme helbreds-, religiøse eller etniske oplysninger der
       IKKE er nødvendige for sagen → fjernes

2. TUI-MEDARBEJDERE (After Travel team, kundeservice, salg) OG
   TUI-GUIDER (på destinationen):
   - Erstattes konsekvent med "Fornavn, TUI" — efternavn + titel/rolle
     fjernes
   - "Maria Hansen, After Travel" → "Maria, TUI"
   - "Vores guide Søren tog imod os" → "Søren, TUI tog imod os"
   - "Pernille fra TUI svarede" → "Pernille, TUI svarede"
   - "Customer service-medarbejder Lars Olsen" → "Lars, TUI"
   - Hvis personen KUN har efternavn eller titel (intet fornavn) →
     erstat hele referencen med "TUI"
     • "Hr. Schmidt fra TUI" → "TUI"
     • "Vores After Travel-medarbejder" → "TUI"

3. HOTELLET OG TUIs EKSTERNE SAMARBEJDSPARTNERE — TITEL + FORNAVN:
   - Hotelnavn, hotelkæde, hotelmærke → BEVARES
   - Hotellets logo, adresse, beliggenhed, faciliteter → BEVARES
   - Hotellets type, klasse, beskrivelser → BEVARES
   - MEN navngivne ansatte hos hotellet/eksterne partnere →
     "Titel + Fornavn" (efternavn fjernes, INGEN TUI tilføjes —
     fordi de IKKE er TUI-ansatte)
     • "Hotelmanager Carlos Rodriguez" → "Hotelmanager Carlos"
     • "Receptionist Maria Garcia" → "Receptionist Maria"
     • "Direktør John Smith" → "Direktør John"
     • "Concierge Pierre Dubois" → "Concierge Pierre"
   - Hvis personen kun har efternavn eller titel uden fornavn →
     bevar titlen alene (eller "[ekstern partner]" hvis ingen titel)
     • "Hr. Schmidt fra hotellet" → "[ekstern partner]"
     • "Hotellets manager" → "Hotellets manager"

   VIGTIGT: Forskellen mellem TUI-medarbejdere og eksterne
   samarbejdspartnere SKAL bevares:
   - TUI-medarbejdere/guider → "Fornavn, TUI" (signalerer TUI-tilknytning)
   - Eksterne ansatte → "Titel + Fornavn" (INGEN TUI — de er ikke
     ansat af TUI, kun samarbejdspartnere)

4. BIPERSONER (medrejsende der ikke selv er klager — ægtefælle,
   børn, venner, rejseledsagere):
   - Navne BEVARES (samme behandling som klager — bipersoner
     anonymiseres IKKE i bilag, kun i svarbrevet)
   - "Min kone Anne" → "Min kone Anne" (uændret)
   - "Mine børn Jonas og Sofie var med" → uændret
   - "Min ven Peter Hansen" → uændret
   - MEN følgende fjernes ALTID — også for bipersoner:
     • CPR-numre → "[CPR fjernet]"
     • Bankoplysninger / kontonumre → "[bankoplysninger fjernet]"
     • Følsomme helbreds-/religiøse/etniske oplysninger der IKKE
       er nødvendige for sagen → fjernes helt

5. OPLYSNINGER DER ALTID BEVARES (relevante for sagens afgørelse):
   - Hotelnavne, feriedestinationer, byer, lande, lufthavne
   - Rejsedatoer, rejseperiode, opholdets længde
   - Priser, beløb, valuta
   - Klagepunkterne i substans
   - Korrespondancens indhold og tone (med ovennævnte regler anvendt)
   - Bilagsnumre, sagsnumre, dokumentationskilder

6. FORMATERING:
   - Bevar tekstens struktur præcist (afsnit, overskrifter, lister)
   - Anvendelse af reglerne skal være ENSARTET gennem hele dokumentet
     (samme person → samme erstatning, hver gang)
   - Hvis noget er gennemstreget eller fremhævet i originalen, bevar
     markeringen på lignende vis

OUTPUT:
Returnér alene den bearbejdede tekst — ingen forklaringer, ingen
intro, ingen afslutningskommentarer. Start direkte med teksten.

Hvis teksten er meget kort eller ikke indeholder noget der skal
ændres, returnér den oprindelige tekst uændret.

---
TEKST DER SKAL BEARBEJDES:
"""


def anonymiser_tekst(tekst, filnavn=None):
    """
    Anonymiserer en enkelt tekstfil efter Ankenævnets regler + de
    autoritative anonymiseringsregler fra Datatilsynet, Jurabibliotek og
    EU Article 29 WP216 (loades automatisk ind i systemet).

    Returnerer den anonymiserede tekst.
    """
    try:
        if not tekst or not tekst.strip():
            return ""
        # For meget lange tekster trunkeres lidt for at holde inden for max_tokens
        if len(tekst) > 50_000:
            tekst = tekst[:50_000] + "\n\n[...teksten er trunkeret på grund af længde...]"

        header = f"\n[Filnavn: {filnavn}]\n" if filnavn else ""
        regler = _hent_anonymiseringsregler_tekst()

        # System-prompten får reglerne som fast baggrund — så modellen
        # altid har dem i "hjernen" uanset inputtets længde.
        #
        # KRITISK: Denne anonymisering er til BILAG, ikke til svarbrev.
        # TUI har sine egne specifikke regler (klagers info bevares, TUI
        # bruges som generisk navn for medarbejdere/guider, partner-
        # ansatte får fornavn + TUI). Disse TUI-regler OVERSTYRER de
        # generelle Ankenævn-/Datatilsyn-regler. Vi gør dette eksplicit
        # i system-prompten, så modellen ikke fejlagtigt anonymiserer
        # klagers navn fordi den autoritative kilde tilsiger det.
        system_prompt = (
            "Du forbereder dokumenter til TUI's brug i klagesager hos "
            "Pakkerejse-Ankenævnet. Følg de TUI-specifikke regler i "
            "brugerprompten PRÆCIST — disse regler overstyrer eventuelle "
            "andre anonymiseringsregler du måtte være trænet i. "
            "Hovedreglerne: (1) klagers navn og kontaktoplysninger MÅ "
            "fremgå i bilag (i modsætning til svarbrevet). (2) "
            "TUI-medarbejdere og TUI-guider erstattes med 'Fornavn, TUI' "
            "(fx 'Maria, TUI'). (3) Eksterne samarbejdspartnere som "
            "hotelpersonale erstattes med 'Titel + Fornavn' UDEN TUI "
            "(fx 'Hotelmanager Carlos', 'Receptionist Maria') — fordi de "
            "ikke er TUI-ansatte."
        )
        if regler:
            system_prompt += (
                "\n\n# BAGGRUNDSREGLER (kun til reference — TUI-reglerne "
                "i brugerprompten har FORRANG ved konflikt):\n\n" + regler
            )

        response = client.messages.create(
            model=MODEL,
            max_tokens=8000,
            temperature=0,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": ANONYMISERING_PROMPT + header + tekst,
            }],
        )
        return response.content[0].text

    except Exception as e:
        return f"[Fejl i anonymisering: {str(e)}]"


def _anonymiser_enkeltfil(fil):
    """
    Anonymiserer én fil (dict med nøglerne 'filnavn', 'type', 'tekst',
    'rolle'). Returnerer et resultat-dict med samme format som
    anonymiser_sag returnerer for hvert element.
    """
    filnavn = fil.get("filnavn", "ukendt")
    rolle = fil.get("rolle", "ukendt")

    # Vejledninger/retningslinjer fra Nævnet skal ikke anonymiseres
    if rolle == "vejledning":
        return {
            "filnavn": filnavn,
            "original_laengde": 0,
            "anonymiseret_tekst": "",
            "status": "sprunget_over",
            "bemaerkning": (
                "Vejledning/retningslinjer fra Nævnet — "
                "ikke relevant at anonymisere"
            ),
        }

    if rolle == "høring":
        return {
            "filnavn": filnavn,
            "original_laengde": 0,
            "anonymiseret_tekst": "",
            "status": "sprunget_over",
            "bemaerkning": (
                "Høringsbrev fra Nævnet — skal ikke sendes tilbage, "
                "anonymiseres ikke"
            ),
        }

    if fil.get("type") == "pdf_bytes":
        return {
            "filnavn": filnavn,
            "original_laengde": 0,
            "anonymiseret_tekst": "",
            "status": "sprunget_over",
            "bemaerkning": (
                "Scannet PDF — kan ikke anonymiseres automatisk "
                "(kræver OCR). Anonymisér manuelt eller konvertér først "
                "til søgbar PDF."
            ),
        }

    if fil.get("type") in ("image_bytes", "mp4_skipped"):
        return {
            "filnavn": filnavn,
            "original_laengde": 0,
            "anonymiseret_tekst": "",
            "status": "sprunget_over",
            "bemaerkning": (
                "Billede eller video — kan ikke anonymiseres tekstuelt. "
                "Gennemse manuelt inden sagsfremstilling."
            ),
        }

    tekst = fil.get("tekst") or ""
    if not tekst.strip():
        return {
            "filnavn": filnavn,
            "original_laengde": 0,
            "anonymiseret_tekst": "",
            "status": "sprunget_over",
            "bemaerkning": "Tom fil — intet at anonymisere",
        }

    try:
        anonymiseret = anonymiser_tekst(tekst, filnavn=filnavn)
        return {
            "filnavn": filnavn,
            "original_laengde": len(tekst),
            "anonymiseret_tekst": anonymiseret,
            "status": "ok",
            "bemaerkning": (
                f"Anonymiseret. Original: {len(tekst)} tegn, "
                f"anonymiseret: {len(anonymiseret)} tegn."
            ),
        }
    except Exception as e:
        return {
            "filnavn": filnavn,
            "original_laengde": len(tekst),
            "anonymiseret_tekst": "",
            "status": "fejl",
            "bemaerkning": f"Fejl: {e}",
        }


def anonymiser_valgte_filer(filer_liste):
    """
    Anonymiserer en LISTE af filer (enhver blanding af sag-filer og
    sagsakter-filer). Bruges når brugeren selv vælger hvilke filer der
    skal anonymiseres via checkboxes i UI'et.

    Returnerer en liste af resultat-dicts — ét pr. fil, i samme
    rækkefølge som input.
    """
    if not filer_liste:
        return []
    return [_anonymiser_enkeltfil(f) for f in filer_liste]


def anonymiser_sag(sag):
    """
    Anonymiserer alle tekst-baserede filer i en sag. Returnerer en liste af
    dicts:
      [{"filnavn": str, "original_laengde": int, "anonymiseret_tekst": str,
        "status": "ok"|"sprunget_over"|"fejl", "bemaerkning": str}]

    Scannede PDF'er springes over (kræver vision + OCR som vi ikke har
    implementeret endnu — den version kan vi bygge senere).
    """
    resultat = []
    filer = sag.get("filer") or []

    for fil in filer:
        filnavn = fil.get("filnavn", "ukendt")
        rolle = fil.get("rolle", "ukendt")

        # Spring vejledninger og interne meta-filer over
        if rolle == "vejledning":
            resultat.append({
                "filnavn": filnavn,
                "original_laengde": 0,
                "anonymiseret_tekst": "",
                "status": "sprunget_over",
                "bemaerkning": "Vejledning/retningslinjer fra Nævnet — ikke relevant at anonymisere",
            })
            continue

        # Spring høringsbrevet over — det sendes IKKE tilbage til Nævnet,
        # så det behøver ikke anonymiseres (og det er allerede Nævnets eget)
        if rolle == "høring":
            resultat.append({
                "filnavn": filnavn,
                "original_laengde": 0,
                "anonymiseret_tekst": "",
                "status": "sprunget_over",
                "bemaerkning": "Høringsbrev fra Nævnet — skal ikke sendes tilbage, anonymiseres ikke",
            })
            continue

        if fil.get("type") == "pdf_bytes":
            resultat.append({
                "filnavn": filnavn,
                "original_laengde": 0,
                "anonymiseret_tekst": "",
                "status": "sprunget_over",
                "bemaerkning": (
                    "Scannet PDF — kan ikke anonymiseres automatisk (kræver OCR). "
                    "Anonymisér manuelt eller konvertér først til søgbar PDF."
                ),
            })
            continue

        tekst = fil.get("tekst") or ""
        if not tekst.strip():
            resultat.append({
                "filnavn": filnavn,
                "original_laengde": 0,
                "anonymiseret_tekst": "",
                "status": "sprunget_over",
                "bemaerkning": "Tom fil — intet at anonymisere",
            })
            continue

        try:
            anonymiseret = anonymiser_tekst(tekst, filnavn=filnavn)
            resultat.append({
                "filnavn": filnavn,
                "original_laengde": len(tekst),
                "anonymiseret_tekst": anonymiseret,
                "status": "ok",
                "bemaerkning": (
                    f"Anonymiseret. Original: {len(tekst)} tegn, "
                    f"anonymiseret: {len(anonymiseret)} tegn."
                ),
            })
        except Exception as e:
            resultat.append({
                "filnavn": filnavn,
                "original_laengde": len(tekst),
                "anonymiseret_tekst": "",
                "status": "fejl",
                "bemaerkning": f"Fejl: {e}",
            })

    return resultat


TJEKLISTE_OPGAVE = """
OPGAVE: Læs høringsbrevet fra Pakkerejse-Ankenævnet nøje og udtræk den
EKSAKTE tjekliste over hvad Nævnet beder rejsearrangøren fremsende eller
oplyse. Sammenhold derefter med de uploadede bilag og identificér hvad
der ER dækket og hvad der MANGLER.

OUTPUT — brug nøjagtigt dette format (markdown):

## 📋 Tjekliste fra høringsbrevet

For HVERT punkt Nævnet beder om, lav en linje i formatet:

**N. [Punktet fra høringsbrevet, gengivet ordret eller tæt på ordret]**
- Status: ✅ DÆKKET / ⚠️ DELVIST DÆKKET / ❌ MANGLER / ℹ️ KRÆVER AFKLARING
- Fundet i: [filnavn(e) fra de uploadede bilag, hvis relevant]
- Bemærkning: [1-2 sætninger der forklarer hvad der er dækket / hvad der mangler / hvad juristen skal udfylde]

Eksempler på korrekte punkter:

**1. Første bekræftelsesmail for bestillingen med oversigt over vedhæftede dokumenter, afsender/modtager, dato og emne.**
- Status: ❌ MANGLER
- Fundet i: (ingen)
- Bemærkning: Bekræftelsesmailen er ikke blandt de uploadede bilag. Juristen skal fremsende den fra TUI's e-mail-arkiv.

**2. Første og sidste udgave af rejsebeviset.**
- Status: ⚠️ DELVIST DÆKKET
- Fundet i: Bilag 03 billet version 8.pdf
- Bemærkning: Version 8 (sidste udgave) er uploadet, men første udgave mangler.

Efter hele tjeklisten, tilføj en kort opsummering:

## 🎯 Opsummering

- **Dækket:** X af Y punkter
- **Mangler:** liste over punkter der ikke er dækket
- **Bemærkning:** 1-2 sætninger om hvor stor en indsats der skal til for at fuldstændiggøre svaret

STRENGE KRAV:
- Læs høringsbrevet grundigt og gengiv Nævnets egne formuleringer så præcist som muligt.
- Gennemgå ALLE de uploadede bilag før du markerer noget som "manglende".
- Opfind ikke punkter Nævnet ikke har bedt om.
- Hvis høringsbrevet ikke findes blandt bilagene, skriv: "Kan ikke lave tjekliste — høringsbrev mangler i uploadede filer."
"""


def generer_tjekliste(sag):
    """
    Læser høringsbrev + alle bilag og producerer en struktureret tjekliste
    over hvad Nævnet har bedt om, og hvad der er dækket af bilagene.
    """
    try:
        filer = sag.get("filer") or []
        if not filer:
            return "Ingen filer uploadet — kan ikke lave tjekliste."

        # Tjek om der er et høringsbrev
        har_hoering = any(f.get("rolle") == "høring" for f in filer)
        if not har_hoering:
            return (
                "⚠️ Jeg kan ikke se et høringsbrev blandt de uploadede filer. "
                "Upload venligst høringsbrevet fra Ankenævnet (typisk kaldet "
                "'Høring R.docx' eller lignende) så kan jeg lave tjeklisten."
            )

        indled = (
            "SAGSPAKKEN (høring fra Ankenævnet + bilag fra sagen):\n"
            f"Antal filer: {len(filer)}."
        )
        slutning = TJEKLISTE_OPGAVE

        user_content = _byg_sag_content(sag, indled, slutning)

        response = client.messages.create(
            model=MODEL,
            max_tokens=6000,
            temperature=0,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        return response.content[0].text

    except Exception as e:
        return f"Fejl i generering af tjekliste: {str(e)}"


def byg_svarbrev_opgave(
    inkluder_kildehenvisninger: bool = False,
    verificerede_klagepunkter: list = None,
    tidsforhold: dict = None,
) -> str:
    """Bygger svarbrev-prompten dynamisk.

    inkluder_kildehenvisninger:
        - False (default): Brevet skal IKKE indeholde "[Bilag XX, s. Y]",
          paragraf-referencer eller andre kildehenvisninger. Brevet bliver
          kortere og mere flydende — i overensstemmelse med kollegaens
          ønske om et rent, ikke-akademisk svarbrev.
        - True: Brevet inkluderer præcise kildehenvisninger til bilag,
          rejsevilkår og pakkerejseloven (fx "[Bilag 04, s. 1]" og
          "jf. § 22"). Bruges når juristen specifikt har brug for at
          dokumentere argumentationens grundlag.

    verificerede_klagepunkter (valgfri men STÆRKT anbefalet):
        Liste over alle klagepunkter klager rejser, udtrukket på forhånd
        af udled_alle_klagepunkter(). Når listen er sat, injiceres den
        i prompten som autoritativt facit der SKAL adresseres punkt for
        punkt — det er den eneste pålidelige måde at sikre 100%
        klagepunkt-dækning i svarbrevet.
    """
    # Sektion om tidsforhold — kritisk forsvarsargument hvis klager
    # ikke har reklameret rettidigt. Pakkerejse-Ankenævnet vægter dette
    # ekstremt højt. Vi injicerer kun blokken hvis vi har faktiske
    # observationer at bygge på (ikke gætterier).
    tidsforhold_blok = ""
    if (
        tidsforhold
        and tidsforhold.get("har_problematisk_forsinkelse")
        and not tidsforhold.get("kunne_ikke_udledes")
    ):
        tidsforhold_blok = (
            "\nKRITISK FORSVARSARGUMENT — REKLAMATIONSRETTIDIGHED:\n"
            "Pakkerejse-Ankenævnet vægter rettidig reklamation MEGET "
            "HØJT. Følgende tidsforhold er udledt af bilagene og UDGØR "
            "et stærkt forsvarsargument der SKAL fremhæves i svarbrevet "
            "(typisk i et eget afsnit eller integreret i argumentationen "
            "for relevante klagepunkter):\n\n"
        )
        if tidsforhold.get("samlet_vurdering"):
            tidsforhold_blok += (
                f"  Samlet vurdering: {tidsforhold['samlet_vurdering']}\n\n"
            )
        for obs in tidsforhold.get("konkrete_observationer", []):
            tidsforhold_blok += f"  • {obs}\n"
        tidsforhold_blok += (
            "\nSvarbrevet SKAL adressere denne forsinkelse som "
            "forsvarsargument — TUI havde ikke mulighed for at "
            "afhjælpe manglen på destinationen, hvilket Nævnet "
            "lægger vægt på. Brug konkrete datoer i argumentationen.\n"
        )

    # Sektion om verificerede klagepunkter — kritisk for fuld dækning
    if verificerede_klagepunkter:
        klagepunkter_blok = (
            "\nVERIFICERET LISTE OVER ALLE KLAGEPUNKTER (SKAL ALLE "
            "ADRESSERES I BREVET):\n"
            "Følgende liste er udtrukket på forhånd af en dedikeret "
            "research-AI, og hvert punkt SKAL behandles i svarbrevet — "
            "uden undtagelse. Hvis et punkt udelades, betragtes brevet "
            "som ufuldstændigt. Adressér ALLE punkter, også de små.\n\n"
        )
        for i, kp in enumerate(verificerede_klagepunkter, 1):
            klagepunkter_blok += f"  {i}. {kp}\n"
        klagepunkter_blok += (
            f"\nTotal: {len(verificerede_klagepunkter)} klagepunkter "
            "der ALLE skal adresseres med egen behandling i brevet.\n"
        )
    else:
        klagepunkter_blok = ""

    # Sektion om kildehenvisninger — varierer efter flag
    if inkluder_kildehenvisninger:
        kildehenvisninger_regel = (
            "KILDEHENVISNINGER:\n"
            "Brug præcise henvisninger til bilag, rejsevilkår og lov:\n"
            "  - Bilagshenvisninger: '[Bilag 04, s. 1]', "
            "'[Bilag 21, sidetal ikke angivet]'\n"
            "  - Rejsevilkår: 'jf. vilkårenes pkt. 5.1'\n"
            "  - Pakkerejselov: 'jf. pakkerejselovens § 22'\n"
        )
    else:
        kildehenvisninger_regel = (
            "KILDEHENVISNINGER:\n"
            "Brevet skal IKKE indeholde kildehenvisninger. Specifikt:\n"
            "  - INGEN '[Bilag XX, s. Y]' eller bilagshenvisninger\n"
            "  - INGEN 'jf. vilkårenes pkt. X.Y' eller vilkårshenvisninger\n"
            "  - INGEN 'jf. § XX' eller paragraf-referencer\n"
            "  - INGEN '[sidetal ikke angivet]'\n"
            "Argumentationen står på egne ben — fakta og logik gør "
            "brevet stærkt, ikke konstant kildehenvisning. Brevet bliver "
            "et flydende, naturligt svar — ikke en akademisk afhandling.\n"
        )

    return f"""
OPGAVE: Generer et KOMPLET UDKAST til svarbrev fra {REJSESELSKAB_NAVN} til
Pakkerejseankenævnet. Skriv i et formelt, professionelt juridisk sprog —
men ikke stivt. Brevet skal være kort, direkte og fokuseret.

LÆNGDE — ABSOLUT KRAV:
Brevet skal være KORT. Maksimalt 1-2 A4-sider (omtrent 500-900 ord samlet).
Pakkerejse-Ankenævnet ønsker ikke lange retsskrivelser — hold dig kort,
præcist og juridisk skarpt. Undlad fyld, gentagelser og retoriske
formuleringer. Det bedste svarbrev er det korte, klare og velfunderede.

INDLEDNINGEN:
Brevet starter med PRÆCIS denne ene sætning:
  "{REJSESELSKAB_NAVN} vil hermed komme med sine bemærkninger samt bilag til sagen."
Ingen "Til: Pakkerejse-Ankenævnet"-header, ingen "Vedr."-linje, ingen
sagsnummer-linje, ingen lange standard-introer som "har modtaget
Ankenævnets høring af [dato] vedrørende ovennævnte klage". Den ene
sætning ovenfor er HELE indledningen.

OBLIGATORISK FAKTUM-AFSNIT (kommer LIGE EFTER indledningen):
Direkte efter indledningen skal brevet have et kort, faktuelt
oversigts-afsnit (3-6 sætninger) der præsenterer sagens basale rammer
— uden argumentation. Dette afsnit MÅ IKKE udelades. Inkludér:
  • Klagers booking/rejse: hotel-navn og destination (by, land)
  • Udrejse- og hjemrejse-dato (eller rejseperiode)
  • Antal rejsende
  • Rejsens samlede pris
  • Eventuel allerede udbetalt kompensation (med beløb)
Eksempel-formulering:
  "Klager rejste den X. juni 2025 til [Hotel-navn], [Destination, Land],
  med hjemrejse den Y. juni 2025. Rejsen omfattede [N] rejsende og havde
  en samlet pris på [beløb] kr. {REJSESELSKAB_NAVN} har forud for
  nævnsbehandlingen udbetalt [beløb] kr. i kompensation."
Dette afsnit giver Nævnet en hurtig grundforståelse af sagen, før
argumentationen starter. UDEN det er brevet sværere at læse.

INKLUDÉR IKKE en standard-opsummering af klagers samlede krav i kroner
og ører (fx "Det opdaterede krav udgør herefter X DKK, subsidiært
Y DKK..."). Hvis specifikke beløb er relevante for argumentationen, kan
de indgå løbende i teksten — men ikke som en samlet krav-sammenfatning.

OVERSÆTTELSE FRA ENGELSK (vigtig):
Mange bilag er på engelsk (hotel-mails, partner-korrespondance,
booking-bekræftelser). Hele svarbrevet skal være på korrekt JURIDISK
DANSK. Når du citerer fra eller henviser til engelske dokumenter:
  • Oversæt PRÆCIST til dansk i selve brevteksten
  • Brug danske juridiske termer (mangel, rettidig reklamation,
    forholdsmæssigt afslag — ikke deficiency, timely complaint,
    proportional reduction)
  • Konverter datoer til dansk format ('12. juni 2025')
  • Konverter beløb hvor relevant ('500 EUR (ca. 3.730 DKK)')
  • Bevar egennavne (hotel-, person-, by-navne) på originalsproget
  • Hvis et engelsk citat er centralt for argumentationen, kan
    originalcitatet stå i parentes — fx '"Vi tilbød afhjælpning"
    (oversat fra engelsk: "We offered remediation")'
Pakkerejse-Ankenævnet læser kun dansk — alt skal kunne forstås uden
opslag i originalbilag.

UNDLAD bevidst at citere tidligere afgørelser fra Nævnet — det forventes
ikke i rejsearrangørens svar og gør brevet for detaljeret.

UNDLAD også alt der lyder for 'domstolsagtigt':
  - Ingen "påstand"-sektion
  - Ingen formel "konklusion"-sektion med "anmoder Nævnet om at ..."
  - Ingen udtrykkelig "stillingtagen til kravet"-overskrift
  Pakkerejse-Ankenævnet er ikke en domstol. Skriv direkte og jordnært.

TERMINOLOGI — brug disse konsekvent:
  • Rejseselskabet omtales ALTID som "{REJSESELSKAB_NAVN}" — aldrig "rejseselskabet", "vi", "rejsearrangøren" eller lignende.
  • Klageren omtales ALTID som "klager" med LILLE k — det er en titel/funktion, ikke et navn. Brug stort K KUN i begyndelsen af en sætning. Aldrig "Klager 1", "Klager 2" — kun "klager", uanset hvor mange der er.
  • Underskriftslinje/afsender skal altid være "{REJSESELSKAB_SAGSBEHANDLER}" — aldrig "[Navn på sagsbehandler]" eller personnavne.

KRITISK — ALLE KLAGEPUNKTER SKAL ADRESSERES:
Du SKAL identificere og adressere HVERT ENESTE klagepunkt klager rejser
mod {REJSESELSKAB_NAVN} — uden undtagelse. Læs klagen og bilagene TO
GANGE og kryds hvert klagepunkt af, før du skriver. Hvis klager nævner
8 forskellige problemer, skal alle 8 adresseres i brevet — ikke kun
de 4 'vigtigste'. At udelade et klagepunkt giver Nævnet indtryk af at
{REJSESELSKAB_NAVN} ignorerer klager. Adressér også de 'små' punkter
(fx kommunikation, ventetider, tone) — de kan kort behandles, men de
SKAL behandles.

{klagepunkter_blok}
{tidsforhold_blok}

ABSOLUT ANONYMISERING AF KLAGER (ufravigeligt krav):
Svarbrevet til Nævnet MÅ UNDER INGEN OMSTÆNDIGHEDER indeholde klagerens
navn eller andre personhenførbare oplysninger — hverken for- eller
efternavn, heller ikke i overskrifter, indledning, underskrift,
bilagshenvisninger, citater, e-mails eller andre steder. Følg disse
regler konsekvent i HELE brevet:

  • klager: ALTID "klager" med lille k (uanset hvor mange klagere — aldrig "Klager 1" eller "Klager 2"). Stort K kun ved sætningsstart.
  • {REJSESELSKAB_NAVN}s medarbejdere: omtales ikke ved navn — skriv i stedet "{REJSESELSKAB_SAGSBEHANDLER}" eller "{REJSESELSKAB_NAVN}"
  • Bipersoner (medrejsende ægtefælle, børn, rejseledsagere): "medrejsende" eller "Biperson 1", "Biperson 2"
  • Guider, hotelpersonale: "guiden", "hotelpersonalet" — ingen navne
  • CPR-numre → '[CPR fjernet]'
  • Fødselsdatoer (bortset fra rejsedatoer) → '[fødselsdato fjernet]'
  • Adresser (gadenavn + nr.) → '[adresse fjernet]'
  • Telefonnumre → '[telefon fjernet]'
  • E-mailadresser → '[e-mail fjernet]'
  • Booking-/kundenumre → maskeres (fx '12345678' → '12****78')
  • Bankoplysninger/kontonumre → '[bankoplysninger fjernet]'

Hvis klagen eller sagsakterne indeholder klagerens navn, SKAL du selv
anonymisere det — omskriv citater så navnet er erstattet med "klager".

Hotelnavne, destinationer, lufthavne, rejsedatoer, beløb og klagepunkter
bevares (de er nødvendige for sagens afgørelse).

STRUKTUR:
Brevet består af tre dele — UDEN nummererede sektion-overskrifter:

DEL 1 — INDLEDNING (én sætning):
  "{REJSESELSKAB_NAVN} vil hermed komme med sine bemærkninger samt bilag til sagen."

DEL 2 — FAKTUM-OVERSIGT (3-6 sætninger):
Kort, neutralt afsnit med rejse-grundoplysninger som beskrevet ovenfor
(hotel, destination, datoer, antal, pris, evt. allerede udbetalt
kompensation).

DEL 3 — JURIDISK VURDERING (brevets hoveddel):
Det eneste argumenterende afsnit. Brug emne-overskrifter til at
strukturere de enkelte klagepunkter (fx "Afstandsoplysninger og
markedsføring", "Transfer ved ankomst", "Poolens tilstand",
"Udflugterne") — men IKKE generiske rammeoverskrifter som
"1. Indledning" eller "2. Juridisk vurdering".

ÉN emne-overskrift PER klagepunkt — adressér ALLE klagers
klagepunkter, ingen undtagelser.

For hver emne-overskrift:
  - Indled med kort faktum-grundlag (1-3 sætninger).
  - Argumentér ud fra rejsevilkår, pakkerejselov og sagens fakta.
  - Afslut med {REJSESELSKAB_NAVN}s stilling til klagepunktet.

Afslut hele brevet med "Med venlig hilsen" og
"{REJSESELSKAB_SAGSBEHANDLER}". Ingen titler, ingen e-mailadresser, ingen
[Navn på sagsbehandler]-placeholder.

{kildehenvisninger_regel}

STRENGE KRAV:
- Max 1-2 A4-sider samlet. Hvis du er i tvivl, skriv kortere.
- ALLE klagepunkter skal adresseres — tæl dem i klagen og sørg for at
  hvert ét har sin egen behandling i brevet.
- Faktum-oversigten må IKKE udelades.
- Opfind ALDRIG fakta der ikke står i klagen, sagsakterne eller vidensbanken.
- Skriv på dansk i et formelt, professionelt juridisk sprog.
- Hvis en oplysning mangler der er nødvendig, skriv "[SAGSBEHANDLER UDFYLDER: ...]" som placeholder.
- Brug "{REJSESELSKAB_NAVN}" og "klager" (lille k) konsekvent. Aldrig "rejseselskabet", "K", "Klager 1" eller "Klager 2".
- Underskriftslinjen skal altid være "{REJSESELSKAB_SAGSBEHANDLER}".
- Tjek brevet igennem til sidst: ingen personnavne, ingen sektion-numre, ingen "domstols"-formuleringer, ingen "Til:"-headers, faktum-oversigt med, alle klagepunkter adresseret.
"""


# Backward compatibility — bevares så ældre kald fortsat virker (default
# uden kildehenvisninger, jf. kollegaens feedback).
SVARBREV_OPGAVE = byg_svarbrev_opgave(inkluder_kildehenvisninger=False)


def generer_svarbrev(
    klage,
    sagsakter=None,
    ekstra_instrukser=None,
    inkluder_kildehenvisninger=False,
):
    """
    Genererer et komplet udkast til svarbrev fra rejseselskabet til Nævnet.

    klage: dict fra processor.laes_klage() (samme format som spoerg_ai_med_klage)
    sagsakter: valgfri streng med C4C-notater, e-mails, bookingdetaljer
    ekstra_instrukser: valgfri streng hvis brugeren vil styre tonen eller
                       fokusere på bestemte argumenter
    inkluder_kildehenvisninger: bool. Hvis True inkluderer brevet
                       eksplicitte bilag-/lov-/vilkårs-referencer (fx
                       "[Bilag 04, s. 1]", "jf. § 22"). Default False —
                       brevet skrives uden kildehenvisninger, hvilket
                       giver et mere flydende, naturligt svar.

    Returnerer svarbrevets tekst som markdown, eller en fejlbesked.
    """
    try:
        # Byg den korrekte svarbrev-prompt baseret på flaget.
        # Bemærk: denne single-fil-version har ikke direkte adgang til
        # at udtrække klagepunkter (sag-objekt mangler), så den bruger
        # ikke verificerede_klagepunkter. Den primære flow er via
        # generer_svarbrev_til_sag() som har fuld dækning.
        svarbrev_opgave = byg_svarbrev_opgave(
            inkluder_kildehenvisninger=inkluder_kildehenvisninger
        )
        import base64
        klage_filnavn = klage.get("filnavn", "ukendt_klage")
        sagsakter_tekst = (sagsakter or "").strip()

        # Brug både klagen og sagsakterne som søgestreng, så vi får
        # relevant juridisk præcedens og de mest relevante vilkår-passager
        dele = []
        if klage.get("type") == "tekst":
            klage_tekst = klage.get("tekst") or ""
            if klage_tekst:
                dele.append(klage_tekst)
        if sagsakter_tekst:
            dele.append(sagsakter_tekst)
        dele.append("Udarbejd svarbrev til Pakkerejseankenævnet")
        soge_tekst = "\n\n".join(dele)

        relevante, _ = _hent_relevante_eller_fald_tilbage(
            soge_tekst, udeluk_filnavn=klage_filnavn
        )
        vidensbank = _byg_vidensbank_tekst(relevante) if relevante else (
            "(Ingen tidligere sager fundet i vidensbanken.)"
        )

        kontekst = (
            f"VIDENSBANK (de mest relevante afgørelser og rejsevilkårene):\n"
            f"{vidensbank}\n\n"
            f"NY KLAGE DER SKAL BESVARES — filnavn: {klage_filnavn}\n"
        )

        sagsakter_blok = ""
        if sagsakter_tekst:
            sagsakter_blok = (
                "\nSAGSAKTER (intern viden: C4C, e-mails, booking):\n"
                f"{sagsakter_tekst}\n"
            )

        ekstra = ""
        if ekstra_instrukser and ekstra_instrukser.strip():
            ekstra = (
                f"\nSÆRLIGE INSTRUKSER FRA JURISTEN (skal følges):\n"
                f"{ekstra_instrukser.strip()}\n"
            )

        prompt_tekst = kontekst + sagsakter_blok + ekstra + svarbrev_opgave

        if klage["type"] == "pdf_bytes":
            pdf_b64 = base64.standard_b64encode(klage["bytes"]).decode("utf-8")
            user_content = [
                {"type": "text", "text": kontekst + "Klagen er vedhæftet som PDF nedenfor:"},
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": pdf_b64,
                    },
                },
                {"type": "text", "text": sagsakter_blok + ekstra + svarbrev_opgave},
            ]
        else:
            user_content = (
                kontekst
                + "\nKLAGENS INDHOLD:\n"
                + (klage.get("tekst") or "")
                + "\n"
                + sagsakter_blok
                + ekstra
                + svarbrev_opgave
            )

        response = client.messages.create(
            model=MODEL,
            max_tokens=6000,  # svarbreve kan være længere end analyser
            temperature=0.2,  # lidt temperatur til et mere naturligt sprog
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        svarbrev_tekst = response.content[0].text

        # Sikkerhedsnet: kør svarbrevet gennem den dedikerede anonymiserings-
        # funktion så klagerens navn aldrig slipper igennem til Nævnet.
        return _sikr_svarbrev_anonymiseret(svarbrev_tekst)

    except Exception as e:
        return f"Fejl i generering af svarbrev: {str(e)}"


def _sikr_svarbrev_anonymiseret(svarbrev_tekst):
    """
    Tager et genereret svarbrev og sikrer via en målrettet AI-gennemgang at
    ingen klager- eller persondata er sluppet igennem. Bevarer svarbrevets
    struktur og sproglige tone — fjerner/erstatter kun personnavne og
    identifikatorer.

    Falder tilbage til at returnere originalen hvis AI-kaldet fejler —
    så svarbrevsgenerering aldrig blokeres af anonymiserings-trinnet.
    """
    try:
        if not svarbrev_tekst or not svarbrev_tekst.strip():
            return svarbrev_tekst

        instruktion = (
            "Du modtager et allerede færdigskrevet svarbrev fra "
            f"{REJSESELSKAB_NAVN} til Pakkerejse-Ankenævnet. Din ENESTE "
            "opgave er at sikre at svarbrevet er fuldt anonymiseret — "
            "klagerens navn og personhenførbare oplysninger MÅ IKKE stå "
            "noget sted.\n\n"
            "REGLER:\n"
            "- Personnavne på klager → erstat med 'klager' med LILLE k "
            "(uanset om der er én, to eller flere klagere — brug ALTID "
            "kun 'klager', ALDRIG 'Klager 1' eller 'Klager 2'). Stort K "
            "kun ved sætningsstart.\n"
            f"- Personnavne på {REJSESELSKAB_NAVN}s medarbejdere → omtales "
            f"ikke ved navn. Skriv i stedet '{REJSESELSKAB_SAGSBEHANDLER}' "
            f"eller '{REJSESELSKAB_NAVN}'\n"
            "- Personnavne på medrejsende (ægtefælle, børn, rejseledsagere) "
            "→ 'medrejsende' eller 'Biperson 1', 'Biperson 2'\n"
            "- Guider/hotelpersonale → 'guiden' eller 'hotelpersonalet'\n"
            "- CPR-numre → '[CPR fjernet]'\n"
            "- Fødselsdatoer (bortset fra rejsedatoer) → '[fødselsdato fjernet]'\n"
            "- Adresser (gadenavn + nr.) → '[adresse fjernet]'\n"
            "- Telefonnumre → '[telefon fjernet]'\n"
            "- E-mailadresser → '[e-mail fjernet]'\n"
            "- Booking-/kundenumre → maskeres (fx '12345678' → '12****78')\n"
            "- Bankoplysninger → '[bankoplysninger fjernet]'\n\n"
            f"BEVAR: navnet '{REJSESELSKAB_NAVN}' (det er ikke en person "
            "men en virksomhed), hotelnavne, destinationer, lufthavne, "
            "rejsedatoer, beløb, klagepunkter, juridiske henvisninger, "
            "samt brevets struktur og sproglige tone. Rør IKKE ved andet "
            "end personhenførbare data.\n\n"
            "Returnér kun det rettede svarbrev — ingen forklaringer, ingen "
            "intro, ingen afslutningskommentar. Start direkte med brevteksten.\n\n"
            "SVARBREV DER SKAL GENNEMGÅS:\n"
        )

        regler = _hent_anonymiseringsregler_tekst()
        system_prompt = (
            "Du er en præcis og regel-tro anonymiseringsassistent for "
            "rejsearrangører der skal svare Pakkerejse-Ankenævnet. Du er "
            "trænet på de autoritative danske og europæiske anonymiserings-"
            "regler (Datatilsynet, Jurabibliotek, EU Article 29 WP216)."
        )
        if regler:
            system_prompt += "\n\n" + regler

        response = client.messages.create(
            model=MODEL,
            max_tokens=6000,
            temperature=0,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": instruktion + svarbrev_tekst,
            }],
        )
        ren_tekst = response.content[0].text
        # Sanity-tjek: hvis modellen returnerede noget meget kort eller tomt,
        # så fald tilbage til originalen i stedet for at miste brevet
        if not ren_tekst or len(ren_tekst) < 0.4 * len(svarbrev_tekst):
            print(
                "DEBUG: Anonymiserings-pas gav uventet kort svar — "
                "bruger originalen"
            )
            return svarbrev_tekst
        return ren_tekst

    except Exception as e:
        print(f"DEBUG: Svarbrevs-anonymiseringspas fejlede (ikke kritisk): {e}")
        return svarbrev_tekst


def _byg_sag_content(sag, indled_tekst, slutnings_tekst, ekstra_sagsakter_filer=None):
    """
    Bygger Claude's message-content liste ud fra en sag og evt. sagsakter-filer.

    Tekstfiler inlines som text-blokke.
    Scannede PDF'er sendes som document-blokke (vision).
    Billeder (PNG/JPEG) sendes som image-blokke (vision).

    ekstra_sagsakter_filer (valgfri): liste af sagsakter-filer i samme format
    som sag['filer']. Disse tilføjes efter sagens hovedfiler med egen
    kategorisering som SAGSAKT.
    """
    import base64

    content = [{"type": "text", "text": indled_tekst}]

    filer = sag.get("filer") or []
    if not filer:
        content.append({"type": "text", "text": "(Ingen filer uploadet til sagen.)"})
    else:
        for i, fil in enumerate(filer, 1):
            filnavn = fil.get("filnavn", f"fil{i}")
            rolle = fil.get("rolle", "ukendt")
            rolle_label = rolle.replace("_", " ").upper()

            header = (
                f"\n--- FIL {i}/{len(filer)} — ROLLE: {rolle_label} — "
                f"FILNAVN: {filnavn} ---\n"
            )

            if fil.get("type") == "pdf_bytes" and fil.get("bytes"):
                content.append({
                    "type": "text",
                    "text": header + "[Scannet PDF — læs den via vision nedenfor]",
                })
                pdf_b64 = base64.standard_b64encode(fil["bytes"]).decode("utf-8")
                content.append({
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": pdf_b64,
                    },
                })
            elif fil.get("type") == "image_bytes" and fil.get("bytes"):
                content.append({
                    "type": "text",
                    "text": header + "[Billede — læs indholdet via vision]",
                })
                img_b64 = base64.standard_b64encode(fil["bytes"]).decode("utf-8")
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": fil.get("media_type", "image/png"),
                        "data": img_b64,
                    },
                })
            elif fil.get("type") == "mp4_skipped":
                # Video — PAX læser ikke MP4. Vi nævner eksistensen så
                # Claude ved at der findes yderligere materiale, men
                # beder eksplicit om at juristen selv gennemser filen.
                content.append({
                    "type": "text",
                    "text": (
                        header
                        + "[MP4-videofil. juriitech PAX læser ikke video — "
                        "denne fil er IKKE analyseret. Nævn i vurderingen at "
                        "juristen selv skal gennemse videoen manuelt som "
                        "supplement til analysen.]"
                    ),
                })
            elif fil.get("type") == "fil_ikke_laest":
                aarsag = fil.get("aarsag") or "filen kunne ikke læses"
                content.append({
                    "type": "text",
                    "text": (
                        header
                        + f"[Filen kunne IKKE læses af juriitech PAX. "
                        f"Årsag: {aarsag}. Lav analysen ud fra de "
                        "øvrige filer der KAN læses — men bemærk at "
                        "denne fil kan indeholde information der "
                        "ændrer sagen.]"
                    ),
                })
            else:
                tekst = fil.get("tekst") or "(tom)"
                content.append({"type": "text", "text": header + tekst})

    # Tilføj evt. sagsakter-filer (ekstra intern materiale uploadet af jurist)
    if ekstra_sagsakter_filer:
        content.append({
            "type": "text",
            "text": (
                "\n\n========================================\n"
                "SAGSAKTER — intern materiale fra rejseselskabet "
                "(e-mails, screenshots, bookingdetaljer, mv.)\n"
                "========================================\n"
            ),
        })
        for j, fil in enumerate(ekstra_sagsakter_filer, 1):
            filnavn = fil.get("filnavn", f"sagsakt{j}")
            header = f"\n--- SAGSAKT {j} — FILNAVN: {filnavn} ---\n"

            if fil.get("type") == "pdf_bytes" and fil.get("bytes"):
                content.append({"type": "text", "text": header + "[Scannet PDF]"})
                pdf_b64 = base64.standard_b64encode(fil["bytes"]).decode("utf-8")
                content.append({
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": pdf_b64,
                    },
                })
            elif fil.get("type") == "image_bytes" and fil.get("bytes"):
                content.append({"type": "text", "text": header + "[Screenshot/billede]"})
                img_b64 = base64.standard_b64encode(fil["bytes"]).decode("utf-8")
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": fil.get("media_type", "image/png"),
                        "data": img_b64,
                    },
                })
            elif fil.get("type") == "mp4_skipped":
                content.append({
                    "type": "text",
                    "text": (
                        header
                        + "[MP4-videofil. IKKE analyseret — juristen "
                        "gennemser selv manuelt.]"
                    ),
                })
            elif fil.get("type") == "fil_ikke_laest":
                aarsag = fil.get("aarsag") or "filen kunne ikke læses"
                content.append({
                    "type": "text",
                    "text": header + f"[Filen kunne IKKE læses. Årsag: {aarsag}]",
                })
            else:
                tekst = fil.get("tekst") or "(tom)"
                content.append({"type": "text", "text": header + tekst})

    content.append({"type": "text", "text": slutnings_tekst})
    return content


def udled_sandsynligheder_strukturelt(analyse_tekst):
    """
    Dedikeret fallback-udleder der tvinger tre procentsatser frem baseret
    på en eksisterende analyse. Bruges når regex-parsing af førstevurderingen
    fejler, så dashboardet altid kan vise noget konkret.

    Returnerer en dict:
      {"fuld_medhold": int, "delvist_medhold": int, "afvist": int}
    eller None hvis også denne udledning fejler.
    """
    import json as _json
    import re as _re

    if not analyse_tekst or not analyse_tekst.strip():
        return None

    prompt = (
        "Baseret på nedenstående juridiske analyse af en klagesag fra "
        "Pakkerejse-Ankenævnet, estimér sandsynligheden for tre mulige "
        "udfald. Hvis analysen ikke giver tydeligt grundlag, så baser "
        "estimatet på din viden om Pakkerejse-Ankenævnets praksis og "
        "pakkerejseloven. Du SKAL give tre tal der summer til 100.\n\n"
        f"ANALYSE:\n{analyse_tekst[:6000]}\n\n"
        "RETURNÉR KUN dette JSON-objekt — intet andet, ingen forklaring, "
        "ingen markdown:\n"
        '{"fuld_medhold": X, "delvist_medhold": Y, "afvist": Z}\n\n'
        "X, Y og Z er heltal 0-100 og summer til 100."
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=200,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        svar = response.content[0].text.strip()
        # Fjern evt. markdown-kodeblok
        svar = _re.sub(r"^```(?:json)?\s*", "", svar)
        svar = _re.sub(r"\s*```$", "", svar).strip()
        data = _json.loads(svar)
        if all(k in data for k in ("fuld_medhold", "delvist_medhold", "afvist")):
            # Clip til 0-100 og sanity-check
            f = int(data["fuld_medhold"])
            d = int(data["delvist_medhold"])
            a = int(data["afvist"])
            if all(0 <= v <= 100 for v in (f, d, a)):
                return {"fuld_medhold": f, "delvist_medhold": d, "afvist": a}
    except Exception as e:
        print(f"DEBUG: Struktureret sandsynlighedsudledning fejlede: {e}")
    return None


def udled_alle_klagepunkter(sag, sagsakter_tekst=""):
    """
    DEDIKERET ekstraktions-funktion: udtrækker UDTØMMENDE liste over
    ALLE klagepunkter klager rejser mod rejseselskabet.

    Bruges som autoritativ 'source of truth' der injiceres i alle
    downstream-prompts (førstevurdering, sagsresume, svarbrev) — så de
    ikke skal gen-finde klagepunkter selv, men har en verificeret liste
    at arbejde fra. Dette er den eneste pålidelige måde at sikre 100%
    klagepunkt-dækning på tværs af alle output.

    Returnerer: list[str] med én kort beskrivelse per klagepunkt.
    Tom liste hvis ekstraktion fejler.
    """
    import json as _json
    import re as _re

    indled = (
        "Du er en præcis juridisk research-assistent. Din ENESTE opgave "
        "lige nu er at identificere ALLE klagepunkter klager rejser mod "
        "rejseselskabet i nedenstående sag.\n\n"
        "KRITISK INSTRUKTION (LÆS GRUNDIGT):\n"
        "- Læs HVER ENESTE fil i sagen grundigt.\n"
        "- Læs derefter ALT materialet igennem TO GANGE for at sikre "
        "at du ikke har misset noget. Det er BEDRE at oplistede et "
        "klagepunkt for meget end et for lidt.\n"
        "- Inkludér STORE OG SMÅ klagepunkter — ALLE klagepunkter "
        "skal med, uanset om de virker centrale eller marginale.\n"
        "- Husk at klagepunkter inkluderer BÅDE:\n"
        "  • Konkrete mangler ved rejsen (hotel-standard, mad, "
        "transport, pool, værelse, beliggenhed, faciliteter, "
        "støj, rengøring, manglende ydelser osv.)\n"
        "  • Procesuelle/relations-klager (dårlig kommunikation, "
        "ventetider, tonen i korrespondance, manglende information, "
        "sagsbehandlingstid, kompensations-tilbuddets størrelse, "
        "guide-håndtering, refusion-procedurer osv.)\n"
        "  • Krav om kompensation/refusion (også selvom det måske "
        "er afvist eller delvist accepteret)\n"
        "- Hvis klager nævner 12 forskellige problemer, skal alle "
        "12 stå på listen. Tag ALDRIG genvej eller gruppér flere "
        "punkter sammen.\n"
        "- Hvert klagepunkt formuleres som ÉN kort sætning "
        "(max 20 ord).\n\n"
        "OVERSÆTTELSE FRA ENGELSK (eller andre sprog):\n"
        "Mange dokumenter er på engelsk (hotel-mails, korrespondance osv.). "
        "Du SKAL formulere ALLE klagepunkter på dansk — også når de "
        "stammer fra engelsk-sprogede bilag. Brug PRÆCISE danske termer, "
        "ikke direkte ord-for-ord-oversættelser:\n"
        "  • 'mangel' (ikke 'deficiency')\n"
        "  • 'rettidig reklamation' (ikke 'timely complaint')\n"
        "  • 'manglende bistand' (ikke 'lack of assistance')\n"
        "Klagepunkterne skal kunne læses og forstås direkte af en "
        "dansk jurist uden behov for at konsultere originalsproget.\n\n"
        "FILER FRA SAGEN FØLGER NEDENFOR:\n"
    )

    sagsakter_block = ""
    if sagsakter_tekst and sagsakter_tekst.strip():
        sagsakter_block = (
            f"\n\nSUPPLERENDE SAGSAKTER (interne notater, mails osv. "
            f"der kan indeholde flere klagepunkter):\n"
            f"{sagsakter_tekst[:6000]}"
        )

    slutning = (
        sagsakter_block +
        "\n\nRETURNÉR KUN dette JSON-objekt — ingen forklaring, "
        "ingen markdown, ingen kodeblok:\n"
        "{\n"
        '  "klagepunkter": [\n'
        '    "Klagepunkt 1 i én kort sætning",\n'
        '    "Klagepunkt 2 i én kort sætning",\n'
        '    "..."\n'
        '  ]\n'
        "}\n\n"
        "ABSOLUT REGEL: Returnér ALLE klagepunkter — ingen undtagelser. "
        "Hellere ét for mange end ét for lidt. Det er kritisk at "
        "INTET klagepunkt overses, da det får alvorlige konsekvenser "
        "for downstream juridisk rådgivning."
    )

    try:
        user_content = _byg_sag_content(sag, indled, slutning)

        response = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            temperature=0,
            system=(
                "Du er en grundig juridisk research-assistent specialiseret "
                "i Pakkerejse-Ankenævnet sager. Du leverer altid "
                "udtømmende, præcise klagepunkt-lister."
            ),
            messages=[{"role": "user", "content": user_content}],
        )

        svar = response.content[0].text.strip()
        svar = _re.sub(r"^```(?:json)?\s*", "", svar)
        svar = _re.sub(r"\s*```$", "", svar).strip()
        data = _json.loads(svar)

        klagepunkter = data.get("klagepunkter", [])
        if isinstance(klagepunkter, str):
            klagepunkter = [klagepunkter]
        klagepunkter = [
            str(k).strip() for k in klagepunkter if str(k).strip()
        ]

        return klagepunkter
    except Exception as e:
        print(f"DEBUG: udled_alle_klagepunkter fejlede: {e}")
        return []


def _repair_truncated_json(svar: str):
    """Forsøg at lukke trunkeret JSON pænt så vi kan parse det delvise
    output. Bruges som fallback når AI-svar bliver afkortet midt i et
    string/array/object pga. max_tokens-grænsen.

    Returnerer dict ved succes, None ved manglende repair.
    """
    import json as _json

    if not svar or not svar.strip():
        return None

    s = svar.strip()
    # Find sidste 'sikre' position vi kan trimme tilbage til:
    # - Hvis vi er midt i en string, find sidste " og trim derefter
    # - Luk åbne arrays/objects baseret på balance

    # Tæl uafsluttede åbne tegn
    in_string = False
    escape = False
    stack = []
    sidste_sikre_pos = 0

    for i, ch in enumerate(s):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "[{":
            stack.append(ch)
        elif ch in "]}":
            if stack:
                stack.pop()
        # Markér sidste position hvor vi er på top-niveau OG ikke i string
        if not in_string and ch in ",":
            sidste_sikre_pos = i

    if not stack and not in_string:
        # JSON ser komplet ud — prøv at parse
        try:
            return _json.loads(s)
        except Exception:
            return None

    # Trim tilbage til sidste sikre komma og luk åbne brackets
    if sidste_sikre_pos > 0:
        s = s[:sidste_sikre_pos]

    # Hvis vi er midt i en string, fjern eventuel halv string
    if in_string:
        # Find sidste " der ikke er inde i en value — nemmest er at
        # fjerne alt efter sidste komma (allerede gjort) og se hvad sker
        pass

    # Luk åbne brackets i omvendt rækkefølge
    while stack:
        opener = stack.pop()
        closer = "}" if opener == "{" else "]"
        s += closer

    try:
        return _json.loads(s)
    except Exception as e:
        print(f"DEBUG: _repair_truncated_json fejlede stadig: {e}")
        return None


def udled_tidsforhold(sag, sagsakter_tekst=""):
    """
    DEDIKERET ekstraktions-funktion: udtrækker tidsforhold mellem
    konstatering af mangler og kontakt til rejseselskabet.

    Pakkerejse-Ankenævnet vægter rettidig reklamation MEGET HØJT — det
    er ofte den vigtigste enkelt-faktor i deres afgørelser. Hvis klager
    først reklamerer dage efter en mangel blev konstateret (eller først
    efter hjemkomst), har rejseselskabet ikke haft chancen for at
    afhjælpe på destinationen — og dette er et stærkt forsvarsargument.

    Funktionen returnerer en struktureret dict, der bruges som autoritativ
    'source of truth' i alle downstream-prompts (resume, førstevurdering,
    svarbrev) — så timing-aspektet ikke overses.

    Returnerer:
    {
        "rejseperiode": str,                # fx "8.-22. juni 2025"
        "har_problematisk_forsinkelse": bool,
        "samlet_vurdering": str,
        "konkrete_observationer": [str],
        "kunne_ikke_udledes": bool,
        "begivenheder": [                   # NY: kronologisk tidslinje
            {
                "dato": str,                # "8. juni 2025"
                "tidspunkt": str | None,    # "14:30" eller None
                "type": str,                # "ankomst" | "klage_til_guide" | "tui_reaktion" | "klage_til_tui" | "afgang" | "andet"
                "aktoer": str,              # "Klager" | "TUI guide" | "TUI After Travel" | "Hotel" | etc.
                "beskrivelse": str,         # 1-2 sætninger om hvad der skete
                "betydning": str            # "neutral" | "positiv_for_tui" | "negativ_for_tui"
            }
        ]
    }
    Returnerer None hvis ekstraktion fejler.
    """
    import json as _json
    import re as _re

    indled = (
        "Du er en præcis juridisk research-assistent specialiseret i "
        "Pakkerejse-Ankenævnet sager. Din ENESTE opgave lige nu er at "
        "kortlægge TIDSFORHOLDET mellem hvornår klager konstaterede "
        "mangler/problemer og hvornår klager kontaktede rejseselskabet "
        "(TUI) om dem.\n\n"
        "═══════════════════════════════════════════════════════════════\n"
        "KRITISK PRINCIP: KILDE-FORANKRING (ingen gæt — ingen 'ca.')\n"
        "═══════════════════════════════════════════════════════════════\n"
        "Du må KUN bruge datoer og tidspunkter der EKSPLICIT fremgår af "
        "materialet. Du må ALDRIG:\n"
        "  ✗ Bruge 'ca.' eller cirka-datoer\n"
        "  ✗ Beregne datoer baseret på antagelser ('formentlig dag 2')\n"
        "  ✗ Slynge en dato ind hvis du ikke har den dokumenteret\n"
        "  ✗ Antage at noget ikke skete (fx 'INGEN henvendelse') med "
        "mindre dette EKSPLICIT bekræftes i bilagene\n\n"
        "Hvis en dato/tidspunkt for en bestemt begivenhed ikke fremgår "
        "klart af materialet, SKAL du i stedet skrive at det IKKE kan "
        "verificeres — fx:\n"
        "  '[Bilag XX viser klage indsendt — eksakt konstateringsdato "
        "for manglen kan ikke verificeres af materialet og bør tjekkes "
        "manuelt]'\n"
        "  'Reklamation indsendt 23. juni 2025 — konstateringsdato for "
        "den underliggende mangel fremgår ikke klart af bilagene og bør "
        "verificeres manuelt'\n\n"
        "Hvor datoer FREMGÅR KLART af bilagene (fx i mail-headers, "
        "datoer på dokumenter, eksplicitte datostempler), bruger du dem "
        "med fuld præcision. Henvis ALTID til bilag når du angiver en "
        "verificeret dato, fx '[Bilag 08]'.\n\n"
        "═══════════════════════════════════════════════════════════════\n"
        "JURIDISK BAGGRUND:\n"
        "═══════════════════════════════════════════════════════════════\n"
        "Pakkerejse-Ankenævnet vægter RETTIDIG REKLAMATION ekstremt højt. "
        "Hvis klager:\n"
        "  • Kontaktede TUI samme dag eller umiddelbart efter en mangel "
        "blev konstateret (på destinationen) → RETTIDIG reklamation, "
        "neutralt for sagen\n"
        "  • Ventede flere dage efter konstatering med at kontakte TUI "
        "→ POTENTIELT FOR SEN reklamation, fordel for TUI\n"
        "  • Først kontaktede TUI EFTER hjemkomst → ALMINDELIGVIS FOR "
        "SEN reklamation, stærkt forsvarsargument for TUI\n\n"
        "INSTRUKTION:\n"
        "1. Find rejseperioden (udrejse + hjemrejse) — KUN hvis det "
        "fremgår af bilagene.\n"
        "2. For HVERT klagepunkt der er identificeret i bilagene:\n"
        "   - Hvornår blev manglen konstateret? Brug KUN datoer der "
        "  EKSPLICIT fremgår. Ellers skriv 'konstateringsdato kan "
        "  ikke verificeres — bør tjekkes manuelt'.\n"
        "   - Hvornår kontaktede klager TUI om det? Brug KUN dato fra "
        "  e-mail-headers, dokumentdato eller eksplicit dato i bilag. "
        "  Ellers skriv 'kontaktdato kan ikke verificeres — bør "
        "  tjekkes manuelt'.\n"
        "   - Beregn forsinkelse i dage KUN når BEGGE datoer er "
        "  verificerede.\n"
        "3. Vurdér samlet om reklamationen var rettidig — kun baseret "
        "på verificerede datoer.\n\n"
        "OVERSÆTTELSE FRA ENGELSK (eller andre sprog):\n"
        "Hotel-mails, korrespondance og bookings er ofte på engelsk. "
        "Du SKAL skrive ALT output på dansk:\n"
        "  • Datoer på dansk format ('12. juni 2025', ikke '12 June 2025')\n"
        "  • Vurderinger og observationer i danske juridiske termer\n"
        "  • Brug 'rettidig reklamation' (ikke 'timely complaint'),\n"
        "    'mangel' (ikke 'deficiency'), 'henvendelse til TUI' osv.\n"
        "Output skal kunne læses direkte af en dansk jurist uden\n"
        "konsultation af originalsproget.\n\n"
        "FILER FRA SAGEN FØLGER NEDENFOR:\n"
    )

    sagsakter_block = ""
    if sagsakter_tekst and sagsakter_tekst.strip():
        sagsakter_block = (
            f"\n\nSUPPLERENDE SAGSAKTER (e-mails, C4C-noter, guide-"
            f"rapporter osv. — INDEHOLDER OFTE DE PRÆCISE DATOER):\n"
            f"{sagsakter_tekst[:8000]}"
        )

    slutning = (
        sagsakter_block +
        "\n\nRETURNÉR KUN dette JSON-objekt — ingen forklaring, "
        "ingen markdown, ingen kodeblok:\n"
        "{\n"
        '  "rejseperiode": "fx 8.-22. juni 2025 — eller fremgår ikke",\n'
        '  "har_problematisk_forsinkelse": true|false,\n'
        '  "samlet_vurdering": "2-4 sætninger der opsummerer om '
        'reklamationen var rettidig. Vær KONKRET og NÆVN DATOERNE. '
        'Hvis intet kan udledes, skriv det ærligt.",\n'
        '  "konkrete_observationer": [\n'
        '    "Kort beskrivelse af hvert relevant tidsforhold, fx: '
        '\\"Pool-problem konstateret 9. juni, TUI kontaktet samme dag — '
        'rettidig\\" eller \\"Ekstraseng-problem konstateret 8. juni, '
        'TUI først kontaktet 14. juni efter hjemkomst (6 dages '
        'forsinkelse) — for sen reklamation\\"",\n'
        '    "..."\n'
        '  ],\n'
        '  "kunne_ikke_udledes": true|false,\n'
        '  "begivenheder": [\n'
        '    {\n'
        '      "dato": "8. juni 2025",\n'
        '      "tidspunkt": "14:30 eller null hvis ikke angivet",\n'
        '      "type": "ankomst|klage_til_guide|tui_reaktion|klage_til_tui|afgang|andet",\n'
        '      "aktoer": "Klager / TUI guide / TUI After Travel / Hotel / etc.",\n'
        '      "beskrivelse": "1-2 sætninger om hvad der skete",\n'
        '      "betydning": "neutral|positiv_for_tui|negativ_for_tui"\n'
        '    }\n'
        '  ]\n'
        "}\n\n"
        "VIGTIGE REGLER:\n"
        "- har_problematisk_forsinkelse SKAL være TRUE KUN hvis AT "
        "LEAST ÉN mangel BEVISLIGT (med verificerede datoer fra "
        "bilagene) blev reklameret med betydelig forsinkelse.\n"
        "- har_problematisk_forsinkelse SKAL være FALSE hvis alle "
        "mangler blev rettidigt reklameret eller hvis du ikke har "
        "verificerede datoer.\n"
        "- Hvis materialet IKKE indeholder tilstrækkelige datoer til at "
        "udlede dette, sæt kunne_ikke_udledes=true og skriv det ærligt "
        "i samlet_vurdering. OPFIND ALDRIG datoer.\n"
        "- konkrete_observationer SKAL formuleres ærligt med kilde:\n"
        "  ✓ KORREKT: 'Reklamation modtaget af TUI 23. juni 2025 [Bilag 13]'\n"
        "  ✓ KORREKT: 'TUI's svar fremsendt 14. juli 2025 [Bilag 14] — "
        "dato for klagers oprindelige konstatering af manglen kan ikke "
        "verificeres af materialet og bør tjekkes manuelt'\n"
        "  ✗ FORKERT: 'Mangel konstateret ca. 28.-29. maj 2025' "
        "(brug ALDRIG 'ca.')\n"
        "  ✗ FORKERT: 'INGEN henvendelse til TUI under rejsen' (brug "
        "ALDRIG sådanne påstande uden EKSPLICIT bekræftelse i bilag)\n"
        "  ✗ FORKERT: 'Mangel konstateret dag 2 af opholdet' (gæt "
        "baseret på rejseperiode)\n"
        "- Hvis du er i tvivl om en dato, skriv eksplicit at den IKKE "
        "kan verificeres og BØR TJEKKES MANUELT. Det er ALTID bedre at "
        "være ærlig om manglende information end at gætte.\n"
        "\n"
        "REGLER FOR begivenheder (TIDSLINJE):\n"
        "- DESTINATIONS-PERIODEN ER VIGTIGST: Den juridiske vurdering "
        "  vægter primært hvad der skete PÅ DESTINATIONEN — om klager "
        "  reklamerede til guide/hotel/After Travel mens man stadig var "
        "  der, og hvordan TUI reagerede dér og da. Dette er hjertet af "
        "  'rettidig reklamation'-vurderingen.\n"
        "- Vær EKSTRA OMHYGGELIG og DETALJERET med begivenheder mellem "
        "  ankomst og afgang. Hver enkelt henvendelse til guide, hver "
        "  reaktion fra hotel, hver gang TUI svarede ude på destinationen "
        "  — alt skal med, præcist dateret. Det er på destinationen at "
        "  rejseselskabet enten har haft chancen for at afhjælpe (eller ej).\n"
        "- Inkludér ALLE relevante kronologiske begivenheder med dato:\n"
        "  • Klagers ankomst til destinationen (markér 'type': 'ankomst')\n"
        "  • Hver gang klager henvendte sig til guide/hotel/After Travel "
        "    PÅ destinationen — disse er HØJEST PRIORITET\n"
        "  • Hver gang TUI/hotel reagerede/svarede/handlede PÅ destinationen "
        "    — disse er HØJEST PRIORITET\n"
        "  • Klagers afgang fra destinationen (markér 'type': 'afgang')\n"
        "  • Begivenheder EFTER hjemkomst (klage til TUI After Travel "
        "    hjemmefra, klage til Ankenævnet, TUI's svar hjemmefra) — "
        "    disse må gerne medtages, men er sekundære. Vær kortfattet "
        "    her — fokus skal stadig ligge på destinationen.\n"
        "- Sortér ALTID kronologisk (ældste først).\n"
        "- 'type': 'afgang' SKAL bruges til selve hjemrejsen så frontend'en "
        "  kan markere hvad der er post-destination.\n"
        "- Inkludér tidspunkt KUN hvis det fremgår af materialet — "
        "ellers sæt 'tidspunkt': null.\n"
        "- 'aktoer' beskriver hvem der handler/skriver (ikke hvem der "
        "modtager). Brug 'Klager', 'TUI guide', 'TUI After Travel', "
        "'Hotel', 'Pakkerejse-Ankenævnet'.\n"
        "- 'betydning' er hvordan begivenheden påvirker TUI's "
        "forsvarsposition: 'positiv_for_tui' (fx TUI reagerede hurtigt, "
        "klager reklamerede sent), 'negativ_for_tui' (fx TUI ignorerede "
        "klage, lang ventetid på respons), 'neutral' (faktuel begivenhed "
        "uden vurdering).\n"
        "- Hvis ingen datoer kan udledes, returnér tom liste: "
        '"begivenheder": [].\n'
        "- OPFIND ALDRIG datoer eller begivenheder.\n"
    )

    try:
        user_content = _byg_sag_content(sag, indled, slutning)

        # Hævet fra 2000 → 6000 tokens fordi tidsforhold-JSON ofte
        # indeholder 10-20 begivenheder + observationer + vurdering;
        # 2000 var for lidt og JSON blev trunkeret midt i en string.
        response = client.messages.create(
            model=MODEL,
            max_tokens=6000,
            temperature=0,
            system=(
                "Du er en præcis juridisk research-assistent. Du finder "
                "kun datoer der faktisk fremgår af materialet — du "
                "opfinder ALDRIG tidsangivelser."
            ),
            messages=[{"role": "user", "content": user_content}],
        )

        svar = response.content[0].text.strip()
        svar = _re.sub(r"^```(?:json)?\s*", "", svar)
        svar = _re.sub(r"\s*```$", "", svar).strip()

        # Forsøg at parse — hvis det fejler pga. trunkering, prøv en
        # repair der lukker åbne strings/arrays/objects pænt.
        try:
            data = _json.loads(svar)
        except _json.JSONDecodeError as je:
            print(
                f"DEBUG: udled_tidsforhold JSON-parse fejlede ({je}), "
                "forsøger repair af trunkeret JSON..."
            )
            data = _repair_truncated_json(svar) or {}
            if not data:
                # Repair fejlede også — returner en delvis dict baseret
                # på hvad vi i det mindste kan udlede fra tekstuddraget.
                return {
                    "rejseperiode": "",
                    "har_problematisk_forsinkelse": False,
                    "samlet_vurdering": (
                        "AI-svaret blev trunkeret før det var færdigt. "
                        "Prøv evt. at scanne sagen igen."
                    ),
                    "konkrete_observationer": [],
                    "kunne_ikke_udledes": True,
                    "begivenheder": [],
                }

        # Normalisér begivenheder til konsistent format
        raa_begivenheder = data.get("begivenheder") or []
        begivenheder = []
        for b in raa_begivenheder:
            if not isinstance(b, dict):
                continue
            dato = str(b.get("dato") or "").strip()
            if not dato:
                continue
            tidspunkt_raw = b.get("tidspunkt")
            tidspunkt = (
                str(tidspunkt_raw).strip()
                if tidspunkt_raw and str(tidspunkt_raw).strip().lower()
                not in ("null", "none", "")
                else None
            )
            betydning = str(b.get("betydning") or "neutral").strip().lower()
            if betydning not in (
                "neutral", "positiv_for_tui", "negativ_for_tui"
            ):
                betydning = "neutral"
            begivenheder.append({
                "dato": dato,
                "tidspunkt": tidspunkt,
                "type": str(b.get("type") or "andet").strip(),
                "aktoer": str(b.get("aktoer") or "").strip(),
                "beskrivelse": str(b.get("beskrivelse") or "").strip(),
                "betydning": betydning,
            })

        return {
            "rejseperiode": str(data.get("rejseperiode") or "").strip(),
            "har_problematisk_forsinkelse": bool(
                data.get("har_problematisk_forsinkelse")
            ),
            "samlet_vurdering": str(
                data.get("samlet_vurdering") or ""
            ).strip(),
            "konkrete_observationer": [
                str(o).strip()
                for o in (data.get("konkrete_observationer") or [])
                if str(o).strip()
            ],
            "kunne_ikke_udledes": bool(data.get("kunne_ikke_udledes")),
            "begivenheder": begivenheder,
        }
    except Exception as e:
        print(f"DEBUG: udled_tidsforhold fejlede: {e}")
        return None


def udled_sagsmetadata(sag, sagsakter_tekst=""):
    """
    Udtrækker metadata til svarbrev-headeren: sagsnummer fra
    Pakkerejse-Ankenævnet og klagers fulde navn.

    Disse felter står normalt eksplicit i klageskemaet/forsiden af de
    bilag der er uploadet. Vi bruger et lille AI-kald frem for regex
    fordi formatet varierer (sagsnummer kan stå som "Sag nr.",
    "Sagsnr.", "Vores ref.", "Ankenævnets sag" osv.) og fordi navnet
    skal udtrækkes som det er skrevet i sagen — ikke pseudonymiseret.

    Returnerer:
      {
        "sagsnummer": str,    # fx "25-109-8024327" — tom hvis ikke fundet
        "klagers_navn": str,  # fx "Laura Stephanie Uhler" — tom hvis ikke fundet
      }
    """
    import json as _json
    import re as _re

    indled = (
        "Du er en præcis dokument-ekstraktor. Din ENESTE opgave er at "
        "finde to faktuelle oplysninger i det vedhæftede sagsmateriale:\n"
        "  1. Pakkerejse-Ankenævnets sagsnummer\n"
        "  2. Klagers fulde navn (som det fremgår af klageskemaet)\n\n"
        "═══════════════════════════════════════════════════════════════\n"
        "VIGTIGT OM SAGSNUMMERET — DET FINDES NÆSTEN ALTID:\n"
        "═══════════════════════════════════════════════════════════════\n"
        "Sagsnummeret er Pakkerejse-Ankenævnets interne reference og er "
        "OBLIGATORISK for hver sag de behandler. Det STÅR derfor i "
        "materialet — typisk på følgende steder (skan dem grundigt):\n"
        "  • Øverste højre hjørne af høringsbrevet fra Nævnet (første "
        "    side, ofte i en boks eller tæt på dato)\n"
        "  • I 'Vedr.'-linjen eller 'Sag nr.'-linjen øverst i breve\n"
        "  • Som overskrift eller sidefod på klageskemaet\n"
        "  • I emnefeltet eller signatur på e-mails fra Nævnet\n"
        "  • I filnavne på dokumenter fra Nævnet (fx '25-0123.pdf')\n\n"
        "FORMATER (alle tæller — vær åben):\n"
        "  • 'NN-NNNN' (fx '25-1234')\n"
        "  • 'NN-NNN-NNNNNNN' (fx '25-109-8024327')\n"
        "  • 'NN-NNNN/NNN' eller varianter med skråstreg\n"
        "  • 'NN.NNNN' eller 'NN/NNNN'\n"
        "Anchor-ord at lede efter: 'Sag nr.', 'Sagsnr.', 'Sagsnummer', "
        "'J.nr.', 'Journalnr.', 'Vores ref.', 'Vores sagsnummer', "
        "'Ankenævnets sag', 'Ref.'\n\n"
        "Hvis du finder noget der LIGNER et sagsnummer (åriske cifre "
        "eller bindestreger på en plads hvor man ville forvente et), "
        "skriv det. Bedre at returnere et sandsynligt sagsnummer som "
        "brugeren kan rette, end at returnere tom streng.\n\n"
        "Returnér KUN tom streng hvis materialet helt åbenlyst ikke "
        "indeholder noget sagsnummer (fx hvis det kun er rå sagsakter "
        "fra rejseselskabets eget system uden Nævn-korrespondance).\n\n"
        "═══════════════════════════════════════════════════════════════\n"
        "REGLER FOR KLAGERS NAVN:\n"
        "═══════════════════════════════════════════════════════════════\n"
        "- Klagers navn er navnet på den person der HAR INDGIVET klagen\n"
        "  (ikke rejseselskabets sagsbehandler, ikke advokaten, ikke\n"
        "  evt. medrejsende). Skriv det FULDE navn som det fremgår.\n"
        "- Hvis klagen er indgivet af et par (fx ægtefæller), brug den\n"
        "  først nævnte klager — det er den der står som primær.\n\n"
        "═══════════════════════════════════════════════════════════════\n"
        "GENERELLE REGLER:\n"
        "═══════════════════════════════════════════════════════════════\n"
        "- OPFIND ALDRIG et sagsnummer eller et navn der ikke står i\n"
        "  materialet (men VÆR ÅBEN over for hvad der er et match).\n"
        "- Sagsnummer SKAL returneres uden prefix — kun selve nummeret\n"
        "  ('25-109-8024327'), ikke 'Sag nr. 25-109-8024327'.\n\n"
        "FILER FRA SAGEN FØLGER NEDENFOR:\n"
    )

    sagsakter_block = ""
    if sagsakter_tekst and sagsakter_tekst.strip():
        # Kun de første 4000 tegn af sagsakterne — sagsnummer/navn står
        # næsten altid i toppen af klageskemaet.
        sagsakter_block = (
            "\n\nSUPPLERENDE SAGSAKTER:\n"
            f"{sagsakter_tekst[:4000]}"
        )

    slutning = (
        sagsakter_block +
        "\n\nRETURNÉR KUN dette JSON-objekt — ingen forklaring, "
        "ingen markdown, ingen kodeblok:\n"
        "{\n"
        '  "sagsnummer": "fx 25-109-8024327 — eller tom streng",\n'
        '  "klagers_navn": "fx Laura Stephanie Uhler — eller tom streng"\n'
        "}\n"
    )

    try:
        user_content = _byg_sag_content(sag, indled, slutning)

        response = client.messages.create(
            model=MODEL,
            max_tokens=400,  # JSON er ekstremt lille
            temperature=0,
            system=(
                "Du er en præcis dokument-ekstraktor. Du finder kun "
                "værdier der EKSPLICIT fremgår — du opfinder aldrig data."
            ),
            messages=[{"role": "user", "content": user_content}],
        )

        svar = response.content[0].text.strip()
        svar = _re.sub(r"^```(?:json)?\s*", "", svar)
        svar = _re.sub(r"\s*```$", "", svar).strip()

        data = _json.loads(svar)

        return {
            "sagsnummer": str(data.get("sagsnummer") or "").strip(),
            "klagers_navn": str(data.get("klagers_navn") or "").strip(),
        }
    except Exception as e:
        print(f"DEBUG: udled_sagsmetadata fejlede: {e}")
        return {"sagsnummer": "", "klagers_navn": ""}


def udled_bilag_overskrifter(filer):
    """
    Foreslår en kort dansk overskrift til hvert bilag i bilag-listen
    på et svarbrev (fx 'Første bekræftelsesmail på rejsebestillingen',
    'TUIs rejsevilkår', 'Hotelbeskrivelse vedhæftet i 1. bekræftelsesmail').

    Tager en liste af fil-dicts på formen:
      [{"filnavn": "bilag_05.pdf", "tekst": "...", "rolle": "..."}, ...]

    Returnerer en dict mappet på filnavn:
      {"bilag_05.pdf": "Første bekræftelsesmail på rejsebestillingen", ...}

    Hvis AI-kaldet fejler eller en fil ikke kan beskrives, falder den
    tilbage til et default udledt af filnavnet (uden extension, snyde-
    konverteret til mellemrum).

    Bruges til at auto-udfylde bilag-overskriftsfelterne i bilag-
    håndteringssektionen, så brugeren ikke skal skrive dem fra bunden
    — men kan altid redigere bagefter.
    """
    import json as _json
    import re as _re

    if not filer:
        return {}

    def _filnavn_til_default(fn):
        """Pænt fallback hvis AI'en ikke kan udlede en overskrift."""
        base = (fn or "").rsplit(".", 1)[0]
        base = base.replace("_", " ").replace("-", " ").strip()
        # Kapitaliser første bogstav, behold resten
        if base:
            return base[0].upper() + base[1:]
        return "Bilag"

    # Byg et kompakt prompt-input: filnavn + første ~600 tegn tekst.
    # Vi sender op til 25 filer ad gangen (mere end nok til typiske sager).
    fil_uddrag = []
    for f in filer[:25]:
        filnavn = f.get("filnavn") or ""
        tekst = (f.get("tekst") or "")[:600].strip()
        rolle = (f.get("rolle") or "").strip()
        rolle_str = f" [rolle: {rolle}]" if rolle and rolle != "ukendt" else ""
        fil_uddrag.append(
            f"--- {filnavn}{rolle_str} ---\n{tekst or '(ingen tekst udtrukket)'}"
        )

    indled = (
        "Du er en præcis dokument-klassifikator. Din ENESTE opgave er at "
        "foreslå en KORT dansk overskrift til hvert af nedenstående bilag, "
        "som det vil blive vist i bilag-listen øverst på et svarbrev til "
        "Pakkerejse-Ankenævnet.\n\n"
        "REGLER:\n"
        "- Skriv KUN på dansk.\n"
        "- Hver overskrift må MAX være 80 tegn.\n"
        "- Vær KONKRET og BESKRIVENDE — fortæl hvad bilaget INDEHOLDER, "
        "ikke bare 'Mail 1' eller 'Dokument'.\n"
        "- Eksempler på gode overskrifter:\n"
        "  • 'Første bekræftelsesmail på rejsebestillingen'\n"
        "  • 'TUIs rejsevilkår'\n"
        "  • 'Hotelbeskrivelse vedhæftet i 1. bekræftelsesmail'\n"
        "  • 'Klagers korrespondance med TUI efter hjemkomst'\n"
        "  • 'Voucher vedr. Hotel InterContinental Bali Resort'\n"
        "- Hvis du IKKE kan udlede et fornuftigt indhold (fx fordi teksten "
        "er tom eller meningsløs), brug en pæn default som 'Bilag — "
        "[filnavn]' eller skriv en tom streng.\n"
        "- OPFIND ALDRIG indhold der ikke står i teksten.\n\n"
        "BILAGENE:\n\n"
        + "\n\n".join(fil_uddrag)
    )

    slutning = (
        "\n\nRETURNÉR KUN dette JSON-objekt — ingen forklaring, "
        "ingen markdown, ingen kodeblok. Keys er filnavnene, values "
        "er de foreslåede overskrifter:\n"
        "{\n"
        '  "filnavn1.pdf": "Foreslået overskrift",\n'
        '  "filnavn2.docx": "Foreslået overskrift"\n'
        "}\n"
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1500,  # rigeligt til 25 korte overskrifter
            temperature=0,
            system=(
                "Du er en præcis dokument-klassifikator. Du foreslår "
                "korte danske overskrifter til bilag — du opfinder "
                "aldrig indhold der ikke står i teksten."
            ),
            messages=[{"role": "user", "content": indled + slutning}],
        )

        svar = response.content[0].text.strip()
        svar = _re.sub(r"^```(?:json)?\s*", "", svar)
        svar = _re.sub(r"\s*```$", "", svar).strip()

        data = _json.loads(svar)

        # Saml resultatet, og fyld defaults ud for filer AI'en ikke nævnte
        resultat = {}
        for f in filer:
            fn = f.get("filnavn") or ""
            forslag = data.get(fn) or ""
            forslag = str(forslag).strip()
            # Limit hard cap så lange svar ikke smadrer layoutet
            if len(forslag) > 80:
                forslag = forslag[:77].rstrip() + "…"
            resultat[fn] = forslag or _filnavn_til_default(fn)
        return resultat
    except Exception as e:
        print(f"DEBUG: udled_bilag_overskrifter fejlede: {e}")
        # Fallback: alle får filnavn-baseret default
        return {
            (f.get("filnavn") or ""): _filnavn_til_default(f.get("filnavn") or "")
            for f in filer
        }


def udled_sagsresume_strukturelt(analyse_tekst, sagsakter_tekst=""):
    """
    Udtrækker et struktureret resume af sagen baseret på den allerede
    genererede førstevurdering (og evt. sagsakter). Giver brugeren et
    lynhurtigt overblik over hvad sagen handler om, klagepunkter, krav
    og hvordan rejseselskabet har håndteret den indtil videre.

    Returnerer en dict:
      {
        "emne": str,                 # 1-2 sætninger
        "klagepunkter": [str, ...],  # 3-6 korte bullet points
        "krav": str,                 # klagers krav med beløb hvis oplyst
        "tui_handtering": str,       # hvordan TUI har håndteret det indtil nu
        "forventet_udfald": str      # ultrakort vurdering: udfald + beløb
      }
    eller None hvis udledningen fejler. Funktionen laver ét enkelt AI-kald
    og er designet til at køre lige efter førstevurderingen.
    """
    import json as _json
    import re as _re

    if not analyse_tekst or not analyse_tekst.strip():
        return None

    ekstra_kontekst = ""
    if sagsakter_tekst and sagsakter_tekst.strip():
        ekstra_kontekst = (
            f"\n\nSUPPLERENDE SAGSAKTER:\n{sagsakter_tekst[:3000]}"
        )

    prompt = (
        "Baseret på nedenstående juridiske førstevurdering af en klagesag "
        "fra Pakkerejse-Ankenævnet, udled et KORT struktureret resume af "
        "sagen. Resuméet skal gøre det muligt for en jurist at få "
        "lynhurtigt overblik over sagen.\n\n"
        f"FØRSTEVURDERING:\n{analyse_tekst[:8000]}"
        f"{ekstra_kontekst}\n\n"
        "RETURNÉR KUN dette JSON-objekt — ingen forklaring, ingen "
        "markdown, ingen kodeblok:\n"
        "{\n"
        '  "emne": "1-2 sætninger der forklarer hvad sagen handler om",\n'
        '  "klagepunkter": ["kort punkt 1", "kort punkt 2", "..."],\n'
        '  "krav": "en kort beskrivelse af hvad klager kræver, inkl. beløb hvis oplyst",\n'
        '  "tui_handtering": "kort beskrivelse af hvordan rejseselskabet (TUI) har håndteret sagen INDEN Nævnet blev involveret",\n'
        '  "forventet_udfald": "ULTRAKORT vurdering (max 15 ord) af det mest sandsynlige udfald + beløbsmæssigt estimat"\n'
        "}\n\n"
        "KRAV:\n"
        "- emne: 1-2 sætninger på dansk. Konkret, ikke generisk.\n"
        "- klagepunkter: KRITISK — du SKAL inkludere ALLE klagepunkter "
        "  klager rejser mod TUI, uanset hvor mange der er. Det er IKKE "
        "  nok at finde 3-6 'vigtigste'. Hvis klager nævner 8 forskellige "
        "  problemer, skal alle 8 stå på listen. Tag IKKE genvej. Hvert "
        "  punkt: max ~15 ord.\n"
        "- krav: skal indeholde beløb når de fremgår (fx '18.500 kr. i kompensation').\n"
        "- tui_handtering: ærlig og kort. Hvis det ikke fremgår skriv 'fremgår ikke af bilagene'.\n"
        "- forventet_udfald: ULTRAKORT — max 15 ord. Formater som én linje med det sandsynlige udfald og beløb.\n"
        "  Eksempler:\n"
        "    'Delvist medhold — formentlig 1.000-2.500 kr. i kompensation'\n"
        "    'Afvisning af klagen — TUI får medhold'\n"
        "    'Fuld medhold — kompensation på ca. 18.500 kr.'\n"
        "    'Forligstilbud på 2.000-4.000 kr. er den mest realistiske udgang'\n"
        "- Alt på dansk.\n"
        "- Hvis en oplysning ikke fremgår, skriv 'fremgår ikke' frem for at opfinde."
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=800,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        svar = response.content[0].text.strip()
        svar = _re.sub(r"^```(?:json)?\s*", "", svar)
        svar = _re.sub(r"\s*```$", "", svar).strip()
        data = _json.loads(svar)

        emne = str(data.get("emne") or "").strip()
        krav = str(data.get("krav") or "").strip()
        tui = str(data.get("tui_handtering") or "").strip()
        udfald = str(data.get("forventet_udfald") or "").strip()
        klagepunkter = data.get("klagepunkter") or []
        if isinstance(klagepunkter, str):
            klagepunkter = [klagepunkter]
        klagepunkter = [str(k).strip() for k in klagepunkter if str(k).strip()]

        if not emne:
            return None

        # Hvis modellen droppede 'forventet_udfald'-feltet (hvilket sker
        # nogle gange ved multi-felt JSON), så lav et separat fokuseret
        # kald der KUN producerer den ene linje. Det er billigt og sikrer
        # at boksen aldrig står tom.
        if not udfald or len(udfald) < 5:
            udfald = _udled_forventet_udfald_separat(analyse_tekst) or ""

        return {
            "emne": emne,
            "klagepunkter": klagepunkter,
            "krav": krav or "fremgår ikke",
            "tui_handtering": tui or "fremgår ikke af bilagene",
            "forventet_udfald": udfald or "Vurderingen kunne ikke udledes af analysen",
        }
    except Exception as e:
        print(f"DEBUG: Sagsresume-udledning fejlede: {e}")
        return None


def _udled_forventet_udfald_separat(analyse_tekst):
    """
    Hjælpefunktion: laver et fokuseret kald der KUN producerer den ene
    linje med forventet udfald + beløb. Bruges som fallback hvis det
    primære sagsresume-kald droppede feltet.
    """
    if not analyse_tekst or not analyse_tekst.strip():
        return None
    try:
        prompt = (
            "Læs nedenstående juridiske analyse af en pakkerejse-klagesag "
            "og giv mig ÉN linje (max 15 ord) der opsummerer det mest "
            "sandsynlige udfald + beløbsmæssigt estimat.\n\n"
            "Eksempler på god outputformat:\n"
            "  'Delvist medhold — formentlig 1.000-2.500 kr. i kompensation'\n"
            "  'Afvisning af klagen — TUI får medhold'\n"
            "  'Fuld medhold — kompensation på ca. 18.500 kr.'\n\n"
            "Returnér KUN linjen — ingen forklaring, ingen anførselstegn, "
            "ingen markdown.\n\n"
            f"ANALYSE:\n{analyse_tekst[:5000]}"
        )
        response = client.messages.create(
            model=MODEL,
            max_tokens=80,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip().strip('"').strip("'")
    except Exception as e:
        print(f"DEBUG: Separat forventet-udfald-udledning fejlede: {e}")
        return None


def opsummer_matches_til_visning(uploadet_sag, relevante_sager):
    """
    Generér struktureret match-metadata for hver retriever-match, til brug i
    de visuelle sagskort.

    Returnerer en liste af dicts i samme rækkefølge som 'relevante_sager':
      {
        "sagsnummer": str,
        "titel": str,
        "rejsearrangoer": str,
        "klagers_krav": str,
        "tilkendt_beloeb": str,
        "udfald": "Fuld medhold til klager" | "Delvist medhold" | "Afvist" | "Ukendt",
        "match_begrundelse": [str, str, ...]
      }

    Hvis AI-kaldet fejler eller output ikke kan parses, returneres en tom liste.
    """
    import json as _json
    import re as _re

    if not relevante_sager:
        return []

    # Kort resume af uploadede sag (første 3 filer, 1500 tegn hver)
    filer = uploadet_sag.get("filer") or []
    upload_dele = []
    for f in filer[:3]:
        t = f.get("tekst") or ""
        if t:
            upload_dele.append(f"--- {f.get('filnavn', 'fil')} ---\n{t[:1500]}")
    uploadet_resume = "\n\n".join(upload_dele)[:5000] or "(Ingen tekst udtrukket lokalt)"

    # Byg tekst for hver tidligere afgørelse — bruger udtraek_sagen_angaar
    # til at trække titel + 'Klagen angår'-afsnit + nævnets bemærkninger
    # ud, frem for at sende 5500 rå tegn med procedurel støj. Det giver
    # AI'en meget renere input når den vurderer relevans.
    sager_tekst = ""
    for i, s in enumerate(relevante_sager, 1):
        filnavn = s.get("filnavn", "ukendt")
        raw_indhold = s.get("indhold") or ""
        fokuseret = udtraek_sagen_angaar(raw_indhold, max_chars=2500)
        sager_tekst += (
            f"\n\n=== AFGØRELSE #{i} — filnavn: {filnavn} ===\n"
            f"{fokuseret}\n"
        )

    prompt = (
        "Du får nedenfor en NY KLAGESAG (sagsmateriale fra rejseselskabet) og "
        f"{len(relevante_sager)} TIDLIGERE AFGØRELSER fra Pakkerejse-Ankenævnet "
        "der EVENTUELT kan være relevante for den nye sag.\n\n"
        "DIN OPGAVE: For hver tidligere afgørelse skal du (1) udlede "
        "struktureret metadata, og (2) AFGØRE om den faktisk er JURIDISK "
        "RELEVANT for den nye sag — eller om matchet kun er overfladisk.\n\n"
        "═══════════════════════════════════════════════════════════════\n"
        "KRITISK: HVAD ER ET JURIDISK RELEVANT MATCH?\n"
        "═══════════════════════════════════════════════════════════════\n\n"
        "Et match SKAL være baseret på SPECIFIKKE detaljer der har "
        "RETSANVENDELIG BETYDNING for den nye sag. Det er IKKE nok at "
        "sagerne ligner hinanden overfladisk.\n\n"
        "✗ FORBUDTE (overfladiske, irrelevante) ligheder — DISSE GIVER "
        "IKKE ET MATCH:\n"
        "  - 'Begge sager involverer en familie' — type af rejsende "
        "(familie/par/single) har INGEN juridisk betydning\n"
        "  - 'Begge sager er om et hotel i Grækenland' — destination "
        "(Grækenland, Tyrkiet, Spanien osv.) har INGEN juridisk betydning\n"
        "  - 'Begge sager handler om mangler' — 'mangel' er ALT FOR "
        "BREDT; der findes hundredvis af typer mangler der intet har "
        "med hinanden at gøre juridisk\n"
        "  - 'Begge er pakkerejser' — alle Nævn-sager er pakkerejser\n"
        "  - 'Samme rejsearrangør' — irrelevant medmindre sagen handler "
        "om en specifik praksis hos den arrangør\n"
        "  - 'Samme hotel-kategori (3-stjernet, 4-stjernet osv.)' — "
        "INGEN juridisk betydning\n"
        "  - 'Begge sager involverer kontakt til guide/hotel/"
        "destinationsservice' — næsten ALLE Nævn-sager indeholder en "
        "eller anden form for guide-/hotel-kontakt. At nævne det som "
        "match er meningsløst. Kun den SPECIFIKKE NATUR af kontakten "
        "kan være juridisk relevant (se nedenfor).\n\n"
        "✓ KRÆVEDE (juridisk relevante) ligheder — DISSE TÆLLER SOM "
        "ÆGTE MATCH (én af dem er nok — krav om perfekt overlap er "
        "for stramt):\n"
        "  - LIGNENDE KONKRET MANGEL-TYPE: 'pool-mangel vs pool-mangel', "
        "'støjgener vs støjgener' (uanset om støjen er fra naboer, "
        "natklubber, byggepladser eller veje — det er samme juridiske "
        "tema), 'værelses-standard vs værelses-standard', 'ekstrasenge-"
        "mangel vs ekstrasenge-mangel', 'manglende tilkøbt udflugt vs "
        "samme', 'rengøringsmangel vs rengøringsmangel', 'fejlagtige "
        "afstands-/standardangivelser i markedsføring vs samme'\n"
        "  - SAMME JURIDISKE SPØRGSMÅL: rettidig reklamation, "
        "bistandspligt, forholdsmæssigt afslag, illusorisk opgradering, "
        "hotellets pres ved udtjekning osv.\n"
        "  - SAMME KOMPENSATIONS-PRINCIP: hvordan Nævnet vægter "
        "forholdsmæssigt afslag i sager om TILSVARENDE genekarakter "
        "(fx hvor stort afslag for 'utilstrækkelig nattero', "
        "'manglende rengøring i X dage' osv.) — selv hvis den konkrete "
        "mangel ikke er identisk\n"
        "  - SAMME SPECIFIKKE GUIDE-/DESTINATIONSSERVICE-PROBLEM (ikke "
        "blot at der var guide-kontakt — det er for bredt). Eksempler "
        "på specifikke, sammenlignelige guide-situationer:\n"
        "    • 'Klager kunne ikke komme i kontakt med guide trods "
        "  gentagne forsøg' vs samme\n"
        "    • 'Guide afviste reklamation på destinationen som "
        "  uberettiget' vs samme\n"
        "    • 'Guide var fysisk ikke til stede på hotellet/"
        "  destinationen' vs samme\n"
        "    • 'Guide lovede afhjælpning der ikke blev leveret' vs "
        "  samme\n"
        "    • 'Guide gav forkerte/misvisende oplysninger om "
        "  rejsedetaljer' vs samme\n"
        "    • 'Guide nægtede at registrere klagen formelt' vs samme\n"
        "    • 'Manglende guide-bistand i konkret nødssituation "
        "  (sygdom, skade, hotelafvisning)' vs samme\n"
        "  Generel 'guide-kontakt' er IKKE en juridisk lighed — kun "
        "den SPECIFIKKE problematik tæller.\n"
        "  - SAMME PARAGRAF eller vilkårspunkt anvendt: § 22 "
        "(forholdsmæssigt afslag), § 25 (bistandspligt), vilkårenes "
        "pkt. 5.1 osv.\n"
        "  - SAMME KONKRETE SITUATION: 'hotellet truede med anholdelse "
        "ved udtjekning', 'transfer leveret med taxa i stedet for bus', "
        "'illusorisk opgradering' osv.\n\n"
        "TIP TIL HVOR DU FINDER DE KONKRETE MANGLER:\n"
        "I tidligere afgørelser fra Pakkerejse-Ankenævnet står "
        "klagepunkterne ofte EKSPLICIT på første side under "
        "'Klagen angår' eller lignende. Brug DENNE sektion som "
        "primærkilde til at identificere de konkrete mangler — ikke "
        "kun det generelle resume.\n\n"
        "═══════════════════════════════════════════════════════════════\n"
        "BESLUTNINGS-REGEL FOR juridisk_relevant_match:\n"
        "═══════════════════════════════════════════════════════════════\n\n"
        "Sæt juridisk_relevant_match=TRUE hvis afgørelsen har MINIMUM "
        "ÉN af de KRÆVEDE ligheder ovenfor (lignende mangel-type ELLER "
        "samme juridiske spørgsmål ELLER samme kompensations-princip "
        "ELLER samme paragraf-anvendelse). Det skal ikke være perfekt "
        "match — bare relateret nok til at en jurist kan trække "
        "argumenter eller præcedens fra den.\n\n"
        "Sæt juridisk_relevant_match=FALSE KUN hvis afgørelsen "
        "udelukkende har overfladiske ligheder (samme destination, "
        "samme rejsearrangør, samme type rejsende) UDEN nogen af de "
        "krævede juridiske paralleller. Hellere én moderat-relevant "
        "match end en tom referencer-sektion.\n\n"
        "═══════════════════════════════════════════════════════════════\n"
        "MATERIALE:\n"
        "═══════════════════════════════════════════════════════════════\n\n"
        "NY SAG (uddrag af de uploadede filer):\n"
        f"{uploadet_resume}\n\n"
        "TIDLIGERE AFGØRELSER:"
        f"{sager_tekst}\n\n"
        "═══════════════════════════════════════════════════════════════\n"
        "OUTPUT-FORMAT:\n"
        "═══════════════════════════════════════════════════════════════\n\n"
        f"Returnér KUN en gyldig JSON-array med præcis {len(relevante_sager)} "
        "objekter, i nøjagtig samme rækkefølge som afgørelserne ovenfor. "
        "Ingen forklaring, ingen markdown-blok, intet ud over JSON. "
        "Hvert objekt skal have disse nøgler:\n"
        "  - sagsnummer (string): Nævnets sagsnummer, typisk 'ÅÅ-NNNN' "
        "(fx '24-290'). Udled fra filnavn eller tekst.\n"
        "  - titel (string): Kort beskrivende titel på sagens tema — "
        "4-8 danske ord (fx 'Pool-mangel og refusion afvist').\n"
        "  - rejsearrangoer (string): Navn på rejsearrangøren (fx 'TUI "
        "Danmark A/S'). IKKE CVR-nummer — udelad det. Hvis ikke nævnt, "
        "skriv 'ukendt'.\n"
        "  - klagers_krav (string): Hvad klageren krævede, fx '12.500 kr.' "
        "— eller 'ukendt' hvis ikke tydeligt i teksten.\n"
        "  - tilkendt_beloeb (string): Hvad Nævnet tilkendte klageren, "
        "fx '4.000 kr.' eller '0 kr.' hvis afvist, eller 'ukendt'.\n"
        "  - udfald (string): ÉN af disse PRÆCISE værdier: "
        "'Fuld medhold til klager', 'Delvist medhold', 'Afvist', eller "
        "'Ukendt'.\n"
        "  - juridisk_relevant_match (bool): TRUE hvis sagen har MINIMUM "
        "ÉN konkret juridisk relevant lighed (specifik mangel-type, "
        "samme paragraf, samme juridiske spørgsmål). FALSE hvis kun "
        "overfladiske ligheder (destination, rejsearrangør, "
        "rejsetype).\n"
        "  - match_begrundelse (array of strings): 2-4 KORTE bullets "
        "(6-14 ord hver) der KUN nævner KONKRETE juridisk relevante "
        "ligheder. INGEN overfladiske observationer. Hvis "
        "juridisk_relevant_match=false, skriv da én bullet: 'Ingen "
        "juridisk relevant lighed — kun overfladisk match (fx samme "
        "destination eller rejsearrangør)'.\n\n"
        "VIGTIGT: Returnér intet andet end selve JSON-arrayet. Start "
        "med '[' og slut med ']'."
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=3000,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        svar = response.content[0].text.strip()

        # Strip eventuelle markdown-kodeblokke
        svar = _re.sub(r"^```(?:json)?\s*", "", svar)
        svar = _re.sub(r"\s*```$", "", svar)

        data = _json.loads(svar)
        if not isinstance(data, list):
            return []

        # Sanity-check og normalisering
        resultat = []
        for item in data:
            if not isinstance(item, dict):
                resultat.append({})
                continue
            # juridisk_relevant_match defaulter til True for backward
            # kompatibilitet — hvis AI'en ikke returnerer feltet, antager
            # vi at sagen er relevant. Det betyder dog at filteringen i
            # forside.py kun har effekt når AI'en eksplicit har vurderet
            # juridisk_relevant_match=false.
            jr_raw = item.get("juridisk_relevant_match", True)
            if isinstance(jr_raw, str):
                juridisk_relevant = jr_raw.strip().lower() in (
                    "true", "1", "ja", "yes",
                )
            else:
                juridisk_relevant = bool(jr_raw)

            resultat.append({
                "sagsnummer": str(item.get("sagsnummer", "")).strip(),
                "titel": str(item.get("titel", "")).strip(),
                "rejsearrangoer": str(item.get("rejsearrangoer", "")).strip(),
                "klagers_krav": str(item.get("klagers_krav", "")).strip(),
                "tilkendt_beloeb": str(item.get("tilkendt_beloeb", "")).strip(),
                "udfald": str(item.get("udfald", "Ukendt")).strip(),
                "juridisk_relevant_match": juridisk_relevant,
                "match_begrundelse": [
                    str(b).strip()
                    for b in (item.get("match_begrundelse") or [])
                    if str(b).strip()
                ],
            })
        return resultat

    except Exception as e:
        print(f"DEBUG: opsummer_matches_til_visning fejlede: {e}")
        return []


def chat_om_sag(spoergsmaal, chat_historik, sag, sagsakter=None):
    """
    Kort, præcis chat-agtig besvarelse af et spørgsmål om en aktiv sag.
    Bruges i "Stil spørgsmål til sagen"-sektionen hvor juristen har en
    løbende samtale med PAX — ikke en fuld strukturel analyse.

    Forskelle fra spoerg_ai_med_sag:
      - Svarer KORT og præcist (typisk 1-4 afsnit, max ~300 ord)
      - Ingen pillar-struktur, ingen sandsynlighedsvurdering, ingen
        procenter — den del vises andre steder i UI'et
      - Bruger hele chat-historikken som kontekst så PAX husker hvad
        der allerede er talt om
      - Henter fortsat relevant juridisk præcedens via RAG

    Parametre:
      spoergsmaal: nyt spørgsmål fra brugeren
      chat_historik: liste af {"role": "user"|"assistant", "content": str}
                      — tidligere beskeder i samtalen (ekskl. det nye)
      sag: sag-dict med "filer"-liste
      sagsakter: evt. tekstuelle sagsakter

    Returnerer svartekst (string).
    """
    try:
        sagsakter_tekst = (sagsakter or "").strip()

        # Find relevant præcedens via RAG
        soge_dele = [spoergsmaal]
        # Brug også de seneste par user-beskeder som søgekontekst
        for besked in (chat_historik or [])[-3:]:
            if besked.get("role") == "user" and besked.get("content"):
                soge_dele.append(besked["content"])
        soge_tekst = "\n".join(soge_dele)

        relevante, _ = _hent_relevante_eller_fald_tilbage(soge_tekst)
        vidensbank = (
            _byg_vidensbank_tekst(relevante) if relevante
            else "(Ingen tidligere sager fundet i vidensbanken.)"
        )

        indled = (
            "KONTEKST — relevante tidligere afgørelser, rejsevilkår og "
            "pakkerejselov-paragraffer:\n"
            f"{vidensbank}\n\n"
            "SAGEN DU SKAL SVARE OM:"
        )

        sagsakter_blok = ""
        if sagsakter_tekst:
            sagsakter_blok = (
                "\nSAGSAKTER (intern viden fra juristen):\n"
                f"{sagsakter_tekst}\n"
            )

        chat_system = (
            SYSTEM_PROMPT
            + "\n\nDU ER NU I CHAT-TILSTAND. Svar KORT og præcist — "
            "typisk 1-4 afsnit, max ca. 300 ord. Ingen overskrifter, "
            "ingen pillar-struktur, ingen sandsynlighedsvurdering i "
            "procent. Skriv direkte og jordnært som i en samtale med en "
            "kollega. Henvis gerne til konkrete afgørelser (filnavn + "
            "år) eller lovparagraffer når det er relevant, men undgå "
            "lange udredninger. Hvis spørgsmålet er kort, er svaret kort."
        )

        # Byg sagskontekst som første user-message
        sag_content = _byg_sag_content(
            sag, indled, sagsakter_blok or "",
        )

        # Sammensæt messages: [sag-kontekst] + chat-historik + nyt spørgsmål
        messages = [{"role": "user", "content": sag_content}]

        # Føj et bekræftende assistant-svar så modellen ved at vi er
        # klar til at modtage spørgsmål om sagen
        messages.append({
            "role": "assistant",
            "content": (
                "Jeg har læst sagen og er klar til spørgsmål. "
                "Hvad vil du vide?"
            ),
        })

        # Tilføj historik (trimmes til de seneste 20 beskeder for at
        # holde prompten rimelig)
        for besked in (chat_historik or [])[-20:]:
            rolle = besked.get("role")
            indhold = besked.get("content") or ""
            if rolle in ("user", "assistant") and indhold.strip():
                messages.append({"role": rolle, "content": indhold})

        # Tilføj det nye spørgsmål
        messages.append({"role": "user", "content": spoergsmaal})

        response = client.messages.create(
            model=MODEL,
            max_tokens=1200,
            temperature=0.2,
            system=chat_system,
            messages=messages,
        )
        return response.content[0].text

    except Exception as e:
        return f"Fejl i chat: {e}"


def spoerg_ai_med_sag(
    spoergsmaal,
    sager,
    sag,
    sagsakter=None,
    sagsakter_filer=None,
    returner_relevante=False,
):
    """
    Stil et spørgsmål mod vidensbanken MED en hel sag (flere filer) som
    udgangspunkt. Dette er den nye udgave af spoerg_ai_med_klage der
    understøtter hele sagspakker fra Ankenævnet (høring + klageskema + bilag).

    sag: dict med "filer"-liste hvor hver fil er:
         {"filnavn", "type": "tekst"|"pdf_bytes", "tekst", "bytes", "rolle"}

    sagsakter: valgfri streng — interne C4C-notater, e-mails osv.

    returner_relevante: hvis True, returneres (svar_tekst, relevante_sager),
                       hvor relevante_sager er de RAG-matchede afgørelser/vilkår.
                       Hvis False (default), returneres kun svar-teksten.
    """
    try:
        sagsakter_tekst = (sagsakter or "").strip()
        filer = sag.get("filer") or []

        # Byg søgestreng til RAG: kombiner alle tekst-filer + sagsakter + spørgsmål
        dele = []
        for fil in filer:
            if fil.get("type") == "tekst" and fil.get("tekst"):
                # Kun første ~3000 tegn pr. fil — nok til at ramme tematik
                dele.append((fil.get("tekst") or "")[:3000])
        if sagsakter_tekst:
            dele.append(sagsakter_tekst[:3000])
        dele.append(f"Brugerens spørgsmål: {spoergsmaal}")
        soge_tekst = "\n\n".join(dele)

        # Udeluk alle filer i sagen fra RAG-resultatet så Claude ikke citerer
        # klagens egne filer som præcedens
        udeluk_filnavne = {f.get("filnavn") for f in filer}

        sporgsmaal_emb = embed_sporgsmaal(soge_tekst)
        relevante = []
        if sporgsmaal_emb is not None:
            afgoerelser = find_relevante_sager(
                sporgsmaal_emb,
                top_k=TOP_K_AFGOERELSER,
                dokumenttype="afgoerelse",
            )
            vilkaar = find_relevante_sager(
                sporgsmaal_emb,
                top_k=TOP_K_VILKAAR,
                dokumenttype="vilkaar",
            )
            lovgivning = find_relevante_sager(
                sporgsmaal_emb,
                top_k=TOP_K_LOVGIVNING,
                dokumenttype="lovgivning",
            )
            # Filtrér sagens egne filer ud
            relevante = [
                r for r in (afgoerelser + vilkaar + lovgivning)
                if r.get("filnavn") not in udeluk_filnavne
            ]

        vidensbank = _byg_vidensbank_tekst(relevante) if relevante else (
            "(Ingen tidligere sager fundet i vidensbanken.)"
        )

        indled = (
            f"VIDENSBANK (de mest relevante tidligere afgørelser og "
            f"TUI's rejsevilkår):\n"
            f"{vidensbank}\n\n"
            f"SAGENS DOKUMENTER (høring fra Nævnet + klageskema + bilag — "
            f"{len(filer)} filer i alt):"
        )

        sagsakter_blok = ""
        if sagsakter_tekst:
            sagsakter_blok = (
                "\nSAGSAKTER (intern viden: C4C-notater, e-mails, "
                f"bookingdetaljer):\n{sagsakter_tekst}\n\n"
                "Disse sagsakter supplerer de officielle bilag ovenfor.\n"
            )

        slutning = (
            sagsakter_blok
            + f"\nBRUGERENS SPØRGSMÅL / FOKUS:\n{spoergsmaal}\n\n"
            f"{_opgave_tekst()}\n\n"
            f"Husk: sagen består af FLERE FILER — høringsbrev fra Nævnet, "
            f"klageskema, og diverse bilag. Læs dem ALLE, krydsrefer mellem "
            f"klagerens påstande og bilagenes dokumentation, og identificér "
            f"uoverensstemmelser mellem klagerens version og rejseselskabets "
            f"dokumentation. Brug vidensbanken til præcedens. Inddrag også "
            f"eventuelle sagsakter-filer (screenshots, e-mails osv.) hvis "
            f"de er vedhæftet."
        )

        user_content = _byg_sag_content(
            sag, indled, slutning, ekstra_sagsakter_filer=sagsakter_filer
        )

        messages = [{"role": "user", "content": user_content}]
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            temperature=0,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        # Automatisk fortsættelse hvis modellen blev afbrudt af
        # token-loftet — sikrer at førstevurderingen aldrig afkortes
        # midt i en sætning for betalende brugere.
        svar_tekst = _faerdiggoer_hvis_afkortet(
            response, SYSTEM_PROMPT, messages,
        )
        if returner_relevante:
            return svar_tekst, relevante
        return svar_tekst

    except Exception as e:
        fejl = f"Fejl i forbindelsen til juriitech PAX: {str(e)}"
        if returner_relevante:
            return fejl, []
        return fejl


# ============================================================
# JSON-STRUKTURERET FØRSTEVURDERING (sektion 3-8 på forsiden)
# ============================================================
# Erstatter den frie markdown-tilgang (spoerg_ai_med_sag) for
# førstevurderingen. AI'en kaldes med tool-use og en stram JSON-schema —
# den kan literally ikke afvige fra strukturen fordi schemaet kun
# tillader de 6 felter vi har defineret.
#
# Hvert felt har en RIG beskrivelse der fortæller AI'en præcis hvad
# der skal stå, så indholdet bliver lige så fyldigt og juridisk skarpt
# som før. Forskellen er kun at strukturen er ufravigelig.
FOERSTEVURDERING_TOOL_NAME = "lever_juridisk_foerstevurdering"

FOERSTEVURDERING_SCHEMA = {
    "type": "object",
    "properties": {
        "klagens_kernepunkter": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Liste af de PRIMÆRE klagepunkter klager rejser mod "
                "rejseselskabet. Hvert element er en kort beskrivelse "
                "af et klagepunkt (max ~150 tegn). Inkludér ALLE "
                "klagepunkter fra den verificerede liste i "
                "kontekstprompten — uden undtagelse. Hvis klager "
                "nævner 8 problemer, angiv 8 elementer. Hvis 17, "
                "angiv 17. Brug formatet 'Klagepunkt N: [beskrivelse] "
                "[Bilag XX]' hvor [Bilag XX] er en eksplicit "
                "kildehenvisning i firkantede parenteser."
            ),
        },
        "yderligere_klagepunkter_og_detaljer": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Liste af SEKUNDÆRE klagepunkter, kontekstuelle "
                "detaljer og mindre kritikpunkter. Disse er IKKE "
                "primære for den juridiske vurdering men giver et "
                "komplet billede. Hver post er en kort beskrivelse "
                "med [Bilag XX]-reference. Hvis der ingen sekundære "
                "punkter er, returnér en tom liste []."
            ),
        },
        "rejseselskabets_stillingtagen_indtil_nu": {
            "type": "string",
            "description": (
                "Beskriv KRONOLOGISK hvad rejseselskabet (TUI/Spies/"
                "Apollo osv.) har gjort, tilbudt eller afvist i "
                "forhold til klagen INDEN Nævnet blev involveret. "
                "Inkluder konkrete datoer fra mail-korrespondance og "
                "sagsakter. Strukturér som flere afsnit (separer med "
                "\\n\\n) hvis der er flere faser (på destinationen, "
                "efter hjemkomst, sagsbehandlers svar, osv.). Brug "
                "[Bilag XX]-referencer. Hvis det ikke fremgår tydeligt, "
                "skriv 'fremgår ikke af bilagene'."
            ),
        },
        "kort_juridisk_vurdering": {
            "type": "string",
            "description": (
                "2-4 sætninger om de centrale juridiske spørgsmål i "
                "sagen. Hvilke paragraffer i pakkerejseloven finder "
                "anvendelse? Hvad er kernen i den juridiske "
                "vurdering? Brug konkrete §-henvisninger (fx '§ 22', "
                "'§ 25') og bilag-referencer. SKAL VÆRE KORT — ikke "
                "flere afsnit, ikke nummererede underargumenter, ikke "
                "Argument 1/2/3-format. Den fulde argumentation hører "
                "ikke hjemme her."
            ),
        },
        "sandsynlighedsvurdering": {
            "type": "object",
            "properties": {
                "fuld_medhold_til_klager": {
                    "type": "integer",
                    "description": (
                        "Procentpoint (0-100) for sandsynligheden af "
                        "FULDT medhold til klager."
                    ),
                },
                "delvist_medhold_til_klager": {
                    "type": "integer",
                    "description": (
                        "Procentpoint (0-100) for sandsynligheden af "
                        "DELVIST medhold til klager."
                    ),
                },
                "afvisning_af_klagen": {
                    "type": "integer",
                    "description": (
                        "Procentpoint (0-100) for sandsynligheden af "
                        "FULD afvisning af klagen."
                    ),
                },
                "begrundelse": {
                    "type": "string",
                    "description": (
                        "Kort begrundelse for de tre procenter (3-5 "
                        "sætninger) der forklarer hvorfor netop denne "
                        "fordeling er sandsynlig. Kan henvise til "
                        "tidligere afgørelser fra vidensbanken via "
                        "[Afgørelse XX-YYYY (ÅÅÅÅ)]-format."
                    ),
                },
            },
            "required": [
                "fuld_medhold_til_klager",
                "delvist_medhold_til_klager",
                "afvisning_af_klagen",
                "begrundelse",
            ],
            "description": (
                "Tre procenttal der summer til 100 + en begrundelse. "
                "Selv hvis sagen er ufuldstændigt oplyst, estimér "
                "ærligt baseret på hvad du kan udlede."
            ),
        },
        "konklusion_en_linje": {
            "type": "string",
            "description": (
                "ÉN ENKELT sætning (max 200 tegn) der opsummerer hvad "
                "denne sag samlet anbefales at ende med. Eksempel: "
                "'Sagen anbefales delvist afvist da reklamationen var "
                "for sen, mens TUI tilbyder 1.500 kr. for booking-"
                "fejlen.' INGEN bullets, INGEN flere sætninger, INGEN "
                "ekstra argumentation — kun ÉN linje."
            ),
        },
    },
    "required": [
        "klagens_kernepunkter",
        "yderligere_klagepunkter_og_detaljer",
        "rejseselskabets_stillingtagen_indtil_nu",
        "kort_juridisk_vurdering",
        "sandsynlighedsvurdering",
        "konklusion_en_linje",
    ],
}


def udled_foerstevurdering_struktureret(
    sag,
    sagsakter=None,
    sagsakter_filer=None,
    klagepunkter_facit="",
    tidsforhold_facit="",
    klagepunkter_liste=None,
):
    """
    Genererer den juridiske førstevurdering som STRUKTURERET JSON via
    Anthropics tool-use. AI'en kan bogstaveligt talt ikke producere
    andre felter end de 6 vi har defineret — schemaet håndhæves af
    Anthropic-API'et.

    Returnerer en tuple (data_dict, relevante_sager) hvor:
      data_dict — dict med præcis disse 6 keys:
        • klagens_kernepunkter (list of str)
        • yderligere_klagepunkter_og_detaljer (list of str)
        • rejseselskabets_stillingtagen_indtil_nu (str)
        • kort_juridisk_vurdering (str)
        • sandsynlighedsvurdering (dict)
        • konklusion_en_linje (str)
      relevante_sager — same RAG-result som spoerg_ai_med_sag returnerer,
        bruges af kalderen til match_info + visuelle reference-kort.

    Hvis AI-kaldet fejler, returneres (None, []) og kalderen kan vise
    en venlig fejlboks.
    """
    try:
        sagsakter_tekst = (sagsakter or "").strip()
        filer = sag.get("filer") or []

        # ---------- RAG-SØGNING ----------
        # NY STRATEGI: brug klagepunkter (hvis tilgængelige) som primær
        # embedding-query frem for raw filtekst. Klagepunkter er allerede
        # en koncentreret beskrivelse af HVAD sagen handler om — ingen
        # procedurel støj (datoer, adresser, sagsbehandler-navne osv.).
        # Det giver MEGET mere fokuserede semantiske matches.
        #
        # Falder tilbage til raw filtekst hvis klagepunkter ikke er
        # ekstraheret endnu (fx ved første kald før udled_alle_klagepunkter
        # er kørt).
        if klagepunkter_liste:
            soge_tekst = "Klagepunkter i sagen:\n" + "\n".join(
                f"- {kp}" for kp in klagepunkter_liste
            )
            print(
                f"DEBUG: bruger {len(klagepunkter_liste)} klagepunkter "
                "som RAG-søgequery (fokuseret)"
            )
        else:
            dele = []
            for fil in filer:
                if fil.get("type") == "tekst" and fil.get("tekst"):
                    dele.append((fil.get("tekst") or "")[:3000])
            if sagsakter_tekst:
                dele.append(sagsakter_tekst[:3000])
            soge_tekst = "\n\n".join(dele)
            print(
                "DEBUG: bruger raw filtekst som RAG-søgequery "
                "(fallback — klagepunkter ikke tilgængelige)"
            )

        udeluk_filnavne = {f.get("filnavn") for f in filer}

        sporgsmaal_emb = embed_sporgsmaal(soge_tekst)
        relevante = []
        if sporgsmaal_emb is not None:
            afgoerelser = find_relevante_sager(
                sporgsmaal_emb, top_k=TOP_K_AFGOERELSER,
                dokumenttype="afgoerelse",
            )
            vilkaar = find_relevante_sager(
                sporgsmaal_emb, top_k=TOP_K_VILKAAR,
                dokumenttype="vilkaar",
            )
            lovgivning = find_relevante_sager(
                sporgsmaal_emb, top_k=TOP_K_LOVGIVNING,
                dokumenttype="lovgivning",
            )
            relevante = [
                r for r in (afgoerelser + vilkaar + lovgivning)
                if r.get("filnavn") not in udeluk_filnavne
            ]

        vidensbank = (
            _byg_vidensbank_tekst(relevante) if relevante
            else "(Ingen tidligere sager fundet i vidensbanken.)"
        )

        # ---------- BYG PROMPT-INDLEDNING ----------
        indled = (
            f"VIDENSBANK (de mest relevante tidligere afgørelser og "
            f"TUI's rejsevilkår):\n{vidensbank}\n\n"
            f"SAGENS DOKUMENTER (høring fra Nævnet + klageskema + "
            f"bilag — {len(filer)} filer i alt):"
        )

        sagsakter_blok = ""
        if sagsakter_tekst:
            sagsakter_blok = (
                "\nSAGSAKTER (intern viden: C4C-notater, e-mails, "
                f"bookingdetaljer):\n{sagsakter_tekst}\n\n"
                "Disse sagsakter supplerer de officielle bilag ovenfor.\n"
            )

        slutning = (
            sagsakter_blok
            + klagepunkter_facit
            + tidsforhold_facit
            + "\n\nDIN OPGAVE:\n"
            + "Du skal kalde tool'et "
            + f"'{FOERSTEVURDERING_TOOL_NAME}' med en JSON-struktureret "
            + "førstevurdering af sagen. Læs ALLE bilag, krydsrefer mellem "
            + "klagerens påstande og bilagenes dokumentation, brug "
            + "vidensbanken som juridisk præcedens, og inkluder "
            + "[Bilag XX]-referencer i alle felter. Følg felt-"
            + "beskrivelserne præcist — de definerer indholdet af hver "
            + "sektion. Husk: 'kort_juridisk_vurdering' er KORT (2-4 "
            + "sætninger), og 'konklusion_en_linje' er ÉN sætning."
        )

        user_content = _byg_sag_content(
            sag, indled, slutning, ekstra_sagsakter_filer=sagsakter_filer
        )

        # ---------- KALD CLAUDE MED TOOL-USE ----------
        # tool_choice tvinger modellen til at kalde præcis dette tool —
        # den kan ikke svare med fri tekst i stedet.
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            temperature=0,
            system=SYSTEM_PROMPT,
            tools=[{
                "name": FOERSTEVURDERING_TOOL_NAME,
                "description": (
                    "Lever en struktureret juridisk førstevurdering af "
                    "sagen som JSON. Alle 6 felter er obligatoriske og "
                    "skal udfyldes baseret på sagens dokumenter, "
                    "vidensbankens præcedens og de verificerede "
                    "klagepunkter."
                ),
                "input_schema": FOERSTEVURDERING_SCHEMA,
            }],
            tool_choice={
                "type": "tool",
                "name": FOERSTEVURDERING_TOOL_NAME,
            },
            messages=[{"role": "user", "content": user_content}],
        )

        # ---------- HENT TOOL-USE OUTPUT ----------
        for block in response.content:
            if (
                getattr(block, "type", None) == "tool_use"
                and getattr(block, "name", None)
                == FOERSTEVURDERING_TOOL_NAME
            ):
                data = block.input
                # Defensive normalisering af typer
                return _normalisér_foerstevurdering(data), relevante

        # Hvis vi når hertil har modellen ikke kaldt tool'et — det er
        # meget sjældent når tool_choice er sat, men vi vil ikke crashe.
        print(
            "DEBUG: udled_foerstevurdering_struktureret — modellen "
            "kaldte ikke tool'et som forventet"
        )
        return None, relevante

    except Exception as e:
        print(f"DEBUG: udled_foerstevurdering_struktureret fejlede: {e}")
        return None, []


def _normalisér_foerstevurdering(data):
    """
    Sikrer at alle 6 forventede felter er til stede med korrekte typer.
    Hvis AI-resultatet mangler et felt eller har forkert type, sættes
    en tom default ind — så frontend-renderingen aldrig crasher.
    """
    if not isinstance(data, dict):
        data = {}

    def _str(v):
        if v is None:
            return ""
        if isinstance(v, str):
            return v.strip()
        return str(v).strip()

    def _list_str(v):
        if not isinstance(v, list):
            return []
        return [_str(x) for x in v if _str(x)]

    sandsynlighed = data.get("sandsynlighedsvurdering") or {}
    if not isinstance(sandsynlighed, dict):
        sandsynlighed = {}

    def _int(v, default=0):
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    return {
        "klagens_kernepunkter": _list_str(
            data.get("klagens_kernepunkter")
        ),
        "yderligere_klagepunkter_og_detaljer": _list_str(
            data.get("yderligere_klagepunkter_og_detaljer")
        ),
        "rejseselskabets_stillingtagen_indtil_nu": _str(
            data.get("rejseselskabets_stillingtagen_indtil_nu")
        ),
        "kort_juridisk_vurdering": _str(
            data.get("kort_juridisk_vurdering")
        ),
        "sandsynlighedsvurdering": {
            "fuld_medhold_til_klager": _int(
                sandsynlighed.get("fuld_medhold_til_klager")
            ),
            "delvist_medhold_til_klager": _int(
                sandsynlighed.get("delvist_medhold_til_klager")
            ),
            "afvisning_af_klagen": _int(
                sandsynlighed.get("afvisning_af_klagen")
            ),
            "begrundelse": _str(sandsynlighed.get("begrundelse")),
        },
        "konklusion_en_linje": _str(data.get("konklusion_en_linje")),
    }


def foerstevurdering_dict_til_markdown(data):
    """
    Konverterer JSON-output fra udled_foerstevurdering_struktureret
    til den markdown-format som render_analyse_som_pillars forventer
    (sektioner med **N. Titel**-headers + body).

    Vi bygger markdownen DETERMINISTISK — så uanset hvad AI'en gjorde
    inde i hvert felt, er sektion-strukturen 100% korrekt. Force-mappingen
    i render_analyse_som_pillars vil bekræfte dette og gøre intet (no-op).
    """
    if not data:
        return ""

    def _bullets(items):
        if not items:
            return "_(Ingen punkter at vise.)_"
        return "\n".join(f"- {item}" for item in items)

    sandsynlighed = data.get("sandsynlighedsvurdering") or {}
    fuld = sandsynlighed.get("fuld_medhold_til_klager", 0)
    delvist = sandsynlighed.get("delvist_medhold_til_klager", 0)
    afvist = sandsynlighed.get("afvisning_af_klagen", 0)
    begrundelse = sandsynlighed.get("begrundelse", "")

    # Sandsynlighedsvurdering-sektionen indeholder de tre procenter i
    # det format som vurdering.parse_sandsynligheder kan parse + en
    # kort begrundelse.
    sandsynlighed_body = (
        f"**Fuld medhold til klager:** {fuld}%\n"
        f"**Delvist medhold til klager:** {delvist}%\n"
        f"**Afvisning af klagen:** {afvist}%"
    )
    if begrundelse:
        sandsynlighed_body += f"\n\n{begrundelse}"

    sektioner = [
        ("1. Klagens kernepunkter",
         _bullets(data.get("klagens_kernepunkter") or [])),
        ("2. Yderligere klagepunkter og detaljer",
         _bullets(data.get("yderligere_klagepunkter_og_detaljer") or [])),
        ("3. Rejseselskabets stillingtagen indtil nu",
         data.get("rejseselskabets_stillingtagen_indtil_nu") or
         "_(Fremgår ikke af bilagene.)_"),
        ("4. Kort juridisk vurdering",
         data.get("kort_juridisk_vurdering") or
         "_(Vurdering kunne ikke udledes.)_"),
        ("5. Sandsynlighedsvurdering", sandsynlighed_body),
        ("6. Konklusion i én linje",
         data.get("konklusion_en_linje") or
         "_(Konklusion kunne ikke udledes.)_"),
    ]

    return "\n\n".join(
        f"**{titel}**\n\n{body}" for titel, body in sektioner
    )


def generer_svarbrev_til_sag(
    sag,
    sagsakter=None,
    ekstra_instrukser=None,
    inkluder_kildehenvisninger=False,
    verificerede_klagepunkter=None,
    tidsforhold=None,
):
    """
    Genererer et komplet udkast til svarbrev baseret på HELE sagspakken
    (høring + klageskema + alle bilag), ikke kun én klage-fil.

    inkluder_kildehenvisninger: bool. Hvis True inkluderer brevet
        eksplicitte bilag-/lov-/vilkårs-referencer. Default False.

    verificerede_klagepunkter: list[str] eller None. Hvis None, kører
        vi udled_alle_klagepunkter() automatisk for at sikre 100%
        klagepunkt-dækning.

    tidsforhold: dict eller None. Hvis None, kører vi udled_tidsforhold()
        for at finde reklamations-tidsforhold. Bruges som forsvars-
        argument i svarbrevet hvis klager har reklameret for sent.
    """
    try:
        # KRITISK: Sikr at vi har en udtømmende liste over alle
        # klagepunkter før vi genererer svarbrevet. Uden listen kan AI'en
        # springe punkter over — med listen som facit garanterer vi at
        # alle adresseres. Hvis kalderen allerede har udtrukket listen
        # (forside.py gør det før førstevurderingen), genbruger vi den.
        if verificerede_klagepunkter is None:
            verificerede_klagepunkter = udled_alle_klagepunkter(
                sag=sag,
                sagsakter_tekst=(sagsakter or "").strip(),
            )

        # Tilsvarende: udtræk tidsforhold (rettidig reklamation) hvis
        # ikke allerede gjort. Pakkerejse-Ankenævnet vægter dette
        # ekstremt højt og det er ofte et stærkt forsvarsargument.
        if tidsforhold is None:
            tidsforhold = udled_tidsforhold(
                sag=sag,
                sagsakter_tekst=(sagsakter or "").strip(),
            )

        # Byg den korrekte svarbrev-prompt baseret på flag + data
        svarbrev_opgave = byg_svarbrev_opgave(
            inkluder_kildehenvisninger=inkluder_kildehenvisninger,
            verificerede_klagepunkter=verificerede_klagepunkter,
            tidsforhold=tidsforhold,
        )
        sagsakter_tekst = (sagsakter or "").strip()
        filer = sag.get("filer") or []

        dele = []
        for fil in filer:
            if fil.get("type") == "tekst" and fil.get("tekst"):
                dele.append((fil.get("tekst") or "")[:3000])
        if sagsakter_tekst:
            dele.append(sagsakter_tekst[:3000])
        dele.append("Udarbejd svarbrev til Pakkerejseankenævnet")
        soge_tekst = "\n\n".join(dele)

        udeluk_filnavne = {f.get("filnavn") for f in filer}
        sporgsmaal_emb = embed_sporgsmaal(soge_tekst)
        relevante = []
        if sporgsmaal_emb is not None:
            afgoerelser = find_relevante_sager(
                sporgsmaal_emb,
                top_k=TOP_K_AFGOERELSER,
                dokumenttype="afgoerelse",
            )
            vilkaar = find_relevante_sager(
                sporgsmaal_emb,
                top_k=TOP_K_VILKAAR,
                dokumenttype="vilkaar",
            )
            lovgivning = find_relevante_sager(
                sporgsmaal_emb,
                top_k=TOP_K_LOVGIVNING,
                dokumenttype="lovgivning",
            )
            relevante = [
                r for r in (afgoerelser + vilkaar + lovgivning)
                if r.get("filnavn") not in udeluk_filnavne
            ]
        vidensbank = _byg_vidensbank_tekst(relevante) if relevante else (
            "(Ingen tidligere sager fundet i vidensbanken.)"
        )

        indled = (
            f"VIDENSBANK (præcedens + rejsevilkår):\n{vidensbank}\n\n"
            f"SAGEN DER SKAL BESVARES ({len(filer)} filer):"
        )

        sagsakter_blok = ""
        if sagsakter_tekst:
            sagsakter_blok = (
                f"\nSAGSAKTER (intern viden):\n{sagsakter_tekst}\n"
            )

        ekstra = ""
        if ekstra_instrukser and ekstra_instrukser.strip():
            ekstra = (
                f"\nSÆRLIGE INSTRUKSER FRA JURISTEN:\n"
                f"{ekstra_instrukser.strip()}\n"
            )

        slutning = sagsakter_blok + ekstra + svarbrev_opgave

        user_content = _byg_sag_content(sag, indled, slutning)

        response = client.messages.create(
            model=MODEL,
            max_tokens=6000,
            temperature=0.2,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        svarbrev_tekst = response.content[0].text

        # Sikkerhedsnet: anonymiser svarbrevet før det returneres til juristen
        return _sikr_svarbrev_anonymiseret(svarbrev_tekst)

    except Exception as e:
        return f"Fejl i generering af svarbrev: {str(e)}"


def spoerg_ai_med_klage(spoergsmaal, sager, klage, sagsakter=None):
    """
    Stil et spørgsmål mod vidensbanken MED en uploadet klage som udgangspunkt.

    'klage' er en dict fra processor.laes_klage():
      {"type": "tekst",     "filnavn": str, "tekst": str}
      {"type": "pdf_bytes", "filnavn": str, "bytes": bytes}

    'sagsakter' er en valgfri streng med ekstra kontekst — typisk C4C-notater,
    e-mails, bookingdetaljer, destinationsrapport osv. Denne tekst sendes som
    supplerende materiale til Claude sammen med klagen og gemmes IKKE
    permanent i vidensbanken (den er specifik for denne ene analyse).

    RAG-logik:
      - For tekst-klager: vi embedder en kombination af klagens indhold +
        sagsakter + brugerens spørgsmål for bedst muligt RAG-match.
      - For scannede PDF-klager: vi embedder kun spørgsmål + sagsakter;
        Claude læser selv PDF'en via vision.

    Den aktuelle klage udelades fra RAG-resultatet.

    'sager'-parameteren bevares for bagudkompatibilitet men ignoreres.
    """
    try:
        klage_filnavn = klage.get("filnavn", "ukendt_klage")
        sagsakter_tekst = (sagsakter or "").strip()

        # Byg søgestreng — jo mere kontekst, jo bedre RAG-match.
        dele = []
        if klage.get("type") == "tekst":
            klage_tekst = klage.get("tekst") or ""
            if klage_tekst:
                dele.append(klage_tekst)
        if sagsakter_tekst:
            dele.append(sagsakter_tekst)
        dele.append(f"Brugerens spørgsmål: {spoergsmaal}")
        soge_tekst = "\n\n".join(dele)

        relevante, mode = _hent_relevante_eller_fald_tilbage(
            soge_tekst, udeluk_filnavn=klage_filnavn
        )

        vidensbank = _byg_vidensbank_tekst(relevante) if relevante else (
            "(Ingen tidligere sager fundet i vidensbanken.)"
        )

        tekst_omkring_klage = (
            f"VIDENSBANK (de {len(relevante)} mest relevante tidligere sager "
            f"og vilkår-passager):\n"
            f"{vidensbank}\n\n"
            f"NY KLAGE DER SKAL ANALYSERES — filnavn: {klage_filnavn}\n"
        )

        # Sagsakter-sektion — vises kun hvis der er noget at vise
        sagsakter_blok = ""
        if sagsakter_tekst:
            sagsakter_blok = (
                "\nSAGSAKTER (C4C-notater, e-mails, bookingdetaljer og andre "
                "interne oplysninger fra rejseselskabet):\n"
                f"{sagsakter_tekst}\n"
                "Disse sagsakter er specifik intern viden for DENNE klage. "
                "Brug dem aktivt i analysen.\n"
            )

        opgave = (
            sagsakter_blok
            + f"\nBRUGERENS SPØRGSMÅL / FOKUS:\n{spoergsmaal}\n\n"
            f"{_opgave_tekst()}\n\n"
            f"Husk: læs klagen OG sagsakterne grundigt, identificér hvad sagen "
            f"reelt handler om (forsinkelse, aflysning, mangler ved indlogering, "
            f"osv.), krydsreferer mellem klagens påstande og sagsakternes "
            f"oplysninger, og brug vidensbanken til at finde de mest relevante "
            f"tidligere AFGØRELSER."
        )

        if klage["type"] == "pdf_bytes":
            pdf_b64 = base64.standard_b64encode(klage["bytes"]).decode("utf-8")
            user_content = [
                {"type": "text", "text": tekst_omkring_klage + "Klagen er vedhæftet som PDF nedenfor:"},
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": pdf_b64,
                    },
                },
                {"type": "text", "text": opgave},
            ]
        else:
            user_content = (
                tekst_omkring_klage
                + "\nKLAGENS INDHOLD:\n"
                + (klage.get("tekst") or "")
                + "\n"
                + opgave
            )

        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            temperature=0,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        return response.content[0].text

    except Exception as e:
        return f"Fejl i forbindelsen til juriitech PAX: {str(e)}"
