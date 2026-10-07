from __future__ import annotations

from app.core.config import get_settings
from app.llm.base import BaseLLMClient, LLMMessage, LLMRequest
from app.rag.retriever import format_context, retrieve_relevant_chunks

ARTIFACT_SYSTEM_PROMPT = """You are an artifact generator for The Lenny Growth Assistant.

Use the provided transcript context when the artifact is about product/growth advice.
Do not invent Lenny's Podcast claims outside the context.

When generating a renderable artifact, wrap exactly one artifact in XML:
<artifact type="markdown">...</artifact>
or
<artifact type="html">...</artifact>

Rules:
- Put a short conversational explanation before the artifact.
- The artifact body must be complete and directly renderable.
- HTML artifacts must include complete HTML/CSS in one document.
- Do not wrap the artifact in Markdown code fences.
"""


async def run_artifact_skill(llm_client: BaseLLMClient, user_message: str) -> str:
    chunks = await retrieve_relevant_chunks(user_message, top_k=6, provider=llm_client.provider)
    context = (
        format_context(
            chunks,
            max_chars=get_settings().rag_context_max_chars if llm_client.provider == "local" else None,
        )
        or "No transcript context was retrieved. Be transparent if grounding is required."
    )
    return (
        await llm_client.complete(
            LLMRequest(
                system_prompt=ARTIFACT_SYSTEM_PROMPT,
                messages=[
                    LLMMessage(
                        role="user",
                        content=f"Transcript context:\n{context}\n\nArtifact request:\n{user_message}",
                    )
                ],
                temperature=0.25,
                max_tokens=2_400,
            )
        )
    ).content
