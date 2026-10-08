# Architecture: The Lenny Growth Assistant

## 1. System Overview

The Lenny Growth Assistant is a full-stack conversational RAG application.

It consists of:

- **FastAPI backend** for sessions, messages, model health checks, chat routing, RAG retrieval, and LLM orchestration.
- **Supabase Cloud PostgreSQL** with the `pgvector` extension for persistent chat storage and vector search.
- **LLM strategy layer** for switching between Gemini/OpenAI cloud generation and local Ollama `llama3.2:3b`.
- **Next.js frontend** with Tailwind CSS and shadcn/ui for a polished chat and artifact experience.
- **Standalone ingestion script** to clone/pull Lenny's Podcast transcripts, chunk them, embed them, and store them in Supabase pgvector.

Docker is intentionally skipped. The app requires a local machine with at least 8 GB RAM and uses Supabase Cloud instead of a local database container.

## 2. High-Level Data Flow

```text
User -> Next.js UI -> FastAPI /api/chat
                     -> Session/message persistence in Supabase PostgreSQL
                     -> Router Agent chooses skill
                     -> Retriever fetches transcript chunks from pgvector
                     -> LLM Strategy invokes Gemini, OpenAI, or Ollama
                     -> Response returned to UI
                     -> UI renders chat and optional artifacts
```

## 3. Repository Structure

```text
F:\LENNY_GROWTH_ASSISTANT
â”œâ”€â”€ PRD.md
â”œâ”€â”€ architecture.md
â”œâ”€â”€ design.md
â”œâ”€â”€ README.md                         # Phase 5
â”œâ”€â”€ backend/                          # Phase 1+
â”‚   â”œâ”€â”€ app/
â”‚   â”‚   â”œâ”€â”€ __init__.py
â”‚   â”‚   â”œâ”€â”€ main.py
â”‚   â”‚   â”œâ”€â”€ core/
â”‚   â”‚   â”‚   â”œâ”€â”€ __init__.py
â”‚   â”‚   â”‚   â”œâ”€â”€ config.py             # Settings and env validation
â”‚   â”‚   â”‚   â””â”€â”€ errors.py             # Shared error helpers
â”‚   â”‚   â”œâ”€â”€ db/
â”‚   â”‚   â”‚   â”œâ”€â”€ __init__.py
â”‚   â”‚   â”‚   â”œâ”€â”€ session.py            # Async engine/sessionmaker
â”‚   â”‚   â”‚   â””â”€â”€ models.py             # SQLAlchemy ORM models
â”‚   â”‚   â”œâ”€â”€ schemas/
â”‚   â”‚   â”‚   â”œâ”€â”€ __init__.py
â”‚   â”‚   â”‚   â”œâ”€â”€ chat.py               # Request/response schemas
â”‚   â”‚   â”‚   â”œâ”€â”€ session.py
â”‚   â”‚   â”‚   â””â”€â”€ model_status.py
â”‚   â”‚   â”œâ”€â”€ api/
â”‚   â”‚   â”‚   â”œâ”€â”€ __init__.py
â”‚   â”‚   â”‚   â””â”€â”€ routes/
â”‚   â”‚   â”‚       â”œâ”€â”€ __init__.py
â”‚   â”‚   â”‚       â”œâ”€â”€ chat.py
â”‚   â”‚   â”‚       â”œâ”€â”€ sessions.py
â”‚   â”‚   â”‚       â””â”€â”€ models.py
â”‚   â”‚   â”œâ”€â”€ llm/
â”‚   â”‚   â”‚   â”œâ”€â”€ __init__.py
â”‚   â”‚   â”‚   â”œâ”€â”€ base.py               # BaseLLMClient
â”‚   â”‚   â”‚   â”œâ”€â”€ gemini_client.py      # Gemini implementation
â”‚   â”‚   â”‚   â”œâ”€â”€ openai_client.py      # OpenAI implementation
â”‚   â”‚   â”‚   â”œâ”€â”€ cloud_http.py         # Shared HTTP handling
â”‚   â”‚   â”‚   â”œâ”€â”€ ollama_client.py      # Ollama implementation
â”‚   â”‚   â”‚   â””â”€â”€ factory.py            # Provider selection
â”‚   â”‚   â”œâ”€â”€ rag/
â”‚   â”‚   â”‚   â”œâ”€â”€ __init__.py
â”‚   â”‚   â”‚   â”œâ”€â”€ embeddings.py
â”‚   â”‚   â”‚   â””â”€â”€ retriever.py
â”‚   â”‚   â””â”€â”€ skills/
â”‚   â”‚       â”œâ”€â”€ __init__.py
â”‚   â”‚       â”œâ”€â”€ router.py
â”‚   â”‚       â”œâ”€â”€ qa.py
â”‚   â”‚       â”œâ”€â”€ ship30.py
â”‚   â”‚       â””â”€â”€ artifact.py
â”‚   â”œâ”€â”€ tests/
â”‚   â”œâ”€â”€ .env.example
â”‚   â””â”€â”€ pyproject.toml
â”œâ”€â”€ frontend/                         # Phase 4+
â””â”€â”€ scripts/
    â””â”€â”€ ingest_transcripts.py          # Phase 2
```

## 4. Backend Architecture

### 4.1 FastAPI Responsibilities

The backend owns:

- API request validation.
- Chat session creation and retrieval.
- Message persistence.
- LLM provider selection.
- Model health checks.
- RAG retrieval.
- Skill routing.
- Formatting responses for the frontend.

### 4.2 API Endpoints

#### `POST /api/sessions`

Creates a new chat session.

Request:

```json
{
  "active_llm": "local"
}
```

Response:

```json
{
  "id": "uuid",
  "created_at": "iso-datetime",
  "active_llm": "local",
  "messages": []
}
```

#### `GET /api/sessions/{id}`

Returns a session and ordered messages.

#### `POST /api/chat`

Accepts a user message, persists it, invokes the router/skill/LLM stack, persists the assistant response, and returns the assistant message.

Request:

```json
{
  "session_id": "uuid",
  "message": "What are the best activation lessons from Lenny's Podcast?",
  "active_llm": "cloud"
}
```

#### `GET /api/models`

Returns model availability.

```json
{
  "cloud": {
    "provider": "gemini",
    "configured": true,
    "model": "gemini-3.5-flash-lite"
  },
  "local": {
    "provider": "ollama",
    "online": true,
    "required_model": "llama3.2:3b",
    "available_models": ["llama3.2:3b"]
  }
}
```

## 5. Database Design

The database is Supabase Cloud PostgreSQL with `pgvector` enabled.

### 5.1 Required Extensions

```sql
create extension if not exists vector;
```

### 5.2 Core Chat Tables

#### `sessions`

Stores chat session metadata.

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` | Primary key |
| `created_at` | `timestamptz` | Defaults to now |
| `active_llm` | `text` | `cloud` or `local` |

Future-ready optional columns:

- `user_id uuid null`
- `title text null`
- `updated_at timestamptz`

#### `messages`

Stores chat messages.

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` | Primary key |
| `session_id` | `uuid` | Foreign key to `sessions.id` |
| `role` | `text` | `user`, `assistant`, or `system` |
| `content` | `text` | Message body |
| `created_at` | `timestamptz` | Defaults to now |

### 5.3 Transcript Knowledge Tables

These tables are introduced during the RAG phase.

#### `transcript_documents`

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` | Primary key |
| `source_path` | `text` | Path in cloned GitHub repo |
| `episode_title` | `text` | Parsed from frontmatter/index |
| `guest_name` | `text` | Parsed from frontmatter/index |
| `tags` | `text[]` | Index metadata |
| `published_at` | `date null` | If available |
| `raw_metadata` | `jsonb` | Original frontmatter/index metadata |
| `created_at` | `timestamptz` | Defaults to now |

#### `transcript_chunks`

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` | Primary key |
| `document_id` | `uuid` | Foreign key to `transcript_documents.id` |
| `chunk_index` | `integer` | Stable chunk order |
| `content` | `text` | Enriched chunk content |
| `metadata` | `jsonb` | Guest/title/tags/source path |
| `embedding` | `vector` | Embedding vector |
| `created_at` | `timestamptz` | Defaults to now |

The embedding dimensionality depends on the selected embedding model. It must be configured consistently in the ingestion script and schema migration.

## 6. RAG Ingestion Pipeline

### 6.1 Source Repository

Transcript source:

```text
https://github.com/ChatPRD/lennys-podcast-transcripts
```

The ingestion script will clone the repository if it does not exist locally and pull updates if it does.

### 6.2 Parsing Strategy

For each Markdown transcript:

1. Read Markdown file.
2. Parse YAML frontmatter.
3. Locate relevant metadata from the `/index` folder where available.
4. Extract:
   - Episode title.
   - Guest name.
   - Tags.
   - Source path.
   - Optional publication date.
5. Structured JSON/YAML and Markdown frontmatter records in `/index` are indexed by
   filename/slug and merged with transcript frontmatter (transcript values take precedence).
   If no metadata exists, the transcript filename is used as its title and the guest is
   recorded as unknown.
6. Prepend metadata to raw transcript text before chunking:

```text
Episode Title: ...
Guest: ...
Tags: ...

Transcript:
...
```

This improves retrieval by ensuring each chunk carries semantic context even when the chunk text itself lacks explicit episode metadata.

### 6.3 Chunking Strategy

Use LangChain `RecursiveCharacterTextSplitter` with separators prioritized around paragraph boundaries:

```python
separators=["\n\n", "\n", ". ", " ", ""]
```

Target settings:

- Approximate chunk size: 1,000 tokens.
- Approximate overlap: 200 tokens.

The ingestion command uses the `cl100k_base` tokenizer through `tiktoken` and keeps a
200-token overlap. It processes at most 32 chunks per embedding/write batch to keep memory
bounded on machines with at least 8 GB RAM.

### 6.4 Embedding and Storage

Use `langchain-postgres` to load chunks into Supabase Cloud PostgreSQL with pgvector.

Run from the repository root with `python scripts/ingest_transcripts.py`; it loads
`backend/.env`. The ingestion script must:

- Validate `DATABASE_URL`.
- Validate embedding provider settings.
- Avoid loading the entire corpus into memory at once.
- Process files incrementally/batched to support machines with at least 8 GB RAM.
- Upsert deterministic chunk IDs so repeated runs do not duplicate unchanged chunks.
- Never clear the entire vector collection during routine ingestion.

The `PGVector` integration manages its collection/embedding tables. Enable the `vector`
extension in the Supabase project's SQL editor if it is not already enabled. Retrieval
uses the same collection name, embedding model, and connection URL as ingestion.

## 7. Retrieval Architecture

The backend retriever accepts a query string and returns top-K relevant chunks.

Flow:

```text
query -> embedding -> pgvector cosine similarity search -> ranked chunks -> prompt context
```

Retriever requirements:

- Configurable `top_k`, default around 5.
- Include source metadata with each chunk.
- Return empty context gracefully.
- Never fabricate sources.

## 8. LLM Strategy Pattern

The backend uses a provider-agnostic abstraction so chat orchestration does not depend on a specific LLM vendor.

### 8.1 `BaseLLMClient`

Responsibilities:

- Define async completion/chat interface.
- Accept system prompt, messages, optional tools, and timeout.
- Return normalized assistant output.
- Raise typed exceptions for provider errors.

Conceptual interface:

```python
class BaseLLMClient(ABC):
    provider: LLMProvider

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        ...
```

### 8.2 `GeminiClient` and `OpenAIClient`

Cloud strategy:

- Uses Gemini generateContent or OpenAI Responses through httpx.
- Defaults to `gemini-3.5-flash-lite` or `gpt-4.1-mini`.
- Select with `CLOUD_PROVIDER=gemini` or `openai`; configure the matching API key.
- Sends transcript context and skill instructions as text; no tool calling is enabled.
- Handles missing API key with a typed configuration error.

### 8.3 `OllamaClient`

Local strategy:

- Uses local Ollama HTTP API.
- Model: `llama3.2:3b`.
- Base URL: `http://localhost:11434`.
- Handles connection refused/timeouts.
- Uses conservative defaults for machines with at least 8 GB RAM; larger models and context windows may require more memory.

### 8.4 Factory Selection

The API selects the strategy from:

- Request-level `active_llm` override.
- Session-level `active_llm` default.
- Safe fallback behavior if unavailable.

## 9. Agentic Skill Architecture

The chat endpoint eventually delegates to a Router Agent with three skills.

### 9.1 Q&A Agent

- Default skill.
- Retrieves transcript chunks.
- Answers only from context.
- Refuses when evidence is insufficient.

### 9.2 Ship30for30 Generator

- Triggered by requests for essays, posts, threads, or Ship30for30 formatting.
- Retrieves context.
- Produces approximately 1,250 words.
- Requires hook, bullets, bolding, and clear takeaway.

### 9.3 Artifact Generator

- Triggered by requests for code, UI, Markdown, HTML, CSS, or renderable artifacts.
- Wraps renderable output in XML tags:

```xml
<artifact type="html">
...
</artifact>
```

The frontend uses these tags to extract and render artifacts.

## 10. Error Handling Strategy

### Backend

- Typed exceptions for provider configuration errors.
- Timeout handling around Gemini, OpenAI, and Ollama requests.
- Database errors translated into safe API errors.
- Pydantic validation for all request bodies.
- Clear HTTP status codes:
  - `400` invalid input.
  - `404` missing session.
  - `422` schema validation.
  - `503` unavailable model provider.
  - `500` unexpected internal error.

### Frontend

- Toasts or inline alerts for failed requests.
- Disabled send button while submitting.
- Clear Ollama offline indicator.
- Empty states for no sessions and no artifacts.

## 11. Environment Variables

Backend `.env`:

```env
DATABASE_URL=postgresql+asyncpg://...
CLOUD_PROVIDER=gemini
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-3.5-flash-lite
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4.1-mini
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b
```

Frontend `.env.local`:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

## 12. No Docker Policy

Docker is explicitly not used in this project.

Reasons:

- User machine requires at least 8 GB RAM.
- Local Dockerized databases and services would consume unnecessary memory.
- Supabase Cloud provides the required PostgreSQL and pgvector capabilities remotely.
- Ollama local model selection defaults to `llama3.2:3b` to keep memory usage practical.

