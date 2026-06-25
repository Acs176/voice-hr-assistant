"""Deterministic parsers and validators for slot values."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

EMPLOYEE_ID_PATTERN = re.compile(r"ORB\d{4}(?!\d)")


def spell_out(s: str) -> str:
    """Dash-separated form for letter-by-letter TTS readback ('O-R-B-1-2-3-4')."""
    return "-".join(s)


@dataclass(frozen=True)
class ParseResult:
    value: str | None
    error: str | None

    @property
    def ok(self) -> bool:
        return self.value is not None


def parse_employee_id(raw: str) -> ParseResult:
    """Normalize a spoken/written employee ID into the canonical 'ORB####' form.

    Digit transcription is the STT's job (Deepgram numerals): this layer only
    handles casing, punctuation, accent normalization, and format validation.
    If the caller restates the ID mid-utterance, the last match wins.
    """
    if not raw or not raw.strip():
        return ParseResult(None, "empty input")

    ascii_form = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode()
    normalized = re.sub(r"[^A-Z0-9]", "", ascii_form.upper())

    matches = EMPLOYEE_ID_PATTERN.findall(normalized)
    if matches:
        return ParseResult(matches[-1], None)

    return ParseResult(None, _diagnose(normalized))


def _diagnose(normalized: str) -> str:
    if not normalized:
        return "could not pick out any ID from the input"
    if "ORB" not in normalized:
        return "missing 'ORB' prefix; the ID should be ORB followed by 4 digits"
    tail = normalized.split("ORB", 1)[1]
    digits = "".join(c for c in tail if c.isdigit())
    if len(digits) < 4:
        return f"only got {len(digits)} digit(s) after ORB; expected 4"
    return f"got {len(digits)} digits after ORB; expected exactly 4"
