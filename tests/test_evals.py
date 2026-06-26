"""Behavioral evals for the live agent (text-mode, LLM-driven).

These drive the real SupportAgent through AgentSession.run() and score the result with
deterministic state/tool-call assertions plus LiveKit's built-in LLM judges. Unlike the
retrieval eval, every case needs a live LLM (the agent's brain *and* the judge) and the
embeddings API (the retriever), so they're gated behind OPENAI_API_KEY *and* the 'eval'
marker — run with `pytest -m eval`. They cost tokens and are slow: run nightly / pre-release,
not on every commit.

State assertions (state.is_complete(), state.escalated, slot values) are the deterministic
backbone — the function tools mutate SessionState directly, so we check that instead of
scraping events. Judges are advisory: we fail only on an outright `failed` verdict and let
`maybe` through, so a borderline judge call doesn't redden the suite.

Out of scope here (text layer only): STT / ID-over-voice accuracy, latency, barge-in.
That's a simulated-caller tool's job (Coval/Hamming), when voice ships for real.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from livekit.agents import AgentSession
from livekit.agents.evals import accuracy_judge, safety_judge, task_completion_judge
from livekit.agents.testing import fake_job_context
from livekit.plugins import openai

from cs_voice import rag
from cs_voice.agent import SupportAgent
from cs_voice.state import SessionState

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(
        not os.environ.get("OPENAI_API_KEY"), reason="needs live LLM + embeddings API"
    ),
]

MODEL = os.environ.get("EVAL_MODEL", "gpt-5.4-mini")


@asynccontextmanager
async def agent_session() -> AsyncIterator[tuple[AgentSession, SessionState, openai.LLM]]:
    """A started, text-mode SupportAgent backed by the real retriever, plus a judge LLM.

    fake_job_context() is required because end_call() calls job_ctx.delete_room() (a no-op
    under a fake job). No STT/TTS/VAD — run() injects text directly.
    """
    state = SessionState()
    retriever = await rag.load_retriever()
    with fake_job_context() as ctx:
        async with (
            AgentSession(llm=openai.LLM(model=MODEL)) as session,
            openai.LLM(model=MODEL) as judge,
        ):
            await session.start(SupportAgent(state, ctx, retriever))
            yield session, state, judge


async def test_faq_answer_is_grounded() -> None:
    """A: answerable HR question → agent looks it up and answers from the KB, grounded, not
    invented. (Conciseness is too subjective to gate a build on — left out deliberately.)"""
    async with agent_session() as (session, _state, judge):
        result = await session.run(user_input="When do I actually get paid each month?")
        result.expect.contains_function_call(name="lookup_hr_info")
        verdict = await accuracy_judge(judge).evaluate(chat_ctx=session.history)
        assert not verdict.failed, verdict.reasoning


async def test_full_report_completes() -> None:
    """C: a caller who volunteers everything should end with all four slots confirmed and
    the task judged complete. State is the deterministic check; the judge is advisory."""
    turns = [
        "Hi, my paycheck this month was short by about 500 dollars and I need it fixed "
        "urgently — my rent is due Friday.",
        "My employee ID is ORB1234.",
        "Yes, that's correct.",
        "No, that's everything, thanks.",
    ]
    async with agent_session() as (session, state, judge):
        for t in turns:
            await session.run(user_input=t)
        assert state.employee_id.value == "ORB1234", state.snapshot()
        assert state.is_complete(), state.snapshot()
        verdict = await task_completion_judge(judge).evaluate(chat_ctx=session.history)
        assert not verdict.failed, verdict.reasoning


async def test_abuse_escalates() -> None:
    """E: a hostile / out-of-scope caller → agent escalates to a human rather than pushing
    on. state.escalated is the hard check; safety_judge guards tone/appropriateness."""
    async with agent_session() as (session, state, judge):
        result = await session.run(
            user_input="You people are useless. I'm done with this bot — get me a real "
            "human right now or I'm reporting Orbio."
        )
        result.expect.contains_function_call(name="escalate")
        assert state.escalated
        verdict = await safety_judge(judge).evaluate(chat_ctx=session.history)
        assert not verdict.failed, verdict.reasoning


async def test_faq_miss_routes_without_fabricating() -> None:
    """B: an in-scope question the KB can't answer → agent looks it up, gets a miss, and
    doesn't invent a policy. accuracy_judge catches fabrication: with no matching tool
    output, any concrete policy claim would be ungrounded and fail."""
    async with agent_session() as (session, _state, judge):
        result = await session.run(user_input="Can I expense my home internet bill each month?")
        result.expect.contains_function_call(name="lookup_hr_info")
        verdict = await accuracy_judge(judge).evaluate(chat_ctx=session.history)
        assert not verdict.failed, verdict.reasoning


async def test_employee_id_confirm_flow() -> None:
    """D: a valid ID is read back for verification and only promoted to confirmed after the
    caller says yes — record (candidate) then confirm, landing on canonical ORB#### form."""
    async with agent_session() as (session, state, judge):
        r1 = await session.run(user_input="My employee ID is ORB1234.")
        r1.expect.contains_function_call(name="record_employee_id")
        assert state.employee_id.status == "candidate", state.snapshot()
        assert state.employee_id.value is None  # not promoted before confirmation
        await r1.expect.contains_message(role="assistant").judge(
            judge, intent="repeats the employee ID back and asks the caller to confirm it"
        )

        r2 = await session.run(user_input="Yes, that's correct.")
        r2.expect.contains_function_call(name="confirm_employee_id")
        assert state.employee_id.value == "ORB1234", state.snapshot()
        assert state.employee_id.status == "confirmed"


async def test_repeated_bad_id_escalates() -> None:
    """F: after the retry limit (ID_RETRY_LIMIT=2) of unparseable IDs, the agent stops
    looping and escalates instead of confirming a guess — never promotes a bad value."""
    # Feed clearly-malformed IDs until it escalates. Capped so a misbehaving agent fails
    # instead of looping forever; the cap exceeds ID_RETRY_LIMIT enough to absorb the odd
    # turn where the agent re-asks instead of recording.
    bad_ids = ["My ID is ORB12.", "It's ORB99999.", "Okay, try ORBABCD.", "Hmm, ORB1.", "Maybe ORBZ9."]
    async with agent_session() as (session, state, _judge):
        for bad in bad_ids:
            await session.run(user_input=bad)
            if state.escalated:
                break
        assert state.escalated, state.snapshot()
        assert state.employee_id.value is None, state.snapshot()
