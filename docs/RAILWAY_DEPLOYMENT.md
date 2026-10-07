# Railway deployment

The backend runs FastEmbed on CPU, retrieves 384-dimensional BGE vectors through
Supabase RPC, and generates answers with free Gemma through OpenRouter. All chat
history and vectors remain in Supabase. Local mode continues to use Ollama.
Cloud mode rejects paid model IDs and other cloud providers before generation.
Each request caps prompt, completion, and per-request prices at zero and disables
provider fallback. Free endpoint failures return an error; no paid model is tried.

## Test locally

Run these commands from the repository root. The isolated environment avoids
changing packages in your existing local environment:

```powershell
python -m venv backend/.venv-cloud
backend/.venv-cloud/Scripts/python.exe -m pip install -r requirements.txt
backend/.venv-cloud/Scripts/python.exe backend/prepare_cloud_model.py
```

Save these values in `backend/.env.cloud`. The database URL is inherited from the
existing `backend/.env` during local tests:

```env
APP_ENV=cloud
CLOUD_LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=<your OpenRouter key>
OPENROUTER_MODEL=google/gemma-4-31b-it:free
SUPABASE_URL=https://<your-project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<your backend service-role key>
CORS_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000"]
CREATE_DB_ON_STARTUP=false
```

Create the new cloud table/RPC and ensure `sessions` and `messages` exist:

```powershell
backend/.venv-cloud/Scripts/python.exe scripts/init_supabase_cloud.py --apply
```

The equivalent vector SQL is in `supabase/cloud_rag.sql`. It uses a separate
table, enables RLS, grants backend service-role access, and supports vector
extensions installed in either `public` or `extensions`. The schema helper
refuses incompatible existing tables or an RPC serving another table.

Ingest a small sample, then test a real cloud request:

```powershell
backend/.venv-cloud/Scripts/python.exe scripts/ingest_supabase_cloud.py --limit 1
backend/.venv-cloud/Scripts/python.exe scripts/check_cloud_deployment.py --llm-only
backend/.venv-cloud/Scripts/python.exe scripts/check_cloud_deployment.py
```

The full check creates one Supabase chat session and tests CPU embeddings,
retrieval RPC, the free model, and message persistence. An empty retrieval result
is a failure, even if `/health` succeeds. Questions must match the sample data;
use `--question "<a question about the ingested episode>"` if necessary.

Ingest the entire local corpus by omitting `--limit`. Identical chunks use stable
IDs and are upserted. Changed transcripts create new IDs; old revisions are not
automatically deleted. Both commands write only the dedicated cloud table:

```powershell
backend/.venv-cloud/Scripts/python.exe scripts/ingest_supabase_cloud.py
# Alternative using your existing Supabase PostgreSQL credentials:
backend/.venv-cloud/Scripts/python.exe scripts/ingest_supabase_cloud.py --direct-db
```

To use the cloud backend with the local frontend:

```powershell
$env:APP_ENV_FILE=".env.cloud"
backend/.venv-cloud/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8001
```

Set the frontend's `NEXT_PUBLIC_API_BASE_URL=http://localhost:8001`. This leaves
any existing local backend on port 8000 available. Clear the overlay to return
to the local configuration:

```powershell
Remove-Item Env:APP_ENV_FILE -ErrorAction SilentlyContinue
```

## Configure Railway

Create a backend service from your GitHub repository with these settings:

| Setting | Value |
| --- | --- |
| Root Directory | `/` (repository root) |
| Config File | `/railway.toml` |
| Builder | Railpack |
| Healthcheck Path | `/health` |
| Python | `3.13`, from the root `.python-version` |

The root Python manifest solves language detection without selecting the
frontend. Leave Railway's custom build/start overrides blank so `railway.toml`
controls them. Its build installs dependencies and downloads the model. Its
start command changes into `backend/` and binds Uvicorn to `0.0.0.0:$PORT`.
Raw transcripts, the large ZIP archive, virtual environments, and generated
frontend files are excluded by `.gitignore`; the files remain available locally.

Add these under Railway Variables (Railway does not import `.env.cloud`):

```env
APP_ENV=cloud
CLOUD_LLM_PROVIDER=openrouter
DATABASE_URL=postgresql+asyncpg://<user>:<url-encoded-password>@<supabase-session-pooler-host>:5432/postgres
SUPABASE_URL=https://<your-project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<your backend service-role key>
OPENROUTER_API_KEY=<your OpenRouter key>
OPENROUTER_MODEL=google/gemma-4-31b-it:free
CORS_ORIGINS=["https://<your-frontend-domain>"]
FASTEMBED_THREADS=2
FASTEMBED_LOCAL_FILES_ONLY=true
CREATE_DB_ON_STARTUP=false
RAG_TOP_K=5
RAG_MIN_COSINE_SIMILARITY=0.30
```

Use the Supabase session pooler on port 5432 with the asyncpg URL prefix for chat
storage. No Railway database or persistent volume is needed: vectors and chats
live in Supabase, while the model cache is packaged in the deployment image.
Do not put `APP_ENV_FILE` in Railway; it is a local-test convenience.

Generate a public backend domain. Configure the frontend separately with
`NEXT_PUBLIC_API_BASE_URL=https://<your-backend>.up.railway.app` (no `/api` suffix).
Rebuild the frontend after changing that variable. Use its actual HTTPS origin
in backend `CORS_ORIGINS`, with no trailing slash or wildcard.

After deployment, verify `/health`, `/api/models`, create a session, and send a
transcript question. `/api/models` should show `openrouter`, the `:free` model, and local
Ollama as disabled. Startup validates variables and the cached model;
`/health` itself does not prove Supabase connectivity or free endpoint availability.
Free models have usage quotas and may be temporarily unavailable. API keys are
still required for authentication, but the selected model has zero token pricing.
Railway hosting and Supabase plans are separate from model API costs.

Current checks and provider references:

- [Railpack Python detection](https://railpack.com/languages/python/)
- [Railway monorepo settings](https://docs.railway.com/deployments/monorepo)
- [OpenRouter free models](https://openrouter.ai/docs/guides/routing/model-variants/free)
- [OpenRouter zero-price provider filters](https://openrouter.ai/docs/guides/routing/provider-selection)
- [Groq Llama 3.3 deprecation](https://console.groq.com/docs/deprecations)
