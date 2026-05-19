"""
GDPR auto-anonymiserings-pipeline.

Hovedfunktioner:
- trigger_auto_anonymisering() — entry point for cron, finder rækker
  hvor anonymiseres_efter < NOW() og kører pipelinen
- anonymiser_sag(sag_id, tenant_id) — kerne-funktion per sag
- vurder_k_anonymitet(...) — k≥5 check før shared_patterns
- generer_anonymiserings_rapport(sag_id) — for audit-fremvisning

Pipeline-flow per sag:
1. Hent original-tekst + analyse fra DB (kun is_public=FALSE)
2. AI læser og genererer anonymiseret version (claude-sonnet-4-6)
3. Generaliser quasi-identifikatorer (datoer, beløb)
4. Vurder k-anonymitet via kategori-match — skal mønsteret deles?
5. Opdater DB i én transaktion:
   - Erstat indhold i mine_dokumenter med anonymiseret version
   - Re-generer embeddings fra anonymiseret tekst
   - Slet originale chunks, lav nye chunks fra anonymiseret tekst
   - Sæt anonymiserings_status = 'anonymiseret'
   - Hvis k≥5: indsæt i shared_patterns
6. Skriv audit-log-row

VIGTIGT: Modulet er IKKE aktiveret. Det kaldes hverken fra app eller cron.
Aktiveres først i Fase 4 når cron-trigger sættes op. Indtil da: tomgang.

Køres manuelt for test:
    python3 -c "from gdpr_pipeline import anonymiser_sag; \
                anonymiser_sag('test-sag-id', tenant_id=1)"
"""

import json
import os
import traceback
from datetime import datetime

from database import _connect, _decrypt_sql_expr, _decrypt_key_param


# ----------------------------------------------------------------------
# KONSTANTER
# ----------------------------------------------------------------------

# Anonymiseringsmodel — bruger samme som resten af appen for konsistens
AI_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

# Maks-tegn pr. AI-kald. Lange sager opdeles i chunks der anonymiseres
# separat og samles til sidst.
MAX_CHARS_PER_AI_CALL = 12000

# K-anonymitet tærskel. Et anonymiseret mønster må kun gemmes i den
# fælles pulje (shared_patterns) hvis der allerede findes ≥(K-1)
# lignende mønstre. Dvs. et nyt mønster med 4 lignende kandidater
# bringer total til 5 og er først da OK at dele.
K_ANONYMITET_TAERSKEL = 5

# Kategori-felter brugt til "lignende sag"-match. Skal være
# strukturerede værdier, ikke fri tekst.
KATEGORI_FELTER = ("sag_kategori", "udfald_kategori", "region")


# ----------------------------------------------------------------------
# AI-KLIENT (genbrugt fra ai_engine.py-mønstret)
# ----------------------------------------------------------------------

_anthropic_client = None
_anthropic_init_fejlet = False


def _get_anthropic():
    global _anthropic_client, _anthropic_init_fejlet
    if _anthropic_client is not None:
        return _anthropic_client
    if _anthropic_init_fejlet:
        return None
    try:
        import anthropic
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            print("DEBUG: ANTHROPIC_API_KEY mangler — pipeline disabled")
            _anthropic_init_fejlet = True
            return None
        _anthropic_client = anthropic.Anthropic(api_key=api_key)
        return _anthropic_client
    except Exception as e:
        print(f"DEBUG: Anthropic init fejlede: {e}")
        _anthropic_init_fejlet = True
        return None


# ----------------------------------------------------------------------
# AI-ANONYMISERING
# ----------------------------------------------------------------------

ANONYMISERING_SYSTEM_PROMPT = """\
Du er en juridisk anonymiseringsekspert under GDPR. Din opgave er at \
fjerne ALLE personhenførbare oplysninger fra en pakkerejse-klagesag \
så ingen rimelig indsats kan re-identificere de involverede personer. \
Det er ÆGTE anonymisering, ikke pseudonymisering.

REGLER (følg dem 100%):

1) Direkte identifikatorer FJERNES helt:
   - Navne på klagere, ledsagere, fuldmagtshavere → "[Klageren]", "[Ledsageren]"
   - Adresser, CPR-numre, e-mails, telefonnumre → fjernes
   - Sagsnumre fra Pakkerejse-Ankenævnet (fx "PA-2026-0142") → fjernes helt
   - Bilags-numre med personlige referencer → erstattes med "[Bilag X]"
   - Konto- og fakturanumre → fjernes

2) Quasi-identifikatorer GENERALISERES:
   - Specifikke datoer → måned/kvartal ("ferie i højsæson Q3 2025")
   - Specifikke hotel-navne → kategori ("4-stjernet hotel i Hurghada-området")
   - Beløb under 50.000 kr → afrund til nærmeste 1.000 kr
   - Beløb over 50.000 kr → afrund til nærmeste 5.000 kr
   - Familie-konstellation → "klager med familie" eller "klager alene"

3) Særlige kategorier (GDPR Art. 9) GENERALISERES MAKSIMALT:
   - Sundhedsoplysninger → "klager blev syg under opholdet" (ikke specifik diagnose)
   - Religiøse forhold → fjernes hvis ikke essentielt for sagen
   - Etnisk oprindelse → fjernes
   - Børns alder/oplysninger → fjernes eller maksimal generalisering

4) BEHOLD det der gør sagen meningsfuld som mønster:
   - Type af klage (rengøring, mad, sygdom, ankomst-overnatning osv.)
   - Generel destination (region: Egypten/Sydeuropa/etc., ikke specifikt sted)
   - Beløbskategori (under 5k / 5-15k / 15-50k / over 50k kr)
   - Udfald (medhold/delvist medhold/afvist)
   - Juridisk argumentation, lov-citater, præcedens

Returnér KUN gyldig JSON i dette format:
{
  "anonymiseret_tekst": "...",
  "fjernede_navne": antal_navne_fjernet,
  "generaliserede_datoer": antal_datoer,
  "generaliserede_beloeb": antal_beloeb,
  "generaliserede_lokationer": antal_lokationer,
  "fjernede_sagsnumre": antal_sagsnumre,
  "saerlig_kategori_handteret": antal_aart9_felter,
  "sag_kategori": "rengoering|mad|sygdom|ankomst|service|prisaffald|andet",
  "udfald_kategori": "medhold|delvist_medhold|afvist|forligt|ukendt",
  "region": "Egypten|Tyrkiet|Spanien|Graekenland|Italien|andet"
}
"""


def _ai_anonymiser_tekst(tekst):
    """Sender tekst til Claude og henter struktureret anonymiseret JSON.

    Returnerer dict med felterne fra ANONYMISERING_SYSTEM_PROMPT, eller
    None hvis AI-kaldet fejler (kalder skal fall-back).
    """
    client = _get_anthropic()
    if client is None:
        return None

    try:
        # Tool-use schema for struktureret output (samme mønster som
        # ai_engine.udled_foerstevurdering_struktureret)
        schema = {
            "type": "object",
            "properties": {
                "anonymiseret_tekst": {"type": "string"},
                "fjernede_navne": {"type": "integer"},
                "generaliserede_datoer": {"type": "integer"},
                "generaliserede_beloeb": {"type": "integer"},
                "generaliserede_lokationer": {"type": "integer"},
                "fjernede_sagsnumre": {"type": "integer"},
                "saerlig_kategori_handteret": {"type": "integer"},
                "sag_kategori": {"type": "string"},
                "udfald_kategori": {"type": "string"},
                "region": {"type": "string"},
            },
            "required": [
                "anonymiseret_tekst",
                "sag_kategori",
                "udfald_kategori",
                "region",
            ],
        }
        response = client.messages.create(
            model=AI_MODEL,
            max_tokens=8000,
            temperature=0,
            system=ANONYMISERING_SYSTEM_PROMPT,
            tools=[{
                "name": "anonymiser",
                "description": "Anonymiser tekst og returnér resultat",
                "input_schema": schema,
            }],
            tool_choice={"type": "tool", "name": "anonymiser"},
            messages=[
                {"role": "user", "content": tekst[:MAX_CHARS_PER_AI_CALL]}
            ],
        )
        for block in response.content:
            if block.type == "tool_use":
                return block.input
        return None
    except Exception as e:
        print(f"DEBUG: AI-anonymisering fejlede: {e}")
        return None


# ----------------------------------------------------------------------
# K-ANONYMITET
# ----------------------------------------------------------------------

def vurder_k_anonymitet(sag_kategori, udfald_kategori, region, conn=None):
    """Tæller eksisterende lignende mønstre i shared_patterns.

    Returnerer (k_count, maa_dele).

    k_count = antal eksisterende lignende mønstre + 1 (for det nye).
    maa_dele = True hvis k_count >= K_ANONYMITET_TAERSKEL.
    """
    own_conn = conn is None
    if own_conn:
        conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM shared_patterns
            WHERE sag_kategori = %s
              AND udfald_kategori = %s
              AND region = %s
        """, (sag_kategori, udfald_kategori, region))
        eksisterende = cur.fetchone()[0]
        cur.close()
        # +1 fordi det nye mønster ville bringe total til eksisterende+1
        k_count = eksisterende + 1
        return k_count, k_count >= K_ANONYMITET_TAERSKEL
    finally:
        if own_conn:
            conn.close()


# ----------------------------------------------------------------------
# AUDIT-LOG
# ----------------------------------------------------------------------

def skriv_audit(sag_id, tenant_id, handling, metadata=None, conn=None):
    """Wrapper omkring database.skriv_gdpr_audit der bevarer bagudkompatibel
    signatur for gdpr_pipeline-flowet. Pipeline-handlinger har ikke en
    bruger-kontekst (de kører i baggrund-scheduler), så user_id / email /
    ip er bevidst None her — det er korrekt: anonymisering er en system-
    handling, ikke en bruger-handling.

    For bruger-initierede audit-rows (login, view, eksport) skal callers
    bruge database.skriv_gdpr_audit direkte med user_id + user_email."""
    from database import skriv_gdpr_audit
    skriv_gdpr_audit(
        handling=handling,
        tenant_id=tenant_id,
        sag_id=sag_id,
        metadata=metadata,
        conn=conn,
    )


# ----------------------------------------------------------------------
# KERNE-PIPELINE
# ----------------------------------------------------------------------

def anonymiser_sag(sag_id, tenant_id, dry_run=False):
    """Hovedfunktion. Anonymiser én sag end-to-end.

    Args:
        sag_id: ID af sagen (matcher mine_dokumenter.id eller en
                kunde-given sag-identifier — afhænger af hvordan
                sager grupperes; her bruger vi mine_dokumenter.id)
        tenant_id: Tenant der ejer sagen
        dry_run: Hvis True, køres AI-anonymisering men intet skrives
                 til DB. Rapporten returneres så vi kan inspicere
                 outputtet før vi committer permanent. Koster stadig
                 Anthropic-credits (ca. $0.30-0.50 pr. kørsel) fordi
                 selve AI-kaldet udføres.

    Returns:
        dict med 'success' (bool) og enten 'rapport' (success-detaljer)
        eller 'fejl' (fejl-besked). I dry-run mode inkluderes også
        'anonymiseret_tekst' så du kan se output uden DB-skrivning.

    Pipelinen er TRANSAKTIONEL — hvis nogen del fejler, rollbackes alt
    og sagen forbliver i 'aktiv' state for retry næste cron-cyklus.
    """
    mode = "DRY-RUN" if dry_run else "LIVE"
    print(f"INFO: {mode} anonymiserer sag_id={sag_id} tenant_id={tenant_id}")

    conn = _connect()
    try:
        # Sæt isolation level — vi vil ikke have anden cron-instans
        # til at skrive til samme sag samtidig
        conn.set_isolation_level(2)  # SERIALIZABLE

        cur = conn.cursor()

        # 1. Hent sagens dokumenter.
        #
        # KRITISK: COALESCE mellem dekrypteret krypteret-kolonne og
        # plaintext-kolonnen. Hvis vi læser 'indhold' direkte er den NULL
        # for krypterede dokumenter (data ligger i indhold_krypteret), og
        # pipelinen fejler med "ingen meningsfuld tekst". Det var årsagen
        # til 19/20 fejlede i første dry-run.
        cur.execute(
            f"""
            SELECT id,
                   filnavn,
                   COALESCE(
                       CASE WHEN er_krypteret THEN
                           {_decrypt_sql_expr('indhold_krypteret')}
                       ELSE NULL END,
                       indhold
                   ) AS indhold,
                   dokumenttype
            FROM mine_dokumenter
            WHERE id = %s
              AND tenant_id = %s
              AND is_public = FALSE
              AND anonymiserings_status = 'aktiv'
            FOR UPDATE
            """,
            _decrypt_key_param() + (sag_id, tenant_id),
        )
        row = cur.fetchone()
        if row is None:
            return {
                "success": False,
                "fejl": (
                    "Sag findes ikke, er offentlig, eller "
                    "allerede anonymiseret"
                )
            }
        dok_id, filnavn, indhold, dokumenttype = row

        if not indhold or len(indhold.strip()) < 50:
            return {
                "success": False,
                "fejl": "Sag har ingen meningsfuld tekst at anonymisere"
            }

        # 2. Kør AI-anonymisering
        skriv_audit(
            str(dok_id), tenant_id,
            "anonymisering",
            {"step": "ai_call_start", "indhold_laengde": len(indhold)},
            conn=conn,
        )

        ai_resultat = _ai_anonymiser_tekst(indhold)
        if ai_resultat is None or not ai_resultat.get("anonymiseret_tekst"):
            conn.rollback()
            return {
                "success": False,
                "fejl": "AI-anonymisering fejlede — sag forbliver i 'aktiv'"
            }

        anonym_tekst = ai_resultat["anonymiseret_tekst"]
        sag_kategori = ai_resultat.get("sag_kategori", "andet")
        udfald = ai_resultat.get("udfald_kategori", "ukendt")
        region = ai_resultat.get("region", "andet")

        # 3. Re-generér embedding
        try:
            from embeddings import embed_dokument
            ny_embedding = embed_dokument(anonym_tekst)
        except Exception as e:
            print(f"DEBUG: Embedding-fejl: {e} — sag forbliver 'aktiv'")
            conn.rollback()
            return {
                "success": False,
                "fejl": f"Embedding fejlede: {e}",
            }

        # 4. Erstat indhold + embedding i mine_dokumenter, og ryd
        #    fil_bytes — vi holder ikke originale PDF/billede-bytes i
        #    hvile efter anonymisering (GDPR Art. 5 datasparsommelighed)
        cur.execute("""
            UPDATE mine_dokumenter
            SET indhold = %s,
                embedding = %s::vector,
                anonymiserings_status = 'anonymiseret',
                fil_bytes = NULL,
                fil_mime = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (anonym_tekst, ny_embedding, dok_id))

        # 5. Slet originale chunks for dokumentet, opret nye fra
        # anonymiseret tekst (tabellen hedder dokument_chunks med
        # kolonnerne dokument_id, chunk_index, overskrift, indhold, embedding)
        cur.execute(
            "DELETE FROM dokument_chunks WHERE dokument_id = %s",
            (dok_id,))

        try:
            from embeddings import chunk_tekst, embed_batch
            # chunk_tekst returnerer liste af dicts:
            # [{"overskrift": str, "indhold": str, "chunk_index": int}, ...]
            nye_chunks = chunk_tekst(anonym_tekst)
            if nye_chunks:
                # embed_batch tager liste af strings — ekstraher 'indhold'
                tekst_strings = [c.get("indhold", "") for c in nye_chunks]
                nye_embeddings = embed_batch(tekst_strings)
                for chunk_dict, emb in zip(nye_chunks, nye_embeddings):
                    cur.execute("""
                        INSERT INTO dokument_chunks
                        (dokument_id, chunk_index, overskrift, indhold,
                         embedding)
                        VALUES (%s, %s, %s, %s, %s::vector)
                    """, (
                        dok_id,
                        chunk_dict.get("chunk_index", 0),
                        chunk_dict.get("overskrift", "") or "",
                        chunk_dict.get("indhold", ""),
                        emb,
                    ))
        except Exception as e:
            # Chunk-genereringsfejl er ikke fatalt for anonymisering —
            # men log det. Hovedindholdet er allerede anonymiseret.
            print(f"DEBUG: Chunk re-generation fejlede: {e}")

        # 6. K-anonymitets-vurdering + evt. tilføjelse til shared_patterns
        k_count, maa_dele = vurder_k_anonymitet(
            sag_kategori, udfald, region, conn=conn)

        if maa_dele:
            cur.execute("""
                INSERT INTO shared_patterns
                (sag_kategori, udfald_kategori, region,
                 anonymiseret_tekst, embedding, k_count)
                VALUES (%s, %s, %s, %s, %s::vector, %s)
            """, (
                sag_kategori, udfald, region,
                anonym_tekst, ny_embedding, k_count
            ))

        # 7. Skriv audit-log-rapport
        rapport = {
            "anonymiseret_dato": datetime.utcnow().isoformat(),
            "fjernede_navne": ai_resultat.get("fjernede_navne", 0),
            "generaliserede_datoer":
                ai_resultat.get("generaliserede_datoer", 0),
            "generaliserede_beloeb":
                ai_resultat.get("generaliserede_beloeb", 0),
            "generaliserede_lokationer":
                ai_resultat.get("generaliserede_lokationer", 0),
            "fjernede_sagsnumre":
                ai_resultat.get("fjernede_sagsnumre", 0),
            "saerlig_kategori_handteret":
                ai_resultat.get("saerlig_kategori_handteret", 0),
            "sag_kategori": sag_kategori,
            "udfald_kategori": udfald,
            "region": region,
            "k_count": k_count,
            "delt_til_shared_patterns": maa_dele,
            "indhold_laengde_foer": len(indhold),
            "indhold_laengde_efter": len(anonym_tekst),
            "dry_run": dry_run,
        }

        if dry_run:
            # Ingen audit-log-skrivning, ingen commit — bare rul tilbage
            # alle ændringer og returnér rapport + anonymiseret tekst
            # så kalderen kan inspicere outputtet.
            conn.rollback()
            print(
                f"INFO: DRY-RUN færdig for sag_id={sag_id} — "
                f"intet skrevet til DB. k={k_count}"
            )
            return {
                "success": True,
                "rapport": rapport,
                "anonymiseret_tekst": anonym_tekst,
                "original_tekst_uddrag": indhold[:500],
            }

        skriv_audit(
            str(dok_id), tenant_id,
            "anonymisering",
            {"step": "afsluttet", "rapport": rapport},
            conn=conn,
        )

        conn.commit()
        cur.close()

        print(
            f"INFO: anonymisering OK for sag_id={sag_id}, "
            f"k={k_count}, delt={maa_dele}"
        )
        return {"success": True, "rapport": rapport}

    except Exception as e:
        conn.rollback()
        print(f"FEJL: anonymiser_sag({sag_id}) fejlede: {e}")
        traceback.print_exc()
        return {"success": False, "fejl": str(e)}
    finally:
        conn.close()


# ----------------------------------------------------------------------
# ANALYSE_ARKIV — anonymisering
# ----------------------------------------------------------------------

def anonymiser_arkiv_entry(arkiv_id, tenant_id, dry_run=False):
    """Anonymiserer én række i analyse_arkiv.

    Analyse_arkiv-rækker indeholder AI-genererede analyser og svarbreve
    der typisk citerer klagers navn, sagsnummer, beløb og datoer. Vi
    anonymiserer 'indhold' + 'spoergsmaal' + 'sagsakter' + 'ekstra_instrukser'
    samlet, så semantikken bevares (de hører til samme sag).

    Args:
        arkiv_id: analyse_arkiv.id
        tenant_id: ejende tenant
        dry_run: hvis True skrives intet til DB

    Returns:
        dict med 'success' og 'rapport' eller 'fejl'.
    """
    mode = "DRY-RUN" if dry_run else "LIVE"
    print(f"INFO: {mode} anonymiserer arkiv_id={arkiv_id} tenant_id={tenant_id}")

    conn = _connect()
    try:
        conn.set_isolation_level(2)  # SERIALIZABLE
        cur = conn.cursor()

        # Lock + fetch.
        # COALESCE-mønstret: hvis er_krypteret=TRUE læses dekrypteret
        # data fra _krypteret-kolonnerne, ellers fra plaintext-fallback.
        # Vi sender ENCRYPTION_KEY 4 gange (én pr. felt) som SQL-params.
        nøgle_param = _decrypt_key_param()
        cur.execute(
            f"""
            SELECT id, titel, type, klage_filnavn,
                   COALESCE(
                       CASE WHEN er_krypteret THEN
                           {_decrypt_sql_expr('spoergsmaal_krypteret')}
                       ELSE NULL END,
                       spoergsmaal
                   ) AS spoergsmaal,
                   COALESCE(
                       CASE WHEN er_krypteret THEN
                           {_decrypt_sql_expr('sagsakter_krypteret')}
                       ELSE NULL END,
                       sagsakter
                   ) AS sagsakter,
                   COALESCE(
                       CASE WHEN er_krypteret THEN
                           {_decrypt_sql_expr('ekstra_instrukser_krypteret')}
                       ELSE NULL END,
                       ekstra_instrukser
                   ) AS ekstra_instrukser,
                   COALESCE(
                       CASE WHEN er_krypteret THEN
                           {_decrypt_sql_expr('indhold_krypteret')}
                       ELSE NULL END,
                       indhold
                   ) AS indhold
            FROM analyse_arkiv
            WHERE id = %s
              AND tenant_id = %s
              AND anonymiserings_status = 'aktiv'
            FOR UPDATE
            """,
            nøgle_param * 4 + (arkiv_id, tenant_id),
        )
        row = cur.fetchone()
        if row is None:
            return {
                "success": False,
                "fejl": "Arkiv-entry findes ikke eller er allerede anonymiseret",
            }
        ark_id, titel, type_, klage_filnavn, spoergsmaal, sagsakter, ekstra, indhold = row

        # Saml alle PII-felter i ét AI-kald så semantikken bevares.
        # Vi adskiller med tydelige markører så vi kan splitte resultatet
        # tilbage i de oprindelige felter.
        SEP = "\n\n===FELT-SKILLE===\n\n"
        samlet = (
            f"[INDHOLD]\n{indhold or ''}{SEP}"
            f"[SPOERGSMAAL]\n{spoergsmaal or ''}{SEP}"
            f"[SAGSAKTER]\n{sagsakter or ''}{SEP}"
            f"[EKSTRA_INSTRUKSER]\n{ekstra or ''}"
        )

        ai_resultat = _ai_anonymiser_tekst(samlet)
        if ai_resultat is None or not ai_resultat.get("anonymiseret_tekst"):
            conn.rollback()
            return {
                "success": False,
                "fejl": "AI-anonymisering fejlede — entry forbliver 'aktiv'",
            }

        anonym_samlet = ai_resultat["anonymiseret_tekst"]

        # Split tilbage. Hvis AI har "glemt" en sektion, falder vi tilbage
        # til original (sikrere end at miste data).
        def _hent_sektion(samlet_txt, navn, fallback):
            tag = f"[{navn}]"
            if tag not in samlet_txt:
                return fallback
            efter = samlet_txt.split(tag, 1)[1]
            # Stop ved næste sektion eller SEP
            for stop_tag in ("[INDHOLD]", "[SPOERGSMAAL]", "[SAGSAKTER]",
                             "[EKSTRA_INSTRUKSER]", SEP.strip()):
                if stop_tag != tag and stop_tag in efter:
                    efter = efter.split(stop_tag, 1)[0]
            return efter.strip() or fallback

        nyt_indhold = _hent_sektion(anonym_samlet, "INDHOLD", indhold or "")
        nyt_spoergsmaal = _hent_sektion(anonym_samlet, "SPOERGSMAAL", spoergsmaal or "")
        nyt_sagsakter = _hent_sektion(anonym_samlet, "SAGSAKTER", sagsakter or "")
        nyt_ekstra = _hent_sektion(anonym_samlet, "EKSTRA_INSTRUKSER", ekstra or "")

        rapport = {
            "anonymiseret_dato": datetime.utcnow().isoformat(),
            "fjernede_navne": ai_resultat.get("fjernede_navne", 0),
            "generaliserede_datoer": ai_resultat.get("generaliserede_datoer", 0),
            "generaliserede_beloeb": ai_resultat.get("generaliserede_beloeb", 0),
            "indhold_laengde_foer": len(indhold or ""),
            "indhold_laengde_efter": len(nyt_indhold),
            "dry_run": dry_run,
        }

        if dry_run:
            conn.rollback()
            return {
                "success": True,
                "rapport": rapport,
                "anonymiseret_indhold_uddrag": nyt_indhold[:500],
                "original_indhold_uddrag": (indhold or "")[:500],
            }

        # Live: opdater rækken og marker som anonymiseret. klage_filnavn
        # beholdes som-er fordi det er det filnavn brugeren genkender
        # sagen ved — det er ikke direkte PII medmindre selve filnavnet
        # er konstrueret med klagers navn (i givet fald håndteres det
        # nedstrøms).
        cur.execute("""
            UPDATE analyse_arkiv
            SET indhold = %s,
                spoergsmaal = %s,
                sagsakter = %s,
                ekstra_instrukser = %s,
                anonymiserings_status = 'anonymiseret'
            WHERE id = %s AND tenant_id = %s
        """, (nyt_indhold, nyt_spoergsmaal, nyt_sagsakter, nyt_ekstra,
              ark_id, tenant_id))

        skriv_audit(
            str(ark_id), tenant_id,
            "anonymisering",
            {"step": "arkiv_anonymiseret", "rapport": rapport},
            conn=conn,
        )
        conn.commit()
        cur.close()
        print(f"INFO: arkiv-anonymisering OK arkiv_id={arkiv_id}")
        return {"success": True, "rapport": rapport}

    except Exception as e:
        conn.rollback()
        print(f"FEJL: anonymiser_arkiv_entry({arkiv_id}) fejlede: {e}")
        traceback.print_exc()
        return {"success": False, "fejl": str(e)}
    finally:
        conn.close()


# ----------------------------------------------------------------------
# GEMTE_SAGER — TTL-based sletning
# ----------------------------------------------------------------------

def slet_gamle_gemte_sager(dry_run=False):
    """Sletter gemte_sager-rækker hvor slet_efter < NOW().

    Vi anonymiserer IKKE state_json fordi den indeholder base64-encoded
    fil-bytes og dybt-nestede AI-svar — for komplekst at meningsfuldt
    transformere. I stedet: TTL-based sletning så data ikke akkumuleres
    indefinitely.

    Default slet_efter er sat ved upload til NOW() + 90 dage (jf.
    database.opret_tabeller). Brugeren kan forlænge ved at åbne sagen
    igen (gem_sag_state) eller eksplicit slette via UI.

    Args:
        dry_run: hvis True returneres KUN listen af kandidater uden DELETE

    Returns:
        dict med 'antal_kandidater', 'antal_slettet', 'dry_run'.
    """
    mode = "DRY-RUN" if dry_run else "LIVE"
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, tenant_id, titel, oprettet_dato, slet_efter
            FROM gemte_sager
            WHERE slet_efter IS NOT NULL
              AND slet_efter < NOW()
            ORDER BY slet_efter ASC
        """)
        kandidater = cur.fetchall()
        print(
            f"INFO: {mode} slet_gamle_gemte_sager — "
            f"fandt {len(kandidater)} kandidater"
        )

        antal_slettet = 0
        if not dry_run:
            for sag_id, tenant_id, titel, oprettet, _slet_efter in kandidater:
                cur.execute("""
                    DELETE FROM gemte_sager
                    WHERE id = %s AND tenant_id = %s
                """, (sag_id, tenant_id))
                if cur.rowcount > 0:
                    antal_slettet += 1
                    # Audit-log sletningen så vi har en revisionsspor
                    skriv_audit(
                        str(sag_id), tenant_id,
                        "sletning",
                        {
                            "type": "gemte_sager_ttl",
                            "titel": titel,
                            "oprettet_dato": (
                                oprettet.isoformat() if oprettet else None
                            ),
                        },
                        conn=conn,
                    )
            conn.commit()

        cur.close()
        return {
            "antal_kandidater": len(kandidater),
            "antal_slettet": antal_slettet,
            "dry_run": dry_run,
        }
    except Exception as e:
        conn.rollback()
        print(f"FEJL: slet_gamle_gemte_sager fejlede: {e}")
        traceback.print_exc()
        return {"antal_kandidater": 0, "antal_slettet": 0, "fejl": str(e)}
    finally:
        conn.close()


# ----------------------------------------------------------------------
# CRON-ENTRY POINT
# ----------------------------------------------------------------------

def trigger_auto_anonymisering(maks_per_kørsel=20, dry_run=False,
                                inkluder_arkiv=True,
                                inkluder_gemte_sager=True):
    """Find data der er klar til anonymisering/sletning og kør pipelinen.

    Dækker tre tabeller:
      1. mine_dokumenter — AI-anonymisering af klage-tekst
      2. analyse_arkiv — AI-anonymisering af AI-genererede analyser/svarbreve
      3. gemte_sager — TTL-baseret sletning (90 dage default)

    Kaldes hver time af cron via gdpr_cron_runner.py.

    Args:
        maks_per_kørsel: Maks antal per type pr. cron-cyklus.
        dry_run: hvis True, intet skrives til DB
        inkluder_arkiv: hvis False springes analyse_arkiv over (kan
                        bruges hvis arkivet skal beholdes længere af
                        forretningshensyn)
        inkluder_gemte_sager: hvis False springes gemte_sager-sletning over

    Returns:
        Dict med tællere for alle tre faser.
    """
    mode = "DRY-RUN" if dry_run else "LIVE"
    samlet = {"dry_run": dry_run, "mode": mode}

    # ─── 1) mine_dokumenter ───
    conn = _connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, tenant_id
        FROM mine_dokumenter
        WHERE anonymiserings_status = 'aktiv'
          AND is_public = FALSE
          AND anonymiseres_efter < NOW()
          AND tenant_id IS NOT NULL
        ORDER BY anonymiseres_efter ASC
        LIMIT %s
    """, (maks_per_kørsel,))
    dok_rows = cur.fetchall()
    cur.close()
    conn.close()
    print(f"INFO: {mode} mine_dokumenter — fandt {len(dok_rows)} sager")

    dok_lykkedes = dok_fejlede = 0
    for sag_id, tenant_id in dok_rows:
        result = anonymiser_sag(sag_id, tenant_id, dry_run=dry_run)
        if result["success"]:
            dok_lykkedes += 1
        else:
            dok_fejlede += 1
    samlet["mine_dokumenter"] = {
        "foersogt": len(dok_rows),
        "lykkedes": dok_lykkedes,
        "fejlede": dok_fejlede,
    }

    # ─── 2) analyse_arkiv ───
    if inkluder_arkiv:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, tenant_id
            FROM analyse_arkiv
            WHERE anonymiserings_status = 'aktiv'
              AND anonymiseres_efter < NOW()
              AND tenant_id IS NOT NULL
            ORDER BY anonymiseres_efter ASC
            LIMIT %s
        """, (maks_per_kørsel,))
        arkiv_rows = cur.fetchall()
        cur.close()
        conn.close()
        print(f"INFO: {mode} analyse_arkiv — fandt {len(arkiv_rows)} entries")

        ark_lykkedes = ark_fejlede = 0
        for ark_id, tenant_id in arkiv_rows:
            result = anonymiser_arkiv_entry(ark_id, tenant_id, dry_run=dry_run)
            if result["success"]:
                ark_lykkedes += 1
            else:
                ark_fejlede += 1
        samlet["analyse_arkiv"] = {
            "foersogt": len(arkiv_rows),
            "lykkedes": ark_lykkedes,
            "fejlede": ark_fejlede,
        }
    else:
        samlet["analyse_arkiv"] = {"sprunget_over": True}

    # ─── 3) gemte_sager ───
    if inkluder_gemte_sager:
        result = slet_gamle_gemte_sager(dry_run=dry_run)
        samlet["gemte_sager"] = result
    else:
        samlet["gemte_sager"] = {"sprunget_over": True}

    return samlet


# ----------------------------------------------------------------------
# RAPPORTERING
# ----------------------------------------------------------------------

def generer_anonymiserings_rapport(sag_id, tenant_id):
    """Hent anonymiserings-rapport for en specifik sag.

    Returns:
        Dict med rapport-felter, eller None hvis sagen ikke findes
        eller ikke er anonymiseret endnu.
    """
    conn = _connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT metadata, tidspunkt
        FROM gdpr_audit_log
        WHERE sag_id = %s
          AND tenant_id = %s
          AND handling = 'anonymisering'
          AND metadata->>'step' = 'afsluttet'
        ORDER BY tidspunkt DESC
        LIMIT 1
    """, (str(sag_id), tenant_id))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row is None:
        return None
    metadata, tidspunkt = row
    rapport = metadata.get("rapport", {}) if metadata else {}
    rapport["audit_tidspunkt"] = (
        tidspunkt.isoformat() if tidspunkt else None
    )
    return rapport


# ----------------------------------------------------------------------
# CLI til manuel test
# ----------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    if dry_run:
        args.remove("--dry-run")

    if len(args) == 2:
        sag_id = int(args[0])
        tenant_id = int(args[1])
        print(json.dumps(
            anonymiser_sag(sag_id, tenant_id, dry_run=dry_run),
            indent=2, default=str
        ))
    elif len(args) == 0:
        # Ingen sag-id: kør trigger_auto_anonymisering på alle ventende
        print(json.dumps(
            trigger_auto_anonymisering(dry_run=dry_run),
            indent=2, default=str
        ))
    else:
        print("Bruges:")
        print("  python3 gdpr_pipeline.py [--dry-run]                 # alle ventende sager")
        print("  python3 gdpr_pipeline.py [--dry-run] <sag_id> <tenant_id>  # én bestemt sag")
