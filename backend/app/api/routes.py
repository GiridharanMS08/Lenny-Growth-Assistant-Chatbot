from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.db.database import check_database_connection, get_db
from app.db.models import SessionModel, MessageModel, DeveloperConfigModel
from app.agents.agent import Agent
from app.rag.retrieval import retriever
from app.security.artifact_sanitizer import sanitize_html
from app.config import settings
from app.logging_config import backend_logger, frontend_logger, sanitize_log_value
import uuid
import time

router = APIRouter()

class FrontendLogRequest(BaseModel):
    event: str = Field(min_length=1, max_length=80)
    detail: str | None = Field(default=None, max_length=200)

class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str = Field(min_length=1, max_length=10000)

@router.get('/health')
def health():
    try:
        check_database_connection()
        database_ok = True
    except Exception:
        database_ok = False

    return {
        "status": "ok" if database_ok else "degraded",
        "database": database_ok,
        "index_ready": retriever.index is not None,
    }

@router.post('/logs/frontend', status_code=204)
def frontend_log(req: FrontendLogRequest):
    allowed_prefixes = ("app.", "chat.", "session.", "error.")
    event = req.event.strip().lower()
    if not event.startswith(allowed_prefixes):
        raise HTTPException(400, "Unsupported frontend event")
    frontend_logger.info(
        "event=%s detail=%s",
        sanitize_log_value(event),
        sanitize_log_value(req.detail or "-"),
    )
    return None


@router.post('/sessions')
def create_session(db: Session = Depends(get_db)):
    started = time.perf_counter()
    s = SessionModel(id=str(uuid.uuid4()), user_metadata={})
    db.add(s)
    db.commit()
    backend_logger.info("session_create duration_ms=%.1f", (time.perf_counter() - started) * 1000)
    return {"session_id": s.id}

@router.get('/sessions/{session_id}')
def get_session(session_id: str, db: Session = Depends(get_db)):
    s = db.get(SessionModel, session_id)
    if not s: raise HTTPException(404, 'Session not found')
    return {"session_id": s.id, "messages": [{"role":m.role,"content":m.content,"created_at":m.created_at} for m in s.messages]}

@router.post('/chat')
def chat(req: ChatRequest, db: Session = Depends(get_db)):
    started = time.perf_counter()
    if req.session_id:
        s = db.get(SessionModel, req.session_id)
    else:
        s = SessionModel(id=str(uuid.uuid4()), user_metadata={})
        db.add(s)
        db.commit()

    if not s:
        raise HTTPException(404, 'Session not found')

    history = [
        {"role": m.role, "content": m.content}
        for m in s.messages
    ]

    try:
        result = Agent().run(req.message, history)
    except Exception as e:
        backend_logger.error(
            "chat_failed duration_ms=%.1f error_type=%s",
            (time.perf_counter() - started) * 1000,
            type(e).__name__,
        )
        raise HTTPException(502, f'LLM or retrieval error: {e}')

    # Artifact content is returned separately from the chat answer.
    if result.get("artifact", {}).get("type") == "html":
        html = result["artifact"].get("content", "")
        result["artifact"]["content"] = sanitize_html(
            html[: settings.artifact_max_chars]
        )

    user_message = MessageModel(
        session_id=s.id,
        role='user',
        content=req.message,
    )
    assistant_message = MessageModel(
        session_id=s.id,
        role='assistant',
        content=result['answer'],
    )

    db.add(user_message)
    db.add(assistant_message)

    try:
        # Commit the conversation first. Diagnostic persistence is deliberately
        # best-effort so a diagnostics failure never prevents the user/Lenny
        # messages from being stored.
        db.commit()
    except Exception as e:
        db.rollback()
        backend_logger.error(
            "chat_persistence_failed duration_ms=%.1f error_type=%s",
            (time.perf_counter() - started) * 1000,
            type(e).__name__,
        )
        raise HTTPException(500, "Unable to save conversation")

    # Keep detailed retrieval/LLM diagnostics in a separate developer table.
    # The existing retrieval and generation pipeline is not changed.
    sources = result.get("sources", [])
    latency_ms = (time.perf_counter() - started) * 1000
    developer_config = DeveloperConfigModel(
        session_id=s.id,
        message_id=assistant_message.id,
        retrieved_chunks=[
            {
                "citation_id": source.get("citation_id"),
                "title": source.get("title"),
                "guest": source.get("guest"),
                "chunk_number": source.get("chunk_number"),
                "text": hit.get("text", ""),
            }
            for source, hit in zip(sources, result.get("retrieved_hits", []))
        ],
        reranking_scores=[
            {
                "citation_id": source.get("citation_id"),
                "score": source.get("score"),
            }
            for source in sources
        ],
        faiss_results=[
            {
                "citation_id": source.get("citation_id"),
                "score": source.get("vector_score"),
            }
            for source in sources
        ],
        bm25_results=[
            {
                "citation_id": source.get("citation_id"),
                "score": source.get("bm25_score"),
            }
            for source in sources
        ],
        sources=sources,
        llm_provider=str(result.get("provider", settings.llm_provider)),
        latency_ms=latency_ms,
        retrieval_count=len(sources),
    )

    try:
        db.add(developer_config)
        db.commit()
    except Exception as e:
        db.rollback()
        backend_logger.error(
            "developer_config_persistence_failed error_type=%s",
            type(e).__name__,
        )

    backend_logger.info(
        "chat_completed duration_ms=%.1f intent=%s provider=%s hits=%d",
        latency_ms,
        sanitize_log_value(result.get("intent", "unknown")),
        sanitize_log_value(result.get("provider", "unknown")),
        len(sources),
    )

    result['session_id'] = s.id
    return result

class ArtifactRequest(BaseModel):
    html: str = Field(min_length=1, max_length=100000)

@router.post('/artifacts')
def artifact(req: ArtifactRequest):
    return {"html": sanitize_html(req.html)}

@router.post('/ingestion')
def ingestion():
    try: count = retriever.ingest()
    except Exception as e: raise HTTPException(400, str(e))
    return {"chunks_indexed": count}
