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

Fill this table after running each mode against the same reprocessed document.

| Pipeline                         | hit@1 | hit@3 | hit@5 | hit@12 | mean latency |
|----------------------------------|:-----:|:-----:|:-----:|:------:|:------------:|
| baseline (dense top-k)           |       |       |       |        |              |
| + hybrid (dense + FTS + RRF)     |       |       |       |        |              |
| + cross-encoder rerank (full)    |       |       |       |        |              |

Notes:
- The unanswerable question (`q16`) is excluded from hit metrics; use it to
  confirm the assistant refuses instead of hallucinating.
- Neighbor expansion improves answer completeness (adjacent context) but is not
  scored here because it reorders by document position rather than relevance.
