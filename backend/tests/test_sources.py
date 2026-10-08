from app.rag.retriever import RetrievedChunk, format_sources


def test_format_sources_uses_episode_title_and_path_once() -> None:
    chunks = [
        RetrievedChunk("one", {"episode_title": "Retention", "source_path": "retention.md"}, 0.9),
        RetrievedChunk("two", {"episode_title": "Retention", "source_path": "retention.md"}, 0.8),
        RetrievedChunk("three", {"episode_title": "Activation", "source_path": "activation.md"}, 0.7),
    ]

    assert format_sources(chunks) == (
        "- **Retention** — `retention.md`\n"
        "- **Activation** — `activation.md`"
    )
