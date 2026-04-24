import re
import zipfile
from pypdf import PdfReader
from docx import Document
from io import BytesIO


# Minimum antal tegn vi forventer af et "tekst-baseret" dokument. Hvis
# tekstudtrækket falder under dette, antager vi, at PDF'en er scannet og
# kræver OCR — den sendes så videre som rå bytes til Claude, som selv
# læser den via vision.
SCANNET_TAERSKEL = 100


def laes_pdf_tekst(pdf_fil):
    tekst = ""
    reader = PdfReader(pdf_fil)
    for side in reader.pages:
        udtraek = side.extract_text() or ""
        tekst += udtraek + "\n"
    return tekst


def laes_word_tekst(word_fil):
    doc = Document(word_fil)
    tekst = ""
    for afsnit in doc.paragraphs:
        tekst += afsnit.text + "\n"
    return tekst


def extracer_tekst(fil):
    """
    Bruges til at hente tekst ud af en fil, der skal gemmes i databasen.
    Bevaret uændret så den eksisterende upload-flow stadig virker.
    """
    if fil.name.endswith(".pdf"):
        return laes_pdf_tekst(fil)
    elif fil.name.endswith(".docx"):
        return laes_word_tekst(fil)
    else:
        return "Filformat ikke understøttet."


def laes_klage(fil):
    """
    Bruges til at læse en INDKOMMEN klage, der skal analyseres i chatten.

    Returnerer en dict med én af to former:
      {"type": "tekst",     "filnavn": str, "tekst": str}      # DOCX eller tekst-PDF
      {"type": "pdf_bytes", "filnavn": str, "bytes": bytes}    # scannet PDF

    For scannede PDF'er sender vi de rå bytes direkte videre til Claude,
    som selv kan læse billedsider.
    """
    navn = fil.name

    if navn.lower().endswith(".docx"):
        tekst = laes_word_tekst(fil)
        return {"type": "tekst", "filnavn": navn, "tekst": tekst}

    if navn.lower().endswith(".pdf"):
        # Hent rå bytes først (så vi kan sende dem til Claude, hvis PDF'en er scannet)
        pdf_bytes = fil.getvalue()

        # Prøv at udtrække tekst
        try:
            tekst = laes_pdf_tekst(BytesIO(pdf_bytes))
        except Exception:
            tekst = ""

        if len(tekst.strip()) >= SCANNET_TAERSKEL:
            return {"type": "tekst", "filnavn": navn, "tekst": tekst}

        # Ingen eller næsten ingen tekst — antag scannet PDF
        return {"type": "pdf_bytes", "filnavn": navn, "bytes": pdf_bytes}

    return {"type": "tekst", "filnavn": navn, "tekst": "Filformat ikke understøttet."}


# ---------- BATCH-LÆSNING AF HEL SAG (FLERE FILER / ZIP) ----------

# Heuristik for at gætte filens rolle i en Ankenævn-sag baseret på filnavnet.
# Disse mønstre matcher det typiske navngivningsmønster Nævnet bruger.
ROLLE_MOENSTRE = [
    (re.compile(r"h.?ring", re.I), "høring"),          # "Høring R"
    (re.compile(r"klageskema|bilag\s*0?1", re.I), "klageskema"),
    (re.compile(r"billet|rejsebevis", re.I), "bilag_billet"),
    (re.compile(r"hotel", re.I), "bilag_hotel"),
    (re.compile(r"mail|korrespondance|brev", re.I), "bilag_mail"),
    (re.compile(r"kommentar", re.I), "bilag_kommentar"),
    (re.compile(r"bilag", re.I), "bilag"),
    (re.compile(r"vejledning|retningslinjer", re.I), "vejledning"),
]


def _gaet_rolle(filnavn):
    """Gætter filens rolle i sagen ud fra filnavnet."""
    for moenster, rolle in ROLLE_MOENSTRE:
        if moenster.search(filnavn):
            return rolle
    return "ukendt"


def _laes_fra_bytes(filnavn, data):
    """
    Læser én fil (bytes + filnavn) og returnerer en sag-fil dict:
      {"filnavn": str,
       "type": "tekst" | "pdf_bytes" | "image_bytes" | "mp4_skipped",
       "tekst": str eller "",
       "bytes": bytes eller None,
       "media_type": str eller None,      # kun for image_bytes
       "rolle": str}

    Understøttede formater:
      - DOCX  → tekstudtræk
      - PDF   → tekstudtræk (eller vision via bytes hvis scannet)
      - PNG/JPG/JPEG → sendes som billede til Claude vision
      - MP4   → springes over med besked; PAX læser ikke video endnu
      - DOC   → bevares som filreference (lokal parser mangler)
      - øvrige → markeres som ikke-understøttet
    """
    navn_lower = filnavn.lower()
    rolle = _gaet_rolle(filnavn)

    if navn_lower.endswith(".docx"):
        try:
            tekst = laes_word_tekst(BytesIO(data))
            if not tekst.strip():
                # Tom DOCX — behandles som ulæselig
                return {
                    "filnavn": filnavn,
                    "type": "fil_ikke_laest",
                    "tekst": "",
                    "bytes": None,
                    "media_type": None,
                    "rolle": rolle,
                    "aarsag": "Word-dokumentet indeholder ingen tekst",
                }
            return {
                "filnavn": filnavn,
                "type": "tekst",
                "tekst": tekst,
                "bytes": None,
                "media_type": None,
                "rolle": rolle,
            }
        except Exception as e:
            return {
                "filnavn": filnavn,
                "type": "fil_ikke_laest",
                "tekst": "",
                "bytes": None,
                "media_type": None,
                "rolle": rolle,
                "aarsag": f"DOCX-filen kunne ikke læses ({e})",
            }

    if navn_lower.endswith(".pdf"):
        try:
            tekst = laes_pdf_tekst(BytesIO(data))
        except Exception as e:
            # PDF helt korrupt — kan hverken læses som tekst eller vision
            return {
                "filnavn": filnavn,
                "type": "fil_ikke_laest",
                "tekst": "",
                "bytes": data,
                "media_type": None,
                "rolle": rolle,
                "aarsag": f"PDF-filen kunne ikke åbnes ({e})",
            }
        if len(tekst.strip()) >= SCANNET_TAERSKEL:
            return {
                "filnavn": filnavn,
                "type": "tekst",
                "tekst": tekst,
                "bytes": data,  # bevar bytes også, så anonymisering kan bruge dem
                "media_type": None,
                "rolle": rolle,
            }
        return {
            "filnavn": filnavn,
            "type": "pdf_bytes",
            "tekst": "",
            "bytes": data,
            "media_type": None,
            "rolle": rolle,
        }

    # ---------- BILLEDER (PNG / JPG / JPEG) ----------
    # Sendes direkte til Claude vision som billede-blokke i _byg_sag_content.
    # media_type matcher Anthropic's forventede værdier.
    if navn_lower.endswith(".png"):
        return {
            "filnavn": filnavn,
            "type": "image_bytes",
            "tekst": "",
            "bytes": data,
            "media_type": "image/png",
            "rolle": rolle,
        }
    if navn_lower.endswith(".jpg") or navn_lower.endswith(".jpeg"):
        return {
            "filnavn": filnavn,
            "type": "image_bytes",
            "tekst": "",
            "bytes": data,
            "media_type": "image/jpeg",
            "rolle": rolle,
        }

    # ---------- VIDEO (MP4) ----------
    # juriitech PAX læser ikke video endnu — vi springer over og markerer
    # filen så UI'et kan vise en advarsel om at brugeren skal gennemse den
    # manuelt. Førstevurderingen fortsætter med de øvrige filer.
    if navn_lower.endswith(".mp4"):
        return {
            "filnavn": filnavn,
            "type": "mp4_skipped",
            "tekst": (
                f"[MP4-fil ikke analyseret af juriitech PAX. "
                f"Skal gennemses manuelt af brugeren. Filnavn: {filnavn}]"
            ),
            "bytes": None,  # behold ikke video-bytes — de er store og ikke brugbare
            "media_type": None,
            "rolle": rolle,
        }

    if navn_lower.endswith(".doc"):
        # Gammelt Word-format — kan ikke parses lokalt, markeres som ikke-læst
        return {
            "filnavn": filnavn,
            "type": "fil_ikke_laest",
            "tekst": "",
            "bytes": data,
            "media_type": None,
            "rolle": rolle,
            "aarsag": (
                "Gammelt .doc-format (Word 97-2003). Konvertér til .docx "
                "eller PDF for at juriitech PAX kan læse indholdet."
            ),
        }

    # Ukendt format — gem metadata så brugeren kan se det, men kan ikke bruges
    endelse = navn_lower.rsplit(".", 1)[-1] if "." in navn_lower else "ukendt"
    return {
        "filnavn": filnavn,
        "type": "fil_ikke_laest",
        "tekst": "",
        "bytes": data,
        "media_type": None,
        "rolle": rolle,
        "aarsag": (
            f"Filformatet .{endelse} understøttes ikke af juriitech PAX. "
            "Understøttede formater er PDF, DOCX, PNG, JPG, JPEG, MP4 og ZIP."
        ),
    }


def _rolle_sorteringsnoegle(fil):
    """Rækkefølge: høring → klageskema → andre bilag → vejledninger."""
    rækkefølge = {
        "høring": 0,
        "klageskema": 1,
        "bilag_billet": 2,
        "bilag_hotel": 3,
        "bilag_mail": 4,
        "bilag_kommentar": 5,
        "bilag": 6,
        "ukendt": 7,
        "vejledning": 99,
    }
    return (rækkefølge.get(fil["rolle"], 50), fil["filnavn"])


def udpak_zip_til_filer(zip_bytes):
    """
    Pakker en ZIP op i memory og returnerer en liste af (filnavn, bytes).
    Mapper og __MACOSX-skrald springes over.
    """
    resultat = []
    try:
        with zipfile.ZipFile(BytesIO(zip_bytes)) as z:
            for info in z.infolist():
                if info.is_dir():
                    continue
                # Spring over macOS metadata og skjulte filer
                if info.filename.startswith("__MACOSX/") or info.filename.startswith("."):
                    continue
                # Kun filer i rodniveau eller første undermappe (ikke dybt indlejret)
                kort_navn = info.filename.rsplit("/", 1)[-1]
                if kort_navn.startswith("."):
                    continue
                try:
                    data = z.read(info.filename)
                    resultat.append((kort_navn, data))
                except Exception as e:
                    print(f"DEBUG: Kunne ikke læse {info.filename} fra ZIP: {e}")
    except Exception as e:
        print(f"DEBUG: ZIP-udpakning fejlede: {e}")
    return resultat


def laes_sag_fra_filer(streamlit_filer):
    """
    Læser en liste af Streamlit-UploadedFile-objekter og returnerer en
    sag-dict:
      {"filer": [sag-fil-dicts...]}

    Hvis én af filerne er en ZIP, pakkes den ud og indholdet indgår på
    linje med de øvrige filer.
    """
    alle_fil_bytes = []  # liste af (filnavn, bytes)

    for fil in streamlit_filer:
        navn = fil.name
        data = fil.getvalue()

        if navn.lower().endswith(".zip"):
            udpakket = udpak_zip_til_filer(data)
            for u_navn, u_data in udpakket:
                alle_fil_bytes.append((u_navn, u_data))
        else:
            alle_fil_bytes.append((navn, data))

    # Læs hver fil og gæt dens rolle
    sag_filer = [_laes_fra_bytes(navn, data) for navn, data in alle_fil_bytes]

    # Sortér efter rolle så høring kommer først, klageskema næst, osv.
    sag_filer.sort(key=_rolle_sorteringsnoegle)

    return {"filer": sag_filer}
