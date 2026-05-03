# Auto-scraping af vidensbank — design

**Status:** Spec, godkendt 2026-05-03
**Repos berørt:** `juridisk_assistent` (PAX)

## Mål

Sikre at PAX's vidensbank altid er frisk uden at admin skal huske at trykke knapper. Tre kanaler skal auto-køre:

1. **Ved tenant-oprettelse**: når admin opretter eller opdaterer en tenant med `rejsevilkaar_kilde_url`, køres `vilkaar_scraper.py` automatisk i baggrunden — så nye selskaber får friske vilkår fra dag ét.
2. **Månedligt cron**: Pakkerejse-Ankenævnet — fanger nye afgørelser løbende.
3. **Månedligt cron**: alle tenants' rejsevilkår — fanger ændringer i selskabernes vilkår.

Manuelle knapper i admin-UI bevares som backup, men flytter til "kør hvis nødvendigt"-status.

## Tekniske ændringer

### 1. Auto-scrape ved tenant-oprettelse/-opdatering

**Fil:** `admin.py`

Når admin gemmer en tenant og `rejsevilkaar_kilde_url` er ny eller ændret:
- Vis spinner: "Henter rejsevilkår fra `<domæne>`..."
- Kald `scrape_vilkaar(tenant_slug, kilde_url)` synkront (typisk 30-90 sek.)
- Vis resultat: "Hentet 12 sider — 8 nye, 4 var allerede i databasen"
- Hvis fejl: vis fejl-besked, men gem stadig tenanten (vilkår kan altid scrapes manuelt senere)

**Beslutning:** Synkront, ikke baggrund — så admin ser fejl med det samme. Nem at debugge.

### 2. Månedligt cron — Pakkerejse-Ankenævnet

**Fil:** `scraper_runner_pa.py` (ny)

```python
"""Entry-point for månedlig Pakkerejse-Ankenævn-scraping."""
from scraper import scrape_og_gem_kendelser

def main():
    print(f"=== PA-scraper kørt {datetime.utcnow().isoformat()} ===")
    result = scrape_og_gem_kendelser(max_sager=100)
    print(json.dumps(result, indent=2, default=str))
```

**Fly aktiverings-kommando** (gemmes i [docs/superpowers/scraping_cron_setup.md](docs/superpowers/scraping_cron_setup.md)):

```bash
fly machine run \
    --app pax-juriitech \
    --schedule monthly \
    --region fra \
    --name pa-scraper-monthly \
    registry.fly.io/pax-juriitech:latest \
    python3 scraper_runner_pa.py
```

### 3. Månedligt cron — Alle tenants' rejsevilkår

**Fil:** `scraper_runner_vilkaar.py` (ny)

```python
"""Entry-point for månedlig re-scrape af alle tenants' vilkår."""
from database import hent_alle_tenants
from vilkaar_scraper import scrape_vilkaar

def main():
    tenants = hent_alle_tenants()
    for tenant in tenants:
        if not tenant.get("rejsevilkaar_kilde_url"):
            print(f"SKIP: {tenant['slug']} har ingen rejsevilkaar_kilde_url")
            continue
        result = scrape_vilkaar(
            tenant_slug=tenant["slug"],
            kilde_url=tenant["rejsevilkaar_kilde_url"],
        )
        print(f"{tenant['slug']}: {result}")
```

Fly aktiverings-kommando er parallel — månedligt schedule, separat machine.

### 4. Status-visning i admin-UI

I admin → Tenants-tab, ved siden af hver tenant: "Vilkår sidst hentet: X dage siden" baseret på maks `oprettet_dato` af rækker med `tenant_id=X` AND `dokumenttype='vilkaar'`. Giver admin synlighed.

## Eksplicit ude af scope

- **Diff-detektion ved re-scrape**: notification hvis vilkår er ændret væsentligt. Ville være en fed feature, men kompleks (sammenligning af tekstindhold). Senere.
- **Backup af PDF-blobs**: hvis Ankenævnet stopper offentliggørelse, vil vi gemme PDF-originalerne ved siden af teksten. Separat spec.
- **Manuel "scrape nu"-knap forsvinder**: knapperne bevares som backup. Men de flyttes evt. til admin-UI for at signalere at de normalt ikke er nødvendige.
- **Notifikationer ved scraping-fejl**: hvis månedlig kørsel fejler, vil admin opdage det først ved næste tenant-oprettelse eller via Fly logs. Sentry fanger fejl. Senere kan vi bygge en email-alert.

## Cost-vurdering

| Kilde | Frekvens | Estimeret cost/år |
| --- | --- | --- |
| PA månedlig auto | 12× | ~$1.50 |
| Vilkår månedlig auto (5 tenants) | 60× | ~$1.00 |
| Tenant-oprettelse engangs | per ny | ~$0.003/tenant |
| **Total** | | **~$2.50/år** |

Til sammenligning: i dag bruger systemet ~$5-50/dag på AI-analyse af klagesager. Auto-scraping er en marginal omkostning.

## Beslutnings-historie

- **2026-05-03 (kvartalsvis godkendt for begge):** Bruger valgte kvartalsvis frekvens for både PA og vilkår.
- **2026-05-03 (eskaleret til månedlig):** Fly understøtter kun `hourly/daily/weekly/monthly/yearly`. Månedlig valgt fordi (a) det er Fly's nærmeste, (b) cost-impact er trivielt (under $1 ekstra), (c) friskere data har værdi.
- **2026-05-03 (auto ved tenant-oprettelse):** Synkron scraping (ikke baggrund) når admin gemmer ny tenant — så fejl ses med det samme.
