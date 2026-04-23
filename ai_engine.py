import os
import base64
from dotenv import load_dotenv
import anthropic

from embeddings import embed_sporgsmaal
from database import find_relevante_sager, hent_alle_sager

# Læs API-nøgle fra .env (ikke hardcoded i koden)
load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4000

# Antal AFGØRELSER vi henter pr. spørgsmål — 5 giver Claude nok juridisk
# præcedens til at finde de 3-5 mest relevante referencer.
TOP_K_AFGOERELSER = 5

# Antal VILKÅR/regler-passager vi henter pr. spørgsmål. 3 er nok til at
# dække de relevante kontraktuelle punkter uden at fylde prompten op.
TOP_K_VILKAAR = 3

# Samlet øvre loft når vi falder tilbage til "hent alle" — forhindrer
# at prompten eksploderer hvis RAG svigter.
TOP_K_FALLBACK = 8

# Øvre grænse på hvor lang en tekst vi sender pr. sag. Dette beskytter
# prompten mod ekstremt lange dokumenter og holder svartiden nede.
MAX_CHARS_PR_SAG = 15_000

SYSTEM_PROMPT = (
    "Du er en højt specialiseret juridisk konsulent for et rejseselskab "
    "og ekspert i Pakkerejseankenævnets praksis. Din tone er professionel, "
    "objektiv og analytisk. Du skal altid finde de stærkeste forsvarspunkter "
    "for rejseselskabet baseret på de tidligere afgørelser i vidensbanken.\n"
    "\n"
    "FLERSPROGEDE DOKUMENTER:\n"
    "Sagens bilag kan være på flere sprog — typisk dansk, engelsk, tysk, "
    "svensk eller norsk. Du skal læse, forstå og bruge indholdet i ALLE "
    "bilag uanset sprog. Når du citerer fra et ikke-dansk bilag i din "
    "analyse, så oversæt citatet til dansk og angiv det oprindelige sprog "
    "i parentes, fx: 'Ifølge hotellets e-mail (oversat fra engelsk): "
    '"Vi tilbød værelsesskift ved ankomst." (Bilag 05)\'. Dine svar, '
    "analyser og svarbreve skal altid skrives på dansk.\n"
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
    "VIDENSBANKEN indeholder tre typer dokumenter:\n"
    "  - AFGØRELSE: en tidligere kendelse fra Pakkerejseankenævnet, hvor "
    "udfaldet (fuld medhold / delvist medhold / afvist) og beløb fremgår af teksten. "
    "Disse er din juridiske præcedens.\n"
    "  - KLAGE: en indkommen klage, der IKKE er afgjort endnu. Her kender vi "
    "kravet, men ikke udfaldet. Brug kun KLAGER som kontekst/fingerpeg om "
    "hvilke typer sager rejseselskabet har haft — ALDRIG som juridisk præcedens.\n"
    "  - REJSESELSKABETS VILKÅR: rejsebetingelser, regler, retningslinjer og "
    "procedurer hentet direkte fra rejseselskabets egen hjemmeside. Dette er "
    "kontraktgrundlaget mellem rejseselskabet og kunden og skal bruges aktivt "
    "i argumentationen — 'ifølge punkt X i rejsevilkårene ...'."
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
        "3. SAMMENLIGNING\n"
        "   Forklar hvorfor denne sag minder om eller adskiller sig fra tidligere praksis. "
        "Henvis konkret til afgørelser fra vidensbanken.\n\n"
        "4. SANDSYNLIGHEDSVURDERING\n"
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
        "5. KONKLUSION I ÉN LINJE\n"
        "   En enkelt sætning der opsummerer det mest sandsynlige udfald og "
        "rejseselskabets anbefalede strategi."
    )


def _hent_relevante_eller_fald_tilbage(soge_tekst, udeluk_filnavn=None):
    """
    Finder relevante sager via embedding-søgning og kombinerer tre typer:
      - De TOP_K_AFGOERELSER mest relevante AFGØRELSER (juridisk præcedens)
      - De TOP_K_VILKAAR mest relevante VILKÅR-passager (kontraktgrundlaget)
      - Evt. KLAGER bliver ikke hentet separat (klager er kun kontekst)

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
        kombineret = afgoerelser + vilkaar
        if kombineret:
            return kombineret, "rag"

    # Fallback: hent et begrænset udvalg fra alle sager. Dette er langsommere
    # men sikrer at systemet virker selv hvis embeddings fejler.
    print("DEBUG: RAG-søgning gav intet resultat — falder tilbage til alle sager")
    alle = hent_alle_sager()
    if udeluk_filnavn:
        alle = [s for s in alle if s.get("filnavn") != udeluk_filnavn]
    return alle[:TOP_K_FALLBACK], "fallback"


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

        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            temperature=0,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        return response.content[0].text

    except Exception as e:
        return f"Fejl i forbindelsen til Juriitech: {str(e)}"


ANONYMISERING_PROMPT = """
Du er en anonymiseringsassistent der arbejder efter Pakkerejse-Ankenævnets
officielle retningslinjer (Retningslinjer for anonymisering 2023 + Vejledning
til rejsearrangøren om besvarelse af klagesager og anonymisering 2022).

REGLER DU SKAL FØLGE:

1. GENERISKE BETEGNELSER — brug disse konsekvent i hele teksten:
   - Klager / klagers: **K**  (hvis flere klagere: K1, K2, K3 ...)
   - Rejsearrangør/TUI-medarbejder: **R**
   - Bipersoner (medrejsende ægtefælle, børn, rejseledsagere der ikke er part): **B1**, **B2** ...
   - Guider eller hotelpersonale der er relevante: **G** eller **G1**, **G2**

2. OPLYSNINGER DER SKAL FJERNES ELLER ERSTATTES:
   - Personnavne → erstatter med K, K1, R, B1 osv.
   - Adresser (gadenavn + nr.) → "[adresse fjernet]"
   - CPR-numre → "[CPR fjernet]" (ALTID — også for klager, også for bipersoner)
   - Fødselsdatoer (ud over rejsedatoer) → "[fødselsdato fjernet]"
   - Telefonnumre → "[telefon fjernet]"
   - E-mailadresser → "[e-mail fjernet]"
   - Booking-/kundenumre → maskeres delvist (fx '12345678' → '12****78')
   - Bankoplysninger, kontonumre → "[bankoplysninger fjernet]"
   - Oplysninger om strafbare forhold og følsomme oplysninger (helbred,
     religion, etnicitet) om BIPERSONER → fjernes helt
   - Følsomme oplysninger om klager der IKKE er nødvendige for sagen → fjernes

3. OPLYSNINGER DER SKAL BEVARES (de er relevante for sagens afgørelse):
   - Hotelnavne, feriedestinationer, byer, lande, lufthavne
   - Rejsedatoer, rejseperiode, ophold
   - Priser og beløb
   - Klagepunkterne i substans
   - Selve korrespondance og dialog (bare med anonymiserede navne)
   - Dokumentationskilder og henvisninger (bilagsnumre, sagsnumre)

4. FORMATERING:
   - Bevar teksten i samme struktur som originalen (afsnit, overskrifter, lister)
   - Anonymisering skal være ENSARTET — samme person altid samme kode
   - Hvis noget er gennemstreget eller fremhævet i originalen, marker det på lignende vis
   - Hvis du er i tvivl om en oplysning skal fjernes: fjern den hellere end at lade den stå

OUTPUT:
Returnér alene den anonymiserede tekst — ingen forklaringer, ingen intro,
ingen afslutningskommentarer. Start direkte med teksten.

Hvis teksten er meget kort eller ikke indeholder personoplysninger, returnér
den oprindelige tekst uændret.

---
TEKST DER SKAL ANONYMISERES:
"""


def anonymiser_tekst(tekst, filnavn=None):
    """
    Anonymiserer en enkelt tekstfil efter Ankenævnets regler.
    Returnerer den anonymiserede tekst.
    """
    try:
        if not tekst or not tekst.strip():
            return ""
        # For meget lange tekster trunkeres lidt for at holde inden for max_tokens
        if len(tekst) > 50_000:
            tekst = tekst[:50_000] + "\n\n[...teksten er trunkeret på grund af længde...]"

        header = f"\n[Filnavn: {filnavn}]\n" if filnavn else ""

        response = client.messages.create(
            model=MODEL,
            max_tokens=8000,
            temperature=0,
            system=(
                "Du er en præcis og regel-tro anonymiseringsassistent for "
                "rejsearrangører der skal svare Pakkerejse-Ankenævnet. Du "
                "følger Ankenævnets officielle retningslinjer nøje."
            ),
            messages=[{
                "role": "user",
                "content": ANONYMISERING_PROMPT + header + tekst,
            }],
        )
        return response.content[0].text

    except Exception as e:
        return f"[Fejl i anonymisering: {str(e)}]"


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
            max_tokens=4000,
            temperature=0,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        return response.content[0].text

    except Exception as e:
        return f"Fejl i generering af tjekliste: {str(e)}"


SVARBREV_OPGAVE = """
OPGAVE: Generer et KOMPLET UDKAST til svarbrev fra rejseselskabet til
Pakkerejseankenævnet, struktureret som nedenfor. Skriv i et formelt,
professionelt juridisk sprog — men ikke stivt. Brug præcise henvisninger
til vidensbanken og rejsevilkårene.

STRUKTUR — følg nøjagtigt denne rækkefølge, med overskrifterne som vist:

**1. Indledning**
En kort, formel indledning der bekræfter modtagelsen af klagen og angiver
klagens sagsnummer (hvis tilgængeligt i klagen/sagsakterne) og dato.

**2. Sagens faktuelle omstændigheder**
En neutral, kronologisk gennemgang af hvad der faktisk skete, baseret på
klagen, sagsakterne (C4C, e-mails, booking), og rejsevilkårene. Skelner
tydeligt mellem hvad der er dokumenteret og hvad der er påstand fra klageren.

**3. Rejseselskabets stillingtagen til kravet**
Klar angivelse af om kravet bestrides helt, delvist, eller anerkendes.
Én linje: "Rejseselskabet [bestrider kravet / bestrider kravet delvist /
anerkender kravet delvist]."

**4. Juridisk argumentation**
De stærkeste forsvarsargumenter baseret på:
  a) REJSEVILKÅRENE — citér konkret hvilke punkter der gælder
  b) TIDLIGERE AFGØRELSER fra Nævnet — henvis med filnavn og år, fx
     "I afgørelse 19-1467 (2019) fandt Nævnet, at ..."
  c) SAGSAKTERNES faktuelle oplysninger — brug C4C, e-mails og booking-
     detaljer til at understøtte rejseselskabets version

**5. Konklusion og påstand**
En klar afslutning hvor rejseselskabet anmoder Nævnet om at
[afvise klagen / fastsætte delvis kompensation på X kr. / ...].
Inkludér eventuelt subsidiær påstand.

**6. Afslutning**
Formel afslutning ("Med venlig hilsen, ..."). Brug placeholder
"[Navn på sagsbehandler]" hvis intet navn er oplyst.

STRENGE KRAV:
- Opfind ALDRIG fakta der ikke står i klagen, sagsakterne eller vidensbanken.
- Henvis ALTID til konkrete kilder (filnavn + år for afgørelser, punkt + overskrift for vilkår).
- Skriv på dansk i et formelt, professionelt juridisk sprog.
- Hvis en oplysning mangler der er nødvendig for et solidt brev, skriv
  "[SAGSBEHANDLER UDFYLDER: ...]" som placeholder i stedet for at gætte.
"""


def generer_svarbrev(klage, sagsakter=None, ekstra_instrukser=None):
    """
    Genererer et komplet udkast til svarbrev fra rejseselskabet til Nævnet.

    klage: dict fra processor.laes_klage() (samme format som spoerg_ai_med_klage)
    sagsakter: valgfri streng med C4C-notater, e-mails, bookingdetaljer
    ekstra_instrukser: valgfri streng hvis brugeren vil styre tonen eller
                       fokusere på bestemte argumenter

    Returnerer svarbrevets tekst som markdown, eller en fejlbesked.
    """
    try:
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

        prompt_tekst = kontekst + sagsakter_blok + ekstra + SVARBREV_OPGAVE

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
                {"type": "text", "text": sagsakter_blok + ekstra + SVARBREV_OPGAVE},
            ]
        else:
            user_content = (
                kontekst
                + "\nKLAGENS INDHOLD:\n"
                + (klage.get("tekst") or "")
                + "\n"
                + sagsakter_blok
                + ekstra
                + SVARBREV_OPGAVE
            )

        response = client.messages.create(
            model=MODEL,
            max_tokens=6000,  # svarbreve kan være længere end analyser
            temperature=0.2,  # lidt temperatur til et mere naturligt sprog
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        return response.content[0].text

    except Exception as e:
        return f"Fejl i generering af svarbrev: {str(e)}"


def _byg_sag_content(sag, indled_tekst, slutnings_tekst):
    """
    Bygger Claude's message-content liste ud fra en sag (dict med 'filer'-nøgle).

    Tekstfiler inlines som text-blokke med tydelige separatorer.
    Scannede PDF'er (pdf_bytes) sendes som document-blokke så Claude
    kan læse dem via vision.

    indled_tekst og slutnings_tekst er strenge der pakkes rundt om sagens filer
    (typisk VIDENSBANK før og OPGAVE efter).
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

            # Overskrift for filen
            header = (
                f"\n--- FIL {i}/{len(filer)} — ROLLE: {rolle_label} — "
                f"FILNAVN: {filnavn} ---\n"
            )

            if fil.get("type") == "pdf_bytes" and fil.get("bytes"):
                # Scannet PDF — send som document-blok
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
            else:
                tekst = fil.get("tekst") or "(tom)"
                content.append({"type": "text", "text": header + tekst})

    content.append({"type": "text", "text": slutnings_tekst})
    return content


def spoerg_ai_med_sag(spoergsmaal, sager, sag, sagsakter=None, returner_relevante=False):
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
            # Filtrér sagens egne filer ud
            relevante = [
                r for r in (afgoerelser + vilkaar)
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
            f"dokumentation. Brug vidensbanken til præcedens."
        )

        user_content = _byg_sag_content(sag, indled, slutning)

        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            temperature=0,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        svar_tekst = response.content[0].text
        if returner_relevante:
            return svar_tekst, relevante
        return svar_tekst

    except Exception as e:
        fejl = f"Fejl i forbindelsen til Juriitech: {str(e)}"
        if returner_relevante:
            return fejl, []
        return fejl


def generer_svarbrev_til_sag(sag, sagsakter=None, ekstra_instrukser=None):
    """
    Genererer et komplet udkast til svarbrev baseret på HELE sagspakken
    (høring + klageskema + alle bilag), ikke kun én klage-fil.
    """
    try:
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
            relevante = [
                r for r in (afgoerelser + vilkaar)
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

        slutning = sagsakter_blok + ekstra + SVARBREV_OPGAVE

        user_content = _byg_sag_content(sag, indled, slutning)

        response = client.messages.create(
            model=MODEL,
            max_tokens=6000,
            temperature=0.2,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        return response.content[0].text

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
        return f"Fejl i forbindelsen til Juriitech: {str(e)}"
