import re
from functools import lru_cache

from app.config import settings
from app.rag.retrieval import retriever
from app.llm.ollama import OllamaProvider
from app.llm.openai_provider import OpenAIProvider
from app.agents.skills.ship30 import SHIP30_INSTRUCTIONS


SYSTEM = """You are Lenny Growth Assistant.

Answer product, growth, startup, leadership, and career questions using
supplied Lenny's Podcast evidence.

Rules:
- Be direct and concise.
- Use evidence for podcast claims; ignore irrelevant evidence.
- Never invent facts, quotes, guests, episodes, or citations.
- Use only citation numbers that exist in the supplied evidence.
- Cite factual claims with [1], [2], etc. when supported.
- If evidence is insufficient, say so.
- For unrelated questions, briefly redirect to supported topics.
"""


@lru_cache(maxsize=2)
def _get_provider(provider_name: str):
    """
    Reuse the provider instance instead of creating a new provider
    for every request.
    """
    if provider_name.lower() == "openai":
        return OpenAIProvider()

    return OllamaProvider()


class Agent:
    def __init__(self):
        self.provider = _get_provider(settings.llm_provider)

    # ============================================================
    # REQUEST TYPE DETECTION
    # ============================================================

    @staticmethod
    def _is_artifact_request(text: str) -> bool:
        q = text.lower().strip()

        request = re.search(
            r"\b(create|generate|make|build|draft|write)\b",
            q,
        )

        artifact_terms = (
            "artifact",
            "html",
            "css",
            "landing page",
            "document",
            "strategy plan",
            "growth plan",
            "roadmap",
            "report",
            "one-page",
            "template",
            "framework",
        )

        return bool(
            request
            and any(term in q for term in artifact_terms)
        )

    @staticmethod
    def _is_ship30_request(text: str) -> bool:
        q = text.lower()

        return any(
            x in q
            for x in (
                "ship 30",
                "ship30",
                "1250 words",
            )
        ) or (
            "essay" in q
            and any(
                x in q
                for x in (
                    "lenny",
                    "podcast",
                    "growth",
                    "product",
                    "startup",
                )
            )
        )

    # ============================================================
    # TAG EXTRACTION
    # ============================================================

    @staticmethod
    def _extract_tag(text: str, tag: str) -> str:
        match = re.search(
            rf"<{tag}>(.*?)</{tag}>",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )

        return (
            match.group(1).strip()
            if match
            else ""
        )

    # ============================================================
    # ARTIFACT CLEANING
    # ============================================================

    @staticmethod
    def _clean_artifact_html(html: str) -> str:
        html = html.strip()

        if html.startswith("```"):
            html = re.sub(
                r"^```(?:html)?\s*",
                "",
                html,
                flags=re.IGNORECASE,
            )

            html = re.sub(
                r"\s*```$",
                "",
                html,
            )

        return html.strip()

    # ============================================================
    # SOURCE METADATA
    # ============================================================

    @staticmethod
    def _build_sources(hits):
        """
        Convert retrieval results into a stable source structure.

        This keeps source metadata separate from LLM-generated text.
        """

        sources = []

        for i, hit in enumerate(hits, start=1):
            source = hit.get("source", {}) or {}

            title = (
                source.get("title")
                or source.get("guest")
                or "Lenny's Podcast transcript"
            )

            guest = source.get("guest") or ""
            publish_date = source.get("publish_date") or ""
            path = source.get("path") or ""

            sources.append(
                {
                    "citation_id": i,
                    "title": title,
                    "guest": guest,
                    "publish_date": publish_date,
                    "path": path,
                    "chunk_number": source.get(
                        "chunk_number"
                    ),
                    "score": hit.get("score"),
                    "vector_score": hit.get(
                        "vector_score"
                    ),
                    "bm25_score": hit.get(
                        "bm25_score"
                    ),
                    "rrf_score": hit.get(
                        "rrf_score"
                    ),
                }
            )

        return sources

    # ============================================================
    # CITATION NORMALIZATION
    # ============================================================

    @staticmethod
    def _normalize_citations(answer: str, hit_count: int):
        """
        Remove citation numbers that don't correspond to a retrieved
        source.
        """

        citation_pattern = re.compile(
            r"\[(\d+)\]"
        )

        valid_ids = set(
            range(
                1,
                hit_count + 1,
            )
        )

        def replace_citation(match):
            citation_id = int(
                match.group(1)
            )

            if citation_id in valid_ids:
                return match.group(0)

            return ""

        return citation_pattern.sub(
            replace_citation,
            answer,
        )

    # ============================================================
    # SOURCE FALLBACK
    # ============================================================

    @staticmethod
    def _add_source_fallback(
        answer: str,
        sources: list[dict],
    ):
        """
        If the LLM did not emit citations, add a deterministic source
        section using actual retrieval metadata.

        This prevents:
            Sources: , ,

        """

        if not sources:
            return answer

        citation_pattern = re.compile(
            r"\[(\d+)\]"
        )

        valid_ids = {
            source["citation_id"]
            for source in sources
        }

        used_citations = {
            int(value)
            for value in citation_pattern.findall(answer)
            if int(value) in valid_ids
        }

        # Model already cited at least one valid source.
        if used_citations:
            return answer

        source_lines = []

        for source in sources:
            citation_id = source["citation_id"]
            title = source["title"]
            guest = source["guest"]

            if guest:
                source_lines.append(
                    f"[{citation_id}] {title} — {guest}"
                )
            else:
                source_lines.append(
                    f"[{citation_id}] {title}"
                )

        return (
            f"{answer.rstrip()}\n\n"
            "Sources:\n"
            + "\n".join(source_lines)
        )

    # ============================================================
    # MAIN AGENT
    # ============================================================

    def run(
        self,
        user_message: str,
        history: list[dict],
    ):
        # --------------------------------------------------------
        # 1. DETECT REQUEST TYPE
        # --------------------------------------------------------

        is_artifact = self._is_artifact_request(
            user_message
        )

        is_ship30 = self._is_ship30_request(
            user_message
        )

        # --------------------------------------------------------
        # 2. RETRIEVE EVIDENCE
        # --------------------------------------------------------

        hits = retriever.search(
            user_message
        )

        context_parts = []

        for i, hit in enumerate(
            hits,
            start=1,
        ):
            source = hit.get(
                "source",
                {},
            ) or {}

            title = (
                source.get("title")
                or "Lenny's Podcast transcript"
            )

            guest = (
                source.get("guest")
                or "Unknown guest"
            )

            text = hit.get(
                "text",
                "",
            )

            context_parts.append(
                f"[{i}] {title} — {guest}\n{text}"
            )

        context = "\n\n".join(
            context_parts
        )

        # --------------------------------------------------------
        # 3. BUILD TASK
        # --------------------------------------------------------

        if is_artifact:
            task = """Create a polished, self-contained HTML artifact based only
on the supplied evidence.

Return exactly two tagged sections and nothing else:

<ANSWER>One brief description of the artifact.</ANSWER>
<ARTIFACT><!doctype html><html>...</html></ARTIFACT>

Rules:
- Do not include JavaScript.
- Put CSS inside a <style> tag.
- Do not invent podcast facts.
- Do not invent guest names, episodes, quotes, statistics,
  or other factual claims.
- If the supplied evidence is insufficient, keep the artifact
  generic rather than inventing information."""

            max_tokens = min(
                1400,
                max(
                    700,
                    settings.artifact_max_chars // 70,
                ),
            )

        elif is_ship30:
            task = SHIP30_INSTRUCTIONS
            max_tokens = 1500

        else:
            task = (
                "Answer the user's question concisely but usefully, "
                "grounded only in the evidence."
            )

            max_tokens = 300

        # --------------------------------------------------------
        # 4. BUILD LLM MESSAGES
        # --------------------------------------------------------

        messages = [
            {
                "role": "system",
                "content": (
                    SYSTEM
                    + "\n\n"
                    + task
                    + "\n\n"
                    "TRANSCRIPT EVIDENCE:\n"
                    + (
                        context
                        if context
                        else "NO EVIDENCE"
                    )
                ),
            }
        ]

        messages += history[-8:]

        messages.append(
            {
                "role": "user",
                "content": user_message,
            }
        )

        # --------------------------------------------------------
        # 5. CALL LLM
        # --------------------------------------------------------

        raw = self.provider.chat(
            messages,
            max_tokens=max_tokens,
        )

        artifact_html = ""
        answer = raw

        # --------------------------------------------------------
        # 6. PARSE ARTIFACT
        # --------------------------------------------------------

        if is_artifact:
            parsed_answer = self._extract_tag(
                raw,
                "ANSWER",
            )

            artifact_html = self._clean_artifact_html(
                self._extract_tag(
                    raw,
                    "ARTIFACT",
                )
            )

            if parsed_answer:
                answer = parsed_answer

            # If the model returned raw HTML instead of tagged HTML.
            if (
                not artifact_html
                and "<html" in raw.lower()
            ):
                artifact_html = (
                    self._clean_artifact_html(
                        raw
                    )
                )

                answer = (
                    "Created the requested artifact."
                )

            # Respect existing artifact limit.
            if len(artifact_html) > settings.artifact_max_chars:
                artifact_html = artifact_html[
                    : settings.artifact_max_chars
                ]

        # --------------------------------------------------------
        # 7. NORMALIZE CITATIONS
        # --------------------------------------------------------

        answer = self._normalize_citations(
            answer,
            len(hits),
        )

        # --------------------------------------------------------
        # 8. BUILD SOURCES
        # --------------------------------------------------------

        sources = self._build_sources(
            hits
        )

        # --------------------------------------------------------
        # 9. ADD SOURCES WHEN THE MODEL FORGOT THEM
        # --------------------------------------------------------

        answer = self._add_source_fallback(
            answer,
            sources,
        )

        # --------------------------------------------------------
        # 10. BUILD FINAL RESULT
        # --------------------------------------------------------

        result = {
            "answer": answer,

            # Clean source metadata for frontend.
            "sources": sources,

            # Full retrieval diagnostics for
            # developer_config / debugging.
            "retrieved_hits": hits,

            "intent": (
                "artifact"
                if is_artifact
                else "ship30"
                if is_ship30
                else "qa"
            ),

            "provider": settings.llm_provider,
        }

        # --------------------------------------------------------
        # 11. ADD ARTIFACT IF GENERATED
        # --------------------------------------------------------

        if artifact_html:
            result["artifact"] = {
                "type": "html",
                "content": artifact_html,
            }

        return result