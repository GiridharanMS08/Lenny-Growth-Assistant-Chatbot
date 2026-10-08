# Lenny Growth Assistant

A conversational workspace for asking questions about Lenny's Podcast transcripts, producing grounded Ship30for30 posts, and previewing generated Markdown or HTML artifacts.

## Architecture

- `backend/`: FastAPI API, async SQLAlchemy session/message storage, model strategy layer, RAG retrieval, and skill router.
- `scripts/ingest_transcripts.py`: clones/pulls the transcript source, enriches metadata, creates token-aware chunks, and stores embeddings in Supabase pgvector.
- `frontend/`: Next.js application with a resizable chat workspace and sandboxed artifact preview.

The app intentionally has no Docker configuration. Supabase Cloud hosts PostgreSQL and pgvector; Ollama uses `llama3.2:3b` locally by default. Local development requires at least 8 GB RAM.

## Prerequisites

- Python 3.11+
- Node.js 20+
- A Supabase project with the `vector` extension enabled
- Ollama, with `llama3.2:3b` and `nomic-embed-text` pulled
- An OpenRouter API key for Railway cloud mode (local Ollama needs no model API key)

```powershell
ollama pull llama3.2:3b
ollama pull nomic-embed-text
```

In Supabase SQL Editor, enable pgvector once:

```sql
create extension if not exists vector;
```

## Backend setup

```powershell
cd backend
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Update `backend/.env`. `DATABASE_URL` must use the SQLAlchemy asyncpg dialect:

```env
DATABASE_URL=postgresql+asyncpg://postgres:<password>@<supabase-host>:5432/postgres
CLOUD_PROVIDER=gemini
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.5-flash-lite
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
GEMINI_EMBEDDING_API_KEY=
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
GEMINI_EMBEDDING_DIMENSIONS=768
GEMINI_EMBEDDING_BATCH_SIZE=8
GEMINI_VECTOR_COLLECTION_NAME=lenny_podcast_transcripts_gemini
```

For a quick development schema creation, set `CREATE_DB_ON_STARTUP=true` temporarily. Use migrations for a deployed environment.

Start the API:

```powershell
fastapi dev app/main.py
```

Swagger is available at `http://localhost:8000/docs`.

## Ingest transcripts

Run from the repository root after backend setup:

```powershell
python scripts/ingest_transcripts.py
```

It clones or updates `ChatPRD/lennys-podcast-transcripts`, merges metadata from frontmatter and the repository index, prepends title/guest/tags, splits with approximately 1,000-token chunks and a 200-token overlap, then upserts chunks into the configured pgvector collection.

## Frontend setup

```powershell
cd frontend
Copy-Item .env.local.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000`. The model selector checks `/api/models`; select Local when Ollama and `llama3.2:3b` are ready, or Cloud after configuring the selected provider's API key.

## Cloud providers

Set `CLOUD_PROVIDER=gemini` and fill `GEMINI_API_KEY`, or set `CLOUD_PROVIDER=openai` and fill `OPENAI_API_KEY`, in `backend/.env`. Only the selected provider needs a key. Change `GEMINI_MODEL` or `OPENAI_MODEL` there to choose another model available to your account. Restart FastAPI after changes; the frontend obtains the provider name and model from `/api/models`.

Create a Gemini key in [Google AI Studio](https://aistudio.google.com/apikey) or an OpenAI key in the [OpenAI API platform](https://platform.openai.com/api-keys). Availability, quotas, and API billing depend on your account. The UI's "key configured" status checks key presence, not validity or remaining quota.

The adapters use [Gemini generateContent](https://ai.google.dev/api/generate-content) and [OpenAI Responses](https://developers.openai.com/api/docs/guides/text) over the existing `httpx` dependency. No Anthropic SDK is required. Secrets stay on the backend, and request errors identify missing keys, unavailable models, and quota limits.

### Railway cloud RAG (FastEmbed + hosted model)

The original Ollama ingestion script and collection remain unchanged. For Railway, use the dedicated `transcript_chunks_cloud` table because `BAAI/bge-small-en-v1.5` produces 384-dimensional vectors and must never be mixed with the local Ollama embeddings.

Follow [the Railway deployment guide](docs/RAILWAY_DEPLOYMENT.md) for the exact commands and variables. `APP_ENV=cloud` uses OpenRouter and supports explicitly selected free or paid models. The default is `nvidia/nemotron-3.5-lightning:free`; set `OPENROUTER_MODEL` to a full catalog ID such as `deepseek/deepseek-v4.1-flash` to use a paid model with account credits. Free selections retain zero-price filters. Provider fallback and automatic model routing are disabled, so the application never silently switches from a free model to a paid one. Groq and other legacy adapters are not selected by this Railway path.

Transcript Q&A uses cosine retrieval, removes duplicate passages, and allows evidence from multiple episodes. Answers display exact excerpts verified against the context and cite only the passages used. If no retrieved passage supports the question, the response says it could not find a supportive transcript source. Model or API errors are reported separately from missing evidence.

The root `requirements.txt` enables Railway's Python detection. Railway builds from the repository root, downloads the embedding model into the image, and starts the backend. Runtime model loading uses that cache with `FASTEMBED_LOCAL_FILES_ONLY=true`. Cloud startup checks required variables and warms the CPU model before accepting traffic.

For local cloud testing, use the ignored `backend/.env.cloud` overlay and set `APP_ENV_FILE=.env.cloud`. The existing `backend/.env` remains the local Ollama configuration. Cloud ingestion uses BGE's own tokenizer with 480-token chunks and 80-token overlap, preserving the full text within its 512-token input limit. A `--direct-db` ingestion option uses the existing Supabase PostgreSQL connection when API credentials are not yet configured; Railway retrieval still uses the Supabase RPC.

### Cloud Gemini RAG migration

Cloud mode uses Gemini `gemini-embedding-001` and the separate physical table `public.langchain_pg_embedding_gemini`. The migration reads the exact existing chunk text and metadata from the Ollama collection in `langchain_pg_embedding`, without re-running the splitter or modifying original tables:

```powershell
python scripts/migrate_gemini_embeddings.py --apply
```

Run this after setting `GEMINI_API_KEY` (or `GEMINI_EMBEDDING_API_KEY`) and `DATABASE_URL`. It writes 768-dimensional Gemini vectors with insert-only SQL into the new table. Rerunning skips completed chunks; it refuses to overwrite conflicting rows. Each API batch is saved before requesting the next. The default pause is 10 seconds between batches; free-tier quota can still stop migration. Without `--apply`, it only inspects the source. Cloud question vectors use the same configured model and dimensions, cosine search reads only the new table, and `CLOUD_PROVIDER=gemini` selects Gemini generation. Restart FastAPI to load the changed retrieval code. Test cloud answers after migration completes. Original Ollama tables and the former Gemini collection remain untouched. [Gemini embedding documentation](https://ai.google.dev/api/embeddings)

## Skills

- **Q&A**: retrieves transcript chunks and answers from those chunks only.
- **Ship30for30**: uses retrieved evidence to create a roughly 1,250-word skimmable post with a hook, bolding, bullets, and a clear takeaway.
- **Artifact**: requests for Markdown, HTML, CSS, UI, or code produce a single `<artifact>` block. The browser removes that block from chat and renders Markdown or sandboxed HTML in the artifact panel.

## Test

```powershell
cd backend
pytest
```

