"""
generer_test_sager.py

Genererer 5 fiktive Pakkerejse-Ankenævn-sager til test-brug, så Mikkel
ikke skal bruge intern virksomhedsdata til at teste systemet.

Hver sag har et klageskema + 2-3 bilag. Alle navne, adresser, sagsnumre,
beløb og rejsedetaljer er KOMPLET OPDIGTET — enhver lighed med virkelige
personer eller sager er tilfældig.

KØRSEL:
    python3 scripts/generer_test_sager.py

OUTPUT:
    pax-next/public/test-sager/sag-XX-<selskab>/
        klageskema.pdf
        bilag-01-*.pdf
        bilag-02-*.pdf
        ...

Idempotent: genskaber filer fra bunden hver gang.
"""

import os
import sys
import shutil
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER


ROD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(ROD, "pax-next", "public", "test-sager")


def _styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle(
        name="Titel",
        parent=s["Heading1"],
        fontSize=16,
        alignment=TA_CENTER,
        spaceAfter=12,
    ))
    s.add(ParagraphStyle(
        name="Subtitel",
        parent=s["Heading2"],
        fontSize=11,
        alignment=TA_CENTER,
        textColor=colors.grey,
        spaceAfter=18,
    ))
    s.add(ParagraphStyle(
        name="SektionsTitel",
        parent=s["Heading3"],
        fontSize=12,
        spaceBefore=12,
        spaceAfter=6,
        textColor=colors.HexColor("#1a3a52"),
    ))
    s.add(ParagraphStyle(
        name="Brod",
        parent=s["BodyText"],
        fontSize=10,
        leading=14,
        alignment=TA_LEFT,
        spaceAfter=6,
    ))
    s.add(ParagraphStyle(
        name="Lille",
        parent=s["BodyText"],
        fontSize=8,
        leading=11,
        textColor=colors.grey,
    ))
    return s


def _info_tabel(rows, styles):
    tbl = Table(rows, colWidths=[5 * cm, 11 * cm])
    tbl.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.lightgrey),
    ]))
    return tbl


def _afsender_header(styles, dato):
    """Pakkerejse-Ankenævn header øverst på klageskema."""
    return [
        Paragraph("PAKKEREJSE-ANKENÆVNET", styles["Titel"]),
        Paragraph(
            "Røjelskær 11, 3. sal · 2840 Holte · Tlf. 45 46 11 00 · "
            "info@pakkerejseankenaevnet.dk",
            styles["Lille"],
        ),
        Spacer(1, 0.4 * cm),
        Paragraph(f"Klageskema modtaget: {dato}", styles["Lille"]),
        Spacer(1, 0.6 * cm),
    ]


def _byg_klageskema(path, sag):
    """
    sag: dict med felter:
      sagsnr, modtaget_dato, indklagede, klager_navn, klager_adresse,
      klager_email, klager_tlf, destination, rejseperiode, antal_rejsende,
      rejse_pris, klagepunkter (str), paastand (str), tidligere_korrespondance (str)
    """
    doc = SimpleDocTemplate(
        path, pagesize=A4,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm,
        topMargin=1.8 * cm, bottomMargin=1.8 * cm,
        title=f"Klageskema sag {sag['sagsnr']}",
    )
    s = _styles()
    story = []

    story.extend(_afsender_header(s, sag["modtaget_dato"]))

    story.append(Paragraph(f"Klagesag j.nr. {sag['sagsnr']}", s["Subtitel"]))

    story.append(Paragraph("Parterne", s["SektionsTitel"]))
    story.append(_info_tabel([
        ["Klager:", sag["klager_navn"]],
        ["Adresse:", sag["klager_adresse"]],
        ["E-mail:", sag["klager_email"]],
        ["Telefon:", sag["klager_tlf"]],
        ["Indklagede:", sag["indklagede"]],
    ], s))

    story.append(Paragraph("Rejsen", s["SektionsTitel"]))
    story.append(_info_tabel([
        ["Destination:", sag["destination"]],
        ["Rejseperiode:", sag["rejseperiode"]],
        ["Antal rejsende:", sag["antal_rejsende"]],
        ["Rejsens samlede pris:", sag["rejse_pris"]],
        ["Bookingreference:", sag["bookingref"]],
    ], s))

    story.append(Paragraph("Klagepunkter", s["SektionsTitel"]))
    for afsnit in sag["klagepunkter"].strip().split("\n\n"):
        story.append(Paragraph(afsnit.strip(), s["Brod"]))

    story.append(Paragraph("Klagers påstand", s["SektionsTitel"]))
    story.append(Paragraph(sag["paastand"], s["Brod"]))

    story.append(Paragraph("Tidligere korrespondance", s["SektionsTitel"]))
    story.append(Paragraph(sag["tidligere_korrespondance"], s["Brod"]))

    story.append(Spacer(1, 1.0 * cm))
    story.append(Paragraph(
        "Indklagede anmodes om at fremsende bemærkninger til klagen "
        "senest 4 uger fra dato. Manglende svar kan medføre, at klagen "
        "afgøres på det foreliggende grundlag, jf. nævnets vedtægter § 6.",
        s["Brod"],
    ))
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph(
        "Med venlig hilsen<br/>"
        "Pakkerejse-Ankenævnet<br/>"
        "Sekretariatet",
        s["Brod"],
    ))

    story.append(Spacer(1, 1.5 * cm))
    story.append(Paragraph(
        "[FIKTIV TESTSAG — alle oplysninger er opdigtede og må kun "
        "bruges til test af juriitech PAX]",
        s["Lille"],
    ))

    doc.build(story)


def _byg_bilag(path, titel, undertitel, indhold_afsnit, bilag_nr):
    doc = SimpleDocTemplate(
        path, pagesize=A4,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm,
        topMargin=1.8 * cm, bottomMargin=1.8 * cm,
        title=f"Bilag {bilag_nr}: {titel}",
    )
    s = _styles()
    story = [
        Paragraph(f"Bilag {bilag_nr}", s["Lille"]),
        Paragraph(titel, s["Titel"]),
        Paragraph(undertitel, s["Subtitel"]),
    ]
    for afsnit in indhold_afsnit:
        if isinstance(afsnit, list):
            # tabel-data: liste af [label, værdi]
            story.append(_info_tabel(afsnit, s))
            story.append(Spacer(1, 0.3 * cm))
        else:
            story.append(Paragraph(afsnit, s["Brod"]))
    story.append(Spacer(1, 1.5 * cm))
    story.append(Paragraph(
        "[FIKTIV TESTSAG — alle oplysninger er opdigtede]",
        s["Lille"],
    ))
    doc.build(story)


def _byg_staevning(path, sag):
    """
    Bygger nævnets formelle cover-letter / underretning til indklagede.
    Sendes typisk sammen med klageskema + bilag som første kontakt.
    """
    doc = SimpleDocTemplate(
        path, pagesize=A4,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm,
        topMargin=1.8 * cm, bottomMargin=1.8 * cm,
        title=f"Stævning sag {sag['sagsnr']}",
    )
    s = _styles()
    story = [
        Paragraph("PAKKEREJSE-ANKENÆVNET", s["Titel"]),
        Paragraph(
            "Røjelskær 11, 3. sal · 2840 Holte · Tlf. 45 46 11 00 · "
            "info@pakkerejseankenaevnet.dk · CVR 19438319",
            s["Lille"],
        ),
        Spacer(1, 1.2 * cm),
    ]

    story.append(Paragraph(f"<b>{sag['indklagede']}</b>", s["Brod"]))
    story.append(Paragraph(sag["indklagede_adresse"], s["Brod"]))
    story.append(Spacer(1, 0.8 * cm))

    story.append(_info_tabel([
        ["J.nr.:", sag["sagsnr"]],
        ["Dato:", sag["modtaget_dato"]],
        ["Sagsbehandler:", sag["sagsbehandler_initialer"]],
        ["Vedrører:", "Pakkerejselov § 32"],
    ], s))

    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph("UNDERRETNING OM INDGIVET KLAGE", s["SektionsTitel"]))

    body = (
        f"Pakkerejse-Ankenævnet har den {sag['modtaget_dato'].lower()} modtaget "
        f"vedhæftede klage fra <b>{sag['klager_navn']}</b> over en pakkerejse "
        f"til {sag['destination']} i perioden {sag['rejseperiode']}, formidlet "
        f"af {sag['indklagede'].split(',')[0]}.\n\n"
        f"<b>Kort om klagen</b>\n"
        f"{sag['staevning_resume']}\n\n"
        f"<b>Klagers påstand</b>\n"
        f"{sag['staevning_paastand_kort']}\n\n"
        "Klagen med tilhørende bilag er vedlagt nærværende skrivelse.\n\n"
        "<b>Frist for bemærkninger</b>\n"
        "I henhold til nævnets vedtægter § 5 anmodes indklagede om inden "
        "<b>4 uger fra dato</b> at fremsende skriftlige bemærkninger til "
        "klagen. Bemærkningerne bedes adresseret til sekretariatet med "
        "tydelig angivelse af det ovenfor anførte journalnummer.\n\n"
        "Hvis indklagede ikke svarer inden fristens udløb, kan klagen "
        "afgøres på det foreliggende grundlag, jf. nævnets vedtægter § 6.\n\n"
        "<b>Klagegebyr og sagsomkostninger</b>\n"
        "Pakkerejse-Ankenævnet bemærker, at der i medfør af "
        "pakkerejseloven § 35 og nævnets vedtægter § 14 kan idømmes "
        "klageomkostninger samt sagsomkostninger til Pakkerejse-Ankenævnet, "
        "såfremt klagen tages helt eller delvist til følge.\n\n"
        "<b>Forligsmæssig løsning</b>\n"
        "Inden sagen behandles i nævnet opfordres parterne til at søge "
        "en forligsmæssig løsning. Eventuelt forlig bedes meddelt "
        "sekretariatet hurtigst muligt, så sagen kan afsluttes.\n\n"
        "Eventuelle spørgsmål kan rettes til sekretariatet på "
        "info@pakkerejseankenaevnet.dk eller telefon 45 46 11 00 "
        "(hverdage 10:00–14:00)."
    )

    for afsnit in body.split("\n\n"):
        story.append(Paragraph(afsnit.strip(), s["Brod"]))

    story.append(Spacer(1, 0.8 * cm))
    story.append(Paragraph(
        "Med venlig hilsen<br/>"
        "Pakkerejse-Ankenævnet<br/>"
        f"v/ {sag['sagsbehandler_navn']}, juridisk sagsbehandler<br/>"
        "Sekretariatet",
        s["Brod"],
    ))

    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph(
        "<b>Vedlagt:</b> Klageskema · Bilag 1–3 fra klager",
        s["Brod"],
    ))

    story.append(Spacer(1, 1.2 * cm))
    story.append(Paragraph(
        "[FIKTIV TESTSAG — alle oplysninger er opdigtede og må kun "
        "bruges til test af juriitech PAX]",
        s["Lille"],
    ))

    doc.build(story)


def _byg_selskabsdokument(path, selskab_navn, titel, undertitel,
                          indhold_afsnit, fortroligt=True):
    """
    Bygger et internt selskabsdokument (email, kontraktudrag, system-log
    osv.) der ligner det rejseselskabets egne sagsmapper indeholder.
    Adskilles visuelt fra klagers bilag via en tydelig header-stripe.
    """
    doc = SimpleDocTemplate(
        path, pagesize=A4,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm,
        topMargin=1.8 * cm, bottomMargin=1.8 * cm,
        title=f"{selskab_navn} — {titel}",
    )
    s = _styles()

    header_label = (
        "INTERN · FORTROLIGT" if fortroligt else "INTERN"
    )

    story = []
    # Topmarkering der adskiller fra klage-dokumenter
    klassifikation_tabel = Table(
        [[f"{header_label} · {selskab_navn}"]],
        colWidths=[16 * cm],
    )
    klassifikation_tabel.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fef3c7")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#92400e")),
        ("FONT", (0, 0), (-1, -1), "Helvetica-Bold", 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#92400e")),
    ]))
    story.append(klassifikation_tabel)
    story.append(Spacer(1, 0.6 * cm))

    story.append(Paragraph(titel, s["Titel"]))
    story.append(Paragraph(undertitel, s["Subtitel"]))

    for afsnit in indhold_afsnit:
        if isinstance(afsnit, list):
            story.append(_info_tabel(afsnit, s))
            story.append(Spacer(1, 0.3 * cm))
        else:
            story.append(Paragraph(afsnit, s["Brod"]))

    story.append(Spacer(1, 1.2 * cm))
    story.append(Paragraph(
        "[FIKTIV TESTSAG — alle oplysninger er opdigtede og må kun "
        "bruges til test af juriitech PAX]",
        s["Lille"],
    ))

    doc.build(story)


# ─────────────────────────────────────────────────────────────────
# SAG 1 — QuickTour A/S — Forsinkelse af hjemrejse
# ─────────────────────────────────────────────────────────────────

SAG_1 = {
    "mappe": "sag-01-quicktour",
    "sagsnr": "25-2401",
    "modtaget_dato": "15. oktober 2025",
    "indklagede": "QuickTour A/S, CVR 12345678",
    "klager_navn": "Mette Lindgaard og Kasper Lindgaard",
    "klager_adresse": "Skovvej 14, 8000 Aarhus C",
    "klager_email": "mette.lindgaard@eksempelmail.dk",
    "klager_tlf": "22 33 44 55",
    "destination": "Mallorca, Spanien — Hotel Sol y Mar, Palma",
    "rejseperiode": "12. august 2025 – 19. august 2025 (7 nætter)",
    "antal_rejsende": "2 voksne",
    "rejse_pris": "14.800 kr. samlet",
    "bookingref": "QT-887421",
    "klagepunkter": (
        "Vi var bookede på QuickTours hjemrejsefly QT4471 fra Palma til "
        "Billund søndag den 19. august 2025 med planlagt afgang kl. 14:30. "
        "Flyet blev først aflyst kl. 13:45 — under en halv time før "
        "boarding skulle begynde — og vi blev henvist til en ny afgang "
        "samme aften kl. 23:00. Den nye afgang blev efterfølgende også "
        "forsinket, og vi landede først i Billund kl. 02:40 mandag morgen, "
        "ca. 12 timer efter den oprindeligt planlagte ankomst.\n\n"
        "Under ventetiden i Palma Lufthavn fik vi INGEN information fra "
        "QuickTours repræsentanter. Skranken var ubemandet hele "
        "eftermiddagen, og vi blev nødt til at købe måltider og drikke "
        "for egen regning. Vores forsøg på at ringe til QuickTours "
        "vagttelefon resulterede i 40 minutters venten uden svar.\n\n"
        "Forsinkelsen medførte, at min mand måtte melde sig syg fra "
        "arbejde mandag, og vores datter kunne ikke afhentes fra "
        "børnehaven til normal tid."
    ),
    "paastand": (
        "Klagerne kræver kompensation efter EU-forordning 261/2004 om "
        "lange forsinkelser (400 EUR pr. person = ca. 5.960 kr.) samt "
        "refusion af dokumenterede udgifter til måltider og drikke under "
        "ventetiden (i alt 2.540 kr., jf. bilag 2). Samlet krav: 8.500 kr."
    ),
    "tidligere_korrespondance": (
        "Klagerne har henvendt sig skriftligt til QuickTour A/S den "
        "22. august 2025 og igen den 8. september 2025. QuickTour har "
        "svaret den 19. september 2025, hvor selskabet anerkender "
        "forsinkelsen, men afviser ansvar med henvisning til "
        "\"ekstraordinære omstændigheder\" (manglende cockpit-mandskab). "
        "QuickTour har tilbudt et værdibevis på 1.000 kr., hvilket "
        "klagerne har afvist."
    ),
}

SAG_1_BILAG = [
    {
        "filnavn": "bilag-01-boardingpas-og-rejseplan.pdf",
        "titel": "Boardingpas og oprindelig rejseplan",
        "undertitel": "QuickTour rejseref. QT-887421",
        "bilag_nr": "1",
        "indhold": [
            "Original rejseplan modtaget fra QuickTour A/S 5. august 2025:",
            [
                ["Udrejse:", "QT4470 · BLL → PMI · 12.08.2025 kl. 06:15 → 09:35"],
                ["Hjemrejse:", "QT4471 · PMI → BLL · 19.08.2025 kl. 14:30 → 18:00"],
                ["Sæder:", "23A og 23B"],
                ["Bagage:", "2 × 23 kg checked, 2 × 8 kg håndbagage"],
            ],
            "Faktisk ankomst Billund: 20. august 2025 kl. 02:40 — "
            "forsinkelse 8 timer 40 minutter i forhold til den oprindelige "
            "afgang og ca. 12 timer i forhold til planlagt ankomst.",
        ],
    },
    {
        "filnavn": "bilag-02-kvitteringer.pdf",
        "titel": "Kvitteringer for udgifter under ventetiden",
        "undertitel": "Palma Lufthavn, 19. august 2025",
        "bilag_nr": "2",
        "indhold": [
            "Udgifter afholdt af klagerne under den uvarslede ventetid "
            "på 12 timer i Palma Lufthavn:",
            [
                ["Bar Café Sol (15:20):", "Sandwich og vand · 28,50 EUR"],
                ["Restaurant Mediterraneo (17:45):", "Frokost for 2 · 67,80 EUR"],
                ["Bar Café Sol (20:10):", "Drikkevarer · 18,20 EUR"],
                ["McDonald's T2 (22:30):", "Aftensmad for 2 · 24,90 EUR"],
                ["Lufthavnskiosk:", "Vand og snacks · 14,60 EUR"],
                ["Powerbank (22:55):", "Til opladning af telefon · 24,00 EUR"],
                ["TOTAL:", "178,00 EUR = 1.329 kr. (kurs 7,46)"],
            ],
            "Hertil kommer taxi fra Billund til Aarhus 20. august kl. 03:30, "
            "i alt 1.210 kr. (jf. vedhæftet taxikvittering nr. 4471-A).",
            "Samlede dokumenterede udgifter: 2.540 kr.",
        ],
    },
    {
        "filnavn": "bilag-03-korrespondance.pdf",
        "titel": "E-mail-korrespondance med QuickTour A/S",
        "undertitel": "August – september 2025",
        "bilag_nr": "3",
        "indhold": [
            "<b>E-mail fra klager til QuickTour, 22. august 2025 kl. 19:42:</b>",
            "\"Vi var rejsende på QT4471 søndag den 19. august, der blev "
            "aflyst med under en halv time varsel. Vi modtog ingen "
            "information, ingen mad, ingen alternativ booking til samme "
            "dag — først om aftenen kl. 23:00. Vi forventer kompensation "
            "efter EU 261/2004 samt refusion af dokumenterede udgifter. "
            "Bilag vedhæftet.\"",
            "<b>Svar fra QuickTour A/S, 19. september 2025:</b>",
            "\"Tak for din henvendelse vedr. QT4471 den 19. august. Vi "
            "beklager den oplevede forsinkelse. Aflysningen skyldes "
            "ekstraordinære omstændigheder (manglende cockpit-besætning "
            "som følge af pludselig sygdom), hvilket fritager QuickTour "
            "for kompensation efter EU 261/2004 artikel 5(3). Som en "
            "kulancegestus tilbyder vi et værdibevis på 1.000 kr. til "
            "fremtidige rejser med QuickTour. Med venlig hilsen, "
            "Kundeservice, QuickTour A/S.\"",
            "<b>Svar fra klager, 23. september 2025:</b>",
            "\"Tilbuddet afvises. Pludselig sygdom blandt egne ansatte "
            "kan ikke kvalificere som ekstraordinære omstændigheder, "
            "jf. EU-Domstolens praksis. Sagen indbringes for "
            "Pakkerejse-Ankenævnet.\"",
        ],
    },
]


# ─────────────────────────────────────────────────────────────────
# SAG 2 — FirstWorldTravel ApS — Manglende standard på luksushotel
# ─────────────────────────────────────────────────────────────────

SAG_2 = {
    "mappe": "sag-02-firstworldtravel",
    "sagsnr": "26-0142",
    "modtaget_dato": "8. februar 2026",
    "indklagede": "FirstWorldTravel ApS, CVR 23456789",
    "klager_navn": "Annika Berggren",
    "klager_adresse": "Strandgade 7, 1401 København K",
    "klager_email": "a.berggren@eksempelmail.dk",
    "klager_tlf": "31 22 11 89",
    "destination": "Maldiverne — Sunset Paradise Resort, Baa Atoll",
    "rejseperiode": "3. januar 2026 – 13. januar 2026 (10 nætter)",
    "antal_rejsende": "1 voksen (solo)",
    "rejse_pris": "78.500 kr.",
    "bookingref": "FWT-MLE-9921",
    "klagepunkter": (
        "Jeg bookede en 10-nætters luksusrejse til Sunset Paradise Resort "
        "via FirstWorldTravels Premium Maldives-katalog. Pakken inkluderede "
        "ifølge bookingmaterialet (bilag 1):\n\n"
        "• \"Beach Villa med direkte havudsigt og privat terrasse\"\n"
        "• \"Adgang til alle hotellets restauranter, herunder den prisbelønnede "
        "à la carte-restaurant Coral\"\n"
        "• \"Adgang til hotellets infinity-pool med solnedgangsudsigt\"\n"
        "• \"Daglig morgenmad og 5-retters middag inkluderet (halvpension+)\"\n\n"
        "Ved ankomsten 3. januar oplevede jeg følgende:\n\n"
        "1. Jeg blev indkvarteret i en \"Garden Villa\" der vendte ud mod "
        "personaleparkeringen og et generatorhus. Ingen havudsigt. På "
        "min indvending svarede receptionen, at Beach Villaerne var "
        "\"overbookede pga. et bryllup\".\n\n"
        "2. Infinity-poolen var lukket hele opholdet pga. renovering "
        "(jf. opslag dateret 28. december 2025 — altså før min ankomst). "
        "Jeg blev ikke informeret før afrejse.\n\n"
        "3. Coral-restauranten var lukket alle 10 dage \"pga. mangel på "
        "personale\". Det blev oplyst ved ankomst.\n\n"
        "4. Den lovede 5-retters middag blev erstattet af buffet i "
        "hovedrestauranten, hvor menuen var næsten identisk hver aften."
    ),
    "paastand": (
        "Klager kræver forholdsmæssigt afslag i rejsens pris med 35.000 kr., "
        "svarende til ca. 45% af pakkens pris. Subsidiært kræves "
        "kompensation for ikke-leverede ydelser efter pakkerejselovens § 24."
    ),
    "tidligere_korrespondance": (
        "Klager har skriftligt henvendt sig til FirstWorldTravel ApS "
        "ved hjemkomst (14. januar 2026) og igen den 27. januar 2026. "
        "FirstWorldTravel har den 2. februar 2026 tilbudt en "
        "kompensation på 8.000 kr. samt et værdibevis på 5.000 kr. til "
        "fremtidig rejse. Klager har afvist tilbuddet."
    ),
}

SAG_2_BILAG = [
    {
        "filnavn": "bilag-01-bookingbekraeftelse.pdf",
        "titel": "Bookingbekræftelse og hotelbeskrivelse",
        "undertitel": "FirstWorldTravel ApS · Premium Maldives 2026",
        "bilag_nr": "1",
        "indhold": [
            "<b>Bookingbekræftelse FWT-MLE-9921 · udstedt 18. november 2025</b>",
            [
                ["Rejsende:", "Annika Berggren (1 voksen)"],
                ["Destination:", "Sunset Paradise Resort, Baa Atoll, Maldiverne"],
                ["Periode:", "03.01.2026 – 13.01.2026"],
                ["Værelseskategori:", "Beach Villa — havudsigt"],
                ["Forplejning:", "Halvpension+ (morgenmad + 5-retters middag)"],
                ["Adgang til:", "Alle restauranter og faciliteter"],
                ["Pris i alt:", "78.500 kr. inkl. flytransport, transfer, måltider"],
            ],
            "<b>Uddrag fra kataloget \"Premium Maldives 2026\", side 47:</b>",
            "\"Sunset Paradise Resort er et af FirstWorldTravels flagskibe i "
            "Det Indiske Ocean. Vores Beach Villaer giver dig direkte adgang "
            "til den hvide sandstrand og fuld havudsigt fra din private "
            "terrasse. Resorten byder på tre restauranter, herunder den "
            "prisbelønnede à la carte-restaurant Coral, samt en spektakulær "
            "infinity-pool med solnedgangsudsigt — et garanteret højdepunkt "
            "for enhver gæst.\"",
            "<b>Bemærk:</b> Hotelbeskrivelsen indeholdt ingen oplysninger om "
            "renovering, lukninger eller andre forhold der kunne påvirke "
            "opholdet i den bookede periode.",
        ],
    },
    {
        "filnavn": "bilag-02-fotos-og-dagbog.pdf",
        "titel": "Foto-dokumentation og daglig dagbog",
        "undertitel": "Maldiverne · 3.–13. januar 2026",
        "bilag_nr": "2",
        "indhold": [
            "<b>Foto-dokumentation (vedhæftet separat):</b>",
            "• Foto 1: Garden Villa nr. 117, udsigt mod parkeringsplads og generatorhus",
            "• Foto 2: Lukket infinity-pool med afspærring og opslag dateret 28.12.2025",
            "• Foto 3: Aflåst dør til Coral-restauranten med \"Closed\" skilt",
            "• Foto 4: Buffet-bordet i hovedrestauranten (samme retter dag 2, dag 5 og dag 9)",
            "<b>Dagbog — udvalgte dage:</b>",
            "<b>Dag 1 (03.01):</b> Ankomst kl. 16:30. Indkvartering i Garden "
            "Villa 117 i stedet for booket Beach Villa. Receptionen oplyste "
            "at \"alle Beach Villaer er overbookede pga. et bryllup hele "
            "ugen\". Tilbudt opgradering mod betaling 380 USD/nat — afvist.",
            "<b>Dag 2 (04.01):</b> Forsøgte at booke bord på Coral. Fik "
            "besked om at restauranten var \"midlertidigt lukket pga. "
            "personalemangel\" hele opholdet. Buffet i hovedrestaurant.",
            "<b>Dag 4 (06.01):</b> Gik til poolen kl. 09:00. Lukket med "
            "byggeplast og opslag: \"Pool under renovation since 28 Dec — "
            "reopening late January 2026\". Pool var altså lukket FØR min "
            "rejse blev bekræftet.",
            "<b>Dag 7 (09.01):</b> Klage indgivet til hotellets manager — "
            "lovet \"30% rabat på næste ophold\". Ikke acceptabelt.",
            "<b>Dag 10 (13.01):</b> Hjemrejse. Hovedrestaurantens menu "
            "havde været stort set identisk alle 10 aftener (3 hovedretter "
            "i rotation: kylling, fisk, vegetarisk pasta).",
        ],
    },
    {
        "filnavn": "bilag-03-korrespondance.pdf",
        "titel": "Korrespondance med FirstWorldTravel ApS",
        "undertitel": "Januar – februar 2026",
        "bilag_nr": "3",
        "indhold": [
            "<b>E-mail fra Annika Berggren til kundeservice@firstworldtravel.dk, "
            "14. januar 2026:</b>",
            "\"Jeg vendte hjem fra Maldiverne i går efter en rejse, der på "
            "INGEN måde levede op til det, jeg bookede og betalte 78.500 kr. "
            "for. Beach Villa blev til Garden Villa mod parkering. "
            "Coral-restauranten var lukket alle 10 dage. Pool var lukket "
            "alle 10 dage. Den lovede 5-retters middag blev til kedelig "
            "buffet med samme menu. Jeg kræver forholdsmæssigt afslag.\"",
            "<b>Svar fra Mette Krogh, kundeservicechef FWT, 2. februar 2026:</b>",
            "\"Kære Annika. Tak for din udførlige henvendelse. Vi beklager "
            "de oplevede gener. Pool-renoveringen blev iværksat med kort "
            "varsel, og vi har desværre ikke nået at opdatere alle "
            "rejsende. Som kompensation tilbyder vi 8.000 kr. samt et "
            "værdibevis på 5.000 kr. til en fremtidig rejse med "
            "FirstWorldTravel. Vi håber, du vil acceptere dette tilbud.\"",
            "<b>Svar fra Annika Berggren, 5. februar 2026:</b>",
            "\"8.000 kr. ud af 78.500 kr. — altså 10% — er ikke et "
            "rimeligt forholdsmæssigt afslag, når 3 ud af 4 kerneydelser "
            "ikke blev leveret som lovet. Jeg indbringer sagen for "
            "Pakkerejse-Ankenævnet.\"",
        ],
    },
]


# ─────────────────────────────────────────────────────────────────
# SAG 3 — SuperSafari A/S — Sygdom under rejse (sandsynligvis afvist)
# ─────────────────────────────────────────────────────────────────

SAG_3 = {
    "mappe": "sag-03-supersafari",
    "sagsnr": "25-3187",
    "modtaget_dato": "20. december 2025",
    "indklagede": "SuperSafari A/S, CVR 34567890",
    "klager_navn": "Henrik Nørgaard",
    "klager_adresse": "Birkholmsvej 22, 5000 Odense C",
    "klager_email": "henrik.noergaard@eksempelmail.dk",
    "klager_tlf": "40 55 66 77",
    "destination": "Kenya — Maasai Mara safari (Keekorok Lodge + Mara Serena)",
    "rejseperiode": "5. november 2025 – 19. november 2025 (14 nætter)",
    "antal_rejsende": "1 voksen",
    "rejse_pris": "42.000 kr.",
    "bookingref": "SS-KEN-7711",
    "klagepunkter": (
        "Jeg deltog i SuperSafaris 14-dages Maasai Mara-safari i november "
        "2025. På turens dag 9 begyndte jeg at få høj feber, kraftige "
        "kuldegysninger og hovedpine. Lokal lægeundersøgelse i Narok "
        "bekræftede malaria (P. falciparum). Jeg blev hospitaliseret i "
        "4 dage og missede de sidste 3 dage af programmet samt en "
        "udflugt til Lake Nakuru.\n\n"
        "Jeg gør gældende, at SuperSafari har et ansvar fordi:\n\n"
        "1. Programmet og brochuren nævner ikke malaria-risiko, kun at "
        "\"vaccinationer kan være relevante — kontakt din læge\". Dette "
        "er efter min vurdering utilstrækkelig information om en "
        "potentielt livstruende sygdom.\n\n"
        "2. Vores safariguide medbragte ikke insektmiddel til gæsterne. "
        "Da jeg spurgte, sagde han, at det \"plejer gæsterne selv at "
        "have med\".\n\n"
        "3. Lodgerne havde ikke myggenet over alle senge (Keekorok "
        "Lodge værelse 24 manglede komplet net).\n\n"
        "4. Min lægebehandling og 4 nætter på Narok County Hospital "
        "kostede mig 1.250 USD, som rejseforsikringen kun delvist har "
        "dækket (selvrisiko + udgifter ud over godkendt sats)."
    ),
    "paastand": (
        "Klager kræver 25.000 kr. som forholdsmæssigt afslag for de 5 "
        "dage, der gik tabt pga. sygdom, samt godtgørelse på 12.000 kr. "
        "for ikke-dækkede behandlingsudgifter. Samlet krav: 37.000 kr."
    ),
    "tidligere_korrespondance": (
        "Klager har henvendt sig til SuperSafari A/S den 26. november 2025. "
        "SuperSafari har afvist klagen den 8. december 2025 med "
        "henvisning til at malaria-risiko er almindeligt kendt for "
        "rejsemålet, og at klager forud for afrejse modtog skriftlig "
        "information med opfordring til lægekonsultation om "
        "malariaprofylakse. Klager har herefter indbragt sagen for "
        "Pakkerejse-Ankenævnet."
    ),
}

SAG_3_BILAG = [
    {
        "filnavn": "bilag-01-laegeerklaering.pdf",
        "titel": "Lægeerklæring og hospitalsudskrivning",
        "undertitel": "Narok County Referral Hospital, Kenya · 14. november 2025",
        "bilag_nr": "1",
        "indhold": [
            "<b>Patient:</b> Henrik Nørgaard, dansk statsborger, født 1974",
            "<b>Indlagt:</b> 13. november 2025 kl. 21:40",
            "<b>Udskrevet:</b> 17. november 2025 kl. 14:15",
            "<b>Diagnose:</b> Plasmodium falciparum malaria, ukompliceret (ICD-10: B50.9)",
            "<b>Forløb:</b> Patienten ankom med 39,8°C feber, kuldegysninger, "
            "hovedpine og let kvalme. Hurtigtest positiv for P. falciparum. "
            "Behandling påbegyndt med artemether-lumefantrin (Coartem) og "
            "IV-væsketerapi. Stabil temperatur fra dag 2. Udskrevet i god "
            "almentilstand med oral behandling de næste 3 dage.",
            "<b>Anbefaling:</b> Hvile minimum 7 dage efter udskrivning. "
            "Opfølgende blodprøve hos egen læge i hjemlandet inden for "
            "14 dage.",
            "<b>Behandlingsomkostninger:</b> 1.250 USD (faktura vedhæftet)",
            "Underskrift: Dr. Joseph K. Wanjiru, MD",
            "(Bemærk: dokumentet er translateret fra engelsk til dansk for "
            "Pakkerejse-Ankenævnets behandling.)",
        ],
    },
    {
        "filnavn": "bilag-02-rejseprogram.pdf",
        "titel": "Officielt rejseprogram fra SuperSafari A/S",
        "undertitel": "Maasai Mara Big Five · efterår 2025",
        "bilag_nr": "2",
        "indhold": [
            "<b>SuperSafari Maasai Mara Big Five · 14 dage</b>",
            "<b>Dag 1-2:</b> Ankomst Nairobi, overnatning Sarova Stanley Hotel.",
            "<b>Dag 3-5:</b> Transport til Keekorok Lodge i Maasai Mara. "
            "Game drives morgen og eftermiddag.",
            "<b>Dag 6-9:</b> Skift til Mara Serena Safari Lodge. "
            "Game drives og besøg ved Mara River.",
            "<b>Dag 10-12:</b> Lake Nakuru udflugt, flamingoer og næsehorn.",
            "<b>Dag 13-14:</b> Retur til Nairobi og hjemrejse.",
            "<b>Praktiske oplysninger (citat side 14 i program):</b>",
            "\"Inden afrejse anbefaler vi, at du konsulterer din læge "
            "vedrørende relevante vaccinationer og forholdsregler for "
            "rejser til Østafrika. Pas, visum og rejseforsikring er den "
            "rejsendes ansvar. SuperSafari medbringer en grundlæggende "
            "førstehjælpskasse, men gæster bør selv medbringe personlige "
            "lægemidler og evt. insektmiddel.\"",
            "<b>Bemærk:</b> Programmet nævner IKKE eksplicit malaria, "
            "tyfus eller dengue. Ingen risikoprofil for sygdomme.",
        ],
    },
    {
        "filnavn": "bilag-03-svar-fra-supersafari.pdf",
        "titel": "Afvisning fra SuperSafari A/S",
        "undertitel": "Brev af 8. december 2025",
        "bilag_nr": "3",
        "indhold": [
            "<b>Fra:</b> Camilla Westergaard, kundeservicechef, SuperSafari A/S",
            "<b>Til:</b> Henrik Nørgaard",
            "<b>Dato:</b> 8. december 2025",
            "<b>Vedr.:</b> Din henvendelse af 26. november 2025 — booking SS-KEN-7711",
            "Kære Henrik,",
            "Vi har modtaget din henvendelse og forstår, at du fik et "
            "alvorligt sygdomsforløb under din Maasai Mara-rejse. Det er "
            "vi naturligvis kede af på dine vegne.",
            "Vi må dog afvise din klage med følgende begrundelse:",
            "<b>1. Information om sundhedsrisiko:</b> Du modtog forud for "
            "afrejse vores praktiske rejseinfo (vedhæftet din bekræftelse "
            "den 12. september 2025), hvor vi udtrykkeligt opfordrer til "
            "lægekonsultation om vaccinationer og forholdsregler for "
            "Østafrika. Det er almen kendt, at Maasai Mara er et "
            "malariaområde, og forebyggende medicin (malariaprofylakse) "
            "samt insektmiddel er den rejsendes eget ansvar.",
            "<b>2. Forhold på lodgerne:</b> Keekorok Lodge og Mara Serena "
            "er anerkendte 4-stjernede safari-lodges med myggenet over "
            "alle senge som standard. Hvis nettet på dit værelse var "
            "defekt, burde det være rapporteret til receptionen, så det "
            "kunne udskiftes.",
            "<b>3. Erstatning:</b> Pakkerejseloven indebærer ikke et "
            "objektivt ansvar for sygdom pådraget under rejsen, når "
            "rejseinformationen har været tilstrækkelig.",
            "Vi tilbyder dog som kulancegestus et værdibevis på 3.000 kr. "
            "til en fremtidig SuperSafari-rejse, gældende i 24 måneder.",
            "Med venlig hilsen, Camilla Westergaard",
        ],
    },
]


# ─────────────────────────────────────────────────────────────────
# SAG 4 — EUtripper ApS — Aflyste udflugter
# ─────────────────────────────────────────────────────────────────

SAG_4 = {
    "mappe": "sag-04-eutripper",
    "sagsnr": "25-2876",
    "modtaget_dato": "1. november 2025",
    "indklagede": "EUtripper ApS, CVR 45678901",
    "klager_navn": "Camilla og Frederik Holm m.fl.",
    "klager_adresse": "Lærkevej 8, 2750 Ballerup",
    "klager_email": "camilla.holm@eksempelmail.dk",
    "klager_tlf": "29 18 44 22",
    "destination": "Rom, Italien — Hotel Quirinale, centrum",
    "rejseperiode": "14. oktober 2025 – 18. oktober 2025 (4 nætter)",
    "antal_rejsende": "2 voksne + 2 børn (alder 9 og 12)",
    "rejse_pris": "22.400 kr. samlet for 4 personer",
    "bookingref": "EUT-ROM-4488",
    "klagepunkter": (
        "Vi bookede EUtrippers pakke \"Det evige Rom\" til vores efterårsferie "
        "med vores to børn. Pakken inkluderede ifølge bookingbekræftelsen "
        "(bilag 1) flytransport, hotel, morgenmad, og 2 guidede udflugter:\n\n"
        "• Udflugt 1: Vatikanmuseerne og Det Sixtinske Kapel "
        "(fredag 17. oktober kl. 09:00)\n"
        "• Udflugt 2: Colosseum, Forum Romanum og Palatin-højen "
        "(lørdag 18. oktober kl. 10:00)\n\n"
        "BEGGE udflugter blev aflyst af EUtripper. Vi modtog en e-mail "
        "torsdag aften kl. 22:15 (mindre end 12 timer før den første "
        "udflugt) der lakonisk meddelte, at \"begge udflugter desværre "
        "må aflyses pga. interne forhold hos vores lokale partner\". "
        "Der blev ikke tilbudt alternativer eller refusion.\n\n"
        "Vi forsøgte selv at booke nye billetter til Vatikanet og "
        "Colosseum lokalt, men begge var fuldt udsolgte for vores "
        "rejsedage. Vores børn blev meget skuffede — udflugterne var "
        "hele formålet med rejsen for dem.\n\n"
        "Hjemkommen kontaktede vi EUtripper, der har henvist os til at "
        "kræve refusion gennem rejseforsikringen — men forsikringen "
        "dækker ikke aflyste udflugter fra arrangøren."
    ),
    "paastand": (
        "Klagerne kræver refusion af de aflyste udflugters andel af "
        "pakkeprisen. Udflugterne udgør efter vores beregning ca. 30% "
        "af rejsens samlede merværdi (uden hotel og fly). Konkret krav: "
        "6.800 kr. (1.700 kr. pr. person × 4) samt en symbolsk "
        "godtgørelse for tabt ferieoplevelse på 2.000 kr. — i alt 8.800 kr."
    ),
    "tidligere_korrespondance": (
        "Klagerne har skriftligt henvendt sig til EUtripper ApS den "
        "21. oktober 2025. EUtripper har svaret den 28. oktober 2025 "
        "og afvist refusion med henvisning til, at \"udflugterne var "
        "leveret af tredjepart, og kompensationen skal kræves derfra\". "
        "Klagerne afviser denne tolkning, da udflugterne var en del "
        "af den samlede pakke købt af EUtripper."
    ),
}

SAG_4_BILAG = [
    {
        "filnavn": "bilag-01-bookingbekraeftelse.pdf",
        "titel": "Bookingbekræftelse — \"Det evige Rom\"",
        "undertitel": "EUtripper ApS · pakke EUT-ROM-4488",
        "bilag_nr": "1",
        "indhold": [
            "<b>Bookingbekræftelse · udstedt 12. august 2025</b>",
            [
                ["Rejsende:", "Camilla Holm, Frederik Holm, Astrid (12), Magnus (9)"],
                ["Periode:", "14.10.2025 – 18.10.2025"],
                ["Hotel:", "Hotel Quirinale, 4★, central Rom"],
                ["Forplejning:", "Morgenmad inkluderet"],
                ["Fly:", "SAS København–Rom t/r"],
                ["Pakkepris:", "22.400 kr. samlet"],
            ],
            "<b>Inkluderede udflugter:</b>",
            "✓ Vatikanmuseerne og Det Sixtinske Kapel — guidet, 3,5 timer "
            "(fredag 17.10 kl. 09:00). Inkluderer skip-the-line adgang, "
            "headset, dansktalende guide.",
            "✓ Colosseum, Forum Romanum og Palatin-højen — guidet, 4 timer "
            "(lørdag 18.10 kl. 10:00). Inkluderer skip-the-line adgang, "
            "audioguide, dansktalende guide.",
            "<b>Bemærk:</b> Begge udflugter er fast del af pakken og kan "
            "ikke fravælges. Værdi anslået til 425 kr. pr. person pr. "
            "udflugt på almindelig billet hos lokal udbyder.",
        ],
    },
    {
        "filnavn": "bilag-02-aflysning-fra-eutripper.pdf",
        "titel": "E-mail om aflysning af udflugter",
        "undertitel": "Modtaget 16. oktober 2025 kl. 22:15",
        "bilag_nr": "2",
        "indhold": [
            "<b>Fra:</b> bookings@eutripper.dk",
            "<b>Til:</b> camilla.holm@eksempelmail.dk",
            "<b>Dato:</b> 16. oktober 2025 kl. 22:15",
            "<b>Emne:</b> Vedr. booking EUT-ROM-4488 — udflugter aflyst",
            "Kære Camilla,",
            "Vi beklager at måtte oplyse, at begge guidede udflugter på "
            "din pakke \"Det evige Rom\" (fredag Vatikanet og lørdag "
            "Colosseum) desværre må aflyses pga. interne forhold hos "
            "vores lokale partner Roma Tours s.r.l.",
            "Vi anbefaler, at du selv arrangerer alternative besøg på "
            "egne hånd. Hotellets concierge kan være behjælpelig.",
            "Refusion af udflugterne er ikke mulig, da disse er leveret "
            "af tredjepart. Vi henviser til din rejseforsikring.",
            "God ferie!",
            "Med venlig hilsen, EUtripper Bookingteam",
        ],
    },
    {
        "filnavn": "bilag-03-korrespondance-efter.pdf",
        "titel": "Korrespondance efter hjemkomst",
        "undertitel": "Oktober 2025",
        "bilag_nr": "3",
        "indhold": [
            "<b>E-mail fra Camilla Holm til EUtripper, 21. oktober 2025:</b>",
            "\"Vi vendte hjem i søndags efter en rejse, hvor halvdelen af "
            "indholdet i \"Det evige Rom\"-pakken ikke blev leveret. "
            "Vi kræver refusion af de aflyste udflugter — vi købte en "
            "samlet pakke af jer, ikke separate ydelser. Hverken "
            "Vatikanmuseerne eller Colosseum kunne vi booke billetter "
            "til selv, da alt var udsolgt. Vores børn var meget "
            "skuffede.\"",
            "<b>Svar fra Jonas Petersen, EUtripper kundeservice, "
            "28. oktober 2025:</b>",
            "\"Kære Camilla. Vi forstår jeres frustration, men må fastholde, "
            "at udflugterne blev leveret af tredjepart (Roma Tours s.r.l.). "
            "Aflysningen lå uden for EUtrippers kontrol. Vi opfordrer jer "
            "til at kontakte jeres rejseforsikring eller fremsætte krav "
            "direkte mod Roma Tours. EUtripper kan tilbyde 1.000 kr. som "
            "kulance.\"",
            "<b>Svar fra Camilla Holm, 30. oktober 2025:</b>",
            "\"Tilbuddet afvises. Pakkerejselovens § 2 er klar: arrangøren "
            "(EUtripper) er ansvarlig for hele pakkens levering, uanset "
            "hvem der er underleverandør. Vi indbringer sagen for "
            "Pakkerejse-Ankenævnet.\"",
        ],
    },
]


# ─────────────────────────────────────────────────────────────────
# SAG 5 — SportsTours International — Ugyldige billetter
# ─────────────────────────────────────────────────────────────────

SAG_5 = {
    "mappe": "sag-05-sportstours",
    "sagsnr": "26-0408",
    "modtaget_dato": "25. marts 2026",
    "indklagede": "SportsTours International ApS, CVR 56789012",
    "klager_navn": "Jens Petersen m.fl. (6 personer)",
    "klager_adresse": "Vesterbrogade 132, 1620 København V",
    "klager_email": "jens.petersen@eksempelmail.dk",
    "klager_tlf": "26 14 88 02",
    "destination": "Liverpool, England — Premier League Weekend-pakke",
    "rejseperiode": "8. marts 2026 – 10. marts 2026 (2 nætter)",
    "antal_rejsende": "6 voksne",
    "rejse_pris": "75.000 kr. samlet (12.500 kr. pr. person)",
    "bookingref": "STI-LFC-2266",
    "klagepunkter": (
        "Vi var 6 venner der havde glædet os til denne tur i over et år. "
        "SportsTours' \"Liverpool Premier League Weekend\" indeholdt:\n\n"
        "• Fly København–Manchester t/r\n"
        "• 2 nætter på Hard Days Night Hotel\n"
        "• 6 billetter til Liverpool FC vs. Arsenal på Anfield, lørdag "
        "9. marts 2026 kl. 17:30\n"
        "• Anfield Stadium Tour (lørdag formiddag)\n"
        "• Pubcrawl med guide fredag aften\n\n"
        "Vi mødte op ved Anfield kl. 16:45, klar til kamp. Ved indgangen "
        "(turnstile 18-25) blev ALLE 6 BILLETTER afvist af scanneren. "
        "Stewarden tilkaldte en supervisor, der efter 10 minutters "
        "kontrol oplyste, at billetterne var \"udstedt fra en kilde, "
        "der ikke er Liverpool FCs officielle billetdistribution\" — "
        "og at vi derfor ikke kunne komme ind på stadion.\n\n"
        "Vi forsøgte gentagne gange at ringe til SportsTours' "
        "vagttelefon — ingen svar. Vi sendte SMS, ingen svar. Vi gik "
        "tilbage til hotellet og så kampen på pub. Hele rejsens "
        "højdepunkt var ødelagt.\n\n"
        "Senere har det vist sig, at billetterne sandsynligvis var "
        "købt på det \"grå marked\" — uautoriseret videresalg som "
        "Premier League-klubberne aktivt blokerer."
    ),
    "paastand": (
        "Klagerne kræver fuld refusion af billetkomponenten samt "
        "godtgørelse for tabt rejseoplevelse: 6 × 4.500 kr. (billet-værdi "
        "iht. pakke) = 27.000 kr. samt 18.000 kr. (3.000 kr. pr. person) "
        "for tabt oplevelse og spildt rejse. Samlet krav: 45.000 kr."
    ),
    "tidligere_korrespondance": (
        "Klagerne har henvendt sig til SportsTours International ApS "
        "den 11. marts 2026 (umiddelbart efter hjemkomst). "
        "SportsTours har svaret den 19. marts 2026 og oplyst, at "
        "billetterne \"normalt fungerer fint\" og at det \"må være en "
        "fejl hos Liverpool FCs scanningssystem\". SportsTours har "
        "tilbudt 5.000 kr. samlet for hele gruppen. Klagerne har "
        "afvist tilbuddet."
    ),
}

SAG_5_BILAG = [
    {
        "filnavn": "bilag-01-billetkopi-og-rejseplan.pdf",
        "titel": "Billetkopi og rejseplan",
        "undertitel": "Premier League Weekend · marts 2026",
        "bilag_nr": "1",
        "indhold": [
            "<b>Pakke STI-LFC-2266 · 6 personer</b>",
            [
                ["Fly ud:", "SK1465 · CPH → MAN · 08.03.2026 kl. 10:25"],
                ["Fly hjem:", "SK1464 · MAN → CPH · 10.03.2026 kl. 14:50"],
                ["Hotel:", "Hard Days Night Hotel, Liverpool (2 dobbeltværelser + 1 enkelt)"],
                ["Kamp:", "Liverpool FC vs. Arsenal · Anfield · 09.03.2026 kl. 17:30"],
                ["Sektion:", "Anfield Road End, blok 124, række 31-32, sæder 14-19"],
                ["Billet-værdi (iht. pakke):", "4.500 kr. pr. person"],
            ],
            "<b>Billet-stub (eksempel):</b>",
            "PREMIER LEAGUE 2025/26 — Liverpool FC vs. Arsenal",
            "Saturday 9 March 2026 · 5:30 PM kick-off · Anfield",
            "Block: 124 · Row: 31 · Seat: 14",
            "Ticket ID: AR-2266-014  (alle 6 billetter har sekventielle "
            "ID'er: 014–019)",
            "Issued via: SportsTours International (kontrakt med Anfield Hospitality)",
            "<b>Bemærk:</b> Liverpool FC har efterfølgende på e-mail "
            "(jf. bilag 3) bekræftet at de pågældende ticket-ID'er IKKE "
            "var registreret i deres officielle distributionssystem.",
        ],
    },
    {
        "filnavn": "bilag-02-foto-og-vidneudsagn.pdf",
        "titel": "Vidneudsagn og foto fra Anfield",
        "undertitel": "Anfield Stadium · 9. marts 2026 kl. 17:00",
        "bilag_nr": "2",
        "indhold": [
            "<b>Foto-dokumentation (vedhæftet separat):</b>",
            "• Foto 1: Scannerens display med rød fejlkode \"INVALID — "
            "TICKET NOT IN SYSTEM\" ved turnstile 22, kl. 16:52.",
            "• Foto 2: Gruppen samlet uden for indgangen efter afvisning, "
            "kl. 17:08.",
            "• Foto 3: Supervisor Stewart Healey (synlig på ID-kort) i "
            "samtale med klager Jens Petersen.",
            "<b>Skriftligt vidneudsagn fra steward-supervisor "
            "(udleveret på stedet, jf. Anfield-stewardpolicy):</b>",
            "\"On 9 March 2026 at approximately 17:05 I was called to "
            "turnstile 22 to assist with a party of 6 Danish supporters "
            "whose tickets failed to scan. Upon inspection in our system, "
            "ticket IDs AR-2266-014 through AR-2266-019 do not appear in "
            "our authorised distribution. The tickets are not valid for "
            "entry. The party were polite and cooperative, and were "
            "advised to seek redress from their travel provider. "
            "— Stewart Healey, Senior Steward Supervisor, Anfield.\"",
            "<b>Klagers tilføjelse:</b> Trods 11 ubesvarede opkald og "
            "4 SMS'er til SportsTours' vagttelefon i tidsrummet 17:10-18:30 "
            "fik vi INGEN reaktion fra SportsTours den aften. Først "
            "mandag morgen fik vi kontakt.",
        ],
    },
    {
        "filnavn": "bilag-03-email-fra-liverpool-fc.pdf",
        "titel": "E-mail fra Liverpool Football Club",
        "undertitel": "Officiel bekræftelse på ugyldige billetter",
        "bilag_nr": "3",
        "indhold": [
            "<b>Fra:</b> ticketing-enquiries@liverpoolfc.com",
            "<b>Til:</b> jens.petersen@eksempelmail.dk",
            "<b>Dato:</b> 13. marts 2026",
            "<b>Re:</b> Invalid match tickets — Liverpool vs. Arsenal, 9 March 2026",
            "Dear Mr. Petersen,",
            "Thank you for contacting Liverpool Football Club regarding "
            "the invalid tickets you presented at Anfield on Saturday "
            "9 March 2026.",
            "I can confirm that ticket IDs AR-2266-014 through "
            "AR-2266-019, presented at turnstile 22, were NOT issued "
            "through our official distribution channels. These tickets "
            "appear to originate from a secondary market source not "
            "authorised by Liverpool FC.",
            "Premier League regulations and our own ticketing terms "
            "prohibit the resale of match tickets through unauthorised "
            "third parties. We have no commercial agreement with "
            "\"SportsTours International\" or any subsidiary thereof.",
            "We recommend that you pursue compensation directly from "
            "the company who sold you the tickets. We are unable to offer "
            "refund or alternative attendance.",
            "Best regards,",
            "Sarah Mitchell · Customer Services · Liverpool Football Club",
            "<b>Klagers kommentar:</b> Denne mail dokumenterer entydigt, "
            "at SportsTours International har solgt os billetter til en "
            "kamp, de ikke havde lovlig adgang til at videredistribuere. "
            "Det er efter vores opfattelse ikke en \"fejl hos Liverpool "
            "FCs scanningssystem\", som SportsTours hævder.",
        ],
    },
]


# ─────────────────────────────────────────────────────────────────
# STÆVNINGS-METADATA — pr. sag
# Berig hver sag-dict med disse felter inden _byg_staevning kaldes.
# ─────────────────────────────────────────────────────────────────

STAEVNING_META = {
    "sag-01-quicktour": {
        "indklagede_adresse": "Lufthavnsvej 4 · 7190 Billund",
        "sagsbehandler_initialer": "LK/jw",
        "sagsbehandler_navn": "Louise Kjær",
        "staevning_resume": (
            "Klagen vedrører forsinkelse af hjemrejsefly QT4471 fra Palma "
            "til Billund den 19. august 2025 med ca. 12 timer i forhold til "
            "den planlagte ankomst, samt manglende information og forplejning "
            "under ventetiden i Palma Lufthavn. Indklagede har afvist kompensation "
            "med henvisning til \"ekstraordinære omstændigheder\"."
        ),
        "staevning_paastand_kort": (
            "Klagerne kræver 8.500 kr., bestående af kompensation efter "
            "EU-forordning 261/2004 (5.960 kr.) og refusion af dokumenterede "
            "udgifter (2.540 kr.)."
        ),
    },
    "sag-02-firstworldtravel": {
        "indklagede_adresse": "Vester Voldgade 18 · 1552 København V",
        "sagsbehandler_initialer": "MM/jw",
        "sagsbehandler_navn": "Mathias Munk",
        "staevning_resume": (
            "Klagen vedrører manglende levering af kerneydelser på Sunset "
            "Paradise Resort, Maldiverne, i perioden 3.–13. januar 2026. "
            "Klager har modtaget Garden Villa i stedet for booket Beach Villa, "
            "infinity-pool og à la carte-restaurant var lukket hele opholdet, "
            "og halvpension+ blev erstattet af ensartet buffet."
        ),
        "staevning_paastand_kort": (
            "Klager kræver 35.000 kr. som forholdsmæssigt afslag (ca. 45% af "
            "pakkeprisen). Subsidiært kompensation efter pakkerejselovens § 24."
        ),
    },
    "sag-03-supersafari": {
        "indklagede_adresse": "Hovedvejen 142 · 2600 Glostrup",
        "sagsbehandler_initialer": "AB/jw",
        "sagsbehandler_navn": "Anne Bisgaard",
        "staevning_resume": (
            "Klagen vedrører malaria (P. falciparum) pådraget under en "
            "14-dages safari-rejse til Maasai Mara, Kenya, i november 2025. "
            "Klager gør gældende, at indklagede har givet utilstrækkelig "
            "information om malariarisiko, ikke har medbragt insektmiddel til "
            "gæsterne, og at myggenet på lodgerne var mangelfulde."
        ),
        "staevning_paastand_kort": (
            "Klager kræver 37.000 kr., bestående af forholdsmæssigt afslag "
            "for tabt ferie (25.000 kr.) og ikke-dækkede behandlingsudgifter "
            "(12.000 kr.)."
        ),
    },
    "sag-04-eutripper": {
        "indklagede_adresse": "Bredgade 22 · 1260 København K",
        "sagsbehandler_initialer": "PN/jw",
        "sagsbehandler_navn": "Pernille Nørby",
        "staevning_resume": (
            "Klagen vedrører aflysning af to guidede udflugter "
            "(Vatikanmuseerne og Colosseum), der var inkluderet i en samlet "
            "pakkerejse til Rom i oktober 2025. Udflugterne blev aflyst "
            "aftenen før første udflugt og uden tilbud om alternativer eller "
            "refusion. Indklagede har henvist klager til tredjepart "
            "(Roma Tours s.r.l.)."
        ),
        "staevning_paastand_kort": (
            "Klagerne kræver 8.800 kr. — refusion af udflugternes andel af "
            "pakkeprisen (6.800 kr.) samt godtgørelse for tabt ferieoplevelse "
            "(2.000 kr.)."
        ),
    },
    "sag-05-sportstours": {
        "indklagede_adresse": "Refshalevej 153A · 1432 København K",
        "sagsbehandler_initialer": "TS/jw",
        "sagsbehandler_navn": "Thomas Sønderby",
        "staevning_resume": (
            "Klagen vedrører ugyldige kampbilletter til Liverpool FC vs. "
            "Arsenal på Anfield den 9. marts 2026. Alle seks billetter blev "
            "afvist ved indgangen, da de ikke var registreret i Liverpool FCs "
            "officielle distributionssystem. Klagerne opnåede ikke adgang "
            "til kampen. Liverpool FC har bekræftet, at indklagede ikke har "
            "kommerciel aftale med klubben."
        ),
        "staevning_paastand_kort": (
            "Klagerne kræver 45.000 kr., bestående af refusion af billet-værdi "
            "(27.000 kr.) og godtgørelse for tabt rejseoplevelse (18.000 kr.)."
        ),
    },
}


# ─────────────────────────────────────────────────────────────────
# SELSKABS-INTERNE DOKUMENTER — pr. sag
# Tre dokumenter pr. sag: intern korrespondance, vilkår, og et
# sag-specifikt dokument (system-log, kontrakt, faktura osv.).
# ─────────────────────────────────────────────────────────────────

SELSKAB_DOCS = {
    "sag-01-quicktour": [
        {
            "filnavn": "selskab-01-intern-korrespondance.pdf",
            "selskab": "QuickTour A/S",
            "titel": "Intern e-mailkorrespondance — QT4471 19/8",
            "undertitel": "PMI Station Manager → Operations Center København",
            "indhold": [
                "<b>━━ E-MAIL 1 ━━</b>",
                [
                    ["Fra:", "Lars Mogensen <lars.m@quicktour.dk>"],
                    ["Til:", "ops-center@quicktour.dk"],
                    ["CC:", "trine.h@quicktour.dk · brian.r@quicktour.dk"],
                    ["Dato:", "19. august 2025 kl. 13:08"],
                    ["Emne:", "AKUT: QT4471 — kaptajn ude, ingen standby"],
                ],
                "Ops,",
                "Vi har en akut situation på PMI. Kaptajn på QT4471 "
                "(Brian Westergaard) har meldt sig syg kl. 12:45 med "
                "svimmelhed efter natfly fra TFS. Lokal læge har skrevet "
                "ham ud af tjeneste minimum 24 timer. Vi har <b>ingen</b> "
                "standby-kaptajn i PMI i dag — nærmeste tilgængelige er "
                "i Barcelona med ETA tidligst 18:00.",
                "<b>Min anbefaling:</b> Aflys QT4471 (planlagt afgang 14:30) "
                "og rebook de 142 passagerer på returflyet QT4475 i aften. "
                "QT4475 har plads til ekstra 84 pax — vi må have ca. 58 på "
                "natfly QT4477 i morgen tidlig. Forsinkelse for hovedparten "
                "bliver ca. 8 timer; for resten ca. 16 timer.",
                "Vi har ikke tid til SMS-blast før boarding skulle begynde. "
                "Skranken i T2 lukker normalt kl. 16:00 — kan vi få Iberia "
                "handling til at holde åbent?",
                "/Lars Mogensen, Station Manager Palma",
                "<b>━━ E-MAIL 2 ━━</b>",
                [
                    ["Fra:", "Trine Holm <trine.h@quicktour.dk>"],
                    ["Til:", "Lars Mogensen"],
                    ["CC:", "ops-center · kundeservice-leder"],
                    ["Dato:", "19. august 2025 kl. 13:32"],
                    ["Emne:", "SV: AKUT: QT4471"],
                ],
                "Lars,",
                "Godkendt. Aflys QT4471, rebook på QT4475 og QT4477. "
                "Vi sender SMS-blast så snart vi har bekræftet gates.",
                "<b>VIGTIG retningslinje for ekstern kommunikation:</b> I "
                "al kontakt med passagerer og senere kundeservice-håndtering "
                "skal vi fastholde linjen om \"ekstraordinære omstændigheder\" "
                "jf. EU 261/2004 art. 5(3). Pludselig sygdom hos enkelt "
                "besætningsmedlem kan argumenteres som dette — jeg ved at "
                "EU-Domstolens praksis (Krüsemann m.fl., C-195/17) er imod "
                "os, men vi prøver det indtil videre. Kundeservice må <b>ikke</b> "
                "love kontant kompensation. Hvis krav indløber, tilbyd "
                "værdibevis 1.000 kr.",
                "Iberia handling kontaktes via vores SLA-line. Skranken "
                "lukker stadig kl. 16:00, vi har ikke budget til overtid.",
                "/Trine Holm, Operations Manager",
                "<b>━━ E-MAIL 3 ━━</b>",
                [
                    ["Fra:", "Brian Rasmussen <brian.r@quicktour.dk>"],
                    ["Til:", "Trine Holm · Lars Mogensen"],
                    ["Dato:", "19. august 2025 kl. 14:48"],
                    ["Emne:", "SV: AKUT: QT4471 — passagerer er sure"],
                ],
                "Hej,",
                "QT4471 er nu aflyst. Skranken i PMI har været ubemandet "
                "siden 13:50 (Iberia kunne ikke holde åbent — krævede "
                "yderligere 4.500 EUR for overtid). Vi har ca. 90 passagerer "
                "der står i terminalen uden info. Telefonen til vagten i "
                "København er ringet til 47 gange siden 14:00 — uden svar "
                "fordi vi kun har 2 medarbejdere på pga. weekend.",
                "Jeg har lige fået første formelle klage på e-mail. Lægger "
                "den i kundeservice-køen.",
                "/Brian Rasmussen, vagt-kundeservice",
            ],
        },
        {
            "filnavn": "selskab-02-rejsebetingelser-uddrag.pdf",
            "selskab": "QuickTour A/S",
            "titel": "Rejsebetingelser 2025 — uddrag",
            "undertitel": "§ 12–14 om forsinkelser, ekstraordinære omstændigheder og kompensation",
            "indhold": [
                "<b>§ 12. Forsinkelser og aflysning af fly</b>",
                "12.1 QuickTour bestræber sig på at gennemføre alle planlagte "
                "afgange til den annoncerede tid. Forsinkelser eller aflysninger "
                "kan dog forekomme, og QuickTour påtager sig intet ansvar for "
                "indirekte tab, herunder mistet arbejdsindtjening, "
                "børnepasningsomkostninger eller missede tilslutningsforbindelser.",
                "12.2 Ved aflysning vil QuickTour tilbyde alternativ transport "
                "snarest muligt. Hvis alternativet medfører forsinkelse over "
                "5 timer, refunderes rejsen helt eller delvist efter "
                "selskabets skøn.",
                "<b>§ 13. Ekstraordinære omstændigheder</b>",
                "13.1 QuickTour er fritaget for kompensation efter "
                "pakkerejseloven § 23, stk. 2, samt efter EU-forordning "
                "261/2004 art. 5(3), hvis aflysning eller forsinkelse skyldes "
                "ekstraordinære omstændigheder. Dette omfatter blandt andet:",
                "(a) Vejrforhold der gør operationen usikker.",
                "(b) Politiske uroligheder, strejke, krig, terrorhandling.",
                "(c) <b>Akut og uforudset sygdom hos besætningsmedlem</b>, "
                "som ikke kan erstattes inden for rimelig tid.",
                "(d) Lufthavnsmæssige forhold uden for QuickTours kontrol "
                "(slot-problemer, ATC-restriktioner).",
                "13.2 Bevisbyrden for ekstraordinære omstændigheder påhviler "
                "QuickTour og dokumenteres på forespørgsel.",
                "<b>§ 14. Kompensation og servicestandarder</b>",
                "14.1 Ved aflysning eller forsinkelse på over 3 timer kan "
                "kompensation kræves efter EU-forordning 261/2004, medmindre "
                "årsagen er ekstraordinære omstændigheder.",
                "14.2 QuickTour kan tilbyde værdibevis i stedet for kontant "
                "udbetaling. Værdibeviser har 24 måneders gyldighed og kan "
                "ikke ombyttes til kontanter.",
                "14.3 Forplejning under ventetid følger EU 261/2004 art. 9 "
                "— måltider og drikkevarer i rimelig mængde tilbydes af "
                "selskabets stations-personale.",
                "<b>Bemærk (intern note, ikke i kunde-PDF):</b> § 14.3 er "
                "skrevet i form af forpligtelse, men i praksis tilbyder vi "
                "kun måltider på station hvor vi har egne medarbejdere. På "
                "PMI har vi ikke fast personale efter kl. 16:00.",
            ],
        },
        {
            "filnavn": "selskab-03-ops-log-qt4471.pdf",
            "selskab": "QuickTour A/S",
            "titel": "Operations log — QT4471 · 19. august 2025",
            "undertitel": "Auto-genereret udskrift fra OPS-system",
            "indhold": [
                "<b>Flyvningsdetaljer</b>",
                [
                    ["Rute:", "QT4471 · PMI → BLL"],
                    ["Type:", "B737-800, OY-QTC \"Lærken\""],
                    ["Planlagt afgang:", "19.08.2025 kl. 14:30 LT"],
                    ["Planlagt ankomst:", "19.08.2025 kl. 18:00 LT"],
                    ["Passagerer ombord (planlagt):", "142"],
                    ["Besætning:", "2 cockpit + 4 cabin"],
                ],
                "<b>Tidslinje 19. august 2025 (alle tidspunkter LT Palma)</b>",
                "<b>12:45</b> — Captain Brian Westergaard (CPT-414) reports "
                "unfit for duty. Cause: vertigo after night-rotation TFS-PMI. "
                "Local medical assessment: 24h grounded.",
                "<b>12:52</b> — Station Manager L. Mogensen notified. "
                "Standby crew check initiated.",
                "<b>13:04</b> — No standby captain available at PMI base. "
                "Closest: BCN, ETA 18:00.",
                "<b>13:08</b> — Email escalation to OPS København (see "
                "selskab-01).",
                "<b>13:32</b> — OPS approval: cancel QT4471, rebook on "
                "QT4475 (22:30) and QT4477 (next morning).",
                "<b>13:45</b> — Cancellation published in DCS system. "
                "Boarding gate B24 reassigned.",
                "<b>13:50</b> — Iberia handling station closes for QT-affiliated "
                "operations (overtime not authorized).",
                "<b>14:00</b> — First passenger complaint logged "
                "(ticket #QT-CS-887421-001 — \"Mette Lindgaard\", booking "
                "QT-887421).",
                "<b>14:08</b> — SMS-blast attempted: 142 recipients. Delivery "
                "confirmed for 89 numbers. 53 failed (Danish phones in "
                "roaming mode, T-Mobile EU SMS gateway issue).",
                "<b>14:30</b> — Original scheduled departure time. Flight "
                "officially logged as CANCELLED in regulatory reporting.",
                "<b>22:48</b> — QT4475 (rebooked) departs PMI with 84 "
                "rebooked passengers + 178 original passengers (full).",
                "<b>02:40 (20.08)</b> — QT4475 lands BLL. 8h 40m delay vs. "
                "original QT4471 scheduled arrival.",
                "<b>Note fra OPS:</b> Manglende SMS-leverance til 53 "
                "passagerer er en kendt issue med vores T-Mobile EU SMS-aftale. "
                "Tilskrives ikke ekstraordinære omstændigheder.",
            ],
        },
    ],

    "sag-02-firstworldtravel": [
        {
            "filnavn": "selskab-01-intern-korrespondance.pdf",
            "selskab": "FirstWorldTravel ApS",
            "titel": "Intern e-mailkorrespondance vedr. Sunset Paradise Resort",
            "undertitel": "Bookingafdeling København ↔ Resort Manager · december 2025 – januar 2026",
            "indhold": [
                "<b>━━ E-MAIL 1 — fra Resort ━━</b>",
                [
                    ["Fra:", "Faisal Rahman <gm@sunsetparadise.mv>"],
                    ["Til:", "bookings@firstworldtravel.dk"],
                    ["Dato:", "28. december 2025 kl. 09:14 (MVT)"],
                    ["Emne:", "Important: pool refurbishment + Coral closure"],
                ],
                "Dear FirstWorldTravel team,",
                "I am writing to inform you that our infinity pool will be "
                "closed for refurbishment from December 28, 2025 until "
                "approximately January 25, 2026. The work cannot be delayed "
                "due to structural concerns identified during last week's "
                "inspection.",
                "Additionally, our à la carte restaurant Coral will be closed "
                "throughout January 2026 due to staffing shortages following "
                "the departure of our head chef. We will operate buffet "
                "service in the main restaurant.",
                "I sincerely apologize for the short notice. Please inform "
                "all guests with arrivals in January and offer them the "
                "option to rebook or receive partial compensation.",
                "We are prepared to offer FirstWorldTravel guests:",
                "(1) Free upgrade to Beach Villa (subject to availability)",
                "(2) 30% discount on next booking within 12 months",
                "(3) Complimentary spa treatment (2 × 60 min per stay)",
                "Best regards, Faisal Rahman · General Manager · Sunset Paradise Resort",
                "<b>━━ E-MAIL 2 — intern besked ━━</b>",
                [
                    ["Fra:", "Camilla Larsen <camilla.l@firstworldtravel.dk>"],
                    ["Til:", "mette.k@firstworldtravel.dk"],
                    ["CC:", "premium-team@firstworldtravel.dk"],
                    ["Dato:", "29. december 2025 kl. 11:42"],
                    ["Emne:", "VS: Sunset Paradise — pool/Coral lukket januar"],
                ],
                "Mette,",
                "Vi har et problem. Sunset Paradise har lige meldt at både "
                "pool og Coral er lukket i hele januar. Vi har <b>14 "
                "rejsende</b> med januar-ankomst hos os, herunder Annika "
                "Berggren (FWT-MLE-9921) der ankommer 3. januar.",
                "Hotellet tilbyder gratis Beach Villa-opgradering, 30% rabat "
                "på næste booking, og spa-treatments. Det dækker ikke vores "
                "tab — vi har solgt halvpension+ med Coral som hovedindgang.",
                "Spørgsmål til jer:",
                "(1) Skal vi notify alle 14 gæster nu? Det vil koste os "
                "kompensation per kunde + dårlig anmeldelse-risk.",
                "(2) Eller venter vi til de er på resort og lader hotellet "
                "håndtere det? Sparer os notifikations-byrden, men juridisk "
                "risikabelt.",
                "(3) Premium-pakken har \"havudsigt-Beach Villa\" som "
                "specifik feature i markedsføringen. Kan vi sige det er "
                "leveret, hvis vi kun opgraderer halvdelen?",
                "Brug for input INDEN nytår — mange gæster rejser januar.",
                "/Camilla, Booking Premium",
                "<b>━━ E-MAIL 3 — intern beslutning ━━</b>",
                [
                    ["Fra:", "Mette Krogh <mette.k@firstworldtravel.dk>"],
                    ["Til:", "Camilla Larsen"],
                    ["CC:", "premium-team · jura@firstworldtravel.dk"],
                    ["Dato:", "30. december 2025 kl. 16:08"],
                    ["Emne:", "SV: VS: Sunset Paradise — strategi"],
                ],
                "Camilla,",
                "<b>Beslutning:</b>",
                "<b>(1)</b> Vi notifier <b>ikke</b> proaktivt. Vi har "
                "kontraktlig dækning i § 6.2 (force majeure-lignende "
                "vedligehold). Lad hotellet håndtere det in-person.",
                "<b>(2)</b> Beach Villa opgradering: vi tilbyder kun til "
                "gæster der KLAGER. Reduktion af proaktive omkostninger.",
                "<b>(3)</b> Hvis kunder klager efter hjemkomst: standard-"
                "tilbud 8.000 kr. + 5.000 kr. værdibevis. Hvis de afviser "
                "og ankenævn-truer: vurder case-by-case. Vores erfaring er "
                "at 70% accepterer 8.000-tilbudet.",
                "Husk: undgå at indrømme \"manglende leverance\" skriftligt "
                "— kald det altid \"uventede vedligeholdelsesforhold\".",
                "/Mette, Customer Service Manager",
            ],
        },
        {
            "filnavn": "selskab-02-hotel-rammeaftale-uddrag.pdf",
            "selskab": "FirstWorldTravel ApS",
            "titel": "Rammeaftale med Sunset Paradise Resort — uddrag",
            "undertitel": "Allotment Agreement 2024–2026 · § 4 og § 6",
            "indhold": [
                "<b>Rammeaftale mellem FirstWorldTravel ApS (\"FWT\") og "
                "Sunset Paradise Resort Maldives Pvt. Ltd. (\"Hotel\")</b>",
                "Indgået 1. november 2023 · gælder for kalenderår 2024–2026",
                "<b>§ 4. Hotellets forpligtelser</b>",
                "4.1 Hotel garanterer at alle bookede ydelser leveres i "
                "overensstemmelse med den til enhver tid gældende "
                "produktbeskrivelse (Annex A).",
                "4.2 <b>Forhåndsvarsel om ændringer:</b> Hotel skal "
                "underrette FWT skriftligt om enhver væsentlig ændring i "
                "produktbeskrivelsen (lukninger, renoveringer, ændret "
                "restaurant-/pool-tilbud m.v.) <b>senest 60 dage før "
                "ændringens ikrafttræden</b>.",
                "4.3 Ved manglende rettidig varsel hæfter Hotel for FWT's "
                "rimelige omkostninger til omkonkretering, herunder "
                "kompensation til berørte gæster, refusion og PR-skade.",
                "<b>§ 6. Ansvarsbegrænsning</b>",
                "6.1 Hotel er ikke ansvarlig for force majeure (krig, "
                "naturkatastrofer, pandemi-relaterede restriktioner).",
                "6.2 Akut og uforudsigeligt vedligehold der er nødvendigt af "
                "sikkerhedshensyn, kan gennemføres uden de 60 dages varsel, "
                "<b>men kun mod skriftlig dokumentation af, at vedligeholdet "
                "ikke kunne have været identificeret tidligere ved "
                "rimelig inspektion</b>.",
                "<b>Intern marginale fra FWT jura, dateret 30.12.2025:</b>",
                "\"Hotellet henviser til 'structural concerns identified "
                "during last week's inspection' — uklart om dette opfylder "
                "§ 6.2's beviskrav. FWT bør dokumentere hotellets "
                "begrundelse skriftligt for at sikre regreskrav.\"",
                "<b>Annex A — produktbeskrivelse 2025-2026 (uddrag)</b>",
                "Beach Villa (kategori BV-PRM): direkte stranddagang, fuld "
                "havudsigt, privat terrasse, 65 m². Garanteret tilgængelig "
                "for FWT Premium-pakke.",
                "Garden Villa (kategori GV-STD): havesektion mod "
                "intern resort-side, 45 m². Ikke en del af FWT Premium.",
                "Faciliteter: 3 restauranter (Coral à la carte, Lagoon buffet, "
                "Sunset bar), 2 pools (infinity sunset pool + family pool), "
                "spa, dive center.",
            ],
        },
        {
            "filnavn": "selskab-03-premium-pakke-betingelser.pdf",
            "selskab": "FirstWorldTravel ApS",
            "titel": "Premium Maldives 2026 — pakkebetingelser",
            "undertitel": "Som udleveret til kunder · revision 11/2025",
            "indhold": [
                "<b>FirstWorldTravel Premium Maldives 2026 — Hvad du får</b>",
                "Vores Premium-pakker er kurateret for rejsende der "
                "forventer det ypperste. Hvert ophold inkluderer:",
                "<b>✓ Garanteret Beach Villa</b> — direkte havadgang og "
                "uhindret havudsigt fra din private terrasse.",
                "<b>✓ Adgang til alle resort-faciliteter</b> — herunder "
                "à la carte-restauranter, spa, infinity-pool og water sports.",
                "<b>✓ Halvpension+</b> — daglig morgenmad samt 5-retters "
                "middag på resortets signatur-restaurant.",
                "<b>✓ Privat transfer</b> — sølvfly eller speedboat afhængig "
                "af resortets beliggenhed.",
                "<b>✓ FirstWorldTravel-konsierge</b> — dedikeret kontaktperson "
                "i hele opholdet.",
                "<b>Vores Premium-garanti</b>",
                "Hvis et lovet element af din Premium-pakke ikke leveres "
                "som beskrevet, refunderer FirstWorldTravel den forholdsmæssige "
                "værdi <b>op til 10% af pakkeprisen</b> som kompensation. "
                "Anmodning skal fremsættes inden for 30 dage efter hjemkomst.",
                "<b>Forbehold</b>",
                "(1) Tilfældige faciliteter (specifikke restauranter, "
                "bestemte aktiviteter) kan ændres uden varsel.",
                "(2) Vejrforhold og andre force majeure-omstændigheder er "
                "ikke dækket af Premium-garantien.",
                "(3) Værelseskategorier kan opgraderes eller flyttes "
                "afhængig af hotellets aktuelle situation. Beach Villa er "
                "altid den foretrukne kategori, men ikke kontraktlig "
                "garanti.",
                "(4) Kompensation kan udbetales som værdibevis efter "
                "FirstWorldTravels valg.",
                "<b>Intern note (ikke i kunde-PDF):</b> \"§4.3 er bevidst "
                "skrevet vagt — 10%-loftet er vores hovedforsvarspunkt mod "
                "større krav. Faktisk juridisk skal vi følge pakkerejseloven "
                "§ 24 om forholdsmæssigt afslag, men i 80% af sager "
                "accepterer kunderne vores loft.\"",
            ],
        },
    ],

    "sag-03-supersafari": [
        {
            "filnavn": "selskab-01-intern-korrespondance.pdf",
            "selskab": "SuperSafari A/S",
            "titel": "Intern korrespondance vedr. Henrik Nørgaard",
            "undertitel": "Rejseleder Nairobi → Hovedkontor Glostrup · november 2025",
            "indhold": [
                "<b>━━ E-MAIL 1 — Akut underretning ━━</b>",
                [
                    ["Fra:", "David Karingu <david.k@supersafari.dk>"],
                    ["Til:", "operations@supersafari.dk"],
                    ["CC:", "kundeservice@supersafari.dk"],
                    ["Dato:", "13. november 2025 kl. 22:18 (EAT)"],
                    ["Emne:", "Gæst Henrik Nørgaard — hospitaliseret malaria"],
                ],
                "Hej operations,",
                "Henrik Nørgaard (booking SS-KEN-7711, dag 9 af 14) har i "
                "dag fået konstateret P. falciparum malaria. Han blev "
                "transporteret til Narok County Referral Hospital efter "
                "feber 39,8°C og kraftige kuldegysninger.",
                "Tilstand stabiliseret med Coartem og IV-væske. Lægen "
                "forventer udskrivning på 3–4 dage. Henrik er ikke "
                "kritisk syg.",
                "Bemærkninger til sagen:",
                "(1) Henrik fortalte mig på dag 2, at han <b>ikke</b> tog "
                "malariaprofylakse. Han sagde \"jeg har læst på nettet at "
                "Maasai Mara ikke er højrisiko\". Jeg gentog vores standard-"
                "anbefaling om at tage Malarone hele opholdet, men han "
                "afviste.",
                "(2) Hans værelse på Keekorok Lodge — værelse 24 — havde et "
                "<b>defekt myggenet</b> (rev i venstre side, ca. 10 cm). "
                "Henrik bad lodge-receptionen om at få det repareret dag 3, "
                "men det blev ikke gjort før dag 6.",
                "(3) Jeg havde insektmiddel (Jungle Formula DEET 50%) med "
                "mig i jeep'en, men distribuerede det ikke proaktivt. Jeg "
                "har generelt antaget at gæster medbringer deres eget.",
                "Hvordan håndterer vi det? Jeg ved at vores rejsebetingelser "
                "(§ 19 om sygdom) er ret strikse — men det defekte myggenet "
                "er et problem.",
                "/David Karingu, rejseleder Maasai Mara",
                "<b>━━ E-MAIL 2 — internt svar ━━</b>",
                [
                    ["Fra:", "Camilla Westergaard <camilla.w@supersafari.dk>"],
                    ["Til:", "David Karingu"],
                    ["CC:", "anders.h@supersafari.dk (jurist)"],
                    ["Dato:", "14. november 2025 kl. 08:42"],
                    ["Emne:", "SV: Gæst Henrik Nørgaard — hospitaliseret"],
                ],
                "David,",
                "Tak for hurtig opdatering. Glad for at Henrik er stabil.",
                "Kommunikations-linje fremad:",
                "<b>(1) Officielt:</b> Sygdom under rejsen er gæstens "
                "eget ansvar. Vi henviser til vores rejseinformation der "
                "klart opfordrer til malariaprofylakse. Pakkerejseloven "
                "indebærer intet objektivt ansvar for sygdom.",
                "<b>(2) Værelse 24 myggenet:</b> Internt vigtigt — slet ikke "
                "i officiel kommunikation. Hvis Henrik klager senere og "
                "nævner myggenettet, så hold linjen: \"Beklagelig fejl der "
                "blev udbedret\". Få lodge-management til at skrive at "
                "reparationen blev udført dag 3 (selvom det først var dag 6).",
                "<b>(3) Insektmiddel:</b> Vi siger ikke at vi har det med — "
                "fordi vores rejsebetingelser ikke lover det. Hvis Henrik "
                "spørger: \"vi anbefaler gæster selv at medbringe\".",
                "<b>(4) Refusion af tabte dage:</b> Vi tilbyder 3.000 kr. "
                "kulance-værdibevis. Hvis han presser, max 5.000 kr.",
                "Vigtigt: ingen skriftlig kommunikation der kan tolkes som "
                "indrømmelse. Hold det mundtligt med Henrik når han kommer "
                "hjem.",
                "/Camilla, Customer Service Manager",
                "<b>━━ E-MAIL 3 — opfølgning fra rejseleder ━━</b>",
                [
                    ["Fra:", "David Karingu"],
                    ["Til:", "Camilla Westergaard"],
                    ["Dato:", "17. november 2025 kl. 14:30 (EAT)"],
                    ["Emne:", "SV: SV: Henrik Nørgaard — udskrevet"],
                ],
                "Camilla,",
                "Henrik er udskrevet i dag og fortsætter til Nairobi for "
                "hjemrejse den 19. Jeg mødte ham før afgang fra Narok. "
                "Han nævnte myggenettet flere gange og vil \"nok klage\".",
                "Skal jeg dokumentere noget bestemt? Jeg har stadig mit "
                "logbog der noterer myggenettet på dag 3.",
                "/David",
                "<b>━━ E-MAIL 4 — svar ━━</b>",
                [
                    ["Fra:", "Camilla Westergaard"],
                    ["Til:", "David Karingu"],
                    ["Dato:", "17. november 2025 kl. 17:08"],
                    ["Emne:", "SV: opfølgning"],
                ],
                "David,",
                "<b>Slet logbog-noten om myggenettet.</b> Det er en intern "
                "operationsnote der ikke skal være tilgængelig hvis sagen "
                "indbringes for ankenævnet.",
                "/Camilla",
            ],
        },
        {
            "filnavn": "selskab-02-sundhedsinformation-officiel.pdf",
            "selskab": "SuperSafari A/S",
            "titel": "Forholdsregler ved safari-rejser",
            "undertitel": "Officielt informationsark · udsendt til alle gæster forud for afrejse",
            "indhold": [
                "<b>SuperSafari — Forholdsregler ved safari-rejser i Østafrika</b>",
                "Velkommen til din kommende safari! Dette ark indeholder "
                "praktisk information om forberedelse til rejsen. <b>Det er "
                "den rejsendes eget ansvar</b> at konsultere egen læge "
                "vedrørende vaccinationer og forholdsregler.",
                "<b>Vaccinationer</b>",
                "• Hepatitis A — anbefales",
                "• Hepatitis B — anbefales",
                "• Tyfus — anbefales ved længere ophold (>2 uger)",
                "• Gul feber — krav ved indrejse fra visse lande",
                "• Difteri/tetanus/polio — sørg for at boostere er opdaterede",
                "<b>Malaria</b>",
                "Maasai Mara og det meste af Kenya er klassificeret som "
                "<b>malaria-område</b> af Statens Serum Institut. "
                "Forebyggende medicin (malariaprofylakse) bør overvejes i "
                "samråd med din læge. Gængse muligheder er Malarone, "
                "Doxycyclin eller Lariam.",
                "Suppler altid med fysisk beskyttelse:",
                "• Brug DEET-baseret insektmiddel (minimum 30%, helst 50%)",
                "• Bær lange ærmer og bukser efter solnedgang",
                "• Sov under myggenet",
                "<b>SuperSafaris service</b>",
                "Vores lodges har myggenet som standard. Insektmiddel skal "
                "gæsten selv medbringe (kan købes i lufthavne eller "
                "specialforretninger). Vores rejseledere har grundlæggende "
                "førstehjælpskasse med, men ikke medicin.",
                "<b>Ved sygdom under rejsen</b>",
                "Kontakt straks din rejseleder. Vi sikrer transport til "
                "nærmeste hospital. Bemærk at lokal behandling kan være "
                "dyr — sørg for at rejseforsikringen dækker dette område. "
                "SuperSafari erstatter ikke lægebehandling.",
                "<b>Forsikring</b>",
                "<b>Det er krav</b>, at du har gyldig rejse- og "
                "sygdomsforsikring der dækker Østafrika, inkl. "
                "evakuering. Uden gyldig forsikring kan SuperSafari "
                "afvise at deltage i transport- og behandlingslogistik.",
                "<b>God rejse!</b>",
                "Med venlig hilsen, SuperSafari A/S",
                "<b>Intern note (ikke i kunde-PDF):</b> Dette ark sendes "
                "automatisk som vedhæftet PDF i bookingbekræftelsen, men "
                "er ikke en del af kontrakten — alene en information. "
                "Vores forsvar i sygdomssager hænger på § 19 i "
                "rejsebetingelserne.",
            ],
        },
        {
            "filnavn": "selskab-03-rejsebetingelser-uddrag.pdf",
            "selskab": "SuperSafari A/S",
            "titel": "SuperSafari Rejsebetingelser 2025 — § 18–20",
            "undertitel": "Bestemmelser om sundhedsmæssige forhold, sygdom og ansvar",
            "indhold": [
                "<b>§ 18. Sundhedsmæssige forhold</b>",
                "18.1 Det er den rejsendes eget ansvar at sikre, at "
                "vedkommende har et tilstrækkeligt helbred til at gennemføre "
                "rejsen. SuperSafari kan ikke holdes ansvarlig for forhold "
                "knyttet til den rejsendes fysiske eller psykiske helbred.",
                "18.2 Forebyggende vaccinationer og malariaprofylakse er "
                "den rejsendes eget ansvar. SuperSafari yder vejledning, "
                "men erstatter ikke konsultation hos egen læge.",
                "<b>§ 19. Sygdom under rejsen</b>",
                "19.1 SuperSafari er ikke ansvarlig for sygdom, der pådrages "
                "under rejsen, medmindre sygdommen utvivlsomt skyldes "
                "selskabets <b>grov uagtsomhed</b> eller <b>forsætlig "
                "tilsidesættelse</b> af pakkerejselovens bestemmelser om "
                "den rejsendes sikkerhed.",
                "19.2 SuperSafari yder praktisk bistand ved sygdom — "
                "transport til hospital, kontakt til den rejsendes "
                "forsikringsselskab, og logistisk hjælp. Lægebehandling "
                "samt medicinudgifter dækkes <b>aldrig</b> af SuperSafari "
                "og skal afregnes via den rejsendes rejseforsikring.",
                "19.3 Hvis sygdom medfører, at den rejsende ikke kan "
                "gennemføre rejsen, refunderes ikke den ikke-anvendte del "
                "af pakkeprisen, medmindre andet er aftalt ved "
                "afbestillingsforsikring.",
                "<b>§ 20. Force majeure og ekstraordinære omstændigheder</b>",
                "20.1 SuperSafari er fritaget for ansvar for forhold, der "
                "skyldes force majeure, herunder pandemi, krig, terror, "
                "strejker, og lokale myndighedsindgreb.",
                "20.2 Sygdom pådraget af den rejsende selv betragtes som "
                "force majeure-lignende omstændighed, jf. § 19.",
                "<b>Intern note vedr. tolkning af § 19 (jura-team, 2024):</b>",
                "\"§ 19.1's krav om grov uagtsomhed er bevidst sat højt for "
                "at minimere risiko. I praksis vil vi argumentere for, at "
                "selv forhold som defekte myggenet kun udløser kompensation "
                "hvis SuperSafari KENDTE til defekten og undlod at "
                "udbedre. Almindelig vedligeholdelse er underleverandørens "
                "ansvar (lodge), ikke SuperSafaris.\"",
            ],
        },
    ],

    "sag-04-eutripper": [
        {
            "filnavn": "selskab-01-intern-korrespondance.pdf",
            "selskab": "EUtripper ApS",
            "titel": "Korrespondance med Roma Tours s.r.l. + intern strategi",
            "undertitel": "Oktober 2025",
            "indhold": [
                "<b>━━ E-MAIL 1 — fra Roma Tours ━━</b>",
                [
                    ["Fra:", "Giulia Mariani <giulia@romatours.it>"],
                    ["Til:", "bookings@eutripper.dk"],
                    ["Dato:", "16. oktober 2025 kl. 19:47 (CET)"],
                    ["Emne:", "URGENT: cancellation for tours 17-18 October"],
                ],
                "Dear EUtripper team,",
                "I am extremely sorry to inform you on such short notice. "
                "Our company has been forced to cancel all guided tours "
                "scheduled for October 17 and 18 due to:",
                "(1) Loss of accreditation with Vatican Museums (administrative "
                "dispute, unresolved as of today)",
                "(2) Our senior guide Marco hospitalized this evening "
                "(non-COVID)",
                "(3) Our junior guide Sofia on family emergency leave since "
                "October 14",
                "We cannot fulfill the tours for the following EUtripper "
                "bookings tomorrow and Saturday:",
                "• EUT-ROM-4488 (Holm family, 4 pax)",
                "• EUT-ROM-4502 (Andersen couple)",
                "• EUT-ROM-4519 (Bertelsen group, 6 pax)",
                "We acknowledge full liability per our master agreement "
                "§ 7.2 — please send us an invoice for the affected services. "
                "We will refund or credit EUtripper at our standard rate "
                "(85 EUR per person per tour).",
                "Sincerely, Giulia Mariani · Operations Manager · Roma Tours s.r.l.",
                "<b>━━ E-MAIL 2 — intern beslutning EUtripper ━━</b>",
                [
                    ["Fra:", "Sara Lykke <sara.l@eutripper.dk>"],
                    ["Til:", "jonas.p@eutripper.dk"],
                    ["CC:", "ledelse@eutripper.dk"],
                    ["Dato:", "16. oktober 2025 kl. 21:30"],
                    ["Emne:", "VS: URGENT: cancellation Rom 17-18 — håndtering?"],
                ],
                "Jonas,",
                "Vi har et stort problem. Roma Tours aflyser alle vores "
                "tours i morgen og lørdag. <b>11 kunder</b> bliver berørt.",
                "Mulige tilgange:",
                "<b>(A) Refusion fra os direkte til kunder (1.700 kr. pr. "
                "pers. × 11 = 18.700 kr.).</b> Vi får tilsvarende fra Roma "
                "Tours over deres master-aftale (85 EUR × 11 = ca. 7.000 kr.) "
                "— men dække vores omkostninger fuldt ud kan vi <b>ikke</b>.",
                "<b>(B) Henvis kunder til at få refusion via Roma Tours direkte.</b> "
                "Vi tager ikke ansvar, sparer 11.700 kr. i tab — men kunderne "
                "vil have svært ved at få fat i Roma Tours på dansk og "
                "vil i praksis ende uden refusion.",
                "<b>(C) Henvis kunder til rejseforsikring.</b> Forsikringer "
                "dækker normalt IKKE aflyste arrangør-udflugter — det vil "
                "kunderne hurtigt finde ud af.",
                "Anbefaling: <b>(B)</b>. Vi tager juridisk risiko, men "
                "sandsynligvis vil maks. 2-3 kunder gå hele vejen til "
                "Pakkerejse-Ankenævnet, og selv hvis vi taber alle, er "
                "tabet mindre end fuld proaktiv refusion.",
                "/Sara, kundeserviceansvarlig",
                "<b>━━ E-MAIL 3 — godkendelse fra ledelse ━━</b>",
                [
                    ["Fra:", "Henrik Bager <henrik.b@eutripper.dk>"],
                    ["Til:", "Sara Lykke · Jonas Petersen"],
                    ["Dato:", "16. oktober 2025 kl. 22:01"],
                    ["Emne:", "SV: VS: URGENT"],
                ],
                "Hej,",
                "Godkender (B). Vi sender SMS/email til kunder NU med "
                "henvisning til Roma Tours og rejseforsikring. Vi indrømmer "
                "ikke ansvar. Hvis nogen klager senere og truer med "
                "ankenævn: standard-tilbud 1.000-1.500 kr.",
                "Husk at få Giulia til at IKKE bekræfte master-aftale § 7.2 "
                "skriftligt overfor kunder. Den klausul er vores akilleshæl.",
                "/Henrik, direktør",
                "<b>━━ E-MAIL 4 — kunde-svar til Holm ━━</b>",
                [
                    ["Fra:", "Jonas Petersen <kundeservice@eutripper.dk>"],
                    ["Til:", "camilla.holm@eksempelmail.dk"],
                    ["Dato:", "16. oktober 2025 kl. 22:15"],
                    ["Emne:", "Vedr. booking EUT-ROM-4488 — udflugter aflyst"],
                ],
                "(— se klagers bilag 2 for fuld e-mail —)",
                "Bemærk: \"<b>udflugter er leveret af tredjepart</b>\" er "
                "den bevidst valgte formulering. Pakkerejseloven § 2 gør "
                "EUtripper til den juridisk ansvarlige arrangør, men "
                "formuleringen skal afskrække kunder fra at forfølge sagen.",
            ],
        },
        {
            "filnavn": "selskab-02-rammeaftale-roma-tours.pdf",
            "selskab": "EUtripper ApS",
            "titel": "Rammeaftale med Roma Tours s.r.l. — uddrag",
            "undertitel": "Master Service Agreement 2024–2027 · § 7",
            "indhold": [
                "<b>Master Service Agreement</b>",
                "Mellem EUtripper ApS (\"EUtripper\") og Roma Tours s.r.l. "
                "(\"Provider\"), indgået 1. marts 2024.",
                "<b>§ 5. Leveringsforpligtelse</b>",
                "5.1 Provider leverer guidede udflugter i Rom og omegn i "
                "henhold til EUtrippers produktbeskrivelser. Tidspunkter, "
                "rutevalg og guide-tildeling er Providers ansvar inden for "
                "rammerne af EUtrippers booking.",
                "<b>§ 7. Aflysning og kompensation</b>",
                "7.1 Provider er forpligtet til at gennemføre alle bekræftede "
                "udflugter, medmindre force majeure (jf. § 11) gør sig "
                "gældende.",
                "7.2 <b>Ved aflysning eller manglende levering, der ikke "
                "skyldes force majeure, hæfter Provider over for EUtripper "
                "for det fulde tab</b>, herunder:",
                "(a) Den aftalte udflugts-pris (85 EUR pr. person)",
                "(b) Rimelige omkostninger til alternative arrangementer",
                "(c) Kompensation som EUtripper måtte betale til "
                "slutkunder, op til 200 EUR pr. berørt person",
                "7.3 Krav efter § 7.2 skal fremsættes inden for 30 dage "
                "efter aflysningen.",
                "<b>§ 11. Force majeure</b>",
                "11.1 Force majeure omfatter naturkatastrofer, terror, "
                "regeringsindgreb, pandemiforhold og lignende ekstraordinære "
                "forhold uden for Providers kontrol. <b>Administrative "
                "tvister, personalemangel og almindelig sygdom er ikke "
                "force majeure.</b>",
                "<b>Intern note fra EUtripper jura (16.10.2025):</b>",
                "\"Roma Tours' aflysning skyldes (1) administrativ tvist "
                "med Vatikanet og (2) personalemangel. <b>Ingen af disse "
                "er force majeure efter § 11.1.</b> Roma Tours har "
                "fuldt ansvar efter § 7.2 — inkl. kompensation til "
                "slutkunder op til 200 EUR per pers.",
                "Vores håndtering bør være: kræv refusion fra Roma Tours "
                "for FULDT tab, og send refusion videre til kunderne. "
                "Den valgte strategi (henvis kunder til selv at kontakte "
                "Roma Tours) er kommercielt rationel men juridisk svag.\"",
            ],
        },
        {
            "filnavn": "selskab-03-almindelige-betingelser.pdf",
            "selskab": "EUtripper ApS",
            "titel": "EUtrippers Almindelige Betingelser — uddrag",
            "undertitel": "Som offentliggjort på eutripper.dk · juni 2025",
            "indhold": [
                "<b>§ 8. Underleverandører og lokale partnere</b>",
                "8.1 EUtripper kan benytte underleverandører til levering "
                "af enkeltdele af pakkerejsen, herunder transport, hotel, "
                "udflugter og guideservice.",
                "8.2 <b>EUtripper er den juridisk ansvarlige arrangør</b> "
                "for pakkerejsen som helhed i overensstemmelse med "
                "pakkerejseloven § 2. Den rejsende kan rette ethvert krav "
                "mod EUtripper, uanset hvem der faktisk har leveret "
                "ydelsen.",
                "8.3 EUtripper forbeholder sig retten til at foretage "
                "regreskrav over for underleverandører efter de mellem "
                "EUtripper og underleverandøren gældende kontrakter.",
                "<b>§ 12. Ændringer i rejseprogrammet</b>",
                "12.1 EUtripper kan af driftsmæssige årsager foretage "
                "mindre ændringer i programmet uden forudgående varsel.",
                "12.2 Ved væsentlige ændringer (aflysning af kerneydelser, "
                "hotelskift af lavere kategori m.v.) informeres den "
                "rejsende hurtigst muligt. Den rejsende kan vælge mellem:",
                "(a) At acceptere ændringen",
                "(b) At få tilbudt alternativ rejse af tilsvarende værdi",
                "(c) Refusion af den manglende ydelses værdi",
                "<b>§ 14. Reklamationer</b>",
                "14.1 Reklamationer skal fremsættes hurtigst muligt over "
                "for EUtripper eller den lokale repræsentant.",
                "14.2 Reklamationer efter hjemkomst skal være EUtripper "
                "i hænde inden for 14 dage efter rejsens afslutning.",
                "14.3 Hvis EUtripper og kunden ikke kan opnå enighed, kan "
                "sagen indbringes for Pakkerejse-Ankenævnet, "
                "Røjelskær 11, 2840 Holte.",
                "<b>Intern note (ikke i kunde-PDF):</b> § 8.2 er svær at "
                "tale sig fra — pakkerejselovens § 2 er absolut. Vores "
                "førstevalgs-strategi i klagesager er derfor at få "
                "kunden til at acceptere lavt forlig (ofte 30-50% af "
                "deres krav), inden de finder ud af § 8.2's rækkevidde.",
            ],
        },
    ],

    "sag-05-sportstours": [
        {
            "filnavn": "selskab-01-intern-korrespondance.pdf",
            "selskab": "SportsTours International ApS",
            "titel": "Korrespondance med billetbroker + intern panik",
            "undertitel": "Marts 2026",
            "indhold": [
                "<b>━━ E-MAIL 1 — fra broker ━━</b>",
                [
                    ["Fra:", "James Whitlock <j.whitlock@premier-hospitality.uk>"],
                    ["Til:", "tickets@sportstours.dk"],
                    ["Dato:", "5. februar 2026 kl. 11:23 (GMT)"],
                    ["Emne:", "Liverpool vs Arsenal 9 March — 6 tickets confirmed"],
                ],
                "Hi Thomas,",
                "Confirming 6 tickets for Liverpool FC vs Arsenal on "
                "March 9, 2026 (17:30 kick-off):",
                "• Section: Anfield Road End, Block 124, Row 31",
                "• Seats: 14, 15, 16, 17, 18, 19",
                "• Total: GBP 2,640 (£440 per ticket)",
                "Payment due in 7 days. Tickets will be issued electronically "
                "3 days before match. Note: as discussed, these are sourced "
                "via our season-ticket-holder network — official LFC channels "
                "would have been GBP 89 face value but completely unavailable.",
                "Best, James · Premier Hospitality UK Ltd",
                "<b>━━ E-MAIL 2 — intern bekymring ━━</b>",
                [
                    ["Fra:", "Mikkel Damsgaard <mikkel.d@sportstours.dk>"],
                    ["Til:", "Thomas Berg <thomas.b@sportstours.dk>"],
                    ["Dato:", "5. februar 2026 kl. 14:08"],
                    ["Emne:", "Premier Hospitality — er det stadig OK?"],
                ],
                "Thomas,",
                "Jeg ser at vi bruger Premier Hospitality igen til "
                "Anfield-pakken. Sidste år havde vi 4 tilfælde hvor "
                "billetter blev afvist ved indgangen. Skal vi finde "
                "alternative leverandører?",
                "Jeg ved at LFC har strammet meget op om uautoriseret "
                "videresalg. Ekstrabillet-handler bliver lukket ned. "
                "Premier League § Schedule 13 forbyder netop dette.",
                "/Mikkel",
                "<b>━━ E-MAIL 3 — svar ━━</b>",
                [
                    ["Fra:", "Thomas Berg"],
                    ["Til:", "Mikkel Damsgaard"],
                    ["Dato:", "5. februar 2026 kl. 16:42"],
                    ["Emne:", "SV: Premier Hospitality"],
                ],
                "Mikkel,",
                "Jeg ved det. Men:",
                "(1) Vi har 6 solgte pakker til denne kamp. Aflysning nu "
                "= 75.000 kr. tab + dårlig PR.",
                "(2) Vores margin er 65% på Anfield-pakker. Selv hvis "
                "1 ud af 6 grupper bliver afvist og kræver refusion, "
                "er det stadig profitabelt.",
                "(3) Premier Hospitality er den eneste leverandør der "
                "kan levere 6 sæder sammen til en udsolgt kamp.",
                "Vi kører videre. Hvis nogen klager: tilbyd 5.000 kr. for "
                "hele gruppen og henvis til vores ansvarsbegrænsning "
                "§ 11.4 om \"event-relaterede uregelmæssigheder\".",
                "Husk: <b>aldrig</b> nævne Premier Hospitality skriftligt "
                "overfor kunder. Hold det vage.",
                "/Thomas, indkøbsansvarlig",
                "<b>━━ E-MAIL 4 — efter klagen ━━</b>",
                [
                    ["Fra:", "Lone Bay <lone.b@sportstours.dk>"],
                    ["Til:", "Thomas Berg · Mikkel Damsgaard"],
                    ["Dato:", "11. marts 2026 kl. 09:30"],
                    ["Emne:", "Jens Petersen-sagen — Anfield 9/3 — KRISE"],
                ],
                "Hej,",
                "Som I så i weekenden: alle 6 Petersen-billetter blev "
                "afvist på Anfield. Jeg har lige fået første klagebrev "
                "(\"forlange fuld refusion + skadeserstatning\").",
                "Spørgsmål: hvad er strategien? Pre-emptive forlig på "
                "10.000 kr. for at lukke det hurtigt? Eller hold linjen "
                "om \"fejl hos Liverpool FC scanningssystem\"?",
                "Bemærk: hvis sagen kommer til Pakkerejse-Ankenævnet, og "
                "LFC bekræfter at vores billetter var ulovligt videresolgt, "
                "kan det blive en SAGSNUMMER-ÆNDRENDE præcedens for hele "
                "vores forretningsmodel.",
                "/Lone, jura-ansvarlig",
            ],
        },
        {
            "filnavn": "selskab-02-faktura-fra-broker.pdf",
            "selskab": "SportsTours International ApS",
            "titel": "Faktura nr. PH-2026-0188 fra Premier Hospitality UK",
            "undertitel": "Modtaget 8. februar 2026 · betalt 12. februar 2026",
            "indhold": [
                "<b>Premier Hospitality UK Limited</b>",
                "Suite 14, 7 Brick Lane · London E1 6PR · United Kingdom",
                "VAT GB 287-4001-22 · Company No. 09887401",
                [
                    ["Faktura nr.:", "PH-2026-0188"],
                    ["Dato:", "8. februar 2026"],
                    ["Forfald:", "15. februar 2026"],
                    ["Til:", "SportsTours International ApS"],
                    ["Att:", "Thomas Berg"],
                ],
                "<b>Specifikation</b>",
                [
                    ["Event:", "Liverpool FC vs Arsenal · 09.03.2026 · Anfield"],
                    ["Section:", "Anfield Road End, Block 124, Row 31"],
                    ["Sæder:", "14, 15, 16, 17, 18, 19 (6 stk.)"],
                    ["Pris pr. billet:", "GBP 440,00"],
                    ["Subtotal:", "GBP 2.640,00"],
                    ["Service fee (administration):", "GBP 180,00"],
                    ["Total ex VAT:", "GBP 2.820,00"],
                    ["VAT 0% (reverse charge, B2B):", "GBP 0,00"],
                    ["<b>Total:</b>", "<b>GBP 2.820,00</b> (DKK 24.580,00)"],
                ],
                "<b>Betalingsoplysninger</b>",
                "Barclays Bank · Sort code 20-26-31 · Account 87401922",
                "IBAN: GB44 BARC 2026 3187 4019 22",
                "<b>Vilkår</b>",
                "(1) Tickets are sourced via Premier Hospitality's "
                "season-ticket-holder network. Final issue 3 days before event.",
                "(2) Premier Hospitality acts as intermediary only — "
                "actual ticket terms are determined by Liverpool FC.",
                "(3) <b>Refunds are NOT available</b> for tickets denied "
                "entry at venue.",
                "(4) Premier Hospitality does not warrant that tickets are "
                "issued through official channels. Buyer accepts risk of "
                "ticket invalidation by event organizer.",
                "<b>Intern note (SportsTours):</b> Vilkår 2 og 4 er den "
                "klare red flag. Vores ansvar overfor slutkunden kan ikke "
                "afvises ved disse vilkår — pakkerejseloven § 2 gør os "
                "fuldt ansvarlige for pakkens levering.",
            ],
        },
        {
            "filnavn": "selskab-03-ansvarsbegraensning.pdf",
            "selskab": "SportsTours International ApS",
            "titel": "Rejsebetingelser — § 11 om sportsarrangementer",
            "undertitel": "Som offentliggjort på sportstours.dk",
            "indhold": [
                "<b>§ 11. Sportsarrangementer og event-pakker</b>",
                "11.1 SportsTours International tilbyder pakkerejser der "
                "inkluderer adgang til sportsbegivenheder. Adgang til "
                "selve begivenheden afhænger af arrangørens "
                "(klub/forbund) regler.",
                "11.2 <b>Billetter</b> til sportsbegivenheder leveres "
                "typisk gennem partnerleverandører. SportsTours garanterer "
                "ikke, at billetter er udstedt direkte af eventarrangøren.",
                "11.3 Den rejsende accepterer ved booking, at "
                "billetlevering kan ske kort før eventet (op til 24 timer "
                "før kick-off).",
                "11.4 <b>Event-relaterede uregelmæssigheder</b> — herunder "
                "men ikke begrænset til billet-validering, sikkerhedstjek, "
                "venue-restriktioner og arrangørens regler om "
                "tilskuersammensætning — er <b>ikke SportsTours' ansvar</b>. "
                "I sådanne tilfælde kan SportsTours efter konkret vurdering "
                "tilbyde delvis refusion eller værdibevis.",
                "11.5 Aflyste eller udsatte sportsbegivenheder håndteres "
                "således:",
                "(a) Aflysning: billet-værdien refunderes; resten af "
                "pakken (fly, hotel) leveres som planlagt.",
                "(b) Udsættelse: SportsTours forsøger at sikre adgang til "
                "den udsatte begivenhed.",
                "11.6 Den rejsende er <b>selv ansvarlig</b> for at overholde "
                "billet-betingelser, herunder forbud mod videresalg, "
                "krav om billet-indehaverens identifikation m.v.",
                "<b>Intern note (SportsTours jura):</b>",
                "\"§ 11.4 er vores stærkeste forsvarspunkt i klagesager. "
                "Den er bevidst formuleret bredt for at kunne dække "
                "scenarier som ugyldige billetter, ulovligt videresalg "
                "osv. — men <b>denne formulering kan IKKE tilsidesætte "
                "pakkerejselovens § 2</b>, som gør SportsTours til den "
                "ansvarlige arrangør. I sager der når til Pakkerejse-"
                "Ankenævnet er § 11.4 typisk underkendt.\"",
                "\"Vores tab-prevention er at få kunder til at forlige sig "
                "inden de finder ud af dette.\"",
            ],
        },
    ],
}


SAGER = [
    (SAG_1, SAG_1_BILAG),
    (SAG_2, SAG_2_BILAG),
    (SAG_3, SAG_3_BILAG),
    (SAG_4, SAG_4_BILAG),
    (SAG_5, SAG_5_BILAG),
]


def main():
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    total_filer = 0
    for sag, bilag in SAGER:
        sag_dir = os.path.join(OUTPUT_DIR, sag["mappe"])
        os.makedirs(sag_dir, exist_ok=True)

        # Berig sag-dict med stævnings-metadata (in-place; OK, scriptet kører engangs)
        sag.update(STAEVNING_META[sag["mappe"]])

        # 1. Stævning fra nævnet (cover-letter til indklagede)
        staevning_path = os.path.join(sag_dir, "00-staevning-fra-naevnet.pdf")
        _byg_staevning(staevning_path, sag)
        total_filer += 1
        print(f"  ✓ {sag['mappe']}/00-staevning-fra-naevnet.pdf")

        # 2. Klageskema
        klageskema_path = os.path.join(sag_dir, "klageskema.pdf")
        _byg_klageskema(klageskema_path, sag)
        total_filer += 1
        print(f"  ✓ {sag['mappe']}/klageskema.pdf")

        # 3. Klagers bilag
        for b in bilag:
            bilag_path = os.path.join(sag_dir, b["filnavn"])
            _byg_bilag(
                bilag_path,
                b["titel"],
                b["undertitel"],
                b["indhold"],
                b["bilag_nr"],
            )
            total_filer += 1
            print(f"  ✓ {sag['mappe']}/{b['filnavn']}")

        # 4. Selskabsinterne dokumenter
        selskab_docs = SELSKAB_DOCS.get(sag["mappe"], [])
        for s_doc in selskab_docs:
            s_path = os.path.join(sag_dir, s_doc["filnavn"])
            _byg_selskabsdokument(
                s_path,
                s_doc["selskab"],
                s_doc["titel"],
                s_doc["undertitel"],
                s_doc["indhold"],
            )
            total_filer += 1
            print(f"  ✓ {sag['mappe']}/{s_doc['filnavn']}")

    # Manifest — frontenden bruger det til at vise download-links grupperet pr. kilde
    manifest_path = os.path.join(OUTPUT_DIR, "manifest.json")
    import json
    manifest = []
    for sag, bilag in SAGER:
        sag_dir_rel = sag["mappe"]
        selskab_docs = SELSKAB_DOCS.get(sag["mappe"], [])
        filer = (
            [{"navn": "00-staevning-fra-naevnet.pdf",
              "titel": "Stævning fra nævnet",
              "kilde": "naevnet"}]
            + [{"navn": "klageskema.pdf",
                "titel": "Klageskema",
                "kilde": "naevnet"}]
            + [{"navn": b["filnavn"],
                "titel": b["titel"],
                "kilde": "klager"} for b in bilag]
            + [{"navn": d["filnavn"],
                "titel": d["titel"],
                "kilde": "selskab"} for d in selskab_docs]
        )
        sag_entry = {
            "mappe": sag_dir_rel,
            "sagsnr": sag["sagsnr"],
            "indklagede": sag["indklagede"].split(",")[0],
            "klager": sag["klager_navn"],
            "destination": sag["destination"],
            "rejseperiode": sag["rejseperiode"],
            "antal_rejsende": sag["antal_rejsende"],
            "rejse_pris": sag["rejse_pris"],
            "filer": filer,
        }
        manifest.append(sag_entry)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"  ✓ manifest.json")

    print()
    print(f"=== Færdig: {total_filer} PDF'er + manifest oprettet ===")
    print(f"Lokation: {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
