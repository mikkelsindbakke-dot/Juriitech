# GDPR Fase 3: Anonymiserings-pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Bygge `gdpr_pipeline.py`-modulet der automatisk anonymiserer kunde-uploadede sager 24 timer efter analyse er færdig — fjerner alle personhenførbare oplysninger, re-genererer embeddings fra anonymiseret tekst, og bidrager (når k≥5) til den fælles cross-tenant pulje.

**Architecture:** Modulet eksponerer én entry point `trigger_auto_anonymisering()` som cron-jobbet kalder hver time (Fase 4). Funktionen finder rækker hvor `anonymiserings_status='aktiv'` AND `anonymiseres_efter < NOW()` AND `is_public=FALSE`, og kører pipelinen sekventielt på hver. Pipelinen er idempotent — sager der allerede er anonymiseret skippes.

**Tech Stack:** Python 3.11, Anthropic Claude (claude-sonnet-4-6) til AI-anonymisering, Voyage AI til re-embedding, psycopg2 til DB.

**Status:** Implementeret som STAND-ALONE modul, IKKE koblet til app eller cron. Sikker at have liggende i repo. Aktiveres først i Fase 4 når brugeren tilkobler cron.

---

## File Structure

- **Create:** `gdpr_pipeline.py` — hovedmodul
- **Create:** `test_gdpr_pipeline.py` — unit-tests for kerne-logik (k-anonymitet, generaliseringer)

## Forventede edge cases der ER håndteret

- Sag eksisterer men er allerede anonymiseret (status='anonymiseret') → skip
- Sag findes i `mine_dokumenter` men ikke i `chunks` → fortsæt anyway
- AI-anonymisering returnerer ugyldig JSON → fall-back til regex-baseret anonymisering
- Voyage embeddings fejler → behold gamle embeddings (slet ikke originalfilen!)
- Database-fejl midt i pipelinen → rollback transaction, behold original-data, retry næste cron-cyklus

## Forventede edge cases der IKKE er håndteret (kommer senere)

- Concurrent runs (to cron-jobs starter samtidig) — afhænger af deployment, kommer i Fase 4
- AI-anonymisering misser felter (hallucination) — kvartalsvis manuel revision (per spec)
- "Genoptaget sag" der allerede er anonymiseret — kunden re-uploader filerne (per design-beslutning)

## Implementation steps

Selve koden er i `gdpr_pipeline.py` — se kommentarer i koden for detaljeret forklaring af hver funktion. Plan-dokumentet her er introduktion + scope-deklaration.

## Eksplicit ude af scope

- Cron-trigger setup (Fase 4)
- Brugerflader til at se anonymiseringer (Fase 4)
- Migration af eksisterende `aktiv` sager til pipelinen (Fase 4)
- Service-role-separation for DB-access (Fase 4)
