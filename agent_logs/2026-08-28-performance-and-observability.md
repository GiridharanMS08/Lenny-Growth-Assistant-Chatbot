# 2026-08-28 — Performance and observability pass

## Objective
Improve response speed, retrieval-path efficiency, and operational visibility without changing the configured retrieval stages or model/generation settings.

## Attempt 1 — considered changing retrieval breadth
- Idea: reduce the hybrid candidate pool or change retrieval/reranking behavior to make CPU inference faster.
- Result: **rejected**.
- Reason: changing candidate breadth can change recall and therefore answer/source accuracy.
- Correction: keep the existing FAISS + BM25 + RRF + Cross-Encoder path and configured `TOP_K=3` unchanged.

## Attempt 2 — considered changing generation settings
- Idea: lower LLM generation limits to reduce latency.
- Result: **rejected**.
- Reason: generation limits are part of the existing behavior/configuration and can affect answer quality.
- Correction: keep the existing QA/artifact/Ship 30 token limits unchanged.

## Implemented low-risk performance corrections
1. Reuse a single provider/client instance per process instead of constructing a new provider and HTTP client for every chat request.
2. Cache repeated retrieval queries in-process with bounded LRU caching.
3. Clear retrieval cache automatically after re-ingestion so stale results cannot survive an index rebuild.
4. Warm retrieval models during FastAPI startup so the first real user request does not pay the model-load cost.

## Implemented observability corrections
- Added dedicated `logs/frontend.logs`, `logs/backend.logs`, and `logs/db.logs`.
- Backend request/retrieval timing is logged without user message content.
- Database connectivity/session lifecycle is logged without SQL credentials or parameters.
- Frontend sends only small, allow-listed event names to the backend asynchronously; events are sanitized before being written.

## Security correction
- The distributed `.env.example` contained a concrete-looking PostgreSQL password.
- Correction: replace it with `YOUR_PASSWORD` so credentials are not committed.

## PostgreSQL verification
The project configuration points to PostgreSQL as required. In this isolated validation environment, the connection test could not complete because the runtime did not have the `psycopg` package installed and therefore could not open a PostgreSQL connection. The submitted startup script already performs `SELECT 1` using the project's virtual-environment Python on the user's machine.

## Validation correction
- Initial log-sanitizer test exposed a bug in the generic secret masking path for `Bearer ...` values.
- Correction: handle Bearer credentials with an explicit masking branch.
- Re-tested with PostgreSQL URL, password, bearer token, and normal event metadata; sensitive values are masked and normal metadata is preserved.
