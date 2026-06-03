"""Email triage and reply drafting.

This module only generates recommendations and draft text. It deliberately does
not include any email-sending behavior.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from typing import Literal

from config import Settings, load_settings


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
class EmailMessage:
    sender: str
    subject: str
    body: str


@dataclass(frozen=True)
class TriageResult:
    priority: Priority
    category: Category
    summary: str
    action_required: bool
    reply_draft: str
    safety_note: str = "Draft only. No email was sent."


def triage_email(email: EmailMessage, settings: Settings | None = None) -> TriageResult:
    """Triage an email and generate a reply draft."""

    settings = settings or load_settings()
    if settings.use_openai:
        return _triage_with_openai(email, settings)

    return _triage_with_rules(email, settings)


def _triage_with_openai(email: EmailMessage, settings: Settings) -> TriageResult:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError(
            "OPENAI_API_KEY is configured, but the openai package is not installed. "
            "Run `pip install -r requirements.txt`."
        ) from exc

    client = OpenAI(api_key=settings.openai_api_key)

    prompt = {
        "sender": email.sender,
        "subject": email.subject,
        "body": email.body,
        "reply_tone": settings.default_reply_tone,
        "max_draft_words": settings.max_draft_words,
    }

    response = client.responses.create(
        model=settings.openai_model,
        input=[
            {
                "role": "system",
                "content": (
                    "You triage emails and draft replies for human review. "
                    "Never claim that an email has been sent. Return only JSON "
                    "with keys: priority, category, summary, action_required, "
                    "reply_draft. Priority must be low, normal, high, or urgent. "
                    "Category must be billing, scheduling, support, sales, "
                    "personal, newsletter, or other."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(prompt),
            },
        ],
        text={"format": {"type": "json_object"}},
    )

    data = json.loads(response.output_text)
    return TriageResult(
        priority=_coerce_priority(data.get("priority")),
        category=_coerce_category(data.get("category")),
        summary=str(data.get("summary", "")).strip() or "No summary provided.",
        action_required=bool(data.get("action_required")),
        reply_draft=str(data.get("reply_draft", "")).strip()
        or _default_reply_draft(email, settings),
    )


def _triage_with_rules(email: EmailMessage, settings: Settings) -> TriageResult:
    subject = email.subject.lower()
    body = email.body.lower()
    text = f"{subject}\n{body}"

    priority: Priority = "normal"
    if any(word in text for word in ("urgent", "asap", "immediately", "emergency")):
        priority = "urgent"
    elif any(word in text for word in ("deadline", "blocked", "overdue", "today")):
        priority = "high"
    elif any(word in text for word in ("newsletter", "unsubscribe", "digest")):
        priority = "low"

    category = _categorize(text)
    action_required = priority in {"high", "urgent"} or any(
        phrase in text
        for phrase in (
            "can you",
            "could you",
            "please",
            "let me know",
            "confirm",
            "question",
            "?",
        )
    )

    return TriageResult(
        priority=priority,
        category=category,
        summary=_rule_summary(email, category, action_required),
        action_required=action_required,
        reply_draft=_default_reply_draft(email, settings),
    )


def _categorize(text: str) -> Category:
    if any(word in text for word in ("invoice", "payment", "billing", "paid", "refund")):
        return "billing"
    if any(word in text for word in ("meeting", "schedule", "calendar", "call", "appointment")):
        return "scheduling"
    if any(word in text for word in ("bug", "issue", "error", "problem", "support")):
        return "support"
    if any(word in text for word in ("demo", "pricing", "proposal", "sales")):
        return "sales"
    if any(word in text for word in ("family", "dinner", "weekend", "birthday")):
        return "personal"
    if any(word in text for word in ("newsletter", "digest", "unsubscribe")):
        return "newsletter"
    return "other"


def _rule_summary(email: EmailMessage, category: Category, action_required: bool) -> str:
    action = "appears to need a response" if action_required else "may not need a response"
    return f"{email.sender} sent a {category} email about '{email.subject}' that {action}."


def _default_reply_draft(email: EmailMessage, settings: Settings) -> str:
    return (
        f"Hi,\n\n"
        f"Thanks for your email about {email.subject or 'this'}. "
        f"I have received it and will review the details before following up.\n\n"
        f"Best,\n"
    )


def _coerce_priority(value: object) -> Priority:
    allowed: set[Priority] = {"low", "normal", "high", "urgent"}
    if isinstance(value, str) and value.lower() in allowed:
        return value.lower()  # type: ignore[return-value]
    return "normal"


def _coerce_category(value: object) -> Category:
    allowed: set[Category] = {
        "billing",
        "scheduling",
        "support",
        "sales",
        "personal",
        "newsletter",
        "other",
    }
    if isinstance(value, str) and value.lower() in allowed:
        return value.lower()  # type: ignore[return-value]
    return "other"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Triage an email and create a reply draft. Does not send email."
    )
    parser.add_argument("--from", dest="sender", default="", help="Sender email address")
    parser.add_argument("--subject", default="", help="Email subject")
    parser.add_argument("--body", default=None, help="Email body. Defaults to stdin.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    body = args.body if args.body is not None else sys.stdin.read()

    email = EmailMessage(sender=args.sender, subject=args.subject, body=body.strip())
    result = triage_email(email)
    print(json.dumps(asdict(result), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
