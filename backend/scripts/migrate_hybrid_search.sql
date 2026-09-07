-- Large-file RAG upgrade: hybrid search (BM25/FTS) + TOC flag.
-- Safe to run multiple times (IF NOT EXISTS guards).
--
-- After running this you must reprocess existing documents so chunks are
-- re-chunked and re-embedded with the new model (POST /documents/{id}/reprocess),
-- because the embedding model changed (MiniLM -> BGE-small).

-- Table-of-contents flag, down-weighted during fusion.
ALTER TABLE document_chunks
    ADD COLUMN IF NOT EXISTS is_toc boolean NOT NULL DEFAULT false;

-- Full-text search vector, generated from chunk_text.
ALTER TABLE document_chunks
    ADD COLUMN IF NOT EXISTS tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', chunk_text)) STORED;

-- GIN index for fast keyword search.
CREATE INDEX IF NOT EXISTS document_chunks_tsv_gin
    ON document_chunks
    USING gin (tsv);
