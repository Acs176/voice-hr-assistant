"""State-machine tests for SupportAgent's ID two-step flow."""

from __future__ import annotations

import pytest

from cs_voice.agent import SupportAgent
from cs_voice.state import SessionState


class _FakeJobCtx:
    """Minimal stand-in: only end_call would touch it, and these tests don't."""

    def delete_room(self) -> None:
        return None


class _NullRetriever:
    """Never matches — these tests don't exercise lookup."""

    async def search(self, query: str, k: int = 3) -> list:
        return []

    async def best(self, query: str) -> None:
        return None


@pytest.fixture
def agent() -> SupportAgent:
    return SupportAgent(SessionState(), _FakeJobCtx(), _NullRetriever())  # type: ignore[arg-type]


async def test_successful_parse_enters_candidate_state(agent: SupportAgent) -> None:
    msg = await agent.record_employee_id("my id is ORB1234")
    slot = agent.state.employee_id
    assert slot.status == "candidate"
    assert slot.candidate == "ORB1234"
    assert slot.value is None
    assert slot.last_error is None
    assert "O-R-B-1-2-3-4" in msg
    assert "confirm_employee_id" in msg


async def test_successful_parse_does_not_burn_attempts(agent: SupportAgent) -> None:
    # Regression: previously every call incremented attempts, so a clean ID
    # followed by one mishear would trip the retry limit.
    await agent.record_employee_id("ORB1234")
    assert agent.state.employee_id.attempts == 0


async def test_confirm_promotes_candidate_and_resets_slot(agent: SupportAgent) -> None:
    await agent.record_employee_id("ORB1234")
    msg = await agent.confirm_employee_id()
    slot = agent.state.employee_id
    assert slot.status == "confirmed"
    assert slot.value == "ORB1234"
    assert slot.candidate is None
    assert slot.attempts == 0
    assert slot.last_error is None
    assert "ORB1234" in msg


async def test_confirm_without_candidate_is_a_no_op(agent: SupportAgent) -> None:
    msg = await agent.confirm_employee_id()
    assert "no candidate" in msg
    assert agent.state.employee_id.status == "empty"


async def test_self_correction_overwrites_candidate(agent: SupportAgent) -> None:
    await agent.record_employee_id("ORB1234")
    await agent.record_employee_id("actually ORB5678")
    slot = agent.state.employee_id
    assert slot.candidate == "ORB5678"
    assert slot.status == "candidate"
    # Neither call failed — attempts must not have ticked.
    assert slot.attempts == 0


async def test_failed_parse_records_error_and_stays_empty(agent: SupportAgent) -> None:
    msg = await agent.record_employee_id("no idea")
    slot = agent.state.employee_id
    assert slot.status == "empty"
    assert slot.candidate is None
    assert slot.attempts == 1
    assert slot.last_error is not None
    assert "parse failed" in msg


async def test_failures_beyond_retry_limit_trigger_escalation(agent: SupportAgent) -> None:
    # ID_RETRY_LIMIT = 2 → escalation hint surfaces on the third failure.
    await agent.record_employee_id("garbage one")
    msg2 = await agent.record_employee_id("garbage two")
    msg3 = await agent.record_employee_id("garbage three")
    assert "escalate" not in msg2
    assert "escalate" in msg3
    assert agent.state.employee_id.attempts == 3


async def test_successful_confirm_clears_retry_budget(agent: SupportAgent) -> None:
    # Caller fumbles, then nails it, then confirms: the retry counter should
    # not carry into a later re-recording (e.g. mid-call correction).
    await agent.record_employee_id("garbage")
    await agent.record_employee_id("ORB1234")
    await agent.confirm_employee_id()
    assert agent.state.employee_id.attempts == 0
