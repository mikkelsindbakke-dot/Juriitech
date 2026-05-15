"""
generer_norsk_test_sag.py

Genererer ÉN fiktiv norsk testsag til test af norsk PAX (FjordTravel AS).
Bygger PDF-filer i pax-next/public/test-sager/sag-06-fjordtravel-norge/
og merger entry ind i den eksisterende manifest.json.

Selvstændigt: rør IKKE de 5 danske test-sager. Idempotent: kan køres
igen — bygger filer fra bunden og opdaterer manifest-entry uden duplikater.

KØRSEL:
    python3 scripts/generer_norsk_test_sag.py

OUTPUT:
    pax-next/public/test-sager/sag-06-fjordtravel-norge/
        00-staevning-fra-nemnda.pdf
        klageskema.pdf
        bilag-01-bookingbekreftelse.pdf
        bilag-02-fotos-fra-hotellet.pdf
        bilag-03-korrespondanse.pdf
        selskab-01-intern-korrespondanse.pdf
        selskab-02-rammeavtale-hotell.pdf
        selskab-03-reisebetingelser-uddrag.pdf

    pax-next/public/test-sager/manifest.json (opdateret med norsk entry)

Scenario: Familie Hansen bestilte 7-dages pakkereise til Kreta hos
FjordTravel AS. Hotel Sirenes Beach Resort 4★ viste sig at være under
renovation — byggestøy 07-19, basseng stengt, restaurant med begrenset
meny. Klagere krev prisavslag + erstatning. Norsk pakkereiselov §§ 27,
31, 32 er relevante.
"""

import json
import os
import shutil
import sys

ROD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROD, "scripts"))

# Genbrug PDF-helpers fra det danske script — styles + info-tabel er
# sprog-agnostic og produktklare. Vi overskriver kun de funktioner hvor
# hardcoded dansk tekst optræder.
from generer_test_sager import (  # noqa: E402
    _styles,
    _info_tabel,
)
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

OUTPUT_DIR = os.path.join(ROD, "pax-next", "public", "test-sager")
SAG_MAPPE = "sag-06-fjordtravel-norge"
SAG_DIR = os.path.join(OUTPUT_DIR, SAG_MAPPE)
MANIFEST_PATH = os.path.join(OUTPUT_DIR, "manifest.json")


# ─────────────────────────────────────────────────────────────────
# SAG-DATA — Familie Hansen mod FjordTravel AS
# ─────────────────────────────────────────────────────────────────
SAG = {
    "mappe": SAG_MAPPE,
    "sagsnr": "2026-00892",
    "modtaget_dato": "14. mai 2026",
    "sagsbehandler_initialer": "MTH",
    "sagsbehandler_navn": "Mari Tordis Halvorsen",
    "indklagede": "FjordTravel AS",
    "indklagede_adresse": "Karl Johans gate 22, 0159 Oslo",
    "klager_navn": "Lars og Ingrid Hansen",
    "klager_adresse": "Bygdøy Allé 21, 0262 Oslo",
    "klager_email": "lars.hansen@email.no",
    "klager_tlf": "+47 91 23 45 67",
    "destination": "Kreta, Hellas — Hotel Sirenes Beach Resort 4★, Stalida",
    "rejseperiode": "6. april 2026 – 13. april 2026 (7 netter)",
    "antal_rejsende": "2 voksne + 2 barn (alder 8 og 11)",
    "rejse_pris": "38.400 NOK samlet",
    "bookingref": "FT-26-08423",
    "klagepunkter": (
        "Vi bestilte den 14. januar 2026 en familieferie til Kreta hos "
        "FjordTravel AS. Hotellet ble markedsført som «Hotel Sirenes Beach "
        "Resort 4★ — nyrenovert anlegg med stor basseng-park, à la carte-"
        "restaurant og barnetilbud». Den faktiske opplevelsen var radikalt "
        "annerledes.\n\n"
        "Ved ankomst søndag 6. april 2026 viste det seg at hotellet var "
        "under omfattende renovation. Hele den ene fløyen var innhyllet i "
        "stillas, og deler av hovedbygningen var avstengt med presenninger. "
        "Allerede første morgen, kl. 07:00, begynte byggestøyen — boremaskiner, "
        "tunge hammere og slipemaskiner — og fortsatte uavbrutt til kl. 19:00 "
        "hver eneste dag, søndag inkludert.\n\n"
        "Bassenget, som var et hovedargument for valget av hotellet (særlig "
        "for våre barn på 8 og 11 år), var fullstendig stengt i hele "
        "oppholdsperioden. Det stod skilt om «teknisk vedlikehold», men "
        "ifølge resepsjonen var årsaken renoveringen.\n\n"
        "À la carte-restauranten var lukket alle kveldene. I stedet ble vi "
        "henvist til et midlertidig buffet-telt med svært begrenset utvalg — "
        "for det meste pasta, ris og brød. Det ble ikke servert ferske grønnsaker "
        "eller fisk i hele perioden.\n\n"
        "Vi fikk INGEN informasjon om disse forholdene før avreise. "
        "Hverken bookingsystemet, bekreftelsesmailen 14. januar 2026, eller "
        "siste «klar for avreise»-mail 4. april 2026 nevnte noe om at "
        "hotellet skulle være under renovation."
    ),
    "paastand": (
        "Klagerne krever et prisavslag på 50 % av reisens pris, samt "
        "erstatning for tapt ferieverdi for begge barn. Samlet krav: "
        "<b>22.500 NOK</b> (19.200 NOK i prisavslag + 3.300 NOK i "
        "erstatning for barnetilbud som ikke ble levert).\n\n"
        "Subsidiært kreves prisavslag etter rettens skjønn, jf. "
        "pakkereiseloven § 31, samt erstatning etter § 32 for mangler "
        "som arrangøren burde ha opplyst om."
    ),
    "tidligere_korrespondance": (
        "Klagerne kontaktet FjordTravels reisedeleder på destinasjonen "
        "allerede 7. april (dag 2 av oppholdet). Reisedeleren henviste til "
        "hovedkontoret i Oslo. Klagerne sendte deretter en skriftlig "
        "klage 14. april 2026 (umiddelbart etter hjemkomst) med krav om "
        "kompensasjon. FjordTravel besvarte 28. april med et tilbud om "
        "et verdibevis på 4.000 NOK til fremtidig reise — uten medhold i "
        "selve klagens innhold. Klagerne fant dette utilstrekkelig og "
        "innga klage til Pakkereisenemnda 12. mai 2026."
    ),
    # Stævnings-metadata
    "staevning_resume": (
        "Klagen gjelder mangler ved et 4-stjerners hotell på Kreta som "
        "etter klagernes opplysninger var under omfattende renovation "
        "i hele oppholdsperioden 6.–13. april 2026. Byggestøy fra "
        "kl. 07:00–19:00, fullstendig stengt basseng, samt nedlagt "
        "à la carte-restaurant. Klagerne fikk ingen forhåndsvarsel om "
        "disse forholdene før avreise."
    ),
    "staevning_paastand_kort": (
        "Prisavslag 50 % (19.200 NOK) + erstatning 3.300 NOK = "
        "samlet 22.500 NOK. Subsidiært prisavslag etter "
        "pakkereiseloven § 31 og erstatning etter § 32."
    ),
}


# Klagers bilag (3 stk)
BILAG = [
    {
        "filnavn": "bilag-01-bookingbekreftelse.pdf",
        "bilag_nr": 1,
        "titel": "Bookingbekreftelse og hotellbeskrivelse",
        "undertitel": "Bekreftelsesmail fra FjordTravel AS, 14. januar 2026",
        "indhold": [
            "<b>FjordTravel AS — Bookingbekreftelse</b>",
            [
                ["Bookingreferanse:", "FT-26-08423"],
                ["Bestillingsdato:", "14. januar 2026"],
                ["Hovedreisende:", "Lars Hansen"],
                ["Antall reisende:", "2 voksne + 2 barn (8 og 11 år)"],
                ["Destinasjon:", "Stalida, Kreta — Hellas"],
                ["Reiseperiode:", "6. april 2026 – 13. april 2026 (7 netter)"],
                ["Hotell:", "Hotel Sirenes Beach Resort 4★"],
                ["Romtype:", "Familierom med havutsikt, halvpensjon"],
                ["Fly:", "Norwegian DY1872 OSL–HER / DY1873 HER–OSL"],
                ["Total pris:", "NOK 38.400 (inkl. flyseter, transfer, "
                 "halvpensjon)"],
            ],
            "<b>Beskrivelse av hotellet (fra FjordTravel.no — 14. januar 2026)</b>",
            "«Hotel Sirenes Beach Resort er et nyrenovert 4-stjerners "
            "anlegg beliggende direkte ved Stalidas sandstrand, kun "
            "300 meter fra strandpromenaden. Hotellet tilbyr stor "
            "basseng-park med separat barnebasseng, à la carte-"
            "restaurant med mediterransk og internasjonal meny, "
            "samt et eget barnetilbud (Mini Club) med daglige "
            "aktiviteter for barn 4–12 år. Perfekt for familieferier.»",
            "<b>Halvpensjon inkluderer</b>",
            "Frokostbuffet kl. 07:00–10:00 og 3-retters middag i "
            "à la carte-restauranten kl. 19:00–22:00. Drikke til "
            "maten er ikke inkludert.",
            "<b>Bekreftelse</b>",
            "Vi gleder oss til å ønske dere velkommen. Detaljert "
            "reiseinformasjon kommer i en separat mail ca. 7 dager "
            "før avreise.",
            "Med vennlig hilsen<br/>FjordTravel AS<br/>"
            "Kundeservice — bookingteam Hellas",
        ],
    },
    {
        "filnavn": "bilag-02-fotos-fra-hotellet.pdf",
        "bilag_nr": 2,
        "titel": "Foto-dokumentasjon og dagbok fra oppholdet",
        "undertitel": "Tatt av familien Hansen 6.–13. april 2026",
        "indhold": [
            "<b>Bilde 1 — Hovedinngang, 6. april 2026 kl. 16:42</b>",
            "[FIKTIVT BILDE — beskrivelse]: Hovedinngangen er delvis "
            "tildekket av byggestillas. Et stort presenning-skilt på "
            "venstre side med teksten «UNDER RENOVATION — PARDON THE "
            "DUST». Tre arbeidere i orange refleksvester foran "
            "inngangsdøren.",
            "<b>Bilde 2 — Bassengområdet, 7. april 2026 kl. 09:15</b>",
            "[FIKTIVT BILDE — beskrivelse]: Hovedbassenget tomt for "
            "vann, omkring 60–70 % nedtappet, fliser i ferd med å "
            "skiftes. Barnebassenget også tomt, avsperret med rødt "
            "plastbånd. Skilt: «Pool closed — technical maintenance».",
            "<b>Bilde 3 — Buffet-teltet, 8. april 2026 kl. 19:30</b>",
            "[FIKTIVT BILDE — beskrivelse]: Et stort hvitt telt med "
            "to lange bord. Maten består av tre store former med "
            "pasta, ris, hvitt brød, og noen tørre salater. Ingen "
            "ferske grønnsaker, ingen fisk, ingen frukt synlig.",
            "<b>Bilde 4 — À la carte-restauranten, 9. april 2026 kl. 20:00</b>",
            "[FIKTIVT BILDE — beskrivelse]: Restauranten ses gjennom "
            "glassdørene — alle stolene er stablet på bordene, "
            "kjøkkenet stengt. Skilt på døren: «Closed for renovation "
            "until further notice».",
            "<b>Dagbok-utdrag — ført av Ingrid Hansen</b>",
            "<b>Mandag 7. april:</b> Vekket kl. 06:55 av boremaskiner. "
            "Barna gråt. Forsøkte å forklare resepsjonen at vi hadde "
            "betalt 38.400 for ferie — fikk «We are sorry, please call "
            "FjordTravel Norway». Ringte FjordTravels reisedeler — "
            "han sa han ikke kunne gjøre noe på stedet og henviste "
            "oss til Oslo.",
            "<b>Onsdag 9. april:</b> Tredje natt med dårlig søvn. Lillegutt "
            "(8 år) våknet hver morgen kl. 07. Storesøster (11 år) sa "
            "«mamma, dette er ikke ferie, dette er straff». "
            "Bassenget fortsatt stengt. Barn-clubben hadde 2 stk "
            "aktiviteter — én tegnetime og én «discotek-kveld» — i "
            "stedet for det daglige programmet.",
            "<b>Fredag 11. april:</b> Forsøkt å flytte til annet hotell — "
            "FjordTravel sa det «var ikke mulig på stedet». Vi forble.",
        ],
    },
    {
        "filnavn": "bilag-03-korrespondanse.pdf",
        "bilag_nr": 3,
        "titel": "Korrespondanse med FjordTravel AS — etter hjemkomst",
        "undertitel": "E-poster mellom Lars Hansen og FjordTravel AS, 14.–28. april 2026",
        "indhold": [
            "<b>E-post 1 — Fra Lars Hansen, 14. april 2026 kl. 10:42</b>",
            "Til: kundeservice@fjordtravel.no<br/>"
            "Fra: lars.hansen@email.no<br/>"
            "Emne: Reklamasjon — booking FT-26-08423 — Kreta 6.–13. april 2026",
            "Til FjordTravel AS,<br/>"
            "Vi kom hjem i går kveld fra det vi var lovet ville være en "
            "rolig familieferie til Kreta. Det det viste seg å være var "
            "en uke i et byggevarehus.<br/><br/>"
            "Hotel Sirenes Beach Resort var under omfattende renovation "
            "gjennom HELE vårt 7-dagers opphold. Vi opplevde: "
            "(a) byggestøy fra kl. 07:00–19:00 daglig, (b) basseng og "
            "barnebasseng fullstendig stengt, (c) à la carte-restauranten "
            "lukket — erstattet av et midlertidig buffet-telt med svært "
            "begrenset meny, (d) reduserte Mini Club-aktiviteter for "
            "barna.<br/><br/>"
            "På INTET tidspunkt før avreise ble vi informert om at "
            "hotellet var under renovation. Bookingbekreftelsen omtalte "
            "et «nyrenovert 4-stjerners anlegg».<br/><br/>"
            "Vi krever:<br/>"
            "1) Prisavslag på 50 % av reisens pris (19.200 NOK)<br/>"
            "2) Erstatning for tapt ferieverdi for begge barn — i alt "
            "3.300 NOK<br/>"
            "Samlet kravsum: 22.500 NOK<br/><br/>"
            "Vi ber om skriftlig svar innen 14 dager.<br/><br/>"
            "Med vennlig hilsen,<br/>Lars Hansen<br/>+47 91 23 45 67",

            "<b>E-post 2 — Fra FjordTravel AS, 28. april 2026 kl. 14:18</b>",
            "Til: lars.hansen@email.no<br/>"
            "Fra: kundeservice@fjordtravel.no<br/>"
            "Emne: SV: Reklamasjon — booking FT-26-08423",
            "Hei Lars,<br/><br/>"
            "Tusen takk for din henvendelse av 14. april. Vi beklager "
            "at deres ferie ikke ble som forventet.<br/><br/>"
            "Vi har gjennomgått saken med vår destinasjonsleverandør "
            "i Hellas (Hellas Holiday Partners), og det stemmer at "
            "hotellet hadde vedlikeholdsarbeid i uke 14–15. Vi var "
            "ikke gjort kjent med omfanget før i forrige uke, da vår "
            "destinasjonssjef gjorde befaring.<br/><br/>"
            "Som en kommersiell goodwill-gest tilbyr vi følgende: "
            "Et verdibevis pålydende <b>NOK 4.000</b>, som kan benyttes "
            "som rabatt på en fremtidig reise med FjordTravel innen "
            "31. desember 2027. Vi mener dette er rimelig, da en "
            "vesentlig del av reisens kjernetjenester (overnatting, "
            "frokost, transfer) ble levert.<br/><br/>"
            "Med vennlig hilsen,<br/>"
            "FjordTravel AS — Kundeserviceavdelingen<br/>"
            "Ref: KS-2026-1881",

            "<b>E-post 3 — Fra Lars Hansen, 30. april 2026 kl. 09:05</b>",
            "Til: kundeservice@fjordtravel.no<br/>"
            "Fra: lars.hansen@email.no<br/>"
            "Emne: Re: SV: Reklamasjon — booking FT-26-08423",
            "Til FjordTravel AS,<br/><br/>"
            "Et verdibevis på 4.000 NOK — som vi <i>kanskje</i> kan "
            "benytte hvis vi noen gang vil reise med dere igjen — er "
            "ikke et akseptabelt tilbud. Vi har krav på et reelt "
            "prisavslag etter pakkereiseloven § 31, ikke en rabattkupong.<br/><br/>"
            "Hvis ikke vi mottar et akseptabelt tilbud innen 7 dager, "
            "vil vi innbringe saken for Pakkereisenemnda.<br/><br/>"
            "Med vennlig hilsen,<br/>Lars Hansen",

            "<b>Status pr. 12. mai 2026</b>",
            "FjordTravel har ikke svart på e-post 3. Klagen er nå "
            "formelt innbrakt for Pakkereisenemnda.",
        ],
    },
]


# Selskaps-interne dokumenter (3 stk)
SELSKAB_DOCS = [
    {
        "filnavn": "selskab-01-intern-korrespondanse.pdf",
        "selskab": "FjordTravel AS",
        "titel": "Intern korrespondanse — Sirenes Beach Resort, uke 14–15",
        "undertitel": "E-poster mellom FjordTravel og Hellas Holiday Partners",
        "indhold": [
            "<b>E-post 1 — 5. april 2026 kl. 11:30 (dagen før Hansen-familien reiser)</b>",
            "Fra: katerina@hellas-holiday.gr<br/>"
            "Til: destinasjon@fjordtravel.no<br/>"
            "Emne: Sirenes Beach — uvanlig støy denne uken",
            "Hi FjordTravel destination team,<br/><br/>"
            "Quick note about Sirenes Beach Resort — the hotel "
            "started Phase 2 of their pool/restaurant renovation on "
            "30 March. We were told it would be «mostly cosmetic» and "
            "finished by end of week 14 (April 7). However, our local "
            "inspector reports that the work is now much more "
            "extensive than originally planned, including a full pool "
            "shutdown for 2 weeks and a-la-carte restaurant closure.<br/><br/>"
            "I would recommend reaching out to guests booked for "
            "week 14–15 to set expectations. Hansen-family arrives "
            "tomorrow.<br/><br/>"
            "Best,<br/>Katerina Stavros<br/>Hellas Holiday Partners",

            "<b>E-post 2 — 5. april 2026 kl. 16:42 (intern fra destinasjons-sjef)</b>",
            "Fra: jens.olsen@fjordtravel.no (destinasjons-sjef Hellas)<br/>"
            "Til: ledelse@fjordtravel.no<br/>"
            "Emne: Sirenes Beach — bør vi informere uke 14–15-gjester?",
            "Hei,<br/><br/>"
            "Katerina varsler at renovasjonen er mer omfattende enn "
            "først meldt. Det er 14 norske bookinger berørt i uke 14–15 "
            "(ca. 50 personer). To alternativer:<br/><br/>"
            "1) Sende info-mail til berørte gjester NÅ — risikerer "
            "kanselleringer + krav om refusjon før avreise.<br/><br/>"
            "2) Avvente og se hvor mye støy det blir — håndtere "
            "reklamasjoner ved tilbakekomst, sannsynligvis lavere "
            "totalkostnad.<br/><br/>"
            "Hva er din anbefaling? Hansen-familien (FT-26-08423) er "
            "blant de første som ankommer.<br/><br/>"
            "Jens",

            "<b>E-post 3 — 5. april 2026 kl. 18:01 (svar fra ledelsen)</b>",
            "Fra: ledelse@fjordtravel.no<br/>"
            "Til: jens.olsen@fjordtravel.no<br/>"
            "Emne: Re: Sirenes Beach",
            "Jens — la oss gå for alternativ 2. Sjansen for at det "
            "blir så ille som Katerina antyder er liten. Hvis det "
            "kommer reklamasjoner ved hjemkomst, behandler vi dem "
            "individuelt — typisk har vi et goodwill-budsjett på "
            "5–10 % av reiseprisen som vi kan trekke fra.<br/><br/>"
            "Mvh<br/>Ledelsen",
        ],
        "fortroligt": True,
    },
    {
        "filnavn": "selskab-02-rammeavtale-hotell.pdf",
        "selskab": "FjordTravel AS",
        "titel": "Rammeavtale FjordTravel ↔ Hotel Sirenes Beach Resort — utdrag",
        "undertitel": "Avtale signert 12. november 2025 — relevante klausuler",
        "indhold": [
            "<b>§ 3 Hotellets forpliktelser overfor FjordTravels gjester</b>",
            "Hotellet plikter i hele leveringsperioden å sikre at "
            "samtlige felles fasiliteter — herunder, men ikke "
            "begrenset til, hovedbasseng, barnebasseng, à la carte-"
            "restaurant og barnetilbud (Mini Club) — er fullt "
            "operative i markedsført utstrekning.",

            "<b>§ 4 Varslingsplikt ved planlagte vedlikeholdsarbeider</b>",
            "Hotellet plikter å gi FjordTravel skriftlig varsel <b>minst "
            "60 dager</b> før påbegynnelse av enhver renovation, "
            "ombygging eller annet større vedlikeholdsarbeid som "
            "kan påvirke gjesteopplevelsen.",
            "Ved manglende varsling kan FjordTravel kreve prisavslag "
            "fra hotellet med inntil 30 % av netto bookingpris pr. "
            "berørt gjest, samt erstatning for eventuelle krav fra "
            "gjester som måtte oppstå.",

            "<b>§ 7 FjordTravels informasjonsplikt overfor egne gjester</b>",
            "FjordTravel forplikter seg til, så snart selskapet får "
            "kunnskap om forhold som vesentlig kan påvirke "
            "kjernetjenestene (jf. § 3), å videreformidle dette til "
            "berørte gjester uten ugrunnet opphold. Dette gjelder "
            "uavhengig av om hotellet har overholdt sin varslingsplikt "
            "etter § 4.",

            "<b>Kommentar (intern):</b> Sirenes Beach ga oss "
            "<i>ingen</i> formell varsling om Phase 2-renovasjonen "
            "før 5. april 2026 — én dag før uke 14-gjestene reiste. "
            "Det er klart brudd på § 4 i rammeavtalen, og vi har "
            "regress mot hotellet. Men vår § 7-plikt overfor gjester "
            "ble ikke aktivert (jf. ledelsens beslutning 5. april).",
        ],
        "fortroligt": True,
    },
    {
        "filnavn": "selskab-03-reisebetingelser-uddrag.pdf",
        "selskab": "FjordTravel AS",
        "titel": "FjordTravel Reisebetingelser 2026 — utdrag §§ 12, 18–20",
        "undertitel": "Almenne vilkår for pakkereiser — versjon januar 2026",
        "indhold": [
            "<b>§ 12 Mangler ved pakkereisen</b>",
            "Dersom det foreligger en mangel ved pakkereisen som "
            "ikke skyldes den reisende selv, plikter FjordTravel å "
            "avhjelpe mangelen så raskt som mulig, og uten "
            "merkostnad for den reisende, jf. pakkereiseloven § 27.",
            "Dersom mangelen ikke avhjelpes, har den reisende krav på "
            "prisavslag i samsvar med pakkereiseloven § 31, "
            "tilsvarende mangelens omfang og varighet.",

            "<b>§ 18 Reklamasjonsfrist</b>",
            "Reklamasjon må fremsettes innen rimelig tid etter at "
            "den reisende oppdaget eller burde ha oppdaget mangelen. "
            "Reklamasjon fremsatt mer enn 60 dager etter hjemreise "
            "kan ikke gjøres gjeldende.",
            "Klager bør først fremsettes overfor FjordTravels "
            "reisedeleder på destinasjonen, slik at det er mulig å "
            "avhjelpe mangelen mens den fortsatt foreligger.",

            "<b>§ 19 FjordTravels ansvarsbegrensning</b>",
            "FjordTravels samlede erstatningsansvar for en pakkereise "
            "kan ikke overstige tre ganger pakkereisens samlede pris, "
            "med mindre annet følger av pakkereiseloven § 33.",
            "Vi er ikke ansvarlige for forhold som ligger utenfor "
            "vår kontroll, herunder force majeure-hendelser (vær, "
            "natur, streik, politiske forhold mv.).",

            "<b>§ 20 Verdibevis som kompensasjonsform</b>",
            "Som alternativ til kontant utbetaling kan FjordTravel "
            "tilby den reisende et verdibevis (gavekort) som kan "
            "benyttes som rabatt på fremtidig reise. Aksept av "
            "verdibevis er <b>frivillig</b> og medfører ikke at den "
            "reisende fraskriver seg krav etter pakkereiseloven.",
        ],
        "fortroligt": False,
    },
]


# ─────────────────────────────────────────────────────────────────
# PDF-buildere — norsk-tilpasset versjon
# ─────────────────────────────────────────────────────────────────

def _norsk_nemnda_header(styles, dato):
    """Pakkereisenemnda header (norsk pendant til _afsender_header)."""
    return [
        Paragraph("PAKKEREISENEMNDA", styles["Titel"]),
        Paragraph(
            "Postboks 5462 Majorstuen · 0305 Oslo · Tlf. 23 13 60 00 · "
            "post@pakkereisenemnda.no",
            styles["Lille"],
        ),
        Spacer(1, 0.4 * cm),
        Paragraph(f"Klage mottatt: {dato}", styles["Lille"]),
        Spacer(1, 0.6 * cm),
    ]


def _byg_norsk_klageskema(path, sag):
    doc = SimpleDocTemplate(
        path, pagesize=A4,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm,
        topMargin=1.8 * cm, bottomMargin=1.8 * cm,
        title=f"Klageskjema sak {sag['sagsnr']}",
    )
    s = _styles()
    story = []
    story.extend(_norsk_nemnda_header(s, sag["modtaget_dato"]))
    story.append(Paragraph(f"Klagesak nr. {sag['sagsnr']}", s["Subtitel"]))

    story.append(Paragraph("Partene", s["SektionsTitel"]))
    story.append(_info_tabel([
        ["Klager:", sag["klager_navn"]],
        ["Adresse:", sag["klager_adresse"]],
        ["E-post:", sag["klager_email"]],
        ["Telefon:", sag["klager_tlf"]],
        ["Innklaget:", sag["indklagede"]],
    ], s))

    story.append(Paragraph("Reisen", s["SektionsTitel"]))
    story.append(_info_tabel([
        ["Destinasjon:", sag["destination"]],
        ["Reiseperiode:", sag["rejseperiode"]],
        ["Antall reisende:", sag["antal_rejsende"]],
        ["Reisens samlede pris:", sag["rejse_pris"]],
        ["Bookingreferanse:", sag["bookingref"]],
    ], s))

    story.append(Paragraph("Klagepunkter", s["SektionsTitel"]))
    for afsnit in sag["klagepunkter"].strip().split("\n\n"):
        story.append(Paragraph(afsnit.strip(), s["Brod"]))

    story.append(Paragraph("Klagers påstand", s["SektionsTitel"]))
    story.append(Paragraph(sag["paastand"], s["Brod"]))

    story.append(Paragraph("Tidligere korrespondanse", s["SektionsTitel"]))
    story.append(Paragraph(sag["tidligere_korrespondance"], s["Brod"]))

    story.append(Spacer(1, 1.0 * cm))
    story.append(Paragraph(
        "Innklagede anmodes om å fremsende skriftlige bemerkninger til "
        "klagen senest 4 uker fra dato. Manglende svar kan medføre at "
        "klagen avgjøres på det foreliggende grunnlag, jf. "
        "Pakkereisenemndas vedtekter § 6.",
        s["Brod"],
    ))
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph(
        "Med vennlig hilsen<br/>Pakkereisenemnda<br/>Sekretariatet",
        s["Brod"],
    ))
    story.append(Spacer(1, 1.5 * cm))
    story.append(Paragraph(
        "[FIKTIV TESTSAK — alle opplysninger er oppdiktet og må kun "
        "brukes til test av juriitech PAX]",
        s["Lille"],
    ))
    doc.build(story)


def _byg_norsk_staevning(path, sag):
    doc = SimpleDocTemplate(
        path, pagesize=A4,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm,
        topMargin=1.8 * cm, bottomMargin=1.8 * cm,
        title=f"Underretning sak {sag['sagsnr']}",
    )
    s = _styles()
    story = [
        Paragraph("PAKKEREISENEMNDA", s["Titel"]),
        Paragraph(
            "Postboks 5462 Majorstuen · 0305 Oslo · Tlf. 23 13 60 00 · "
            "post@pakkereisenemnda.no · Org. nr. 982 932 357",
            s["Lille"],
        ),
        Spacer(1, 1.2 * cm),
    ]
    story.append(Paragraph(f"<b>{sag['indklagede']}</b>", s["Brod"]))
    story.append(Paragraph(sag["indklagede_adresse"], s["Brod"]))
    story.append(Spacer(1, 0.8 * cm))
    story.append(_info_tabel([
        ["Saksnr.:", sag["sagsnr"]],
        ["Dato:", sag["modtaget_dato"]],
        ["Saksbehandler:", sag["sagsbehandler_initialer"]],
        ["Gjelder:", "Pakkereiseloven §§ 27, 31 og 32"],
    ], s))
    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph("UNDERRETNING OM INNGITT KLAGE",
                           s["SektionsTitel"]))

    body = (
        f"Pakkereisenemnda har den {sag['modtaget_dato'].lower()} mottatt "
        f"vedlagte klage fra <b>{sag['klager_navn']}</b> over en pakkereise "
        f"til {sag['destination']} i perioden {sag['rejseperiode']}, "
        f"formidlet av {sag['indklagede']}.\n\n"
        "<b>Kort om klagen</b>\n"
        f"{sag['staevning_resume']}\n\n"
        "<b>Klagers påstand</b>\n"
        f"{sag['staevning_paastand_kort']}\n\n"
        "Klagen med tilhørende vedlegg følger som vedlegg til "
        "nærværende skriv.\n\n"
        "<b>Frist for bemerkninger</b>\n"
        "I henhold til Pakkereisenemndas vedtekter § 5 anmodes "
        "innklagede om innen <b>4 uker fra dato</b> å fremsende "
        "skriftlige bemerkninger til klagen.\n\n"
        "Bemerkningene bes adressert til sekretariatet med tydelig "
        "angivelse av ovennevnte saksnr.\n\n"
        "Hvis innklagede ikke svarer innen fristens utløp, kan "
        "klagen avgjøres på det foreliggende grunnlag, jf. nemndas "
        "vedtekter § 6.\n\n"
        "<b>Saksomkostninger</b>\n"
        "Pakkereisenemnda bemerker at det i medhold av "
        "pakkereiseloven § 50 og nemndas vedtekter kan ilegges "
        "saksomkostninger til Pakkereisenemnda dersom klagen helt "
        "eller delvis tas til følge.\n\n"
        "<b>Forlik</b>\n"
        "Før saken behandles i nemnda oppfordres partene til å søke "
        "en forliksløsning. Eventuelt forlik bes meddelt "
        "sekretariatet snarest mulig.\n\n"
        "Eventuelle spørsmål kan rettes til sekretariatet på "
        "post@pakkereisenemnda.no eller telefon 23 13 60 00 "
        "(hverdager 10:00–14:00)."
    )

    for afsnit in body.split("\n\n"):
        story.append(Paragraph(afsnit.strip(), s["Brod"]))

    story.append(Spacer(1, 0.8 * cm))
    story.append(Paragraph(
        "Med vennlig hilsen<br/>Pakkereisenemnda<br/>"
        f"v/ {sag['sagsbehandler_navn']}, juridisk saksbehandler<br/>"
        "Sekretariatet",
        s["Brod"],
    ))
    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph(
        "[FIKTIV TESTSAK — alle opplysninger er oppdiktet]",
        s["Lille"],
    ))
    doc.build(story)


def _byg_norsk_vedlegg(path, titel, undertitel, indhold_afsnit, vedlegg_nr):
    """Norsk pendant til _byg_bilag — 'Vedlegg' i stedet for 'Bilag'."""
    doc = SimpleDocTemplate(
        path, pagesize=A4,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm,
        topMargin=1.8 * cm, bottomMargin=1.8 * cm,
        title=f"Vedlegg {vedlegg_nr}: {titel}",
    )
    s = _styles()
    story = [
        Paragraph(f"Vedlegg {vedlegg_nr}", s["Lille"]),
        Paragraph(titel, s["Titel"]),
        Paragraph(undertitel, s["Subtitel"]),
    ]
    for afsnit in indhold_afsnit:
        if isinstance(afsnit, list):
            story.append(_info_tabel(afsnit, s))
            story.append(Spacer(1, 0.3 * cm))
        else:
            story.append(Paragraph(afsnit, s["Brod"]))
    story.append(Spacer(1, 1.5 * cm))
    story.append(Paragraph(
        "[FIKTIV TESTSAK — alle opplysninger er oppdiktet]",
        s["Lille"],
    ))
    doc.build(story)


def _byg_norsk_selskap(path, selskap, titel, undertitel,
                       indhold_afsnit, fortroligt=True):
    """Norsk pendant til _byg_selskabsdokument."""
    doc = SimpleDocTemplate(
        path, pagesize=A4,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm,
        topMargin=1.8 * cm, bottomMargin=1.8 * cm,
        title=f"{selskap} — {titel}",
    )
    s = _styles()
    header_label = "INTERNT · KONFIDENSIELT" if fortroligt else "INTERNT"

    story = []
    klassifikation = Table(
        [[f"{header_label} · {selskap}"]], colWidths=[16 * cm],
    )
    klassifikation.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fef3c7")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#92400e")),
        ("FONT", (0, 0), (-1, -1), "Helvetica-Bold", 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#92400e")),
    ]))
    story.append(klassifikation)
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
        "[FIKTIV TESTSAK — alle opplysninger er oppdiktet]",
        s["Lille"],
    ))
    doc.build(story)


# ─────────────────────────────────────────────────────────────────
# Manifest-merge — lægger norsk entry ind uden at rør de danske
# ─────────────────────────────────────────────────────────────────

def _opdater_manifest():
    """Læs eksisterende manifest, fjern evt. gammel sag-06-entry, tilføj ny."""
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    else:
        manifest = []

    # Fjern eksisterende sag-06-entry (idempotens)
    manifest = [e for e in manifest if e.get("mappe") != SAG_MAPPE]

    # Tilføj norsk entry
    filer = [
        {"navn": "00-staevning-fra-nemnda.pdf",
         "titel": "Underretning fra Pakkereisenemnda",
         "kilde": "naevnet"},
        {"navn": "klageskema.pdf",
         "titel": "Klageskjema",
         "kilde": "naevnet"},
    ] + [
        {"navn": b["filnavn"], "titel": b["titel"], "kilde": "klager"}
        for b in BILAG
    ] + [
        {"navn": d["filnavn"], "titel": d["titel"], "kilde": "selskab"}
        for d in SELSKAB_DOCS
    ]

    norsk_entry = {
        "mappe": SAG_MAPPE,
        "sagsnr": SAG["sagsnr"],
        "indklagede": SAG["indklagede"],
        "klager": SAG["klager_navn"],
        "destination": SAG["destination"],
        "rejseperiode": SAG["rejseperiode"],
        "antal_rejsende": SAG["antal_rejsende"],
        "rejse_pris": SAG["rejse_pris"],
        "land": "NO",
        "filer": filer,
    }
    manifest.append(norsk_entry)

    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def main():
    # Sletter KUN den norske sag-mappe — rører ikke de 5 danske
    if os.path.exists(SAG_DIR):
        shutil.rmtree(SAG_DIR)
    os.makedirs(SAG_DIR, exist_ok=True)

    print(f"=== Bygger norsk testsag i {SAG_DIR} ===\n")

    # 1. Underretning fra nemnda
    p = os.path.join(SAG_DIR, "00-staevning-fra-nemnda.pdf")
    _byg_norsk_staevning(p, SAG)
    print(f"  ✓ {SAG_MAPPE}/00-staevning-fra-nemnda.pdf")

    # 2. Klageskjema
    p = os.path.join(SAG_DIR, "klageskema.pdf")
    _byg_norsk_klageskema(p, SAG)
    print(f"  ✓ {SAG_MAPPE}/klageskema.pdf")

    # 3. Klagers vedlegg
    for b in BILAG:
        p = os.path.join(SAG_DIR, b["filnavn"])
        _byg_norsk_vedlegg(p, b["titel"], b["undertitel"],
                           b["indhold"], b["bilag_nr"])
        print(f"  ✓ {SAG_MAPPE}/{b['filnavn']}")

    # 4. Selskabsinterne dokumenter
    for d in SELSKAB_DOCS:
        p = os.path.join(SAG_DIR, d["filnavn"])
        _byg_norsk_selskap(p, d["selskab"], d["titel"], d["undertitel"],
                           d["indhold"], d.get("fortroligt", True))
        print(f"  ✓ {SAG_MAPPE}/{d['filnavn']}")

    # 5. Manifest merge
    _opdater_manifest()
    print(f"  ✓ manifest.json (norsk entry merget ind)")

    print()
    print(f"=== Færdig: 8 PDF'er + manifest opdateret ===")
    print(f"Lokation: {SAG_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
