# Project Notes

Bug log and day-by-day explainers. Keep this updated as you hit issues.

---

## Day 1 — Learn block (quick reference)

### ASGI vs WSGI
- **WSGI** (e.g. classic Flask): synchronous request/response. One worker handles one request at a time unless you add threads/processes.
- **ASGI** (FastAPI / Starlette): async-native. The event loop can await I/O (DB, HTTP to Gemini, Redis) without blocking the whole worker.
- FastAPI is ASGI; run it with **Uvicorn**, not a WSGI server like Gunicorn alone (Gunicorn can wrap Uvicorn workers in production).

### SQLAlchemy: Base, Session, engine
- **engine**: connection pool to Postgres (created once at startup).
- **Session**: unit of work for one request (or one background task). Do not share a session across concurrent requests.
- **Base**: declarative base class; all ORM models inherit from it so `Base.metadata.create_all()` / Alembic know the schema.
- Sessions are **per-request** via `get_db()` so connections return to the pool and you never leak open transactions.

### Pydantic v2 + BaseSettings
- Pydantic models validate request/response shapes at the API boundary.
- **BaseSettings** (pydantic-settings) loads typed config from environment / `.env` — 12-factor style. No secrets in source code.

### What pgvector is
- A PostgreSQL **extension** that adds a `vector` column type and distance operators (`<=>` cosine, `<->` L2, `<#>` inner product).
- Day 4 will store 384-dim embeddings and use an HNSW index; Day 1 only enables the extension.

### Why `get_db()` uses `yield` (Explain answer)
FastAPI treats a generator dependency as setup → inject → teardown. Code after `yield` runs after the response is sent (or after an error), so `db.close()` always runs. `return` would hand over the session with no guaranteed cleanup.

---

## Day 1 — Database + pgvector setup (manual)

**Preferred (matches the 14-day plan): Supabase**

1. Create a project at https://supabase.com
2. Project Settings → Database → copy the **URI** connection string
3. In repo-root `.env`, set (note the SQLAlchemy driver prefix):
   `DATABASE_URL=postgresql+psycopg2://postgres:[PASSWORD]@db.[PROJECT_REF].supabase.co:5432/postgres`
4. SQL Editor → run `backend/scripts/enable_pgvector.sql`
5. Verify from the repo root:
   `backend\venv\Scripts\python.exe backend\scripts\verify_pgvector.py`
   Or in SQL: `SELECT * FROM pg_extension WHERE extname = 'vector';`

**Local alternative:** any Postgres with pgvector installed. Point `DATABASE_URL` at it
(default in `.env` is `127.0.0.1:5432/sourced`). Then run the same verify script.

> Note (2026-07-20): Docker Desktop on this machine hit an I/O error pulling
> `pgvector/pgvector:pg16`, so cloud Supabase (or a working local pgvector install)
> is required to fully green-check the extension query.

---

## Day 1 — Verify results (2026-07-20)

| Check | Result |
|---|---|
| `GET /` → `{"status":"ok"}` | Pass |
| `/docs` HTTP 200 | Pass |
| `.env` ignored by git | Pass (`gitignore:2:.env`) |
| `vector` extension row in Postgres | Pending — set real `DATABASE_URL` (Supabase), run `enable_pgvector.sql`, then `verify_pgvector.py` |

Server (from `backend/`): `.\venv\Scripts\uvicorn.exe main:app --reload --host 127.0.0.1 --port 8000`

---

## Day 2 — Learn block (quick reference)

### Hashing vs encryption
- **Encryption** is reversible with a key (ciphertext → plaintext). Never use it for passwords — a stolen key would expose every account.
- **Hashing** is one-way. We store bcrypt hashes and compare by hashing the login attempt. There is no decrypt step.

### bcrypt salt + work factor
- Each hash embeds a random **salt**, so identical passwords get different hashes (defeats rainbow tables).
- The **work factor** (cost) makes hashing deliberately slow (~100ms), which throttles brute-force guessing.

### JWT anatomy: signed ≠ encrypted
- Structure: `header.payload.signature` (Base64URL). Anyone can decode the payload and read claims (`sub`, `exp`).
- The **signature** (HMAC with `SECRET_KEY` for HS256) proves the payload was not tampered with. Without the secret, forging `sub` or adding `is_admin` fails verification.

### FastAPI `Depends()` and auth
- Dependencies form a chain: route → `get_current_user` → `oauth2_scheme` + `get_db`.
- `OAuth2PasswordBearer` extracts the Bearer token; `get_current_user` decodes it and loads the User, or raises 401.
- Login uses `OAuth2PasswordRequestForm` so Swagger’s **Authorize** button works (`username` = email).

### Why JWTs aren’t editable to become admin (Explain answer)
Editing the payload changes the bytes that were signed. Verification recomputes HMAC(`header.payload`, `SECRET_KEY`) and compares it to the signature. Without `SECRET_KEY`, the forged token is rejected with 401. (Also: our tokens only carry `sub` + `exp` — admin is loaded from the DB, not from the JWT.)

---

## Day 2 — Verify results (2026-07-22)

| Check | Result |
|---|---|
| `POST /auth/register` → `UserOut` (no `hashed_password`) | Pass |
| `POST /auth/login` → Bearer token | Pass |
| Authorize / Bearer → `GET /auth/me` returns that user | Pass |
| Duplicate email → 400 | Pass |
| Wrong password → 401 | Pass |
| `/docs` HTTP 200 | Pass |

Files added: `core/security.py`, `models/user.py`, `schemas/user.py`, `api/deps.py`, `api/routes/auth.py`. Tables created via `Base.metadata.create_all` on startup.

---

## Day 3 — Learn block (quick reference)

### How PDFs store text
- PDFs store **glyphs at coordinates**, not paragraphs. Extractors reconstruct reading order heuristically — columns, headers, and tables often scramble.
- Extraction is imperfect by nature; chunking and retrieval must tolerate noisy text.

### Tokens vs words vs characters
- Models count **tokens**, not words. Rough rule of thumb: **~0.75 words per token** → `token_count ≈ round(words / 0.75)`.
- Chunk `size=500` / `overlap=50` here are **word** windows within a page.

### Why chunk overlap exists
- Without overlap, a sentence split across two chunk boundaries can make neither chunk match the query well.
- Overlap duplicates edge words so that idea still appears intact in at least one chunk.

### MIME vs extension
- `.pdf` alone is spoofable. We also check content-type and **`%PDF` magic bytes** so a renamed binary is rejected.

### Why per-page chunking hurts a bit but is worth it (Explain answer)
Ideas that span a page break can be split, slightly hurting recall. It is worth it because **citations need a stable `page_number`**. Cross-page chunks would make Day 6 “page N” citations ambiguous or wrong.

---

## Day 3 — Verify results (2026-07-22)

| Check | Result |
|---|---|
| Upload PDF → `status='processing'`, `page_count` > 0, `total_chunks` > 0 | Pass (3 pages, 6 chunks) |
| `GET /documents/{id}` chunks have sensible `page_number` | Pass (pages 1–3) |
| Consecutive same-page chunks show ~50-word overlap | Pass |
| `GET /documents/` lists own docs; unknown id → 404 | Pass |
| `DELETE /documents/{id}` → 204 then 404 | Pass |

Files added: `models/document.py`, `models/chunk.py`, `utils/pdf_parser.py`, `utils/chunker.py`, `schemas/document.py`, `api/routes/documents.py`. Uploads land under `uploads/{user_id}/{doc_id}.pdf`.

---

## Day 4 — Learn block (quick reference)

### What an embedding is
- An embedding maps text → a fixed-length vector so that **nearby vectors ≈ similar meaning**.
- We use `all-MiniLM-L6-v2` → **384 dimensions**. The Postgres `vector(384)` column **must** match that size.

### HNSW
- **HNSW** (Hierarchical Navigable Small World) is an approximate nearest-neighbour graph index.
- Faster than exact scan on large tables; tiny recall trade-off. We use cosine ops: `vector_cosine_ops`.

### Why BackgroundTasks
- Extract + embed can take many seconds. Doing it in the HTTP handler risks timeouts and a stuck UI.
- Upload saves the file, inserts `status='processing'`, returns immediately; `process_document` finishes in the background → `ready` or `failed`.

### Why load SentenceTransformer at module level (Explain answer)
Model load is expensive (download/weights/init, seconds + RAM). Loading inside `embed_*` would redo that work on every batch. Module-level load happens **once per process**.

### Migration note
Day 3 chunks had no embeddings. Run once:

`backend\venv\Scripts\python.exe backend\scripts\run_migrate_day4.py`

Then re-upload PDFs. Script truncates `document_chunks`, adds `embedding vector(384) NOT NULL`, creates HNSW.

---

## Day 4 — Verify results (2026-07-22)

| Check | Result |
|---|---|
| Upload returns quickly with `status='processing'` | Pass (~2s) |
| Poll → `status='ready'`, `total_chunks` == len(chunks) | Pass (6/6) |
| Corrupt `%PDF` body → `status='failed'` + `error_message` | Pass |

Files added: `services/embedding_service.py`, `services/document_service.py`, `scripts/migrate_day4_embeddings.sql`, `scripts/run_migrate_day4.py`. Upload route now uses `BackgroundTasks`.

---

## Day 5 — Learn block (quick reference)

### Cosine vs Euclidean; pgvector operators
- **Cosine distance** (`<=>`) cares about angle (direction), not magnitude — preferred for text embeddings.
- `<->` = L2 (Euclidean); `<#>` = negative inner product. Day 4 HNSW uses `vector_cosine_ops` → match with `<=>`.

### Prompt grounding
- The model is told to answer **only** from retrieved chunks and to refuse with a fixed message when the answer is absent — reduces hallucinations.

### Parameterised SQL
- Never f-string floats into SQL. Bind `:qvec` / `:doc_id` / `:k` so the driver escapes values and injection cannot rewrite the query.

### `/chat/ask` end to end (Explain answer)
1. **`get_current_user`** — JWT → User  
2. **Ownership** — load Document; wrong/missing owner → **404** (IDOR)  
3. **`embed_text`** (`embedding_service`) — question → 384-d vector  
4. **`search_chunks`** (`rag_service`) — pgvector `<=>` top-k  
5. **`build_prompt`** (`rag_service`) — grounded template with `[Chunk N]`  
6. **`generate_answer`** (`llm_service`) — Anthropic Claude (`claude-sonnet-4-6`)  
7. Persist **`ChatSession` / `ChatMessage`** (assistant stores `source_chunks` JSONB)  
8. Return answer + `sources`

### Anthropic setup
Set in repo-root `.env`:

```
ANTHROPIC_API_KEY=your_key_here
ANTHROPIC_MODEL=claude-sonnet-4-6
```

Key: https://console.anthropic.com/settings/keys — then restart the API and re-run grounded/refusal checks in `/docs`.

---

## Day 5 — Verify results (2026-07-22)

| Check | Result |
|---|---|
| `build_prompt` includes refusal + `[Chunk N]` | Pass |
| `search_chunks` returns nearest chunks for ready doc | Pass |
| Other user's `document_id` → 404 | Pass |
| Unknown `document_id` → 404 | Pass |
| Ask without `ANTHROPIC_API_KEY` → 503 | Pass (was Gemini; now Anthropic) |
| In-doc question → grounded answer | Pending — set `ANTHROPIC_API_KEY` and retry in `/docs` |
| Absent question → refusal message | Pending — set `ANTHROPIC_API_KEY` and retry in `/docs` |

Files added: `services/rag_service.py`, `services/llm_service.py`, `models/chat.py`, `schemas/chat.py`, `api/routes/chat.py`. LLM: **Anthropic** `claude-sonnet-4-6` via `anthropic` SDK (switched from Gemini).

---

## Day 6 — Learn block (quick reference)

### Cache-aside + TTLs
- **Cache-aside:** app reads cache → on miss computes → writes cache. Redis is not the source of truth (Postgres still stores messages).
- **TTLs** bound staleness and memory: answers 1h, embeddings 24h.

### Rate limit: `INCR` + `EXPIRE`
- Key `ratelimit:{user_id}:{YYYYMMDDHH}` — `INCR` on each ask; first incr sets `EXPIRE 3600`.
- Count > 20 → **429**. Limits Anthropic cost, not just abuse.

### Why `document_id` is in the answer cache key (Explain answer)
The same question on two PDFs can have different answers. Key is `answer:{doc_id}:{sha256(q)}`. Without `doc_id`, Doc A’s cached answer could be returned for Doc B (**cross-contamination**).

### Ownership order
Ownership/404 runs **before** rate limit and cache reads (IDOR-safe).

### Upstash setup
1. Create a free Redis DB at https://console.upstash.com  
2. Copy the **Redis URL** (`rediss://…`) into repo-root `.env` as `REDIS_URL=`  
3. Restart the API, then re-test cache hit + 21st ask → 429

---

## Day 6 — Verify results (2026-07-22)

| Check | Result |
|---|---|
| Rate limit helper: 21st ask raises | Pass (fakeredis unit) |
| Answer cache scoped by `doc_id` | Pass (fakeredis unit) |
| Embed cache get/set | Pass (fakeredis unit) |
| Ask without `REDIS_URL` → 503 | Pass |
| `GET /chat/sessions` + detail + `DELETE` | Pass |
| Live cache hit speed + HTTP 429 | Pending — set `REDIS_URL` (Upstash) and retry |

Files added: `core/redis_client.py`; ask path wired with rate limit + caches; session CRUD on `/chat/sessions`.

---

## Day 7 — Learn block (quick reference)

### Hooks + AuthContext
- `useState` / `useEffect` drive forms, lists, and polling. Dependency arrays control when effects re-run.
- **AuthContext** holds `user` + `token` + `login` / `logout` so every page shares auth without Redux.

### Axios interceptors
- Request: attach `Authorization: Bearer <token>` from `localStorage`.
- Response **401**: clear token and send the browser to `/login`.

### Polling vs WebSockets
- Document processing is short-lived and infrequent. Polling `GET /documents/{id}` every 3s is enough; WebSockets would add infra for little gain.

### Why polling `useEffect` needs cleanup (Explain answer)
`setInterval` keeps firing after the component unmounts (or after deps change) unless you `clearInterval` in the effect cleanup. Without cleanup you leak timers, hit a removed page, and can set state on an unmounted component.

### Run locally
1. Backend: from `backend/`, `uvicorn main:app --reload --host 127.0.0.1 --port 8000`
2. Frontend: from `frontend/`, `npm run dev` → http://localhost:5173
3. Ensure `.env` `ALLOWED_ORIGINS` includes `http://localhost:5173` and `frontend/.env` has `VITE_API_URL=http://127.0.0.1:8000`

---

## Day 7 — Verify results (2026-07-22)

| Check | Result |
|---|---|
| Vite React scaffold + axios + react-router-dom | Pass |
| Production build (`vite build`) | Pass |
| Browser E2E register → upload → ready → ask → citations | Manual — run both servers and walk the flow |

Files under `frontend/`: `api/axios.js`, `context/AuthContext.jsx`, `components/ProtectedRoute.jsx`, `components/ChatMessage.jsx`, pages Login/Register/Dashboard/Upload/Chat.

---

## Large-file RAG upgrade — standard retrieve → fuse → rerank

Motivation: a ~3260-page Harry Potter omnibus exposed the limits of "page-local
500-word chunks + single dense top-5". Climax scenes that span pages missed the
top-5, and list/aggregate questions collapsed onto table-of-contents pages.

### New pipeline

```
question
  → query rewrite (Claude → 2-3 alternates)
  → dense embed each (BGE-small, query prefix)   ┐
  → Postgres full-text search (question)         ┘→ RRF fuse (TOC down-weighted)
  → cross-encoder rerank (top RAG_CONTEXT_K)
  → neighbor expansion (chunk_index ± 1, capped)
  → grounded prompt → Claude
```

### What changed and why
- Chunking (`utils/chunker.py`): section-aware word windows (default 800/100)
  that span pages *within a chapter/heading* but reset at `CHAPTER/BOOK/PART`
  headings, so scenes crossing page breaks stay together. TOC-like pages are
  flagged (`is_toc`) so they can be down-weighted.
- Embeddings (`services/embedding_service.py`): switched MiniLM → `BAAI/bge-small-en-v1.5`
  (still 384-d, no schema change). BGE is asymmetric: queries get the instruction
  prefix, passages do not; vectors are L2-normalized for cosine.
- Hybrid search (`services/rag_service.py`): dense fails on exact tokens (names,
  spells, numbers); Postgres `tsvector`/`ts_rank` covers lexical matches. Results
  fuse with **Reciprocal Rank Fusion** (`score = Σ 1/(k+rank)`, k=60) which needs
  only ranks, not comparable scores. TOC chunks multiplied by `RAG_TOC_PENALTY`.
- Rerank (`services/rerank_service.py`): a cross-encoder scores each
  `(question, chunk)` jointly — far more accurate than the bi-encoder, too slow
  for the whole corpus, so it runs only over fused candidates (retrieve-then-rerank).
- Neighbor expansion: pulls adjacent chunks so answers that continue past a
  chunk boundary aren't truncated; final context is sorted by `chunk_index`.
- Query rewrite (`services/llm_service.py`): widens semantic recall
  ("how did Voldemort die" → "final duel", "killing curse rebounds").

### Migration + reprocess (required)
The embedding model changed, so old vectors are incompatible.

1. `backend\venv\Scripts\python.exe backend\scripts\run_migrate_hybrid.py`
   (adds `is_toc`, `tsv` generated column, GIN index).
2. `POST /documents/{id}/reprocess` for each existing document to re-chunk and
   re-embed with the new model (no re-upload needed).
3. Answer cache is namespaced by `RAG_PIPELINE_VERSION`, so stale answers are
   ignored automatically after the bump.

### Evaluation
`eval/run_eval.py` scores hit@k (keyword match in top-k) for `baseline`,
`hybrid`, and `full` modes; record numbers in `eval/RESULTS.md`.

### Deploy memory note
BGE-small + a cross-encoder + torch can exceed a free tier's RAM. If OOM on
deploy: keep hybrid + neighbor expansion and disable the reranker (document it),
or move embeddings/rerank to a hosted API — same escape hatch as the plan's Day 11.

---

## Health check + fixes (2026-10-16)

| Issue | Fix |
|---|---|
| A PDF with no extractable text (scanned/image-only) was marked `ready` with 0 chunks, so every question silently refused | `process_document` now raises → `status='failed'` with an OCR-not-supported message. Existing bad row marked `failed`. |
| Embedding cache key `embed:{sha256(q)}` didn't include the model, so after the MiniLM → BGE switch a cached MiniLM vector could be searched against BGE chunks | Key is now `embed:{model_hash}:{sha256(q)}` |
| One pre-Day-4 doc stuck in `processing` forever | Marked `failed`; reprocess or delete |
| `eval/__pycache__/*.pyc` committed | Untracked (`.gitignore` already covers it) |
| pgvector Day 1 check pending | Verified: `vector` 0.8.2 present |
| Retrieval eval table empty | Run 1 recorded in `eval/RESULTS.md` |

## LLM switch: Anthropic → OpenAI (2026-10-16)

`services/llm_service.py` now uses the `openai` SDK (Chat Completions). Config: `OPENAI_API_KEY`, `OPENAI_MODEL` (default `gpt-4o-mini`). It uses `max_completion_tokens` so reasoning models (e.g. the `gpt-5` family) work too. Prompts, refusal message and the rest of the pipeline are unchanged. Earlier Day 5 notes that mention Claude are historical.

## Live verification — Days 2–6 (2026-10-16)

Real server, real OpenAI (`gpt-4o-mini`), real Upstash Redis, Supabase Postgres.

| Check | Result |
|---|---|
| Upload → `ready` | Pass |
| Text-less PDF → `failed` with OCR message | Pass |
| In-doc question → grounded answer with `[Chunk N]` | Pass ("port 7443 [Chunk 0]") |
| Citations carry `page_number` | Pass |
| Same question twice → `cached: true` | Pass (6.4 s → 1.6 s) |
| Absent question → exact refusal message | Pass |
| Other user's `document_id` → 404 | Pass |
| History persisted (`GET /chat/sessions/{id}`) | Pass (6 messages) |
| 21st ask in an hour → 429 | Pass |

Bugs hit while verifying:
- **Upstash `redis://` → "Connection closed by server".** Upstash requires TLS (`rediss://`). Fixed in `.env`, and `redis_client` now upgrades `*.upstash.io` URLs automatically.
- **`uvicorn.exe` fails silently** because the em dash (—) in the repo path breaks pip's exe launchers. Use `venv\Scripts\python.exe -m uvicorn main:app --reload`.


## Citation page ranges (2026-10-16)

**Bug:** the section-aware chunker lets chunks span pages, but each chunk stored only the page it *started* on. On the Harry Potter PDF, **1,676 of 1,682 chunks cross a page break**, so most citations under-reported where the text came from. In a small 2-page test doc, a page-2 fact was cited as "page 1".

**Fix:** a new `document_chunks.page_end` column. The chunker records the start and end page of each window, the prompt shows `(pages 3-4)`, the API returns `page_end`, and the UI shows "Pages 3–4". Re-chunking per page would have fixed this too, but it would have undone the cross-page retrieval gains measured in `eval/RESULTS.md`.

**Migration:** `backend\venv\Scripts\python.exe backend\scripts\run_migrate_page_end.py` adds the column and backfills exact values by re-chunking stored PDFs (no re-embedding). `RAG_PIPELINE_VERSION` was bumped to 3, so cached answers without `page_end` are ignored.

**Related bug:** `documents.file_path` is absolute and still pointed at the repo's old location (`D:\Sourced — …`), so reprocess returned 409 and delete left files behind. `stored_file()` now falls back to `uploads/{user_id}/{doc_id}.pdf`. Day 8's move to Supabase Storage replaces this properly.

**Windows path gotcha:** the `&` in "Q&A" breaks npm's `.cmd` shims. Build with `node node_modules/vite/bin/vite.js build`, or move the repo to a path without `&` or `—`.
