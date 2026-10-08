"""Read-only retrieval diagnostic. No chat records or database rows are written."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import Settings  # noqa: E402
from app.core.errors import ConfigurationError, LLMProviderError  # noqa: E402
from app.rag import retriever  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--allow-download", action="store_true")
    parser.add_argument("--raw", action="store_true")
    parser.add_argument("--answer", action="store_true", help="Also call the configured LLM (may incur API cost).")
    args = parser.parse_args()
    settings = Settings(_env_file=None)
    if args.allow_download:
        settings.fastembed_local_files_only = False
    retriever.get_settings = lambda: settings
    if args.raw:
        chunks = retriever._similarity_search_sync(args.question, args.top_k, "cloud")
    else:
        chunks = asyncio.run(retriever.retrieve_relevant_chunks(args.question, args.top_k, provider="cloud"))
    for chunk in chunks:
        print(json.dumps({"score": chunk.cosine_similarity, "metadata": chunk.metadata, "content": chunk.content}, ensure_ascii=True))
    if args.answer:
        from app.llm.openrouter_client import OpenRouterClient
        from app.skills import qa

        qa.get_settings = lambda: settings
        print(asyncio.run(qa.run_qa_skill(OpenRouterClient(settings), args.question)))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Never dump environment variables or credential-bearing HTTP exceptions.
        detail = str(exc) if isinstance(exc, (ConfigurationError, LLMProviderError)) else type(exc).__name__
        print(f"Retrieval diagnostic failed: {detail}", file=sys.stderr)
        raise SystemExit(1) from None
