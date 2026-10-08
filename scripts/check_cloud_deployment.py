"""Exercise the real cloud API, including embeddings, Supabase RPC, and the selected model.

A full check persists one session and chat in Supabase, just as the frontend does.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.config import Settings, get_settings  # noqa: E402
from app.core.errors import (  # noqa: E402
    ConfigurationError,
    LLMProviderError,
    LLMProviderUnavailableError,  # noqa: E402
)
from app.llm.base import LLMMessage, LLMRequest  # noqa: E402
from app.llm.factory import get_llm_client  # noqa: E402
from app.skills.qa import NO_EVIDENCE  # noqa: E402


def check(settings: Settings, question: str) -> None:
    settings.validate_cloud_configuration()
    from app.main import create_app

    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
        models = client.get("/api/models").json()
        assert models["cloud"]["provider"] == settings.cloud_llm_provider
        print("Cloud API startup and model selection: OK.")
        session = client.post("/api/sessions", json={"active_llm": "cloud"})
        if session.status_code != 201:
            raise RuntimeError(f"Session creation returned HTTP {session.status_code}; check chat tables.")
        print("Supabase session storage: OK.")
        response = client.post("/api/chat", json={
            "session_id": session.json()["id"], "active_llm": "cloud", "message": question,
        })
        if response.status_code != 200:
            raise RuntimeError(f"Cloud chat returned HTTP {response.status_code}; inspect the API with private credentials.")
        content = response.json()["message"]["content"]
        if content == NO_EVIDENCE or "I don't have enough transcript evidence" in content:
            raise RuntimeError("No matching transcript context. Run cloud ingestion and check the similarity threshold.")
        print(f"FastEmbed -> Supabase RPC -> {settings.cloud_llm_provider} -> stored chat: OK.")
        print(content)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=BACKEND / ".env.cloud")
    parser.add_argument("--question", default="What does Lenny's Podcast say about activation metrics?")
    parser.add_argument("--llm-only", action="store_true", help="Check the configured hosted model without Supabase writes.")
    parser.add_argument("--retrieval-only", action="store_true", help="Check live CPU embeddings and Supabase RPC without calling the LLM.")
    args = parser.parse_args()
    os.environ["APP_ENV_FILE"] = str(args.env_file.resolve())
    os.environ["APP_ENV"] = "cloud"
    get_settings.cache_clear()
    settings = get_settings()
    try:
        if args.retrieval_only:
            from app.rag.cloud import match_chunks

            chunks = match_chunks(settings, args.question, settings.rag_top_k)
            if not chunks:
                raise RuntimeError("Supabase RPC returned no matching chunks; ingest more data or adjust the test question.")
            print(f"Live FastEmbed + Supabase RPC: OK ({len(chunks)} chunks).")
        elif args.llm_only:
            client = get_llm_client("cloud")
            result = asyncio.run(client.complete(LLMRequest(
                system_prompt="This is a connectivity check. Reply briefly.",
                messages=[LLMMessage(role="user", content="Reply with: Cloud model ready.")],
                max_tokens=32,
            )))
            print(f"Hosted model connectivity: OK ({result.model}).")
        else:
            check(settings, args.question)
    except (ConfigurationError, LLMProviderError, LLMProviderUnavailableError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Cloud check failed ({type(exc).__name__}); check connectivity and private configuration.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
