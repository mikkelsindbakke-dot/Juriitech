# RAG eval-suite

Et lille framework til at måle RAG-kvaliteten i PAX **objektivt** før/efter ændringer.

## Hvorfor

PAX har 20+ hardcodede tal der styrer chunking og retrieval (`CHUNK_TARGET_CHARS`, `TOP_K_CHUNKS_EMBED`, `TOP_K_CHUNKS_FINAL`, RRF `k`, `MAX_CHARS_PR_CHUNK` osv.). Når vi ændrer dem ved vi ikke om systemet blev bedre eller værre — vi famler i blinde.

Eval-suiten lader os sige fx:
> "Før denne ændring var mean precision@5 = 0.65. Efter er den 0.72. Behold ændringen."

eller:
> "Recall@5 faldt fra 0.81 til 0.74. Roll back."

## Filer

- `cases.json` — kuraterede sager (klage-tekst + kendt-relevante afgørelser)
- `run_eval.py` — runner der bruger PAX's reelle RAG-pipeline (`_hent_relevante_chunks_med_rerank`)
- `README.md` — dette dokument

## Sådan tilføjer du en case

1. Find en sag i din arkiv-side eller i `analyse_arkiv` hvor du KENDER hvilke afgørelser der er præcedens.
2. Tilføj en ny entry i `cases.json`:

```json
{
  "id": "kort-stikordsnavn",
  "description": "Én linje om hvad sagen handler om",
  "query": "Kopi af klagens tekst eller en sammenfatning der ligner klage-tekst i daglig brug. Det er HER vi tester retrieval-kvaliteten.",
  "expected_filenames": [
    "20-1234.pdf",
    "21-5678.pdf"
  ],
  "notes": "Frivilligt — hvorfor disse filer er præcedens"
}
```

**Tips:**
- Brug 2-5 expected_filenames pr. case. Hvis du kun har 1, er signal/støj-forholdet for skrøbeligt.
- Brug ~20-30 cases i alt. Færre giver støjede resultater; flere bliver dyre at vedligeholde.
- Variér case-typer: aflyst rejse, flyforsinkelse, hotel-mangel, sygdom, manglende information, m.fl.

## Kør eval

```bash
# Default — top_k=5
python3 eval/run_eval.py

# Andre top_k værdier
python3 eval/run_eval.py --top-k 3
python3 eval/run_eval.py --top-k 10

# Gem resultater til fil for sammenligning over tid
python3 eval/run_eval.py --json eval/results-baseline.json
# ... lav en RAG-tuning-ændring ...
python3 eval/run_eval.py --json eval/results-after-tuning.json
diff eval/results-baseline.json eval/results-after-tuning.json
```

## Output

```
📄 flyforsinkelse-hotel
   Klage om flyforsinkelse hvor klager kræver hotel-omkostninger
   precision@5: 0.40    recall@5: 0.67
   ✅ Fundet:   20-1234.pdf, 21-5678.pdf
   ❌ Manglede: 22-9012.pdf
   ➕ Andre top-K: 19-aaaa.pdf, 23-bbbb.pdf, 18-cccc.pdf
```

## Metrics

- **precision@K**: andel af de retrievede filer der er relevante. Højt = lidt støj.
- **recall@K**: andel af de relevante filer der blev fundet. Højt = ingen kendt præcedens missed.

For PAX's brugscase (præcedens-search til jurister) er **recall typisk vigtigere end precision** — bedre at få lidt for meget med end at misse en kendt præcedens.

## Begrænsninger (skeleton-version)

- Måler kun retrieval-kvalitet, ikke kvaliteten af Claudes endelige svar.
- Bruger filnavn-matching, ikke sagsnummer-extraction (kunne tilføjes som bedre matching).
- Ingen statistisk signifikans-test — bare deterministisk sammenligning. Hvis cases er små eller varierende, kan resultater være lidt støjede.
- Kører alle cases sekventielt — for 30 cases tager det ~3-5 min (hver case kalder Voyage embeddings + rerank).

## Næste forbedringer (når der er tid)

- Sagsnummer-baseret matching (regex `\d{2}-\d+`) frem for ren filnavn-match
- Per-case timeout
- Statistisk signifikans-test ved sammenligning af to runs
- LLM-as-a-judge for end-to-end-kvalitet (svaret, ikke kun retrieval)
