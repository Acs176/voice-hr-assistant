"""Conversation state: slots, enums, session-level aggregation."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

IssueCategory = Literal["scheduling", "payroll", "onboarding", "documents", "other"]
Urgency = Literal["low", "medium", "high"]
SlotStatus = Literal["empty", "candidate", "confirmed", "failed"]


class Slot(BaseModel):
    candidate: str | None = None
    value: str | None = None
    status: SlotStatus = "empty"
    attempts: int = 0
    last_error: str | None = None


class SessionState(BaseModel):
    employee_id: Slot = Field(default_factory=Slot)
    issue_category: Slot = Field(default_factory=Slot)
    description: Slot = Field(default_factory=Slot)
    urgency: Slot = Field(default_factory=Slot)
    escalated: bool = False
    turn_count: int = 0

    def is_complete(self) -> bool:
        return all(
            s.status == "confirmed"
            for s in (self.employee_id, self.issue_category, self.description, self.urgency)
        )

    def snapshot(self) -> str:
        return json.dumps(
            {
                "employee_id": self.employee_id.model_dump(exclude_none=True),
                "issue_category": self.issue_category.model_dump(exclude_none=True),
                "description": self.description.model_dump(exclude_none=True),
                "urgency": self.urgency.model_dump(exclude_none=True),
                "escalated": self.escalated,
            },
            indent=2,
        )
