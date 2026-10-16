-- Citation page ranges: chunks can span pages within a section, so store the
-- page each chunk ends on as well as the one it starts on.
-- Safe to run multiple times.

ALTER TABLE document_chunks
    ADD COLUMN IF NOT EXISTS page_end integer;

-- Placeholder for existing rows; run_migrate_page_end.py then recomputes the
-- exact value by re-chunking each stored PDF (no re-embedding needed).
UPDATE document_chunks
    SET page_end = page_number
    WHERE page_end IS NULL;

ALTER TABLE document_chunks
    ALTER COLUMN page_end SET NOT NULL;
