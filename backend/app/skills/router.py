from __future__ import annotations

from enum import StrEnum

from app.llm.base import BaseLLMClient


class SkillName(StrEnum):
    QA = "qa"
    SHIP30 = "ship30"
    ARTIFACT = "artifact"


def heuristic_route(user_message: str) -> SkillName:
    text = user_message.lower()
    artifact_keywords = [
        "artifact",
        "html",
        "css",
        "code",
        "component",
        "ui",
        "landing page",
        "dashboard",
        "template",
        "render",
        "markdown table",
    ]
    ship_keywords = ["ship30", "ship 30", "essay", "post", "thread", "newsletter", "1250"]

    if any(keyword in text for keyword in artifact_keywords):
        return SkillName.ARTIFACT
    if any(keyword in text for keyword in ship_keywords):
        return SkillName.SHIP30
    return SkillName.QA


async def route_skill(llm_client: BaseLLMClient, user_message: str) -> SkillName:
    """Choose the skill without a separate local-model request."""
    del llm_client
    return heuristic_route(user_message)
