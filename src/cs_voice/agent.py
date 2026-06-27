"""SupportAgent: the LiveKit Agent with slot-recording tools."""

from __future__ import annotations

import asyncio
from typing import Any

from livekit import agents
from livekit.agents import Agent, ChatContext, ChatMessage, function_tool

from cs_voice import guardrails, rag
from cs_voice.parsing import parse_employee_id, spell_out
from cs_voice.prompts import load_prompt
from cs_voice.state import IssueCategory, SessionState, Urgency

PERSONA = load_prompt("persona")
STATE_HEADER = "\n\n[state — already confirmed]\n"
ID_RETRY_LIMIT = 2

ACTION_COMPLETE = (
    "\n\nACTION: All four slots are confirmed. In your next utterance, give a "
    "one-sentence summary of what you'll route, then call end_call. "
    "Do not ask the caller if there is anything else."
)
ACTION_ESCALATED = (
    "\n\nACTION: This call has been escalated. Briefly tell the caller a human "
    "will follow up shortly, then call end_call."
)


class SupportAgent(Agent):
    def __init__(
        self, state: SessionState, job_ctx: agents.JobContext, retriever: rag.Retriever
    ) -> None:
        super().__init__(instructions=PERSONA)
        self.state = state
        self._job_ctx = job_ctx
        self._retriever = retriever
        # Hold refs to background moderation tasks so the loop doesn't GC them mid-flight.
        self._bg_tasks: set[asyncio.Task[Any]] = set()

    async def _sync_instructions(self) -> None:
        base = PERSONA + STATE_HEADER + self.state.snapshot()
        if self.state.is_complete():
            base += ACTION_COMPLETE
        elif self.state.escalated:
            base += ACTION_ESCALATED
        await self.update_instructions(base)

    async def on_user_turn_completed(self, turn_ctx: ChatContext, new_message: ChatMessage) -> None:
        self.state.turn_count += 1
        # Fire-and-forget moderation: a flagged turn pivots Mar to escalation on the
        # NEXT turn rather than blocking this one on a ~150-500ms moderation round-trip.
        task = asyncio.create_task(self._moderate(new_message.text_content or ""))
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)
        await self._sync_instructions()

    async def _moderate(self, text: str) -> None:
        if await guardrails.is_flagged(text):
            self.state.escalated = True
            # Re-sync so if moderation lands before the LLM turn starts, the
            # escalation branch takes effect immediately instead of next turn.
            await self._sync_instructions()

    @function_tool
    async def lookup_hr_info(self, question: str) -> str:
        """Look up an HR question in the Orbio knowledge base (pay, time off, benefits,
        onboarding, company info).

        Call this whenever the caller asks a general how/when/what question you could
        answer from policy. Pass their question as they asked it. Only call when the user has made a clear question.

        On a hit, returns the relevant policy passage and its source — answer from that
        and mention the source in passing. On a miss, the response tells you to say you
        can't answer it directly and to route it as an issue instead.
        """
        try:
            hit = await self._retriever.best(question)
        except Exception:  # degrade gracefully; a lookup must never kill the turn
            return (
                "lookup failed. Tell the caller you couldn't pull that up just now, "
                "and offer to route it to someone who can."
            )
        if hit is None:
            return (
                "no confident match in the knowledge base. Tell the caller you can't "
                "answer that one directly and will route it to someone who can. You "
                "already have most of what's needed: record the caller's question as the "
                "description and the topic as the category, then ask only for what's "
                "still missing (their employee ID, and anything else)."
            )
        return f"answer from '{hit.chunk.source}': {hit.chunk.text}"

    @function_tool
    async def record_employee_id(self, raw_phrase: str) -> str:
        """Submit the phrase the caller said as their employee ID.

        Pass it as you heard it — surrounding words, punctuation, casing all fine.
        The parser normalizes and validates against the expected format (ORB####).
        On success the ID enters a 'candidate' state: read it back character by
        character, wait for the caller to confirm, then call confirm_employee_id.
        On failure, the return string explains why; apologize and ask again.
        """
        slot = self.state.employee_id
        result = parse_employee_id(raw_phrase)
        if result.value is not None:
            slot.candidate = result.value
            slot.status = "candidate"
            slot.last_error = None
            return (
                f"parsed as {result.value}. Read it back to the caller as "
                f"'{spell_out(result.value)}' so they can verify each "
                "character, then call confirm_employee_id once they say yes."
            )
        slot.attempts += 1
        slot.last_error = result.error
        if slot.attempts > ID_RETRY_LIMIT:
            return (
                f"parse failed again ({result.error}). You've already tried "
                f"{slot.attempts} times. Apologize, explain you can't verify the "
                "ID over voice, and call escalate."
            )
        return f"parse failed: {result.error}."

    @function_tool
    async def confirm_employee_id(self) -> str:
        """Promote the pending candidate ID to confirmed once the caller has said yes."""
        slot = self.state.employee_id
        if slot.status != "candidate" or slot.candidate is None:
            return "no candidate to confirm — call record_employee_id first"
        slot.value = slot.candidate
        slot.status = "confirmed"
        slot.candidate = None
        slot.attempts = 0
        slot.last_error = None
        return f"confirmed employee_id={slot.value}"

    @function_tool
    async def record_category(self, category: IssueCategory) -> str:
        """Record which area the caller's issue falls under, as soon as it's clear."""
        slot = self.state.issue_category
        slot.value = category
        slot.status = "confirmed"
        slot.attempts += 1
        return f"recorded issue_category={category}"

    @function_tool
    async def record_description(self, description: str) -> str:
        """Record a short description of what's actually wrong, in the caller's own words."""
        slot = self.state.description
        slot.value = description
        slot.status = "confirmed"
        slot.attempts += 1
        return "recorded description"

    @function_tool
    async def record_urgency(self, urgency: Urgency) -> str:
        """Record how urgent the issue is."""
        slot = self.state.urgency
        slot.value = urgency
        slot.status = "confirmed"
        slot.attempts += 1
        return f"recorded urgency={urgency}"

    @function_tool
    async def escalate(self, reason: str) -> str:
        """Flag the call for human handoff. Use for anger, abuse, or anything out of scope."""
        self.state.escalated = True
        return f"escalated: {reason}"

    @function_tool
    async def end_call(self) -> str:
        """End the call. Call this after you've summarized for the caller."""
        self._job_ctx.delete_room()  # ponytail: fire-and-forget; awaiting aclose() here deadlocks the tool
        return "ending call"
