"""Content moderation guardrail.

One call per user turn against OpenAI's moderation endpoint. On a flag we
escalate; on any error we fail open — a moderation outage must never kill a
live HR call.
"""

from __future__ import annotations

import logging
from functools import cache

from openai import AsyncOpenAI

log = logging.getLogger(__name__)


@cache
def _client() -> AsyncOpenAI:
    return AsyncOpenAI()


async def is_flagged(text: str) -> bool:
    if not text or not text.strip():
        return False
    try:
        r = await _client().moderations.create(model="omni-moderation-latest", input=text)
    except Exception as e:
        log.warning("moderation call failed, failing open: %s", e)
        return False
    result = r.results[0]
    if result.flagged:
        # categories only — transcripts can carry PII (names, IDs, medical detail)
        cats = [k for k, v in result.categories.model_dump().items() if v]
        log.warning("moderation flagged turn: categories=%s", cats)
    return result.flagged
