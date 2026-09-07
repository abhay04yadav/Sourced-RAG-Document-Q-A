"""
Retrieval evaluation harness.

Runs each dataset question through a retrieval mode and reports hit@k, i.e. how
often a relevant chunk (matched by expected_keywords) appears in the top-k
retrieved chunks. This measures retrieval quality only — it does not call the
LLM — so it is cheap and repeatable.

Modes:
  baseline : single dense vector search (the pre-upgrade pipeline)
  hybrid   : multi-query dense + sparse fused with RRF
  full     : hybrid candidates re-ranked by the cross-encoder

Usage (from repo root or backend/):

    backend\\venv\\Scripts\\python.exe eval\\run_eval.py --mode full
    backend\\venv\\Scripts\\python.exe eval\\run_eval.py --mode baseline --document-id <uuid>

If --document-id is omitted, the newest document with status='ready' is used.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from sqlalchemy import text  # noqa: E402

from core.database import SessionLocal  # noqa: E402
from services.embedding_service import embed_queries, embed_query  # noqa: E402
from services.rag_service import dense_search, hybrid_search  # noqa: E402

_DATASET = Path(__file__).with_name("dataset.json")
_KS = [1, 3, 5, 12]


def _resolve_document_id(db, given: str | None) -> uuid.UUID:
    if given:
        return uuid.UUID(given)
    row = db.execute(
        text(
            "SELECT id FROM documents WHERE status = 'ready' "
            "ORDER BY created_at DESC LIMIT 1"
        )
    ).first()
    if row is None:
        raise SystemExit("No document with status='ready' found. Upload/reprocess first.")
    return row[0]


def _chunk_matches(chunk_text: str, keywords: list[str]) -> bool:
    body = chunk_text.lower()
    return all(kw.lower() in body for kw in keywords)


def _retrieve(db, doc_id, question: str, mode: str, max_k: int) -> list[dict]:
    """Return a ranked list of chunk dicts for the given mode."""
    if mode == "baseline":
        return dense_search(db, doc_id, embed_query(question), max_k)

    # hybrid / full share candidate generation
    from services.llm_service import rewrite_queries

    queries = rewrite_queries(question)
    qvecs = [embed_query(queries[0])]
    if len(queries) > 1:
        qvecs.extend(embed_queries(queries[1:]))

    candidates = hybrid_search(db, doc_id, qvecs, question)

    if mode == "hybrid":
        return candidates[:max_k]

    # full: cross-encoder rerank the fused candidates
    from services.rerank_service import rerank

    return rerank(question, candidates, top_n=max_k)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["baseline", "hybrid", "full"], default="full")
    parser.add_argument("--document-id", default=None)
    args = parser.parse_args()

    data = json.loads(_DATASET.read_text(encoding="utf-8"))
    questions = [q for q in data["questions"] if not q.get("unanswerable")]
    unanswerable = [q for q in data["questions"] if q.get("unanswerable")]

    max_k = max(_KS)
    db = SessionLocal()
    try:
        doc_id = _resolve_document_id(db, args.document_id)
        print(f"Mode: {args.mode}   Document: {doc_id}")
        print(f"Answerable questions: {len(questions)}   (excluded unanswerable: {len(unanswerable)})\n")

        hits = {k: 0 for k in _KS}
        latencies: list[float] = []

        for q in questions:
            t0 = time.perf_counter()
            ranked = _retrieve(db, doc_id, q["question"], args.mode, max_k)
            latencies.append(time.perf_counter() - t0)

            keywords = q["expected_keywords"]
            match_ranks = [
                i + 1
                for i, c in enumerate(ranked)
                if _chunk_matches(c["chunk_text"], keywords)
            ]
            best = match_ranks[0] if match_ranks else None
            for k in _KS:
                if best is not None and best <= k:
                    hits[k] += 1

            marker = f"hit@{best}" if best else "MISS"
            print(f"  {q['id']}: {marker:>7}  {q['question']}")

        n = len(questions)
        print("\n---- Results ----")
        for k in _KS:
            pct = 100.0 * hits[k] / n if n else 0.0
            print(f"  hit@{k:<2}: {hits[k]}/{n}  ({pct:.1f}%)")
        mean_ms = 1000.0 * sum(latencies) / len(latencies) if latencies else 0.0
        print(f"  mean retrieval latency: {mean_ms:.0f} ms")
    finally:
        db.close()


if __name__ == "__main__":
    main()
