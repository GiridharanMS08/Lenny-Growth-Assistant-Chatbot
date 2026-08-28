# PRD — Lenny Growth Assistant

## Discovery brief
### User and problem
Primary users are product managers, growth practitioners, founders, and operators who want actionable answers from Lenny's Podcast without manually searching transcripts. The assistant removes the retrieval and synthesis burden while preserving source traceability.

### Success metrics
- ≥80% of evaluation questions have at least one relevant transcript source.
- 0 unsupported factual claims in a curated grounding test set.
- Fresh clone reaches a usable local demo with documented commands.
- Median local response latency is tracked during the demo.

### Assumptions
- Transcript files are available from an approved repository at ingestion time.
- The evaluator can run Ollama locally.
- PostgreSQL is the required local/hosted persistence backend and is configured through `DATABASE_URL`.
- Local model quality is sufficient for the demo; cloud models are optional for comparison.

### Scope
**Included:** grounded Q&A, follow-up context, source display, Ship 30 skill, HTML artifact generation, sandboxed viewer, local/cloud provider toggle, persistence, tests, one-command start.bat deployment.

**Excluded:** authentication, multi-tenant billing, production-scale vector infrastructure, arbitrary JavaScript execution in artifacts, autonomous web browsing.

### Risks and trade-offs
- Hallucination: strict evidence-only system prompt and visible sources.
- Local model quality: Ollama is the required demo path; cloud provider is a configurable fallback.
- Latency: embeddings are cached in a local FAISS index.
- Cost: local inference avoids API cost for the required demo.
- Artifact security: generated HTML is sanitized and displayed in a sandboxed iframe with no scripts.
- Data leakage: secrets live in `.env`; no secrets are committed.

## Artifact flow
1. User requests a document/HTML artifact.
2. Agent detects artifact intent and retrieves relevant transcript context.
3. Local or cloud LLM generates a short answer plus a self-contained HTML artifact.
4. Backend sanitizes the artifact and returns it separately from the chat answer.
5. Frontend renders it in the Artifact Viewer.

## Core flow
1. User starts a session.
2. User asks a question.
3. Retriever returns relevant transcript chunks.
4. Agent routes the request to Q&A, Ship 30, or artifact behavior.
5. Selected LLM generates a grounded response.
6. Backend persists user/assistant messages.
7. UI displays answer and sources; artifacts render in the side panel.
