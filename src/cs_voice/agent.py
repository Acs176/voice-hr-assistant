"""SupportAgent: the LiveKit Agent with slot-recording tools."""

from __future__ import annotations

from livekit import agents
from livekit.agents import Agent, ChatContext, ChatMessage, function_tool

from cs_voice.prompts import load_prompt
from cs_voice.state import IssueCategory, SessionState, Urgency

PERSONA = load_prompt("persona")
STATE_HEADER = "\n\n[state — already confirmed]\n"


class SupportAgent(Agent):
    def __init__(self, state: SessionState, job_ctx: agents.JobContext) -> None:
        super().__init__(instructions=PERSONA)
        self.state = state
        self._job_ctx = job_ctx

    async def _sync_instructions(self) -> None:
        await self.update_instructions(PERSONA + STATE_HEADER + self.state.snapshot())

    async def on_user_turn_completed(self, turn_ctx: ChatContext, new_message: ChatMessage) -> None:
        self.state.turn_count += 1
        await self._sync_instructions()

    @function_tool
    async def record_employee_id(self, employee_id: str) -> str:
        """Record the caller's employee ID once they've stated and confirmed it."""
        slot = self.state.employee_id
        slot.value = employee_id
        slot.status = "confirmed"
        slot.attempts += 1
        return f"recorded employee_id={employee_id}"

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
