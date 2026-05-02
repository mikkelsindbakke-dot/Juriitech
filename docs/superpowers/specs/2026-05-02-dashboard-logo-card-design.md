# Dashboard PAX-kort: full-bleed logo

**Status:** Spec, godkendt 2026-05-02
**Repo berørt:** `juriitech-landing`

## Mål

Erstat det nuværende PAX-program-kort på `juriitech.com/dashboard.html` (hvid baggrund + farvet ikon-firkant + titel + beskrivelse + sort "Åbn"-knap) med en minimalistisk full-bleed udgave hvor det officielle PAX-logo udgør hele kortet.

## Brugerflow

1. Bruger lander på dashboard
2. Ser PAX-logoet (gult speech-bubble med "PAX" i sort, lille pointer nederst-højre) som det første kort i grid'et
3. Hovrer over → subtil zoom (scale 1.02) + cursor pointer
4. Klikker hvor som helst på logoet → SSO ind i PAX (som hidtil — `buildSsoUrl` flow)

Ingen titel, ingen beskrivelse, ingen knap. Logoet taler for sig selv.

## Tekniske ændringer

**Ny fil:**
- `juriitech-landing/pax-logo.png` — kopieret fra `~/Downloads/Gemini_Generated_Image_ipw4xripw4xripw4.png` (PNG, 2752×1536, RGBA, ~4.8 MB. Bruges direkte; vi optimerer ikke — Vercel håndterer compression)

**`dashboard.html`:**
- `PROGRAMMER`-array: erstat `farve: '#6366f1'` med `logo: '/pax-logo.png'`
- Kort-rendering: erstat hele `<article class="program-card">`-indholdet med kun `<img class="program-logo" src="${p.logo}" alt="${p.navn}">`
- Klik-handler: flyttes fra `.program-open-btn` (eksisterer ikke længere) til hele `kort`-elementet

**`styles.css`:**
- `.program-card`: fjern `background-color`, `border-radius`, `padding`, `box-shadow`, `border` (kortet har ingen visuel container — logoet ER kortet)
- `.program-card`: tilføj `cursor: pointer`, `transition: transform 0.15s ease`
- `.program-card:hover`: `transform: scale(1.02)` (erstat eksisterende shadow-hover)
- `.program-logo`: `width: 100%`, `height: auto`, `display: block`
- Slet ubrugte regler: `.program-icon`, `.program-card h2`, `.program-card p`, `.program-open-btn`, `.program-open-btn:hover`

## Eksplicit ude af scope

- "Velkommen, juriitech" → "Velkommen, Mikkel"-fix: ikke i denne iteration. Kan tilføjes som separat lille ændring senere.
- Optimering af PNG-størrelsen: 4.8 MB er stort, men Vercel komprimerer + browser cacher. Hvis det viser sig at give mærkbart langsom load, optimerer vi efter.
- SVG-version af logoet: PNG er fint for nu; SVG kunne overvejes hvis logoet bruges i mange forskellige størrelser.

## Test

Manuel browser-smoke-test efter deploy:
1. Forsiden loader normalt (intet ændret)
2. Login + dashboard → PAX-logoet vises som ENESTE element i kortet (ingen ramme, ingen tekst, ingen knap)
3. Hover på logoet → subtil scale-up
4. Klik på logoet → seamless SSO til PAX
5. Logo-billedet er ikke unaturligt strakt (aspect ratio bevaret, ca. 320×178 px ved single-column)

## Beslutnings-historie

- **2026-05-02:** Bruger godkendte option A (full-bleed logo som hele kortet) frem for option B (logo + bevaret titel/beskrivelse) eller C (logo som lille ikon). Begrundelse: minimalistisk, og logoet er distinkt nok til at programmet er genkendeligt uden tekst.
