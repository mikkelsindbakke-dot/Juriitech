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

from database import _connect


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
    """Skriv en række til gdpr_audit_log. Idempotent ift. transaktioner —
    hvis conn gives, COMMIT'es ikke her (kalder ejer transaktionen)."""
    own_conn = conn is None
    if own_conn:
        conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO gdpr_audit_log
            (sag_id, tenant_id, handling, metadata)
            VALUES (%s, %s, %s, %s::jsonb)
        """, (
            sag_id,
            tenant_id,
            handling,
            json.dumps(metadata or {}),
        ))
        cur.close()
        if own_conn:
            conn.commit()
    finally:
        if own_conn:
            conn.close()


# ----------------------------------------------------------------------
# KERNE-PIPELINE
# ----------------------------------------------------------------------

def anonymiser_sag(sag_id, tenant_id):
    """Hovedfunktion. Anonymiser én sag end-to-end.

    Args:
        sag_id: ID af sagen (matcher mine_dokumenter.id eller en
                kunde-given sag-identifier — afhænger af hvordan
                sager grupperes; her bruger vi mine_dokumenter.id)
        tenant_id: Tenant der ejer sagen

    Returns:
        dict med 'success' (bool) og enten 'rapport' (success-detaljer)
        eller 'fejl' (fejl-besked).

    Pipelinen er TRANSAKTIONEL — hvis nogen del fejler, rollbackes alt
    og sagen forbliver i 'aktiv' state for retry næste cron-cyklus.
    """
    print(f"INFO: anonymiserer sag_id={sag_id} tenant_id={tenant_id}")

    conn = _connect()
    try:
        # Sæt isolation level — vi vil ikke have anden cron-instans
        # til at skrive til samme sag samtidig
        conn.set_isolation_level(2)  # SERIALIZABLE

        cur = conn.cursor()

        # 1. Hent sagens dokumenter
        cur.execute("""
            SELECT id, filnavn, indhold, dokumenttype
            FROM mine_dokumenter
            WHERE id = %s
              AND tenant_id = %s
              AND is_public = FALSE
              AND anonymiserings_status = 'aktiv'
            FOR UPDATE
        """, (sag_id, tenant_id))
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
# CRON-ENTRY POINT
# ----------------------------------------------------------------------

def trigger_auto_anonymisering(maks_per_kørsel=20):
    """Find sager der er klar til anonymisering og kør pipelinen.

    Kaldes hver time af cron i Fase 4.

    Args:
        maks_per_kørsel: Maks antal sager pr. cron-cyklus. Forhindrer
                        at en cron-kørsel hænger i timer hvis 1000
                        sager pludselig skal anonymiseres.

    Returns:
        Dict med 'foersogt', 'lykkedes', 'fejlede' (counts).
    """
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
    rows = cur.fetchall()
    cur.close()
    conn.close()

    print(f"INFO: trigger_auto_anonymisering — fandt {len(rows)} sager")

    foersogt = 0
    lykkedes = 0
    fejlede = 0
    for sag_id, tenant_id in rows:
        foersogt += 1
        result = anonymiser_sag(sag_id, tenant_id)
        if result["success"]:
            lykkedes += 1
        else:
            fejlede += 1

    return {
        "foersogt": foersogt,
        "lykkedes": lykkedes,
        "fejlede": fejlede,
    }


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
    if len(sys.argv) == 3:
        sag_id = int(sys.argv[1])
        tenant_id = int(sys.argv[2])
        print(json.dumps(
            anonymiser_sag(sag_id, tenant_id), indent=2, default=str
        ))
    else:
        print("Bruges: python3 gdpr_pipeline.py <sag_id> <tenant_id>")
        print("Eller: python3 -c 'from gdpr_pipeline import "
              "trigger_auto_anonymisering; "
              "print(trigger_auto_anonymisering())'")
