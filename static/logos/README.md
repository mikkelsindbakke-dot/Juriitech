# Selskabs-logoer

Drop selskabernes logoer her som PNG-filer. Filnavnet skal matche profil-keyen
i `selskab_profiler.py`:

| Selskab | Forventet filnavn          |
|---------|----------------------------|
| TUI     | `tui.png`                  |
| Spies   | `spies.png`                |
| Apollo  | `apollo.png`               |

## Krav til logo-filer

- **Format:** PNG (helst med transparent baggrund)
- **Bredde:** 200-400 pixels — bliver skaleret ned i Word til ca. 3.5 cm
- **Højde:** Maks 150 pixels (ellers kan headeren blive for høj)
- **Kvalitet:** Skarpt, ikke sløret. Vector-baseret kilde foretrækkes hvis muligt.

## Hvad sker der hvis filen mangler?

Svarbrevet renderes uden logo i top-højre — layoutet crasher ikke. Det betyder
også at man kan teste systemet uden at have logoer på plads endnu.

## Hvordan tilføjer jeg et nyt selskab?

1. Drop logoet her (fx `apollo.png`)
2. Tilføj entry til `SELSKAB_PROFILER` i `selskab_profiler.py`
3. (Når login er live: knyt email-domæne → profil-key)
