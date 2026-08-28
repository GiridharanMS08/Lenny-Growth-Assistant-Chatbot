# Architecture

## Components
- React/Vite frontend
- FastAPI API
- Custom agent router with Ship 30 writing skill
- SentenceTransformers embeddings + FAISS
- BM25 keyword retrieval + RRF fusion
- Cross-Encoder reranking
- Ollama local provider and optional OpenAI provider
- PostgreSQL persistence through SQLAlchemy + psycopg
- Bleach sanitizer + sandboxed iframe for artifacts

## Retrieval
Markdown frontmatter supplies guest/title/date metadata. Documents are split at Markdown headings and paragraph boundaries, with sentence fallback for oversized paragraphs. Chunks are embedded with `all-MiniLM-L6-v2`. Retrieval combines normalized-vector FAISS search and BM25, fuses ranks with RRF, then reranks a small candidate pool with `cross-encoder/ms-marco-MiniLM-L-6-v2`.

## Model routing
`LLM_PROVIDER=ollama` is the default local-demo path. `LLM_PROVIDER=openai` switches providers without changing agent routing(but it is optional). Ollama requests disable Qwen thinking mode and use bounded generation.

## Artifact flow
Artifact intent is detected before generation. The LLM is instructed to return `<ANSWER>` and `<ARTIFACT>` sections. The backend parses and sanitizes the HTML, then returns it as a separate `artifact` object. The frontend renders only that field inside an iframe with an empty `sandbox`, preventing script execution.

## Persistence
Sessions and messages are persisted through SQLAlchemy. PostgreSQL is the required persistence backend. `DATABASE_URL` is loaded from `.env` first, with `.env.example` supported as a local fallback when no real `.env` exists.

## Deployment topology
The submitted local deployment uses `start.bat` to create/check `.venv`, install requirements, verify the Python environment, and start backend/frontend processes. Ollama runs on the host.


## Performance and observability
Provider instances are reused within a backend process, repeated retrieval queries are cached with a bounded in-process LRU cache, and retrieval models are warmed during application startup. These changes do not modify the retrieval stages, `TOP_K`, reranker, or generation limits.

Runtime diagnostics are separated into `logs/frontend.logs`, `logs/backend.logs`, and `logs/db.logs`. The logging layer sanitizes secrets and avoids message/SQL content. Engineering attempts, failed approaches, and corrections are captured in `agent_logs/`.
