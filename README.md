# Juriitech ⚖️

Juridisk AI-assistent til behandling af klagesager fra Pakkerejse-Ankenævnet.

## Hvad den gør

Juriitech automatiserer den tidskrævende del af rejseselskabers behandling af
klager til Pakkerejse-Ankenævnet:

- **Sagsupload** — hele sagspakken (ZIP med høringsbrev + klageskema + bilag)
  uploades på én gang, programmet pakker ud og læser alt
- **Tjekliste** — identificerer automatisk hvad Nævnet beder om, og hvilke
  bilag der er/mangler
- **Juridisk analyse** — strukturret analyse med referencer til tidligere
  afgørelser og rejseselskabets egne vilkår
- **Sandsynlighedsvurdering** — tre udfald (fuld medhold, delvist medhold,
  afvisning) med procenter og strategi-anbefaling
- **Svarbrev-generator** — komplet udkast til svarbrev i korrekt struktur
- **Anonymisering** — automatisk anonymisering af bilag efter Ankenævnets
  retningslinjer
- **Word-eksport** — alle outputs kan downloades som .docx
- **Arkiv** — alle analyser og svarbreve gemmes og kan findes igen

## Teknisk stack

- **Frontend:** Streamlit
- **Database:** Neon (PostgreSQL + pgvector til vektorsøgning)
- **AI:** Anthropic Claude (analyse + generering)
- **Embeddings:** Voyage AI (multilingual-2)
- **Scraping:** requests + BeautifulSoup

## Opsætning (lokalt udvikling)

1. Klon repo
2. Opret virtual environment og installér afhængigheder:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Opret `.env` med API-nøgler:
   ```
   DATABASE_URL=postgres://...
   ANTHROPIC_API_KEY=sk-ant-...
   VOYAGE_API_KEY=pa-...
   ADMIN_KEY=din-admin-noegle
   ```
4. Kør:
   ```bash
   streamlit run app.py
   ```

## Licens

Privat projekt. Alle rettigheder forbeholdes.
