"""Retrieval eval. Chunking runs offline; the Q->source eval needs the embeddings
API (set OPENAI_API_KEY) and is skipped otherwise so CI stays green without network."""

from __future__ import annotations

import os

import pytest

from cs_voice import rag

EXPECTED_SOURCES = {"payroll", "time_off", "benefits", "onboarding", "company"}

# the FAQ deflection cases the agent must route to the right doc
CASES = [
    ("when do I get paid", "payroll"),
    ("my paycheck looks wrong", "payroll"),
    ("how many vacation days do I have left", "time_off"),
    ("I need to call in sick tomorrow", "time_off"),
    ("how do I add my spouse to health insurance", "benefits"),
    ("does Orbio match my 401k", "benefits"),
    ("what should I bring on my first day", "onboarding"),
    ("where are the offices", "company"),
]

needs_api = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"), reason="needs embeddings API"
)


def test_chunking_offline() -> None:
    chunks = rag.load_chunks()
    assert {c.source for c in chunks} == EXPECTED_SOURCES
    assert all(c.text.strip() and c.section for c in chunks)
    # heading is folded into the embedded text so it carries weight
    assert all(c.text.startswith(c.section) for c in chunks)


def test_committed_index_is_fresh() -> None:
    """Guard the footgun: editing the KB without rebuilding the index ships a stale
    index that load_retriever would silently rebuild (network) at job startup."""
    import json

    data = json.loads(rag.INDEX_PATH.read_text())
    want = rag._content_hash(rag.load_chunks(), rag.EMBED_MODEL)
    assert data["hash"] == want, "KB changed — run `python -m cs_voice.rag` to rebuild the index"


@needs_api
@pytest.mark.parametrize("query,expected", CASES)
async def test_top_hit_source(query: str, expected: str) -> None:
    retriever = rag.load_retriever()
    hits = await retriever.search(query, k=3)
    assert hits[0].chunk.source == expected, f"{query!r} -> {[h.chunk.source for h in hits]}"


@needs_api
async def test_threshold_rejects_offtopic() -> None:
    """An unrelated question should clear nothing — best() returns None → agent routes."""
    retriever = rag.load_retriever()
    assert await retriever.best("what's the weather on Mars") is None


@needs_api
async def test_threshold_accepts_ontopic() -> None:
    """A clear question must clear the bar — guards against THRESHOLD set too high."""
    retriever = rag.load_retriever()
    hit = await retriever.best("when do I get paid")
    assert hit is not None and hit.chunk.source == "payroll"
