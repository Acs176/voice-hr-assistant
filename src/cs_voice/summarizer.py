"""Post-call summarizer: turns the transcript into a structured ticket-ready blob."""

from __future__ import annotations

import logging
from functools import cache
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


class CallSummary(BaseModel):
    headline: str = Field(description="One sentence: who called and what they need.")
    key_points: list[str] = Field(
        description="3-6 bullets of what the caller said, in their own framing."
    )
    next_action: str = Field(
        description="What the routed human should do next, concretely."
    )
    caller_sentiment: str = Field(description="The caller's emotional state during the call.")
    resolved: bool = Field(
        description=(
            "True if the caller's question was answered in-call and no follow-up is "
            "needed (e.g. an HR question answered from the knowledge base, no issue to "
            "route). False if the call was escalated, dropped, or an issue was logged "
            "for a human to act on."
        )
    )


@cache
def _client() -> AsyncOpenAI:
    return AsyncOpenAI()


SYSTEM = (
    "You summarize a finished HR support call for the human who will follow up. "
    "Be specific and concrete. If the caller was escalated or hung up early, say so "
    "in next_action. Never invent details not present in the transcript. "
    "The collected-state JSON is ground truth; the transcript is for color and context."
)


def _format_transcript(items: list[dict[str, Any]]) -> str:
    # ponytail: keep only user/assistant turns; tool calls and system msgs are noise here.
    lines: list[str] = []
    for item in items:
        role = item.get("role")
        if role not in ("user", "assistant"):
            continue
        content = item.get("content")
        text = " ".join(c for c in content if isinstance(c, str)) if isinstance(content, list) else content
        if text:
            lines.append(f"{role}: {text}")
    return "\n".join(lines)


async def summarize(
    transcript: list[dict[str, Any]], state_snapshot: str, model: str
) -> CallSummary | None:
    dialogue = _format_transcript(transcript)
    if not dialogue:
        return None
    try:
        resp = await _client().chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM},
                {
                    "role": "user",
                    "content": f"[collected state]\n{state_snapshot}\n\n[transcript]\n{dialogue}",
                },
            ],
            response_format=CallSummary,
        )
    except Exception as e:
        log.warning("summary call failed: %s", e)
        return None
    return resp.choices[0].message.parsed
