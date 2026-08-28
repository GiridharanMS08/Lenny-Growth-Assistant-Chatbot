# Lenny Growth Assistant (No Docker)

A grounded product and growth assistant over Lenny's Podcast transcripts.

## Run locally on Windows

### Prerequisites
- Python 3.10+ (3.13 is supported by the current environment)
- Node.js 18+
- Ollama
- PostgreSQL 14+ (local server or reachable PostgreSQL instance)
- `qwen3:1.7b` for the default 8 GB-RAM-friendly demo

### One-command start
Double-click `start.bat`.

The script:
1. Creates `.venv` if needed.
2. Checks `requirements.txt` using the same Python that runs FastAPI.
3. Verifies `rank_bm25`.
4. Checks Ollama and the configured local model.
5. Validates the PostgreSQL `DATABASE_URL` and opens a test connection.
6. Starts FastAPI with `--reload` and the Vite frontend.

Then open `http://localhost:5173`.

### Knowledge ingestion
Open `http://127.0.0.1:8000/docs` and run `POST /ingestion` after adding/changing transcript Markdown files. Ingestion builds `index.faiss` and `chunks.json`.

### Retrieval
The retrieval pipeline uses structure-aware semantic chunking, FAISS semantic search, BM25 keyword search, Reciprocal Rank Fusion (RRF), and a Cross-Encoder reranker. The source folder is `data/transcripts`, so both `episodes/` and `index/` Markdown files are eligible for ingestion.

### Artifacts
When a user requests an artifact (for example, “Create a growth strategy document”), the agent returns:
- a short chat answer;
- an HTML artifact;
- source metadata.

The frontend renders the artifact in a sandboxed iframe beside the conversation. Generated HTML is sanitized server-side and JavaScript is not allowed.

### Database configuration

PostgreSQL is required for session and message persistence.

The backend resolves configuration in this order:
1. root `.env`
2. `backend/.env`
3. root `.env.example`
4. `backend/.env.example`

This means a fresh clone can be configured by editing `intern/.env.example` and restarting the backend. Once a real `.env` exists, it takes precedence. `DATABASE_URL` must use PostgreSQL (`postgresql+psycopg://...`).

Example:

```text
DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/lenny
```

### Provider configuration
Set `LLM_PROVIDER=ollama` for the required local demo. Set `LLM_PROVIDER=openai` to use the optional OpenAI provider. The selected provider is returned by the API and shown in the UI.

### Manual backend
```bash
cd backend
..\.venv\Scripts\activate
uvicorn app.main:app --reload
```

### Manual frontend
```bash
cd frontend
npm install
npm run dev
```

## Important
- Local deployment intentionally uses `start.bat`; Docker is not required for the submitted local workflow.
- PostgreSQL is the required persistence backend for the submitted workflow.
- Never commit `.env` or API keys.

## API
- `GET /health`
- `POST /sessions`
- `GET /sessions/{session_id}`
- `POST /chat`
- `POST /artifacts`
- `POST /ingestion`


### Performance and observability

The runtime keeps the existing retrieval contract (`TOP_K=3`, FAISS + BM25 + RRF + Cross-Encoder) and existing LLM generation limits. Performance improvements are limited to provider/client reuse, bounded repeated-query caching, and startup warming of retrieval models.

Runtime logs are written to:
- `logs/frontend.logs`
- `logs/backend.logs`
- `logs/db.logs`

Logs intentionally exclude user message bodies, SQL parameters, database credentials, API keys, and tokens. Engineering attempts and corrections are documented under `agent_logs/`.
