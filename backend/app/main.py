from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import time

from app.api.routes import router
from app.config import settings
from app.db.database import Base, engine
from app.logging_config import backend_logger
from app.rag.retrieval import retriever


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Retain automatic table creation for the take-home/local workflow.
    Base.metadata.create_all(bind=engine)
    try:
        retriever._ensure_model()
        retriever._ensure_reranker()
        backend_logger.info("retrieval models warmed")
    except Exception as exc:
        backend_logger.error("retrieval warmup failed error_type=%s", type(exc).__name__)
    yield


app = FastAPI(
    title="Lenny Growth Assistant",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in settings.cors_origins.split(",") if x.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def request_timing_middleware(request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    backend_logger.info(
        "request method=%s path=%s status=%d duration_ms=%.1f",
        request.method,
        request.url.path,
        response.status_code,
        (time.perf_counter() - started) * 1000,
    )
    return response


app.include_router(router)
