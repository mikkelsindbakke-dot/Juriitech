# GDPR cron-setup på Fly.io

**Status:** Klar — IKKE aktiveret. Brugeren skal manuelt køre kommandoer nedenfor.

## Hvad cron-jobbet gør

Hver time:
1. Finder alle rækker i `mine_dokumenter` hvor `anonymiserings_status='aktiv'` AND `is_public=FALSE` AND `anonymiseres_efter < NOW()`
2. Kører `gdpr_pipeline.anonymiser_sag()` på op til 20 sager pr. cyklus
3. Skriver resultater til Fly logs

## Aktiveringskommando (kør manuelt)

```bash
fly machine run \
    --app pax-juriitech \
    --schedule hourly \
    --no-public-ips \
    --region fra \
    python3 gdpr_cron_runner.py
```

Hvis det er første gang du sætter scheduled machines op, så tjek først:
```bash
fly machines list -a pax-juriitech
```

## Verifikation efter aktivering

Kør efter første time:
```bash
fly logs -a pax-juriitech | grep "GDPR cron-runner"
```

Forventet output: `=== GDPR cron-runner kørt YYYY-MM-DDTHH:MM:SS UTC ===` plus JSON med counts.

## Hvis du vil teste manuelt FØR aktivering af cron

```bash
# Lokalt:
cd /Users/mikkelhansen/Desktop/juridisk_assistent
python3 gdpr_cron_runner.py

# Eller på Fly machine:
fly ssh console -a pax-juriitech
cd /app
python3 gdpr_cron_runner.py
```

## Hvis du vil deaktivere cron'en igen

```bash
fly machines list -a pax-juriitech | grep "schedule"
fly machine destroy <machine-id> -a pax-juriitech
```

## Estimeret omkostning

- 20 sager / time × 24 timer / dag = max 480 sager / dag
- Anthropic Claude Sonnet: ca. $0.10-0.50 pr. sag (afhænger af tekstlængde)
- Voyage embeddings: ~$0.001 pr. sag
- **Worst case: $48-240 / dag** (hvis 480 sager hver dag — meget usandsynligt)
- **Forventet realistisk: $5-50 / dag** ved normalt brug

## Anbefalede skridt

1. Test pipelinen MANUELT på 1 sag først:
   ```bash
   python3 -c "from gdpr_pipeline import anonymiser_sag; \
               print(anonymiser_sag(<sag_id>, <tenant_id>))"
   ```
2. Verificer i Supabase at sagen er anonymiseret korrekt
3. Verificer audit-log-entry findes
4. Hvis OK → kør `migration_gdpr_aktiver_eksisterende.py --dry-run` for at se hvor mange sager der vil blive markeret
5. Hvis tallet er rimeligt → kør uden `--dry-run`
6. Aktivér cron med kommandoen ovenfor
7. Tjek Fly logs næste time for at se cron-output
