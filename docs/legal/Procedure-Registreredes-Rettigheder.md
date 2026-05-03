# Procedure for de registreredes rettigheder

**Intern procedure for håndtering af anmodninger fra registrerede via dataansvarlig (kunde)**

---

**Dokumentversion:** 1.0
**Sidst opdateret:** 2026-05-03
**Ansvarlig:** Mikkel Sindbakke, juriitech

---

## 1. Formål

Dette dokument beskriver juriitech's interne procedure for at bistå dataansvarlige (kunder) med at imødekomme anmodninger fra registrerede om udøvelse af deres rettigheder efter GDPR art. 15-22.

Som databehandler modtager juriitech ikke anmodninger direkte fra registrerede. Anmodningen sendes til den dataansvarlige (fx TUI), som videresender den nødvendige instruks til juriitech. Dette dokument fastlægger, hvordan juriitech reagerer på en sådan instruks.

Forpligtelsen følger af GDPR art. 28, stk. 3, litra e, og af DPA'ens punkt 10.

---

## 2. Anvendelsesområde

Proceduren finder anvendelse på alle anmodninger om udøvelse af følgende rettigheder, der videreformidles fra en dataansvarlig:

- Indsigtsret (GDPR art. 15)
- Ret til berigtigelse (GDPR art. 16)
- Ret til sletning ("retten til at blive glemt") (GDPR art. 17)
- Ret til begrænsning (GDPR art. 18)
- Underretningspligt (GDPR art. 19)
- Ret til dataportabilitet (GDPR art. 20)
- Ret til indsigelse (GDPR art. 21)
- Automatiserede afgørelser (GDPR art. 22)

---

## 3. Modtagelse af anmodning

### 3.1 Kanal

Anmodninger fra dataansvarlige skal sendes skriftligt til:

**E-mail:** [Indsæt kontakt-e-mail, fx legal@juriitech.com]
**Emnefelt:** "GDPR — registreret rettighedsanmodning — [tenant-slug]"

### 3.2 Påkrævet information fra den dataansvarlige

For at kunne behandle anmodningen kræver juriitech følgende oplysninger:

1. Hvilken rettighed anmodes (art. 15, 17 osv.)
2. Den registreredes identifikation (navn, kundenummer, sags-id, e-mailadresse — i det omfang den dataansvarlige har dem)
3. Eventuelle relevante sagsnumre eller tidsperioder der afgrænser anmodningen
4. Eventuelle særlige instrukser fra den dataansvarlige (fx om format eller tidsfrist)
5. Bekræftelse fra den dataansvarlige af, at den registreredes identitet er verificeret, og at anmodningen kan imødekommes

### 3.3 Bekræftelse til den dataansvarlige

juriitech bekræfter modtagelsen af anmodningen via e-mail senest **5 arbejdsdage** efter modtagelsen. Bekræftelsen indeholder:

- Reference-id for anmodningen (intern sags-id i juriitech)
- Forventet behandlingstid (typisk 14-30 dage afhængig af kompleksitet)
- Eventuelle yderligere oplysninger der er nødvendige for at gennemføre anmodningen

---

## 4. Identifikation af relevante data

For at lokalisere de personoplysninger, der er omfattet af anmodningen, gennemføres en søgning i:

- **mine_dokumenter** (klagedokumenter overladt af kunden)
- **dokument_chunks** (indekserede tekst-segmenter for søgning)
- **analyse_arkiv** (gemte analyser og førstevurderinger)
- **gemte_sager** (kunde-konfigurerede sags-arkiver)
- **gdpr_audit_log** (referenceoplysninger om tidligere behandling — indeholder ikke selve persondata)
- Backup-data (i det omfang det er nødvendigt for fuld eksekvering)

Søgningen sker som SQL-baseret tekst-match og semantisk søgning på de identifikatorer, den dataansvarlige har oplyst (navn, e-mail, kundenummer, sags-id m.v.).

Resultatet af søgningen dokumenteres som del af anmodningens log.

---

## 5. Eksekvering pr. rettighed

### 5.1 Indsigtsret (art. 15)

**Forpligtelse:** Levere en kopi af de personoplysninger, der behandles om den registrerede, samt øvrige oplysninger om behandlingen (formål, kategorier, modtagere, opbevaringsperiode m.v.).

**Eksekvering:**

1. Identificér alle dokumenter og udledte data, der er knyttet til den registrerede
2. Gener en samlet rapport indeholdende:
   - Kopi af relevante klagedokumenter (eller deres anonymiserede versioner, hvis allerede anonymiseret)
   - Liste over kategorier af personoplysninger, der behandles
   - Formål med behandlingen
   - Identifikation af underdatabehandlere, der har modtaget oplysningerne
   - Opbevaringsperiode
3. Send rapporten til den dataansvarlige i krypteret form
4. Den dataansvarlige videresender til den registrerede i overensstemmelse med egne procedurer

**Tidsfrist:** Inden for 14 dage efter modtagelse af komplet anmodning.

### 5.2 Ret til berigtigelse (art. 16)

**Forpligtelse:** Berigtige urigtige personoplysninger om den registrerede.

**Eksekvering:**

1. Identificér de berørte data
2. Modtag rettelseinstruks fra den dataansvarlige (hvad skal ændres, til hvad)
3. Foretag rettelsen i alle relevante tabeller
4. Regenerer afledte data (embeddings) hvis det er nødvendigt for at sikre konsistens
5. Bekræft rettelsen til den dataansvarlige

**Tidsfrist:** Inden for 7 dage efter modtagelse af komplet instruks.

**Note:** Berigtigelse i juriitech PAX er sjælden, idet de behandlede dokumenter er kopier af originalmateriale fra Pakkerejse-Ankenævnet eller den dataansvarlige selv. Ændringer foretages i regel hos den dataansvarlige, og juriitech sletter blot den oprindelige version og modtager den rettede version som ny upload.

### 5.3 Ret til sletning (art. 17 — "ret til at blive glemt")

**Forpligtelse:** Slette alle personoplysninger om den registrerede.

**Eksekvering:**

1. Identificér alle dokumenter og udledte data knyttet til den registrerede
2. Slet i følgende rækkefølge:
   - dokument_chunks (afledte chunk-tekster og embeddings)
   - mine_dokumenter (originale dokumenter)
   - analyse_arkiv-entries hvor klager er tagget
   - gemte_sager-konfigurationer der refererer til kun denne registrerede
   - eventuelle eksport-filer (DOCX, PDF) genereret af systemet
3. Marker gdpr_audit_log med "tilbage_kald"-event (auditlog-entries indeholder ikke PII, kun sags-id og tenant-id, og kan derfor opbevares)
4. Backup-data anonymiseres ved næstkommende rotation, senest inden for 90 dage
5. Bekræft sletningen til den dataansvarlige med slettelogs-kvittering

**Tidsfrist:** Aktiv sletning inden for 14 dage. Backup-rotation inden for 90 dage.

**Begrænsninger:** Hvis den registrerede er nævnt i en sag, der vedrører flere personer (fx familieklage), kan sletning af den ene registreredes oplysninger kræve, at hele sagen anonymiseres frem for slettes, for ikke at slette oplysninger om de øvrige registrerede. Dette afklares med den dataansvarlige forud for eksekvering.

### 5.4 Ret til begrænsning (art. 18)

**Forpligtelse:** Begrænse behandlingen, så de berørte data fortsat opbevares men ikke aktivt behandles.

**Eksekvering:**

1. Identificér de berørte data
2. Sæt status `anonymiserings_status = 'sletbar'` på de berørte rækker, så de udelukkes fra videre AI-behandling og søgninger
3. Bekræft til den dataansvarlige
4. Når begrænsningen ophæves, sættes status tilbage til `aktiv` eller behandlingen fuldføres

**Tidsfrist:** Inden for 7 dage efter modtagelse af instruks.

### 5.5 Underretningspligt (art. 19)

**Forpligtelse:** Underrette modtagere af de slettede/berigtigede/begrænsede oplysninger.

**Eksekvering:** juriitech leverer ikke selvstændigt oplysninger til andre modtagere end de underdatabehandlere, der er listet i Bilag B til DPA'en. Når sletning eller berigtigelse er gennemført hos juriitech, er de afledte oplysninger hos underdatabehandlerne ligeledes slettet (idet underdatabehandlerne kun behandler oplysninger som transient input til en konkret behandling — de gemmer ikke kunde-data).

For at sikre dette, har juriitech:

- Bekræftelse fra Anthropic om at prompt-data ikke gemmes ud over den nødvendige inferens-runtime
- Bekræftelse fra Voyage AI om samme princip for embedding-input
- Daglig backup-rotation hos databehandling-leverandør sikrer, at slettede data også fjernes fra backup inden for 90 dage

### 5.6 Ret til dataportabilitet (art. 20)

**Forpligtelse:** Udlevere de personoplysninger, den registrerede selv har givet, i et struktureret, almindeligt anvendt og maskinlæsbart format.

**Eksekvering:**

1. Identificér de oprindelige dokumenter, klager har overladt
2. Eksportér i JSON-format med følgende struktur:
   ```json
   {
       "registreret": { "navn": "...", "email": "..." },
       "sager": [{
           "sag_id": "...",
           "oprettet": "...",
           "dokumenter": [{ "filnavn": "...", "type": "...", "indhold": "..." }],
           "analyser": [{ "tidspunkt": "...", "indhold": "..." }]
       }]
   }
   ```
3. Lever filen krypteret til den dataansvarlige

**Tidsfrist:** Inden for 14 dage efter modtagelse af komplet anmodning.

### 5.7 Ret til indsigelse (art. 21)

**Forpligtelse:** Behandling af persondata standses, hvis indsigelsen vedrører behandling baseret på legitim interesse eller direkte markedsføring.

**Eksekvering:** juriitech foretager ikke behandling baseret på legitim interesse — al behandling sker på den dataansvarliges instruks (kontraktuelt grundlag iht. GDPR art. 6(1)(b)). Indsigelse efter art. 21 er derfor ikke direkte relevant for juriitech's behandling. Hvis en indsigelse alligevel modtages, behandles den som en anmodning om begrænsning (art. 18) eller sletning (art. 17), afhængig af kontekst og instruks fra den dataansvarlige.

### 5.8 Automatiserede afgørelser (art. 22)

**Forpligtelse:** Den registrerede har ret til ikke at være underlagt udelukkende automatiserede afgørelser med retsvirkning eller tilsvarende betydelig påvirkning.

**Eksekvering:** juriitech PAX træffer ikke automatiserede afgørelser. AI-genererede vurderinger og udkast til svarbreve er udkast, der vurderes og godkendes af menneskelige sagsbehandlere hos den dataansvarlige inden de sendes ud. Art. 22 finder derfor ikke direkte anvendelse, men hvis en registreret rejser bekymring, oplyses den registrerede om denne menneskelige kontrol via den dataansvarlige.

---

## 6. Bekræftelse til den dataansvarlige

For hver anmodning udsteder juriitech en skriftlig bekræftelse til den dataansvarlige indeholdende:

1. Reference-id for anmodningen
2. Hvilken rettighed der er imødekommet
3. Hvad der er gjort (slettet / berigtiget / udleveret / begrænset)
4. Tidspunkt for eksekvering
5. Eventuelle bemærkninger eller begrænsninger
6. Bekræftelse af, at backup-rotation er igangsat (ved sletning)

Bekræftelsen sendes via e-mail til kontaktpunktet hos den dataansvarlige.

---

## 7. Logning og dokumentation

For hver anmodning logges følgende i intern log:

| Felt | Indhold |
| ---- | ------- |
| Reference-id | Genereres ved modtagelse |
| Modtagelses-dato | Dato og tidspunkt |
| Dataansvarlig | Tenant-slug |
| Rettighed | Art. 15 / 17 / 20 osv. |
| Identifikation af registreret | Hash/pseudonymiseret reference (ikke direkte navn) |
| Eksekverings-dato | Dato og tidspunkt |
| Resultat | Imødekommet / Delvist / Afvist (med begrundelse) |
| Bekræftelse sendt | Dato og tidspunkt |

Logs opbevares i mindst 5 år som dokumentation for compliance med GDPR art. 5(2) ("ansvarlighed").

---

## 8. Eskalering og afvisning

### 8.1 Tilfælde der eskaleres

Anmodninger eskaleres til ekstern juridisk vurdering i følgende tilfælde:

- Anmodningen fremstår uklar eller selvmodsigende
- Den dataansvarliges instruks synes i strid med GDPR
- Anmodningen vedrører særlige kategorier af personoplysninger uden klart behandlingsgrundlag
- Anmodningen kan medføre sletning af data, der efter anden lovgivning skal opbevares (fx bogføringsloven)

### 8.2 Afvisning

juriitech afviser ikke selv en anmodning, idet juriitech som databehandler kun handler på instruks. Hvis den dataansvarliges instruks er problematisk, underretter juriitech den dataansvarlige skriftligt, jf. DPA pkt. 5.2.

---

## 9. Tidsfrister — sammenfatning

| Trin | Frist |
| ---- | ----- |
| Bekræftelse af modtagelse til dataansvarlig | 5 arbejdsdage |
| Aktiv eksekvering (sletning, eksport, berigtigelse) | 14 dage (kan forlænges til 30 ved kompleksitet) |
| Backup-rotation efter sletning | Senest 90 dage |
| Endelig bekræftelse til dataansvarlig | Straks efter eksekvering |

GDPR's overordnede frist på 1 måned (art. 12, stk. 3) skal overholdes af den dataansvarlige overfor den registrerede. juriitech's frister er sat således, at den dataansvarlige har minimum 14 dage tilbage til at færdigbehandle og besvare den registrerede.

---

## 10. Versionshistorik

| Version | Dato | Ændring |
| ------- | ---- | ------- |
| 1.0 | 2026-05-03 | Første udgave oprettet. |

---

## 11. Næste planlagte revision

Proceduren revideres mindst én gang årligt og ved enhver væsentlig ændring i Tjenesten, lovgivningen eller praksis fra tilsynsmyndigheden.

**Næste planlagte revision:** 2027-05-03
