"""
Voyage AI embeddings-wrapper.

Bruges til at oversætte dansk juridisk tekst til 1024-dimensionelle vektorer,
så vi kan lave lynhurtig similarity-søgning i Postgres via pgvector.

Model: voyage-multilingual-2 (stærkeste multilingual embedding-model pr. 2025,
inkl. dansk). Output-dim: 1024.
"""

import os
from dotenv import load_dotenv
import voyageai

load_dotenv()

# Voyage-klienten læser VOYAGE_API_KEY fra miljøet automatisk,
# men vi initialiserer eksplicit for tydelighed og bedre fejlmeddelelser.
_API_KEY = os.getenv("VOYAGE_API_KEY")

MODEL = "voyage-multilingual-2"
DIMENSIONS = 1024

# Voyage har en maksgrænse på ~32.000 tokens pr. input. De fleste
# afgørelser fylder under dette, men vi trunkerer defensivt for at undgå
# fejl på ekstremt lange dokumenter.
MAX_CHARS_PER_DOC = 120_000  # ~30.000 tokens for dansk tekst


# ---------- LAZY KLIENT-INITIALISERING ----------
# KRITISK: Vi initialiserer IKKE Voyage-klienten ved modul-import.
# Hvis vi gjorde det, ville en ugyldig/manglende API-nøgle crashe hele
# appen ved opstart — ingen ville kunne bruge nogen del af PAX. I stedet
# opretter vi klienten første gang den faktisk skal bruges. Hvis den
# fejler, returnerer embed_*-funktionerne pænt None, og resten af appen
# (analyse, dashboard, anonymisering osv.) virker stadig — kun
# arkivsøgning degraderes midlertidigt.
_client = None
_client_init_fejlet = False


def _get_client():
    """Returnér Voyage-klienten. Initialiserer den lazily på første kald.
    Returnerer None hvis API-nøglen mangler eller klient-init fejler —
    kalderen skal håndtere None som 'embedding ikke tilgængelig'."""
    global _client, _client_init_fejlet
    if _client is not None:
        return _client
    if _client_init_fejlet:
        return None
    if not _API_KEY:
        print(
            "DEBUG: VOYAGE_API_KEY mangler — embeddings deaktiveret. "
            "Tilføj nøglen i Streamlit secrets for at genaktivere "
            "arkivsøgning."
        )
        _client_init_fejlet = True
        return None
    try:
        _client = voyageai.Client(api_key=_API_KEY)
        return _client
    except Exception as e:
        print(
            f"DEBUG: Voyage-klient kunne ikke initialiseres: {e}. "
            "Embeddings deaktiveret indtil næste app-restart."
        )
        _client_init_fejlet = True
        return None


def _truncate(text: str) -> str:
    if text is None:
        return ""
    if len(text) > MAX_CHARS_PER_DOC:
        return text[:MAX_CHARS_PER_DOC]
    return text


def embed_dokument(tekst: str):
    """
    Embedder én dokumenttekst (til lagring i databasen).
    Returnerer en liste af 1024 floats, eller None ved fejl.

    Bruger input_type='document' som Voyage anbefaler for ting
    der gemmes og senere søges imod.
    """
    if not tekst or not tekst.strip():
        return None
    client = _get_client()
    if client is None:
        return None
    try:
        result = client.embed(
            [_truncate(tekst)],
            model=MODEL,
            input_type="document",
        )
        return result.embeddings[0]
    except Exception as e:
        print(f"DEBUG: Voyage embed_dokument fejlede: {e}")
        return None


def embed_sporgsmaal(tekst: str):
    """
    Embedder et brugerspørgsmål (til søgning mod dokumenter).
    Returnerer en liste af 1024 floats, eller None ved fejl.

    Bruger input_type='query' som Voyage anbefaler for søgekald —
    det giver bedre matches mellem korte spørgsmål og lange dokumenter.
    """
    if not tekst or not tekst.strip():
        return None
    client = _get_client()
    if client is None:
        return None
    try:
        result = client.embed(
            [tekst],
            model=MODEL,
            input_type="query",
        )
        return result.embeddings[0]
    except Exception as e:
        print(f"DEBUG: Voyage embed_sporgsmaal fejlede: {e}")
        return None


# ---------- CHUNKING ----------
# Dokument-chunking forbedrer RAG-præcision dramatisk: i stedet for at
# embedde et helt 30-siders dokument til én vektor (der bliver et "gennemsnit"
# af alt indhold), splitter vi i bidder og embedder hver bid separat.
# Søgning returnerer så de mest relevante PARAGRAFFER — typisk de faktiske
# ræsonnement-stykker — frem for de mest "lignende" hele dokumenter.
#
# Til Pakkerejse-Ankenævn-afgørelser bruger vi en strukturbaseret split:
# vi forsøger først at splitte på de kendte sektion-overskrifter (som er
# ret konsistente). Hvis vi ikke kan finde nogen overskrifter (fx OCR-
# udtrukket tekst hvor formatering er røget), falder vi tilbage til en
# simpel paragraf/længde-baseret split.

CHUNK_TARGET_CHARS = 2_500     # ~600-700 tokens for dansk tekst
CHUNK_MAX_CHARS = 5_000        # hård øvre grænse hvis sektioner er ekstremt lange
CHUNK_MIN_CHARS = 250          # under dette merger vi op med næste/forrige chunk

# Kanoniske sektion-overskrifter i Pakkerejse-Ankenævnets afgørelser.
# Patterns matches case-insensitivt og som linje-anker. De fleste
# afgørelser har 5-8 af disse, hvilket giver en naturlig opdeling.
_SEKTION_OVERSKRIFTER = [
    r"Klagens?\s+indhold",
    r"Klagen\s+ang(å|aa)r",
    r"Sagen\s+ang(å|aa)r",
    r"Sagsfremstilling",
    r"Klagens?\s+kernepunkt(er)?",
    r"Klagens?\s+p(å|aa)stand(e)?",
    r"Klagepunkt(er)?",
    r"Indklagedes?\s+bem(æ|ae)rkninger",
    r"Indklagedes?\s+p(å|aa)stand(e)?",
    r"Indklagedes?\s+svar",
    r"Rejseselskabets?\s+bem(æ|ae)rkninger",
    r"N(æ|ae)vnets?\s+bem(æ|ae)rkninger\s+og\s+afg(ø|oe)relse",
    r"N(æ|ae)vnets?\s+bem(æ|ae)rkninger",
    r"N(æ|ae)vnets?\s+afg(ø|oe)relse",
    r"Afg(ø|oe)relse",
    r"Konklusion",
    r"Begrundelse",
    r"Hoved\s*sp(ø|oe)rgsm(å|aa)l(et)?",
]


def _split_paa_overskrifter(tekst: str):
    """
    Splitter tekst ved kanoniske sektion-overskrifter. Returnerer
    en liste af (overskrift, indhold)-tuples. Den første tuple kan
    have overskrift = '' (præambel-tekst før første overskrift).
    """
    import re as _re

    # Byg ét stort regex der matcher en linje der STARTER med en af
    # overskrifterne (evt. fulgt af kolon/punktum). Bruger MULTILINE
    # så ^ og $ matcher linje-grænser.
    pattern = (
        r"^[ \t]*(?P<overskrift>("
        + "|".join(_SEKTION_OVERSKRIFTER)
        + r"))[ \t]*[:.]?[ \t]*$"
    )
    regex = _re.compile(pattern, _re.IGNORECASE | _re.MULTILINE)

    matches = list(regex.finditer(tekst))
    if not matches:
        return []

    sektioner = []
    # Præambel: alt før første overskrift
    forste_start = matches[0].start()
    if forste_start > 0:
        praeambel = tekst[:forste_start].strip()
        if praeambel:
            sektioner.append(("", praeambel))

    # Hver sektion fra dens overskrift indtil næste overskrift
    for i, m in enumerate(matches):
        overskrift = m.group("overskrift").strip()
        indhold_start = m.end()
        indhold_slut = matches[i + 1].start() if i + 1 < len(matches) else len(tekst)
        indhold = tekst[indhold_start:indhold_slut].strip()
        if indhold:
            sektioner.append((overskrift, indhold))

    return sektioner


def _split_paa_paragraffer(tekst: str, target_chars: int):
    """
    Fallback-split når vi ikke kan finde sektion-overskrifter.
    Splitter på dobbelt-newlines (paragraffer), og samler så
    paragraffer op i bidder af cirka target_chars tegn.
    """
    paragraffer = [p.strip() for p in tekst.split("\n\n") if p.strip()]
    if not paragraffer:
        # Sidste udvej: hård split på faste afstande
        return [
            tekst[i:i + target_chars]
            for i in range(0, len(tekst), target_chars)
            if tekst[i:i + target_chars].strip()
        ]

    bidder = []
    aktuel = []
    aktuel_laengde = 0
    for p in paragraffer:
        # Hvis tilføjelse ville sprænge target_chars og vi allerede har
        # noget i den aktuelle bid, luk den og start en ny.
        if aktuel and aktuel_laengde + len(p) > target_chars:
            bidder.append("\n\n".join(aktuel))
            aktuel = [p]
            aktuel_laengde = len(p)
        else:
            aktuel.append(p)
            aktuel_laengde += len(p) + 2  # +2 for "\n\n"
    if aktuel:
        bidder.append("\n\n".join(aktuel))
    return bidder


def chunk_tekst(tekst: str, target_chars: int = CHUNK_TARGET_CHARS):
    """
    Splitter en afgørelses-tekst i chunks der hver kan embeddes
    separat. Returnerer en liste af dicts:
        [{"overskrift": str, "indhold": str, "chunk_index": int}, ...]

    Strategi:
      1. Forsøg at splitte på Pakkerejse-Ankenævnets kendte sektion-
         overskrifter ("Klagens indhold", "Nævnets bemærkninger og
         afgørelse" osv.). Det giver semantisk meningsfulde bidder.
      2. Hvis en sektion er længere end CHUNK_MAX_CHARS, split den
         videre på paragraffer.
      3. Hvis der ikke findes nogen overskrifter (fx ren OCR-tekst),
         fald tilbage til paragraf/længde-baseret split.
      4. Merge små bidder (< CHUNK_MIN_CHARS) ind i nabo-bidder.

    chunk_index er 0-baseret og bevarer rækkefølgen i originaldokumentet.
    """
    if not tekst or not tekst.strip():
        return []

    # ---- TRIN 1: Forsøg sektion-baseret split ----
    sektioner = _split_paa_overskrifter(tekst)

    if not sektioner:
        # ---- TRIN 1b: Fallback til paragraf-split ----
        bidder_raa = _split_paa_paragraffer(tekst, target_chars)
        sektioner = [("", b) for b in bidder_raa]

    # ---- TRIN 2: Split lange sektioner videre ----
    finkornet = []
    for overskrift, indhold in sektioner:
        if len(indhold) <= CHUNK_MAX_CHARS:
            finkornet.append((overskrift, indhold))
            continue
        # Sektionen er for lang — split den i paragraf-bidder, og bevar
        # overskriften som kontekst for hver bid.
        for sub in _split_paa_paragraffer(indhold, target_chars):
            finkornet.append((overskrift, sub))

    # ---- TRIN 3: Merge for små bidder ----
    # Når vi merger en lille sektion ind i den forrige, bevarer vi
    # dens overskrift inline i selve teksten — så Claude stadig kan
    # se at fx "Konklusion" begynder midt i chunkken.
    merged = []
    for overskrift, indhold in finkornet:
        if (
            merged
            and len(indhold) < CHUNK_MIN_CHARS
            and len(merged[-1][1]) + len(indhold) < CHUNK_MAX_CHARS
        ):
            prev_overskrift, prev_indhold = merged[-1]
            merge_blok = (
                f"\n\n{overskrift}\n{indhold}" if overskrift else f"\n\n{indhold}"
            )
            merged[-1] = (prev_overskrift, prev_indhold + merge_blok)
        else:
            merged.append((overskrift, indhold))

    # ---- TRIN 4: Format som dicts med chunk_index ----
    return [
        {
            "overskrift": overskrift,
            "indhold": indhold,
            "chunk_index": i,
        }
        for i, (overskrift, indhold) in enumerate(merged)
    ]


# ---------- RERANKER ----------
# Voyage rerank-2 er en cross-encoder der scorer hvor godt hver kandidat
# matcher querien. Vi bruger den som ANDET trin efter embedding-søgning:
# embedding finder ~30 muligvis-relevante chunks, reranker'en udvælger
# de 5-8 faktisk-relevante. Det giver markant højere præcision end ren
# vector-søgning kan klare alene.

RERANK_MODEL = "rerank-2"


def rerank(query: str, dokumenter: list, top_n: int = 10):
    """
    Reranker en liste af dokument-tekster mod en query.

    Argumenter:
      query       — spørgsmål/sagsbeskrivelse
      dokumenter  — liste af strenge (chunk-tekster der skal rerankes)
      top_n       — hvor mange topscorende der returneres

    Returnerer en liste af (index, score)-tuples sorteret faldende
    efter score, hvor index refererer til positionen i dokumenter-
    inputlisten. Hvis reranker fejler, returneres input-rækkefølgen
    (med score=None) som graceful fallback — kalderen kan så stadig
    bruge den oprindelige embedding-rangering.
    """
    if not query or not dokumenter:
        return []
    client = _get_client()
    if client is None:
        # Voyage utilgængelig — bevar embedding-rækkefølgen
        return [(i, None) for i in range(min(top_n, len(dokumenter)))]
    try:
        result = client.rerank(
            query=query,
            documents=dokumenter,
            model=RERANK_MODEL,
            top_k=min(top_n, len(dokumenter)),
        )
        # Voyage returnerer .results[*].index og .results[*].relevance_score
        return [
            (r.index, float(r.relevance_score))
            for r in result.results
        ]
    except Exception as e:
        print(f"DEBUG: Voyage rerank fejlede: {e} — bevarer input-rækkefølge")
        return [(i, None) for i in range(min(top_n, len(dokumenter)))]


def embed_batch(tekster: list):
    """
    Embedder flere dokumenter i ét kald (hurtigere og billigere ved bulk).
    Returnerer en liste af embedding-lister i samme rækkefølge som input.
    """
    if not tekster:
        return []
    client = _get_client()
    if client is None:
        return [None] * len(tekster)
    try:
        result = client.embed(
            [_truncate(t or "") for t in tekster],
            model=MODEL,
            input_type="document",
        )
        return result.embeddings
    except Exception as e:
        print(f"DEBUG: Voyage embed_batch fejlede: {e}")
        return [None] * len(tekster)
