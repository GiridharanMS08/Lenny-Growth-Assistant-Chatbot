from __future__ import annotations

from app.core.config import get_settings
from app.llm.base import BaseLLMClient, LLMMessage, LLMRequest
from app.rag.retriever import format_context, retrieve_relevant_chunks

SHIP30_SYSTEM_PROMPT = """You are a world-class Ship30for30 content strategist.

You must write using ONLY the provided Lenny's Podcast transcript context.
If evidence is insufficient, clearly say so and do not invent examples.

Output requirements:
- Approximately 1,250 words.
- Start with a sharp, curiosity-driven hook.
- Use heavy bulleting for skimmability.
- Bold the most important phrases.
- Use short sections with clear headings.
- Make the writing practical for product/growth operators.
- End with a section titled "Clear takeaway".
- Do not include citations that are not present in the context.
"""


async def run_ship30_skill(llm_client: BaseLLMClient, user_message: str) -> str:
    chunks = await retrieve_relevant_chunks(user_message, top_k=8, provider=llm_client.provider)
    context = format_context(
        chunks,
        max_chars=get_settings().rag_context_max_chars if llm_client.provider == "local" else None,
    )
    if not context:
        return "I don't have enough transcript evidence to create a Ship30for30 post. Run ingestion first."

    return (
        await llm_client.complete(
            LLMRequest(
                system_prompt=SHIP30_SYSTEM_PROMPT,
                messages=[
                    LLMMessage(
                        role="user",
                        content=f"Transcript context:\n{context}\n\nUser request:\n{user_message}",
                    )
                ],
                temperature=0.35,
                max_tokens=2_500,
            )
        )
    ).content
