from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.llm.ollama_client import list_ollama_models
from app.schemas.model_status import CloudModelStatus, LocalModelStatus, ModelStatusResponse

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=ModelStatusResponse)
async def get_models() -> ModelStatusResponse:
    settings = get_settings()
    if settings.app_env == "cloud":
        ollama_online, available_models, ollama_error = False, [], "Disabled in cloud mode."
    else:
        ollama_online, available_models, ollama_error = await list_ollama_models(settings)

    return ModelStatusResponse(
        cloud=CloudModelStatus(
            provider=settings.cloud_llm_provider if settings.app_env == "cloud" else settings.cloud_provider,
            configured=settings.is_cloud_configured,
            model=settings.cloud_model,
        ),
        local=LocalModelStatus(
            online=ollama_online,
            required_model=settings.ollama_model,
            available_models=available_models,
            error=ollama_error,
        ),
    )
