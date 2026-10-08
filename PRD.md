# PRD: The Lenny Growth Assistant

## 1. Problem Statement

Product builders, founders, growth leaders, and operators frequently rely on Lenny's Podcast for high-signal product and growth insights. However, the source material is spread across many long-form transcripts, making it difficult to quickly retrieve grounded answers, synthesize repeatable frameworks, or transform insights into polished written content.

The Lenny Growth Assistant is a full-stack, AI-powered conversational application that ingests Lenny's Podcast transcripts, answers user questions using only that transcript corpus, and generates high-quality content or renderable artifacts on demand.

The assistant must be reliable, source-grounded, extensible, and able to run on a local development machine with at least 8 GB of RAM.

## 2. Goals

- Provide accurate Q&A grounded strictly in ingested Lenny's Podcast transcripts.
- Support multi-session chat history.
- Support switching between cloud and local LLM execution.
- Generate formatted long-form Ship30for30-style essays from transcript-grounded insights.
- Generate renderable artifacts such as Markdown, HTML, and CSS snippets.
- Deliver a polished ChatGPT/Claude-inspired UI with a first-class artifact viewer.
- Avoid Docker entirely due to local hardware constraints.

## 3. Non-Goals

- No Docker-based local development environment.
- No local PostgreSQL database requirement.
- No training or fine-tuning custom models.
- No guarantee that generated answers cover information outside the transcript corpus.
- No production authentication in the initial take-home scope, though the schema should remain extensible for future users.

## 4. Target Users

### Primary User

A product/growth operator who wants fast, grounded answers from Lenny's Podcast transcripts.

### Secondary Users

- Founders researching growth strategy.
- PMs preparing briefs or internal docs.
- Content creators converting podcast insights into essays.
- Engineers/evaluators reviewing architecture, RAG quality, and UI execution.

## 5. Core User Journeys

### Journey 1: Ask a Grounded Question

1. User opens the app.
2. User starts a new chat session.
3. User asks a question such as: "What does Lenny's Podcast say about activation metrics?"
4. Backend retrieves relevant transcript chunks from Supabase pgvector.
5. LLM answers using only retrieved transcript context.
6. UI displays a concise, grounded answer and avoids unsupported claims.

### Journey 2: Generate a Ship30for30 Essay

1. User asks: "Turn this into a Ship30for30-style post about onboarding."
2. Router agent selects the Ship30for30 skill.
3. Backend retrieves relevant transcript context.
4. LLM produces a highly skimmable essay of approximately 1,250 words with:
   - Strong hook.
   - Heavy bulleting.
   - Bolded key ideas.
   - Clear takeaway.
5. UI renders the response in the conversation.

### Journey 3: Generate a Renderable Artifact

1. User asks: "Create a simple HTML landing page based on this growth framework."
2. Router agent selects the Artifact Generator skill.
3. LLM wraps the artifact in explicit XML tags such as `<artifact type="html">...</artifact>`.
4. Frontend strips the artifact from the chat bubble.
5. Artifact panel expands automatically.
6. UI renders HTML/CSS safely in a sandboxed iframe.

### Journey 4: Switch Between Cloud and Local Models

1. User opens the LLM selector in the header.
2. App displays the selected cloud provider's key configuration and Ollama availability.
3. User selects Cloud or Local.
4. Subsequent messages use the selected strategy.
5. If the selected provider is unavailable, the backend returns a clear, actionable error.

## 6. Functional Requirements

### Chat and Sessions

- Create a new chat session.
- Fetch an existing session with messages.
- Persist messages with role and content.
- Store active LLM preference per session.
- Support future expansion to authenticated users.

### RAG Q&A

- Ingest Markdown transcripts from `https://github.com/ChatPRD/lennys-podcast-transcripts`.
- Parse YAML frontmatter where available.
- Enrich chunks with guest name, episode title, and tags from index metadata.
- Store embeddings in Supabase Cloud PostgreSQL using pgvector.
- Retrieve top-K relevant chunks using vector similarity.
- Require answers to be grounded only in retrieved transcript context.
- Refuse or qualify answers when context is insufficient.

### Agentic Skill Routing

- Route general questions to the Q&A Agent.
- Route essay/post requests to the Ship30for30 Generator.
- Route code/UI/Markdown requests to the Artifact Generator.
- Prefer structured tool/function calling where supported.
- Fall back to prompt-based routing for local Ollama models if JSON/tool calling is unreliable.

### LLM Providers

- Cloud providers: Gemini and OpenAI via their REST APIs, selected with CLOUD_PROVIDER in backend/.env.
- Local provider: Ollama `llama3.2:3b` via local HTTP API.
- Shared interface via strategy pattern.
- Timeout and availability handling for both providers.

### Model Health

- `GET /api/models` checks:
  - Whether the selected cloud provider's API key is configured.
  - Whether Ollama is reachable at `localhost:11434`.
  - Which local models are available.

### Artifact Rendering

- Detect `<artifact>` XML blocks in assistant responses.
- Remove artifact payload from regular chat bubble.
- Render Markdown artifacts using Markdown rendering.
- Render HTML/CSS artifacts inside a sandboxed iframe.

## 7. Non-Functional Requirements

### Reliability

- Explicit error handling for missing environment variables.
- Explicit error handling for Ollama offline/timeouts.
- Explicit error handling for database connection failures.
- Graceful frontend empty, loading, and error states.

### Security

- Never expose server-side API keys to the frontend.
- Render HTML artifacts in sandboxed iframes.
- Validate request payloads with strict schemas.
- Keep database connection strings in `.env` only.

### Performance

- Designed for a machine with at least 8 GB RAM.
- No Docker.
- Remote Supabase database instead of local PostgreSQL.
- Local model limited to Ollama `llama3.2:3b`.
- Keep backend modular and lightweight.

### Maintainability

- Clear separation of API routes, services, DB models, RAG utilities, and LLM clients.
- Strict typing with Pydantic/SQLAlchemy typing on the backend and TypeScript on the frontend.
- Extensible skill architecture.

## 8. Success Metrics

- User can ingest transcripts into Supabase pgvector successfully.
- User can create sessions and send messages.
- RAG answers remain grounded in transcript context.
- App clearly refuses when transcript evidence is insufficient.
- Cloud/local model toggle works with understandable status indicators.
- Artifact panel renders Markdown and sandboxed HTML/CSS correctly.
- App can run locally without Docker on a machine with at least 8 GB RAM.
- README enables setup by a reviewer in under 20 minutes, excluding transcript ingestion time.

## 9. Constraints

- Local machine requires at least 8 GB RAM.
- Docker is prohibited.
- Database is Supabase Cloud PostgreSQL with pgvector.
- Local LLM is Ollama `llama3.2:3b`.
- Backend must use FastAPI and async PostgreSQL access.
- Frontend must use Next.js, Tailwind CSS, and shadcn/ui components.

## 10. Phase Delivery Plan

1. Phase 0: Planning and documentation.
2. Phase 1: Backend and database foundation.
3. Phase 2: RAG ingestion and retrieval.
4. Phase 3: Agentic skills and routing.
5. Phase 4: Frontend and artifact UX.
6. Phase 5: Tests, README, and submission prep.
