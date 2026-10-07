from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import LLMProvider, get_settings
from app.core.errors import ConfigurationError, LLMProviderError, LLMProviderUnavailableError
from app.db.models import ChatSession, Message
from app.db.session import get_db_session
from app.llm.factory import get_llm_client
from app.schemas.chat import ChatRequest, ChatResponse
from app.skills.artifact import run_artifact_skill
from app.skills.qa import run_qa_skill
from app.skills.router import SkillName, route_skill
from app.skills.ship30 import run_ship30_skill

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db_session),
) -> ChatResponse:
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.id == payload.session_id)
        .options(selectinload(ChatSession.messages))
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found.",
        )

    selected_provider = (
        "cloud" if get_settings().app_env == "cloud"
        else cast(LLMProvider, payload.active_llm or session.active_llm)
    )
    session.active_llm = selected_provider

    user_message = Message(
        session_id=session.id,
        role="user",
        content=payload.message.strip(),
    )
    db.add(user_message)

    try:
        llm_client = get_llm_client(selected_provider)
        skill = await route_skill(llm_client, payload.message.strip())
        if skill is SkillName.SHIP30:
            response_content = await run_ship30_skill(llm_client, payload.message.strip())
        elif skill is SkillName.ARTIFACT:
            response_content = await run_artifact_skill(llm_client, payload.message.strip())
        else:
            response_content = await run_qa_skill(llm_client, payload.message.strip())
    except ConfigurationError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except LLMProviderUnavailableError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except LLMProviderError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    assistant_message = Message(
        session_id=session.id,
        role="assistant",
        content=response_content,
    )
    db.add(assistant_message)
    await db.commit()
    await db.refresh(assistant_message)

    return ChatResponse(
        session_id=session.id,
        active_llm=selected_provider,
        skill=skill.value,
        message=assistant_message,
    )
