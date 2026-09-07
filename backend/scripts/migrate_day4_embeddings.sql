-- Day 4: add embedding column + HNSW index on document_chunks.
-- Run once after enabling the vector extension (Day 1).
-- Existing Day 3 chunks have no embeddings — they are truncated; re-upload PDFs.

TRUNCATE TABLE document_chunks;

ALTER TABLE document_chunks DROP COLUMN IF EXISTS embedding;

ALTER TABLE document_chunks
    ADD COLUMN embedding vector(384) NOT NULL;

CREATE INDEX IF NOT EXISTS document_chunks_embedding_hnsw
    ON document_chunks
    USING hnsw (embedding vector_cosine_ops);
