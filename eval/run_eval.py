"""
RAG eval-runner.

Måler hvor godt PAX's RAG-pipeline finder kendt-relevante afgørelser
for et sæt kuraterede sager. Bruges som regression-test når vi tuner
chunking, top-K, rerank-input osv.

KØRSEL:
    python3 eval/run_eval.py
    python3 eval/run_eval.py --top-k 5      # default
    python3 eval/run_eval.py --top-k 10
    python3 eval/run_eval.py --json out.json   # gem resultater til fil

OUTPUT:
    Per case: precision@K, recall@K, fundne filnavne, manglende filnavne.
    Aggregeret: mean precision@K, mean recall@K på tværs af alle cases.

DEFINITION:
    For hver case har vi en query (klage-tekst) og en expected_filenames-
    liste (de afgørelser DER MINDST SKAL VÆRE I retrieval-resultatet).

    precision@K = |retrieved ∩ expected| / K
        Hvor mange af de K retrievede er faktisk relevante? Højt =
        systemet returnerer ikke meget irrelevant støj.

    recall@K = |retrieved ∩ expected| / |expected|
        Hvor mange af de relevante afgørelser fandt vi? Højt = vi
        misser ikke nogen kendte præcedenser.

    For RAG i præcedens-search er recall typisk vigtigere end precision —
    bedre at få lidt for meget med end at misse en relevant sag.

WORKFLOW:
    1. Kuratér 20-30 cases i eval/cases.json (start med dem fra dit arkiv
       hvor du KENDER hvilke afgørelser der er relevant).
    2. Kør eval ÉN gang for at få baseline.
    3. Lav en RAG-tuning-ændring (fx ændre TOP_K_CHUNKS_FINAL eller
       chunk-parametre).
    4. Kør eval igen.
    5. Sammenlign: gik mean precision@K op eller ned? Recall@K?
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Sørg for at projektet er på path så vi kan importere ai_engine, database osv.
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

# Lazy import — ai_engine trækker en del Streamlit-warnings når det importeres
# uden for streamlit-konteksten, men funktionerne virker fint.
from ai_engine import _hent_relevante_chunks_med_rerank  # noqa: E402


EVAL_DIR = PROJECT_ROOT / "eval"
DEFAULT_CASES = EVAL_DIR / "cases.json"           # Privat, gitignored
TEMPLATE_CASES = EVAL_DIR / "cases.example.json"  # Versioneret template


def _find_cases_fil(eksplicit_path: str | None):
    """
    Returnerer path til cases-fil. Prioritet:
      1. --cases <path> hvis brugeren har angivet det eksplicit
      2. eval/cases.json hvis den findes (privat, gitignored)
      3. eval/cases.example.json som fallback (med advarsel)

    Multi-tenant-bevidst: brugeren kan også angive
    eval/cases-tui.json eller cases-apollo.json osv. via --cases.
    """
    if eksplicit_path:
        p = Path(eksplicit_path)
        if not p.exists():
            print(f"❌ Cases-fil ikke fundet: {p}")
            sys.exit(1)
        return p
    if DEFAULT_CASES.exists():
        return DEFAULT_CASES
    if TEMPLATE_CASES.exists():
        print(
            "⚠️  eval/cases.json findes ikke. Falder tilbage til cases.example.json\n"
            "    (template med PLACEHOLDER-cases — kan ikke score noget).\n"
            "    For at lave en rigtig eval:\n"
            "      cp eval/cases.example.json eval/cases.json\n"
            "    og udfyld så cases-arrayet med rigtige sager fra DIT arkiv.\n"
            "    cases.json er gitignored — privat klient-data ender aldrig i git.\n"
        )
        return TEMPLATE_CASES
    print("❌ Hverken eval/cases.json eller eval/cases.example.json findes.")
    sys.exit(1)


def hent_cases(eksplicit_path: str | None = None):
    fil = _find_cases_fil(eksplicit_path)
    with fil.open() as f:
        data = json.load(f)
    cases = data.get("cases", [])
    # Frasortér placeholder-cases (id starter med EKSEMPEL-)
    rigtige = [c for c in cases if not c.get("id", "").startswith("EKSEMPEL-")]
    if not rigtige:
        print(
            f"⚠️  Alle cases i {fil.name} er stadig placeholders (EKSEMPEL-*).\n"
            "    Erstat dem med rigtige cases fra DIT arkiv før du kan måle noget.\n"
            "    Format: se kommentar-feltet i cases.example.json eller eval/README.md."
        )
        return []
    tenant = data.get("tenant_slug", "ukendt")
    print(f"📂 Læser {len(rigtige)} cases fra {fil.name} (tenant: {tenant})")
    return rigtige


def kør_case(case, top_k: int):
    """Kør én case gennem RAG-pipelinen og returnér metrics."""
    query = case["query"]
    expected = set(case["expected_filenames"])

    chunks = _hent_relevante_chunks_med_rerank(query)
    # Dedup på filnavn (samme afgørelse kan ramme flere chunks)
    retrieved_filnavne = []
    set_set = set()
    for c in chunks or []:
        fn = c.get("filnavn")
        if fn and fn not in set_set:
            set_set.add(fn)
            retrieved_filnavne.append(fn)
        if len(retrieved_filnavne) >= top_k:
            break

    retrieved_set = set(retrieved_filnavne)
    intersect = retrieved_set & expected

    precision = len(intersect) / top_k if top_k > 0 else 0.0
    recall = len(intersect) / len(expected) if expected else 0.0

    return {
        "id": case["id"],
        "description": case.get("description", ""),
        "expected": sorted(expected),
        "retrieved": retrieved_filnavne,
        "matched": sorted(intersect),
        "missing": sorted(expected - retrieved_set),
        "precision": precision,
        "recall": recall,
    }


def print_resultater(resultater, top_k: int):
    print()
    print("=" * 80)
    print(f"  RAG EVAL — top_k = {top_k}")
    print("=" * 80)

    for r in resultater:
        print()
        print(f"  📄 {r['id']}")
        print(f"     {r['description'][:70]}")
        print(f"     precision@{top_k}: {r['precision']:.2f}    "
              f"recall@{top_k}: {r['recall']:.2f}")
        if r["matched"]:
            print(f"     ✅ Fundet:   {', '.join(r['matched'])}")
        if r["missing"]:
            print(f"     ❌ Manglede: {', '.join(r['missing'])}")
        # Vis også de top-K filer der kom tilbage (selv hvis ikke i expected)
        støj = [f for f in r["retrieved"] if f not in set(r["expected"])]
        if støj:
            print(f"     ➕ Andre top-K: {', '.join(støj[:5])}")

    if resultater:
        mean_p = sum(r["precision"] for r in resultater) / len(resultater)
        mean_r = sum(r["recall"] for r in resultater) / len(resultater)
        print()
        print("-" * 80)
        print(f"  MEAN over {len(resultater)} cases — "
              f"precision@{top_k}: {mean_p:.3f}, recall@{top_k}: {mean_r:.3f}")
        print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Kør RAG-eval mod kuraterede cases")
    parser.add_argument("--top-k", type=int, default=5,
                        help="Antal retrieved filnavne pr. case (default 5)")
    parser.add_argument("--cases", type=str, default=None,
                        help="Sti til cases-fil. Default: eval/cases.json (gitignored), "
                             "fallback eval/cases.example.json. Brug fx "
                             "eval/cases-tui.json hvis du vil holde flere tenant-sæt adskilt.")
    parser.add_argument("--json", type=str, default=None,
                        help="Gem resultater som JSON til denne fil (gitignored hvis "
                             "filnavn matcher results-*.json)")
    args = parser.parse_args()

    cases = hent_cases(eksplicit_path=args.cases)
    if not cases:
        sys.exit(1)

    resultater = []
    for i, case in enumerate(cases, 1):
        print(f"⏳ [{i}/{len(cases)}] {case['id']}...", flush=True)
        r = kør_case(case, top_k=args.top_k)
        resultater.append(r)

    print_resultater(resultater, top_k=args.top_k)

    if args.json:
        out = {"top_k": args.top_k, "results": resultater}
        with open(args.json, "w") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Resultater gemt i {args.json}")


if __name__ == "__main__":
    main()
