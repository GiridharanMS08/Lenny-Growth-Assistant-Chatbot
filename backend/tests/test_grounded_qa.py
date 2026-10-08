from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from app.core.config import Settings
from app.core.errors import LLMProviderError
from app.rag import retriever
from app.rag.retriever import RetrievedChunk, format_context, prepare_context, select_chunks
from app.skills import qa

# Sean Ellis, 01:02:58. The survey-selection discussion at 00:23 is a
# different topic and must not be converted into activation advice.
EVIDENCE = "And then at least try to see if there's a correlation to long-term retention of doing that. Causation is you need to do some experimentation to prove causation."


def chunk(text=EVIDENCE, path="episodes/sean-ellis/transcript.md", score=0.8):
    return RetrievedChunk(text, {"episode_title": "Sean Ellis", "guest_name": "Sean Ellis", "source_path": path}, score)


def output(quote=EVIDENCE, index=1):
    return json.dumps({"excerpts": [{"chunk": index, "quote": quote}]})


@pytest.mark.parametrize("raw", [output("Activation excludes users who signed up months ago."), output(index=99), '{"excerpts":[{"chunk":true,"quote":"fabricated"}]}'])
def test_fabricated_text_or_unknown_source_cannot_be_rendered(raw):
    with pytest.raises(ValueError):
        qa.verified_excerpts(raw, [chunk()])


def test_whitespace_changes_do_not_reject_real_evidence():
    assert qa.verified_excerpts(output(EVIDENCE.replace(". ", ".\n")), [chunk()])[0][0] == EVIDENCE


def test_context_budget_and_sources_only_include_visible_text():
    first = chunk("A useful complete transcript sentence. " * 20)
    second = chunk("Secret unseen passage. " * 20, path="unseen.md")
    selected = prepare_context([first, second], max_chars=900)
    assert len(format_context(selected)) <= 900
    assert len(selected) == 1
    with pytest.raises(ValueError):
        qa.verified_excerpts(output("Secret unseen passage. Secret unseen passage."), selected)


def test_duplicate_and_single_episode_results_do_not_fill_entire_context():
    candidates = [chunk("First", score=.95), chunk("First", score=.94), chunk("Second", score=.93), chunk("Third", score=.92), chunk("Other episode", path="other.md", score=.91)]
    assert [c.content for c in select_chunks(candidates, 3)] == ["First", "Second", "Other episode"]


@pytest.mark.asyncio
async def test_search_uses_topic_and_fetches_enough_candidates(monkeypatch):
    monkeypatch.setattr(retriever, "get_settings", lambda: Settings(_env_file=None))
    calls = []
    monkeypatch.setattr(retriever, "_similarity_search_sync", lambda *args: calls.append(args) or [chunk()])
    assert await retriever.retrieve_relevant_chunks("What does Lenny's Podcast say about activation metrics?", provider="cloud")
    assert calls == [("activation metrics", 15, "cloud")]


class Client:
    provider = "cloud"

    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = 0

    async def complete(self, request):
        self.calls += 1
        return SimpleNamespace(content=next(self.replies))


def setup(monkeypatch, chunks):
    monkeypatch.setattr(qa, "get_settings", lambda: Settings(_env_file=None))

    async def retrieve(*args, **kwargs):
        return chunks

    monkeypatch.setattr(qa, "retrieve_relevant_chunks", retrieve)


@pytest.mark.asyncio
async def test_single_supportive_source_answers_without_unrelated_disclaimer(monkeypatch):
    setup(monkeypatch, [chunk(), chunk("Other unrelated content.", path="uncited.md")])
    result = await qa.run_qa_skill(Client([output()]), "How should I choose activation metrics?")
    assert EVIDENCE in result
    assert "sean-ellis/transcript.md" in result
    assert "uncited.md" not in result
    assert "other episodes" not in result
    assert qa.NO_EVIDENCE not in result


@pytest.mark.asyncio
async def test_no_retrieved_evidence_skips_llm(monkeypatch):
    setup(monkeypatch, [])
    client = Client([])
    assert await qa.run_qa_skill(client, "Unknown fact?") == qa.NO_EVIDENCE
    assert client.calls == 0


@pytest.mark.asyncio
async def test_irrelevant_evidence_returns_no_supportive_source(monkeypatch):
    setup(monkeypatch, [chunk()])
    assert await qa.run_qa_skill(Client(['{"excerpts":[]}']), "Exact weather on Mars tomorrow?") == qa.NO_EVIDENCE


@pytest.mark.asyncio
async def test_malformed_model_response_is_repaired_not_misreported_as_missing_evidence(monkeypatch):
    setup(monkeypatch, [chunk()])
    client = Client(["invented answer", output()])
    assert EVIDENCE in await qa.run_qa_skill(client, "Activation metrics?")
    assert client.calls == 2
    with pytest.raises(LLMProviderError, match="verifiable"):
        await qa.run_qa_skill(Client(["bad", "bad"]), "Activation metrics?")
