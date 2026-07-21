# 14-Day RAG Document Q&A — Build + Learn Plan

**Goal:** A deployed RAG app with measured retrieval quality, ready to defend in a product-company interview.

**Stack:** FastAPI · PostgreSQL + pgvector · Redis · sentence-transformers · Gemini · React (Vite)

**Daily rhythm (~6–7 hrs):**
| Block | Time | What |
|---|---|---|
| Learn | 1–1.5 hr | Read the day's concepts *before* generating code |
| Build | 3–4 hr | Claude Code generates, you review every line |
| Verify | 30 min | Run the day's test. Do not proceed until it passes |
| Explain | 30 min | Say the "Can you explain?" answer out loud, no notes |

> **The Explain block is not optional.** It is the single thing separating "I built this" from "I generated this." Interviewers find the gap in two follow-up questions.

---

## PHASE 1 — SHIP THE CORE (Days 1–8)

Target: a live URL by end of Day 8. Ugly is fine. Working is not optional.

---

### Day 1 — Project Setup + Database Foundation

**Learn first**
- ASGI vs WSGI — why FastAPI is async and Flask traditionally isn't
- SQLAlchemy ORM basics: `Base`, `Session`, `engine`, why sessions are per-request
- Pydantic v2: models as request/response validation, `BaseSettings` for config
- What pgvector is: a Postgres extension adding a `vector` column type + distance operators

**Build**
- [ ] `venv` + install: `fastapi uvicorn sqlalchemy psycopg2-binary pydantic-settings python-dotenv pgvector`
- [ ] Folder structure per Section 4.1 of your guide (`api/routes`, `core`, `models`, `schemas`, `services`, `utils`)
- [ ] `core/config.py` — Pydantic `BaseSettings` reading `.env`
- [ ] `core/database.py` — engine, `SessionLocal`, `Base`, `get_db()` dependency
- [ ] `main.py` — app instance, CORS middleware, `GET /` health route
- [ ] Supabase project created; `CREATE EXTENSION IF NOT EXISTS vector;` run in SQL editor
- [ ] `.gitignore` with `.env`, `__pycache__`, `venv/`, `node_modules/`
- [ ] `.env.example` committed with empty values
- [ ] Git repo initialised, first commit pushed

**Verify:** `/docs` loads, `/` returns `{"status":"ok"}`, `SELECT * FROM pg_extension WHERE extname='vector';` returns a row.

**Can you explain?**
> Why does `get_db()` use `yield` instead of `return`?

---

### Day 2 — Authentication (JWT + bcrypt)

**Learn first**
- Hashing vs encryption — why passwords are hashed and never decrypted
- What bcrypt's salt and work factor do, and why it's deliberately slow
- JWT anatomy: header · payload · signature; **signed ≠ encrypted** (payload is public)
- FastAPI's dependency injection: how `Depends()` chains and where auth plugs in

**Build**
- [ ] Install `passlib[bcrypt] python-jose[cryptography]`
- [ ] `core/security.py` — `hash_password`, `verify_password`, `create_access_token`, `decode_token`
- [ ] `models/user.py` — `id`, `email` (unique), `hashed_password`, `is_admin`, `created_at`
- [ ] `schemas/user.py` — `UserCreate`, `UserOut` (**never expose `hashed_password`**), `Token`
- [ ] `routes/auth.py` — `POST /auth/register`, `POST /auth/login`, `GET /auth/me`
- [ ] `get_current_user()` dependency — decodes JWT, loads user, raises 401 on failure

**Verify:** Register → login → copy token → authorize in `/docs` → `/auth/me` returns your user. Duplicate email returns 400. Wrong password returns 401.

**Can you explain?**
> If JWTs aren't encrypted, what stops a user from editing the payload to make themselves admin?

---

### Day 3 — Upload + Extract + Chunk (page-aware)

**Learn first**
- How PDFs store text (glyph positions, not paragraphs) — why extraction is imperfect
- Tokens vs words vs characters; the ~0.75 words-per-token approximation
- Why chunk overlap exists — the split-sentence retrieval failure
- MIME type vs file extension — why checking extension alone is unsafe

**Build**
- [ ] Install `pymupdf`
- [ ] `models/document.py` — `documents` table (`status`, `total_chunks`, `file_path`, `page_count`)
- [ ] `models/chunk.py` — `document_chunks` with `chunk_text`, `chunk_index`, **`page_number`**, `token_count`
- [ ] `utils/pdf_parser.py` — `extract_pages(path) -> list[tuple[page_num, text]]`
- [ ] `utils/chunker.py` — `chunk_pages(pages, size=500, overlap=50)`, **each chunk keeps its page number**
- [ ] `routes/documents.py` — `POST /documents/upload` validating `.pdf` + MIME + ≤10 MB
- [ ] `GET /documents/`, `GET /documents/{id}`, `DELETE /documents/{id}` — all with ownership checks

> ⚠️ **Chunk within pages, not across them.** Page numbers must survive to Day 6's citations. Retrofitting this on Day 9 is painful.

**Verify:** Upload a real PDF → row created with `status='processing'` → print chunks and confirm each has a sensible `page_number` and visible overlap between consecutive chunks.

**Can you explain?**
> Why does chunking per-page slightly hurt retrieval, and why is it worth it anyway?

---

### Day 4 — Embeddings + Vector Storage + Background Processing

**Learn first**
- What an embedding actually is — text → fixed-length vector where distance ≈ meaning
- Why 384 dimensions; why the column dimension **must** match the model's output
- HNSW: a navigable small-world graph; approximate nearest neighbour, not exact
- Why background work matters: a 30-second upload request will time out

**Build**
- [ ] Install `sentence-transformers`
- [ ] `services/embedding_service.py` — load model **once at module level**, `embed_text`, `embed_many`
- [ ] `embedding` column as `Vector(384)`, `NOT NULL`
- [ ] HNSW index: `CREATE INDEX ON document_chunks USING hnsw (embedding vector_cosine_ops);`
- [ ] `services/document_service.py` — `process_document()`: extract → chunk → batch-embed → bulk insert → `status='ready'`
- [ ] Wire to FastAPI `BackgroundTasks`
- [ ] **`try/except` around the whole task → `status='failed'` + store `error_message`**

**Verify:** Upload → response returns instantly → after ~10s `status='ready'` → `SELECT COUNT(*) FROM document_chunks` matches `total_chunks`. Then deliberately upload a corrupt PDF and confirm `status='failed'`, not a permanent hang.

**Can you explain?**
> Why load the SentenceTransformer at module level instead of inside the function?

---

### Day 5 — Vector Search + LLM + The RAG Loop

**Learn first**
- Cosine similarity vs Euclidean distance — why cosine for text embeddings
- pgvector operators: `<=>` cosine distance, `<->` L2, `<#>` inner product
- Prompt grounding: instructing the model to refuse rather than guess
- Why SQL string concatenation is unsafe and parameterised queries aren't

**Build**
- [ ] `services/rag_service.py` — `search_chunks(db, doc_id, qvec, k=5)` using `ORDER BY embedding <=> CAST(:qvec AS vector)`
- [ ] `build_prompt(question, chunks)` — strict grounding template with `[Chunk N]` markers
- [ ] `services/llm_service.py` — Gemini call (**check the current model name; don't copy an old one**)
- [ ] `models/chat.py` — `chat_sessions` + `chat_messages` (`role`, `content`, `source_chunks` JSONB)
- [ ] `routes/chat.py` — `POST /chat/ask`

> 🔒 **Ownership check is line 1 of the handler.** Before rate limiting. Before the cache read. `if doc.user_id != user.id: raise HTTPException(404)`. This is the IDOR fix — and a Day 14 talking point.

**Verify:** Ask a question you know the answer to → grounded answer. Ask something absent from the PDF → the refusal message, not a hallucination. Ask with another user's `document_id` → 404.

**Can you explain?**
> Walk through `/chat/ask` end to end, naming every service it touches.

---

### Day 6 — Redis: Cache, Rate Limit, Citations

**Learn first**
- Cache-aside pattern; why TTLs exist
- Why `INCR` + `EXPIRE` is the standard rate-limit primitive
- Cache key design — what must be in the key to avoid cross-contamination
- HTTP 429 and why rate limiting is cost control, not just abuse control

**Build**
- [ ] Upstash Redis created; `core/redis_client.py` (install `redis`)
- [ ] Answer cache — key `answer:{doc_id}:{sha256(question)}`, TTL 3600
- [ ] Embedding cache — key `embed:{sha256(question)}`, TTL 86400
- [ ] Rate limit — key `ratelimit:{user_id}:{hour}`, `INCR`, limit 20/hr → 429
- [ ] Return `sources: [{chunk_index, page_number, chunk_text}]` with every answer
- [ ] Persist both user and assistant messages; assistant row stores `source_chunks`
- [ ] `GET /chat/sessions`, `GET /chat/sessions/{id}`, `DELETE /chat/sessions/{id}`

**Verify:** Same question twice — second is visibly instant. 21st query returns 429. Response includes correct page numbers. History persists across restarts.

**Can you explain?**
> Why is `document_id` in the cache key? What breaks if you leave it out?

---

### Day 7 — React Frontend (Minimal)

**Learn first**
- React hooks: `useState`, `useEffect`, dependency arrays
- Context API for global auth state — and why Redux is overkill here
- Axios interceptors — attach token on request, redirect on 401
- Polling vs WebSockets, and why polling wins for this use case

**Build**
- [ ] `npm create vite@latest` (React), install `react-router-dom axios`
- [ ] `api/axios.js` — instance + JWT request interceptor + 401 response interceptor
- [ ] `context/AuthContext.jsx` — user, token, `login()`, `logout()`
- [ ] Pages: `Login`, `Register`, `Dashboard`, `Upload`, `Chat/:docId`
- [ ] Protected route wrapper redirecting to `/login`
- [ ] Dashboard polls `GET /documents/{id}` every 3s while `status='processing'`
- [ ] `ChatMessage.jsx` — bubbles + expandable citations showing page + chunk text

> Plain CSS only today. No Tailwind setup, no component library. Polish is Day 13.

**Verify:** Full flow in the browser — register → upload → watch badge flip to ready → ask → answer with clickable citations. Zero console errors.

**Can you explain?**
> Why does the polling `useEffect` need a cleanup function?

---

### Day 8 — Deploy (do not skip)

**Learn first**
- Environment variables and the 12-factor config principle
- **Ephemeral filesystems** — why Railway/Render wipe local files on every restart
- CORS: what a preflight request is and why the browser sends it
- Cold starts on free tiers

**Build**
- [ ] Move PDF storage to **Supabase Storage** (local disk will lose your files)
- [ ] `requirements.txt` pinned; backend → Railway or Render
- [ ] Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- [ ] All env vars set in the dashboard
- [ ] Frontend → Vercel with `VITE_API_URL` pointing at the live backend
- [ ] `ALLOWED_ORIGINS` updated to the real Vercel domain
- [ ] End-to-end test **in production**, on your phone

> 🧠 If you hit an out-of-memory error, that's sentence-transformers + torch exceeding the free tier. Fix: switch to the ONNX build of MiniLM, or drop to a hosted embedding API. Budget for this — it's the most common Day 8 blocker.

**Verify:** A stranger can open the Vercel URL, register, upload, and get an answer. Screenshot it.

**Can you explain?**
> Your app worked locally but broke in production. Name three likely causes.

---

## PHASE 2 — THE DIFFERENTIATORS (Days 9–14)

Everyone's project ends at Day 8. This is the half that gets you the offer.

---

### Day 9 — Evaluation Harness ⭐

**This is the most important day of the entire plan.**

**Learn first**
- Retrieval metrics: hit rate @k, MRR, precision vs recall
- Why "it feels good" is not evidence
- Establishing a baseline before optimising

**Build**
- [ ] Choose 3 PDFs of different character (a paper, a manual, a report)
- [ ] `eval/dataset.json` — **25 questions**, each with `question`, `expected_page`, `notes`
- [ ] Cover the hard cases too: exact terms/numbers, questions the docs can't answer, follow-ups
- [ ] `eval/run_eval.py` — runs each question through retrieval, checks whether `expected_page` appears in top-k
- [ ] Report **hit@1, hit@3, hit@5** and mean latency
- [ ] Record your baseline in `eval/RESULTS.md`

> ✍️ **Write this script yourself, or read every line twice.** It is the piece you'll be questioned on hardest — and the piece that proves you think like an engineer.

**Verify:** `python eval/run_eval.py` prints a clean table. Baseline hit@5 is probably 55–70%. A low number here is *good* — it's the "before" in your story.

**Can you explain?**
> What does hit@5 measure, and what does it deliberately ignore?

---

### Day 10 — Hybrid Search (BM25 + Vector, fused with RRF)

**Learn first**
- Why dense retrieval fails on exact tokens: product codes, names, numbers, acronyms
- Postgres full-text search: `tsvector`, `tsquery`, `ts_rank`
- Lexical vs semantic matching as complementary failure modes
- **Reciprocal Rank Fusion:** `score = Σ 1/(k + rank)`, k=60 — combines ranked lists without needing comparable scores

**Build**
- [ ] Add `tsv` column: `ALTER TABLE document_chunks ADD COLUMN tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', chunk_text)) STORED;`
- [ ] GIN index on `tsv`
- [ ] `keyword_search(db, doc_id, query, k=20)` using `ts_rank`
- [ ] `reciprocal_rank_fusion(dense_results, sparse_results, k=60)` — ~15 lines
- [ ] `hybrid_search()` — 20 dense + 20 sparse → RRF → top 5
- [ ] Feature-flag it so you can A/B against baseline
- [ ] **Rerun the eval. Record the new number.**

**Verify:** Hit@5 improves (expect +8–20 points). Confirm a query with an exact term or number that previously failed now succeeds.

**Can you explain?**
> Why does RRF use ranks instead of raw scores?

---

### Day 11 — Cross-Encoder Reranking

**Learn first**
- Bi-encoder vs cross-encoder — separate encoding vs joint attention over (query, chunk)
- Why cross-encoders are far more accurate but too slow to run over the whole corpus
- The retrieve-then-rerank pattern: cheap wide net, expensive precise filter
- The latency/quality trade-off you're consciously accepting

**Build**
- [ ] Install reranker: `CrossEncoder("BAAI/bge-reranker-base")` (or `ms-marco-MiniLM-L-6-v2` if memory is tight)
- [ ] `rerank(question, chunks, top_n=5)` — score each pair, sort, truncate
- [ ] Pipeline: hybrid retrieve **20** → rerank → **top 5** → LLM
- [ ] Measure added latency, log it
- [ ] **Rerun the eval. Record the final number.**
- [ ] Complete the results table: `baseline → +hybrid → +reranker`

> If the reranker blows your free-tier memory, keep hybrid search and document the reranker as measured-locally future work. Still a strong story — just be honest about it.

**Verify:** Your `eval/RESULTS.md` now has three rows and rising numbers. **This table is your interview headline.**

**Can you explain?**
> Why not just rerank all chunks and skip vector search entirely?

---

### Day 12 — Streaming Responses (SSE)

**Learn first**
- Server-Sent Events vs WebSockets — one-way vs bidirectional
- FastAPI `StreamingResponse` and Python generators
- Why perceived latency ≠ actual latency
- Handling client disconnects mid-stream

**Build**
- [ ] `POST /chat/ask/stream` returning `StreamingResponse` with `media_type="text/event-stream"`
- [ ] Gemini streaming mode; yield tokens as they arrive
- [ ] Send citations as a final event once the answer completes
- [ ] Frontend consumes the stream and renders progressively
- [ ] Persist the full message to the DB after the stream closes
- [ ] Bypass streaming on cache hits (instant anyway)

**Verify:** Answers appear word by word instead of after a 4-second freeze. Citations land at the end. Refreshing mid-stream doesn't corrupt history.

**Can you explain?**
> Why SSE here rather than WebSockets?

---

### Day 13 — Polish + The Refusal Path

**Learn first**
- Empty states, loading states, error states — the three most-skipped UI states
- Graceful degradation
- Why a system that refuses to answer is more trustworthy than one that always answers

**Build**
- [ ] Loading skeletons on dashboard and chat
- [ ] Error toasts for 401 / 429 / 500 with human-readable messages
- [ ] Empty states: no documents, no messages
- [ ] Rate-limit UI showing remaining queries
- [ ] **Test and demo the refusal path** — ask something absent from the PDF, confirm the honest "I could not find this in the document"
- [ ] Handle `status='failed'` in the UI with a retry button
- [ ] Basic responsive layout (interviewers open things on phones)
- [ ] Mild visual polish — consistent spacing, one accent colour, readable type

**Verify:** Click every broken path deliberately. Nothing shows a raw stack trace or an infinite spinner.

**Can you explain?**
> Why is "I don't know" a feature rather than a failure?

---

### Day 14 — README, Demo, Interview Prep

**Learn first**
- What senior engineers actually look for in a README
- Framing limitations as awareness, not weakness
- STAR format for the bug story

**Build — README**
- [ ] One-line pitch + **live demo link** + demo GIF
- [ ] Architecture diagram (upload flow + query flow)
- [ ] Stack table with a one-line *why* per choice
- [ ] ⭐ **Evaluation section with the results table:**

  | Configuration | hit@1 | hit@3 | hit@5 | Latency |
  |---|---|---|---|---|
  | Dense only (baseline) | | | | |
  | + Hybrid (BM25 + RRF) | | | | |
  | + Cross-encoder rerank | | | | |

- [ ] **Security section** — the IDOR bug: cache read happened before the ownership check, so any authenticated user could pass another user's `document_id` and receive their cached answers. Found it, moved ownership validation to the first line of the handler.
- [ ] Known limitations: no OCR for scanned PDFs, single-document Q&A, English only, free-tier cold starts
- [ ] Future work: OCR, multi-document search, semantic caching, Celery workers
- [ ] Local setup instructions that actually work on a clean machine

**Build — Demo**
- [ ] 3-minute recording: upload → ask → citations → refusal path → rate limit
- [ ] Keep it downloaded; assume the live site is cold during your interview

**Rehearse out loud**
- [ ] Draw the full architecture from memory on paper, in under 3 minutes
- [ ] The retrieval-improvement story with real numbers
- [ ] The IDOR bug story in STAR form
- [ ] "What would you do differently with three more months?"
- [ ] "What's the weakest part of this system?" — answer honestly; it's a trust test

**Verify:** Hand your laptop to a friend with only the README. If they can run it and explain what it does, you're done.

---

## Fallback Order (if you fall behind)

Cut in this order, no exceptions:

1. Streaming (Day 12)
2. Reranker — keep hybrid search (Day 11)
3. Polish (Day 13)

**Never cut:** Day 8 deployment, Day 9 evaluation, Day 14 README. Those three are the project.

---

## Working With Claude Code Without Hollowing Yourself Out

- **Do the Learn block first.** Reviewing generated code you don't understand teaches nothing.
- **Generate one file at a time**, not whole features. You need to be able to hold each piece in your head.
- **Write the eval script by hand** (Day 9). Non-negotiable.
- **End every day by closing the editor** and explaining that day's code aloud. Can't do it? Re-read before moving on.
- **Keep a `NOTES.md`** of every bug you hit and how you fixed it. On Day 14 you'll find your best interview stories are already written down.

---

## Your Three Interview Headlines

By Day 14 you should be able to say, without notes:

1. *"I measured retrieval quality on a 25-question eval set. Dense-only retrieval got X% hit@5; hybrid BM25 + vector with reciprocal rank fusion took it to Y%; adding a cross-encoder reranker got it to Z%."*
2. *"I found an IDOR vulnerability in my own code — the Redis cache read happened before the document ownership check, so any authenticated user could retrieve another user's cached answers by guessing a document ID."*
3. *"The system refuses to answer when the document doesn't contain the information. I'd rather it say 'I don't know' than hallucinate a confident wrong answer."*

Almost nobody at a campus drive says any of these.
