from __future__ import annotations

from app.core.config import get_settings
from app.llm.base import BaseLLMClient, LLMMessage, LLMRequest
from app.rag.retriever import format_context, format_sources, retrieve_relevant_chunks

QA_SYSTEM_PROMPT = """You are The Lenny Growth Assistant, a transcript-grounded Q&A agent.

Rules:
1. Answer ONLY using the provided transcript context.
2. If the context is insufficient, say: "I don't have enough transcript evidence to answer that."
3. Do not use outside knowledge, even if you know the answer.
4. Cite evidence by episode title, never by chunk number.
5. Be concise, structured, and useful. Do not add a Sources section; the application adds it.
"""


async def run_qa_skill(llm_client: BaseLLMClient, user_message: str) -> str:
    settings = get_settings()
    chunks = await retrieve_relevant_chunks(
        user_message, top_k=min(settings.rag_top_k, 3), provider=llm_client.provider
    )
    context = format_context(chunks, max_chars=settings.rag_context_max_chars)
    if not context:
        return "I don't have enough transcript evidence to answer that. Run the ingestion script first."

    answer = (
        await llm_client.complete(
            LLMRequest(
                system_prompt=QA_SYSTEM_PROMPT,
                messages=[
                    LLMMessage(
                        role="user",
                        content=f"Transcript context:\n{context}\n\nQuestion:\n{user_message}",
                    )
                ],
                temperature=0.1,
                max_tokens=(
                    settings.cloud_qa_max_tokens
                    if settings.app_env == "cloud" and llm_client.provider == "cloud"
                    else 500
                ),
            )
        )
    ).content
    sources = format_sources(chunks)
    return f"{answer.rstrip()}\n\n**Sources**\n{sources}" if sources else answer
