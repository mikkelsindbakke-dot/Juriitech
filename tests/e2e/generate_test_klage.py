"""
Genererer en realistisk test-klage som PDF til E2E-smoke-testen.

Output: tests/e2e/fixtures/test_klage.pdf

Klagen er fiktiv men realistisk struktureret som et Pakkerejse-Ankenævn-
klageskema, så PAX' AI-pipeline kan ekstrahere klagepunkter, udlede
sandsynligheder og generere et svarbrev. Brugen er REN test —
indeholder ingen rigtige persondata.

Genereres deterministisk så testen er reproducerbar pr. kørsel.
Indholdet er korte men dækker de typiske klage-temaer:
  - Manglende rengøring i hotel
  - Pool ikke tilgængelig
  - Forsinkelse på udrejse
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
)


_OUTPUT = (
    Path(__file__).parent / "fixtures" / "test_klage.pdf"
)


def _byg_klage_indhold():
    """
    Returnér listen af Paragraph-objekter der udgør klage-PDF'en.

    Strukturen følger et reelt Pakkerejse-Ankenævn-klageskema med
    rubrikker for sagsnummer, klagers navn, rejseinfo og selve klagen.
    """
    styles = getSampleStyleSheet()
    h_style = styles["Heading2"]
    body_style = styles["BodyText"]
    body_style.spaceAfter = 8

    sub_style = ParagraphStyle(
        "Sub",
        parent=body_style,
        fontSize=11,
        leading=14,
        spaceAfter=6,
    )

    indhold = []
    indhold.append(Paragraph("PAKKEREJSE-ANKENÆVNET", styles["Title"]))
    indhold.append(Paragraph(
        "Klageskema — fiktiv testsag (E2E smoke-test)",
        styles["Italic"],
    ))
    indhold.append(Spacer(1, 0.5 * cm))

    indhold.append(Paragraph("Sagsnummer: 26-999-9999999", sub_style))
    indhold.append(Paragraph(
        "Indklagede: TUI Danmark A/S",
        sub_style,
    ))
    indhold.append(Spacer(1, 0.3 * cm))

    indhold.append(Paragraph("Klagers oplysninger", h_style))
    indhold.append(Paragraph("Navn: Test Testesen", sub_style))
    indhold.append(Paragraph(
        "Adresse: Teststraße 1, 9999 Testby",
        sub_style,
    ))
    indhold.append(Paragraph(
        "Email: testesen.test@example.invalid",
        sub_style,
    ))
    indhold.append(Paragraph("Telefon: +45 99 99 99 99", sub_style))
    indhold.append(Spacer(1, 0.3 * cm))

    indhold.append(Paragraph("Rejseoplysninger", h_style))
    indhold.append(Paragraph(
        "Bestillingsnummer: 99999999",
        sub_style,
    ))
    indhold.append(Paragraph(
        "Rejseperiode: 4. februar 2026 til 11. februar 2026 (7 nætter)",
        sub_style,
    ))
    indhold.append(Paragraph("Destination: Gran Canaria", sub_style))
    indhold.append(Paragraph(
        "Hotel: Apartamentos Testbeach, 3 stjerner",
        sub_style,
    ))
    indhold.append(Paragraph("Antal rejsende: 2 voksne", sub_style))
    indhold.append(Paragraph(
        "Samlet pris: 14.999 kr.",
        sub_style,
    ))
    indhold.append(Spacer(1, 0.4 * cm))

    indhold.append(Paragraph("Klagens indhold", h_style))
    indhold.append(Paragraph(
        "Vi klager over flere alvorlige mangler ved vores ophold på "
        "Apartamentos Testbeach på Gran Canaria i perioden 4.-11. "
        "februar 2026:",
        body_style,
    ))
    indhold.append(Paragraph(
        "<b>1. Manglende rengøring.</b> Lejligheden var ikke ordentligt "
        "rengjort ved ankomst. Badeværelset havde tydelige spor af "
        "tidligere gæster, gulvet var støvet, og der var fedtspor i "
        "køkkenet. Vi tog billeder og kontaktede receptionen samme dag "
        "(4. februar). Trods flere henvendelser blev der ikke gjort "
        "rent på et tilfredsstillende niveau før den 7. februar — det "
        "vil sige 3 nætter ud af 7.",
        body_style,
    ))
    indhold.append(Paragraph(
        "<b>2. Pool ikke tilgængelig.</b> Hotellets eneste pool var "
        "lukket hele opholdet pga. reparation. Vi var ikke informeret "
        "om dette ved booking, og pool er angivet som facilitet i "
        "katalogbeskrivelsen. Vi havde booket netop dette hotel pga. "
        "poolen.",
        body_style,
    ))
    indhold.append(Paragraph(
        "<b>3. Forsinkelse på udrejse.</b> Vores fly fra København "
        "den 4. februar var forsinket med 4 timer og 20 minutter. "
        "Forsinkelsen blev først meddelt ved check-in. Det betød at "
        "vi nåede frem til hotellet kl. 02 om natten i stedet for "
        "som planlagt kl. 21.",
        body_style,
    ))
    indhold.append(Spacer(1, 0.3 * cm))

    indhold.append(Paragraph("Krav", h_style))
    indhold.append(Paragraph(
        "Vi kræver et forholdsmæssigt afslag på 5.000 kr. for de "
        "manglende ydelser samt 1.000 kr. som godtgørelse for "
        "forsinkelsen — i alt 6.000 kr.",
        body_style,
    ))
    indhold.append(Spacer(1, 0.3 * cm))

    indhold.append(Paragraph("Tidligere kontakt", h_style))
    indhold.append(Paragraph(
        "Vi kontaktede TUI's kundeservice den 12. februar 2026. "
        "TUI tilbød 1.500 kr. som kulancekompensation. Vi mener "
        "ikke det er tilstrækkeligt og indbringer derfor sagen "
        "for Pakkerejse-Ankenævnet.",
        body_style,
    ))

    return indhold


def main():
    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(_OUTPUT),
        pagesize=A4,
        leftMargin=2.5 * cm,
        rightMargin=2.5 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    doc.build(_byg_klage_indhold())
    print(f"OK: test-klage genereret → {_OUTPUT}")


if __name__ == "__main__":
    main()
