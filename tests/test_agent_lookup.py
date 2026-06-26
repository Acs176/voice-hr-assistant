"""lookup_hr_info branches: hit speaks the source, miss routes, errors degrade —
all with fake retrievers, no network."""

from __future__ import annotations

from cs_voice.agent import SupportAgent
from cs_voice.rag import Chunk, Hit
from cs_voice.state import SessionState


class _FakeJobCtx:
    def delete_room(self) -> None:
        return None


class _HitRetriever:
    async def search(self, query: str, k: int = 3) -> list[Hit]:
        return [await self.best(query)]  # type: ignore[list-item]

    async def best(self, query: str) -> Hit:
        return Hit(Chunk("payroll", "Pay schedule", "Pay schedule. Every two weeks."), 0.81)


class _MissRetriever:
    async def search(self, query: str, k: int = 3) -> list[Hit]:
        return []

    async def best(self, query: str) -> None:
        return None


class _BoomRetriever:
    async def search(self, query: str, k: int = 3) -> list[Hit]:
        raise RuntimeError("embeddings down")

    async def best(self, query: str) -> Hit:
        raise RuntimeError("embeddings down")


def _agent(retriever: object) -> SupportAgent:
    return SupportAgent(SessionState(), _FakeJobCtx(), retriever)  # type: ignore[arg-type]


async def test_hit_returns_answer_with_source() -> None:
    msg = await _agent(_HitRetriever()).lookup_hr_info("when do I get paid")
    assert "payroll" in msg and "Every two weeks" in msg


async def test_miss_tells_agent_to_route() -> None:
    msg = await _agent(_MissRetriever()).lookup_hr_info("can you mail me a llama")
    assert "route" in msg.lower() and "employee id" in msg.lower()


async def test_error_degrades_gracefully() -> None:
    msg = await _agent(_BoomRetriever()).lookup_hr_info("anything")
    assert "couldn't" in msg.lower() or "route" in msg.lower()
