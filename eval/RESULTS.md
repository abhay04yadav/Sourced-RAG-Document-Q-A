# Retrieval evaluation results

Measures retrieval quality (hit@k on `expected_keywords`) on a large Harry
Potter omnibus PDF. Higher is better. Run with:

```
backend\venv\Scripts\python.exe eval\run_eval.py --mode baseline
backend\venv\Scripts\python.exe eval\run_eval.py --mode hybrid
backend\venv\Scripts\python.exe eval\run_eval.py --mode full
```

`baseline` = single dense vector top-k (pre-upgrade).
`hybrid` = multi-query dense + Postgres FTS fused with RRF.
`full` = hybrid candidates re-ranked by the cross-encoder.

### Run 1 — 2026-10-16

Document: `harrypotter.pdf` (3623 pages, 1682 chunks, BGE-small embeddings).
15 answerable questions. **Query rewriting was off** (no LLM API key set),
so "hybrid" here = 1 dense list + 1 FTS list fused with RRF. CPU only.

| Pipeline                         | hit@1 | hit@3 | hit@5 | hit@12 | mean latency |
|----------------------------------|:-----:|:-----:|:-----:|:------:|:------------:|
| baseline (dense top-k)           | 73.3% | 80.0% | 80.0% |  80.0% |   423 ms     |
| + hybrid (dense + FTS + RRF)     | 66.7% | 80.0% | 86.7% |  86.7% |   875 ms     |
| + cross-encoder rerank (full)    | 80.0% | 86.7% | 86.7% | 100.0% |  7598 ms     |

Observations:
- Hybrid fixed the exact-term miss `q12` ("disarm" → *Expelliarmus*) but
  pushed `q04` from rank 1 to rank 4, so hit@1 dipped. RRF widens recall;
  it doesn't sharpen the top.
- The reranker restores precision (hit@1 80%) and pulls the two
  hard narrative questions (`q11` basilisk, `q14` final duel) into the top 12.
- The reranker costs ~6.7 s per query on CPU — the main latency/quality
  trade-off to discuss, and a free-tier deploy risk.
- Caveats: one document, 15 questions, keyword-match scoring. Plan target is
  25 questions across 3 PDFs. Re-run with the API key to measure rewrites.

### Run 2 — 2026-10-16 (query rewriting ON, `gpt-4o-mini`, 2 rewrites)

Same document and questions as Run 1. Baseline has no LLM step, so it is unchanged.

| Pipeline                                | hit@1 | hit@3 | hit@5 | hit@12 | mean latency |
|-----------------------------------------|:-----:|:-----:|:-----:|:------:|:------------:|
| baseline (dense top-k)                  | 73.3% | 80.0% | 80.0% |  80.0% |   423 ms     |
| + hybrid + query rewrite                | 66.7% | 80.0% | 86.7% | 100.0% |  2625 ms     |
| + cross-encoder rerank (full pipeline)  | 80.0% | 86.7% | 86.7% | 100.0% |  6857 ms     |

Observations:
- Rewriting is a recall tool: hybrid hit@12 went 86.7% → 100% (q11, q14 now
  found), at ~1.7 s of extra latency for the LLM rewrite call.
- The reranker turns that recall into precision: hit@1 66.7% → 80% (q04, q10, q12
  promoted to rank 1).
- Remaining weak spot: q11/q14 are found but sit at rank 7, outside the top 5
  context. Candidates for improvement: larger `RAG_CONTEXT_K`, or a stronger
  reranker (`bge-reranker-base`).

Notes:
- The unanswerable question (`q16`) is excluded from hit metrics; use it to
  confirm the assistant refuses instead of hallucinating.
- Neighbor expansion improves answer completeness (adjacent context) but is not
  scored here because it reorders by document position rather than relevance.
