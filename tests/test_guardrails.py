"""Moderation guardrail: flag→True, clean→False, errors→fail-open."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from cs_voice import guardrails


def _fake_response(flagged: bool) -> SimpleNamespace:
    categories = SimpleNamespace(
        model_dump=lambda: {"harassment": flagged, "violence": False}
    )
    return SimpleNamespace(
        results=[SimpleNamespace(flagged=flagged, categories=categories)]
    )


@pytest.mark.asyncio
async def test_flagged(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_create(**_: object) -> SimpleNamespace:
        return _fake_response(flagged=True)

    monkeypatch.setattr(guardrails._client().moderations, "create", fake_create)
    assert await guardrails.is_flagged("I'm going to hurt you") is True


@pytest.mark.asyncio
async def test_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_create(**_: object) -> SimpleNamespace:
        return _fake_response(flagged=False)

    monkeypatch.setattr(guardrails._client().moderations, "create", fake_create)
    assert await guardrails.is_flagged("How do I request time off?") is False


@pytest.mark.asyncio
async def test_empty_input_skips_call(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(**_: object) -> SimpleNamespace:
        raise AssertionError("should not call moderation on empty input")

    monkeypatch.setattr(guardrails._client().moderations, "create", boom)
    assert await guardrails.is_flagged("") is False
    assert await guardrails.is_flagged("   ") is False


@pytest.mark.asyncio
async def test_fails_open_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(**_: object) -> SimpleNamespace:
        raise RuntimeError("api down")

    monkeypatch.setattr(guardrails._client().moderations, "create", boom)
    assert await guardrails.is_flagged("anything") is False
