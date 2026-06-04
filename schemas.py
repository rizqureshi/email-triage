"""Shared schemas for email analysis output."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


Priority = Literal["low", "normal", "high", "urgent"]
Category = Literal[
    "billing",
    "scheduling",
    "support",
    "sales",
    "personal",
    "newsletter",
    "other",
]


@dataclass(frozen=True)
class ActionItem:
    text: str
    owner: str = "me"
    due_date: str | None = None
    priority: Priority = "normal"


@dataclass(frozen=True)
class EmailAnalysis:
    summary: str
    sender_intent: str
    priority: Priority
    category: Category
    requires_response: bool
    action_items: list[ActionItem] = field(default_factory=list)
    suggested_reply: str = ""
    safety_note: str = "Draft only. No email was sent."
