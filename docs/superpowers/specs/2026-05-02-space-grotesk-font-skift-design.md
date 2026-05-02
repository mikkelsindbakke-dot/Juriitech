# Skift fra Inter til Space Grotesk

**Status:** Spec, godkendt 2026-05-02
**Repos berørt:** `juridisk_assistent` (PAX) + `juriitech-landing` (portal/forside)

## Mål

Erstatte den nuværende sans-serif-font (Inter) med **Space Grotesk** for at give juriitech PAX og juriitech.com en mere distinkt brand-følelse, der minder om Anthropic Sans / Styrene B (det Claude.ai bruger). Source Serif 4 bevares til serif-blokke (citater, særlige sektion-overskrifter).

Begrundelse: Inter er en glimrende UI-font men neutral og generisk. Space Grotesk er gratis (OFL-licens på Google Fonts), eksplicit Styrene-inspireret af Florian Karsten, og scorer 72% similarity til Styrene ifølge FontAlternatives. Det giver brand-konsistens med inspirations-kilden uden licensomkostning.

## Tekniske ændringer

### Filer berørte (PAX-repo)

| Fil | Indhold |
| --- | --- |
| `app.py` | font-family + weight-værdi i fejl-box markup |
| `forside.py` | Inter `@import` + 16+ font-family-deklarationer + 8 weight=800-steder |
| `arkiv.py` | Inter `@import` + font-family + weight=800-sted |
| `disclaimer.py` | Inter `@import` + font-family-deklarationer |
| `gemte_sager.py` | Inter `@import` + font-family-deklarationer |
| `ui.py` | font-family-deklarationer i delte komponenter |
| `vurdering.py` | font-weight=900-sted |

### Filer berørte (landing-repo)

| Fil | Indhold |
| --- | --- |
| `styles.css` | Inter `@import` (i HTML) + 11 font-family-deklarationer + weight=800/900 |
| `index.html` | Google Fonts `<link>`-tag |
| `login.html` | Google Fonts `<link>`-tag |
| `dashboard.html` | Google Fonts `<link>`-tag |

### Konkret transformation

**Google Fonts loading (PAX):**
```diff
- @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Source+Serif+4:...&display=swap');
+ @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=Source+Serif+4:...&display=swap');
```

**Google Fonts loading (landing):**
```diff
- <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700;800;900&display=swap" rel="stylesheet">
+ <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&display=swap" rel="stylesheet">
```

**font-family deklarationer (overalt):**
```diff
- font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
+ font-family: 'Space Grotesk', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
```

### Weight-mapping (Space Grotesk maxer ved 700)

Space Grotesk har weights 300, 400, 500, 600, 700. Ingen 800 eller 900. Konkret håndtering:

- `font-weight: 800` → `font-weight: 700` (overalt — wordmark, dashboard-headings, badges)
- `font-weight: 900` → `font-weight: 700` (kun 2 steder: vurdering.py + styles.css)

Wordmarket "juriitech" på landing-siden vil blive ~10% lettere visuelt (700 vs 800), men Space Grotesk's bold er kraftig pga. fontens squarish-karakter — det er stadig markant. Hvis det viser sig ikke at være kraftigt nok, kan vi senere tilføje `letter-spacing: -0.06em` for at kompensere visuelt.

### Bevaret uændret

- `Source Serif 4` (serif-font til citater, sektion-headings i forside-cards, specifikke quote-blokke) — beholdes 1:1
- `SF Mono / Menlo / Consolas` (monospace til code-blokke) — beholdes 1:1
- Alle fallback-chains efter primary-fonten (`-apple-system, BlinkMacSystemFont, ...`)
- Streamlit `config.toml` `font = "sans serif"` — beholdes (det er kategorisk default, ikke specifik font)

## Eksplicit ude af scope

- Skift af serif-fonten Source Serif 4 til Tiempos Text (Anthropic's serif-valg). Tiempos er kommerciel — ikke prioritet nu.
- Custom @font-face self-hosting for hastighed. Google Fonts CDN er fint for nu (caching virker).
- Ændring af font-størrelser eller line-height. Kun font-FAMILY skiftes — proportioner forbliver.
- Inter Display eller Inter Tight som alternativ. Vi vælger ÉN sans-serif (Space Grotesk).

## Test

Manuel browser-smoke-test efter deploy:

1. **juriitech.com forside**: Wordmark "juriitech" rendres i Space Grotesk (lidt mere kvirky end Inter's smoothness — j'et skiller sig ud, t'et har firkantede ender). Ingen FOUT (flash of unstyled text) ved load.
2. **juriitech.com login + dashboard**: Tekst i forms, knapper, headings — alt i Space Grotesk.
3. **PAX (cold load + login)**: Sidebar-nav, body-tekst, headings — alt i Space Grotesk. Source Serif 4 stadig synlig i quote-blokke + section-headings inde i cards.
4. **PAX disclaimer-side**: Body-tekst og headings i Space Grotesk; den fede sidste sætning er stadig fed (weight 700 i stedet for 800).
5. **PAX forside efter analyse**: Dashboard med store tal/badges — sammenlign vægt-følelse mod tidligere screenshot for at sikre wordmark-lighed.
6. **Browser-fanenavn + browser-titel**: Ikke berørt af font-skift (system-font).

## Beslutnings-historie

- **2026-05-02:** Bruger spurgte efter font-anbefaling der ligner Anthropic Sans. Research viste Anthropic bruger Styrene B (kommerciel, ~$200-400). Bruger valgte gratis alternativ. Min anbefaling: Space Grotesk (72% Styrene-similarity, OFL-gratis, eksplicit Styrene-inspireret). Bruger godkendte uden ændringer. Option valgt: Space Grotesk overalt + behold Source Serif 4 til specifikke serif-blokke (matcher claude.ai's "Styrene B + Tiempos serif"-setup).
