"""Read-only email intelligence analysis and reply drafting."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict

from config import Settings, load_settings
from schemas import ActionItem, Category, EmailAnalysis, Priority
from triage import EmailMessage


def analyze_email(email: EmailMessage, settings: Settings | None = None) -> EmailAnalysis:
    """Analyze an email and extract summary, intent, and action items."""

    settings = settings or load_settings()
    if settings.use_openai:
        return _analyze_with_openai(email, settings)

    return _analyze_with_rules(email, settings)


def _analyze_with_openai(email: EmailMessage, settings: Settings) -> EmailAnalysis:
    try:
        client = _create_openai_client(settings.openai_api_key)
    except ImportError as exc:
        raise RuntimeError(
            "OPENAI_API_KEY is configured, but the openai package is not installed. "
            "Run `pip install -r requirements.txt`."
        ) from exc
    except Exception:
        return _analyze_with_rules(email, settings)

    prompt = {
        "sender": email.sender,
        "subject": email.subject,
        "body": email.body,
        "reply_tone": settings.default_reply_tone,
        "max_draft_words": settings.max_draft_words,
    }

    try:
        response = client.responses.create(
            model=settings.openai_model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You analyze emails for human review. Return only JSON "
                        "with keys: summary, sender_intent, priority, category, "
                        "requires_response, action_items, suggested_reply, safety_note. "
                        "Priority must be low, normal, high, or urgent. Category must "
                        "be billing, scheduling, support, sales, personal, newsletter, "
                        "or other. action_items must be a JSON array of objects with "
                        "text, owner, due_date, and priority fields."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(prompt),
                },
            ],
            text={"format": {"type": "json_object"}},
        )
    except Exception:
        return _analyze_with_rules(email, settings)

    output_text = getattr(response, "output_text", None)
    if not isinstance(output_text, str) or not output_text.strip():
        return _analyze_with_rules(email, settings)

    try:
        data = json.loads(output_text)
    except json.JSONDecodeError:
        return _analyze_with_rules(email, settings)

    if not isinstance(data, dict) or not _has_usable_openai_values(data):
        return _analyze_with_rules(email, settings)

    return _analysis_from_model_data(data, email, settings)


def _create_openai_client(api_key: str | None):
    from openai import OpenAI

    return OpenAI(api_key=api_key)


def _analysis_from_model_data(
    data: dict[str, object], email: EmailMessage, settings: Settings
) -> EmailAnalysis:
    local_analysis = _analyze_with_rules(email, settings)

    return EmailAnalysis(
        summary=_coerce_text(data.get("summary")) or local_analysis.summary,
        sender_intent=_coerce_text(data.get("sender_intent")) or local_analysis.sender_intent,
        priority=_coerce_priority(data.get("priority"), local_analysis.priority),
        category=_coerce_category(data.get("category"), local_analysis.category),
        requires_response=_coerce_bool(data.get("requires_response"), local_analysis.requires_response),
        action_items=_coerce_action_items(
            data.get("action_items"), local_analysis.action_items
        ),
        suggested_reply=_coerce_text(data.get("suggested_reply")) or local_analysis.suggested_reply,
        safety_note=_coerce_text(data.get("safety_note")) or local_analysis.safety_note,
    )


def _analyze_with_rules(email: EmailMessage, settings: Settings) -> EmailAnalysis:
    text = _combined_text(email)
    priority = _determine_priority(text)
    category = _categorize(text)
    requires_response = _requires_response(text, priority, category)

    summary = _rule_summary(email, category, requires_response)
    sender_intent = _sender_intent(email, category, requires_response)
    action_items = _extract_action_items(email, text, requires_response)
    suggested_reply = _suggested_reply(email, settings, requires_response)

    return EmailAnalysis(
        summary=summary,
        sender_intent=sender_intent,
        priority=priority,
        category=category,
        requires_response=requires_response,
        action_items=action_items,
        suggested_reply=suggested_reply,
    )


def _combined_text(email: EmailMessage) -> str:
    return f"{email.subject}\n{email.body}".lower()


def _determine_priority(text: str) -> Priority:
    if any(word in text for word in ("urgent", "asap", "immediately", "emergency")):
        return "urgent"
    if any(word in text for word in ("deadline", "blocked", "overdue", "today")):
        return "high"
    if any(word in text for word in ("newsletter", "unsubscribe", "digest")):
        return "low"
    return "normal"


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


def _requires_response(text: str, priority: Priority, category: Category) -> bool:
    if category == "newsletter":
        return False
    return priority in {"high", "urgent"} or any(
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


def _rule_summary(email: EmailMessage, category: Category, requires_response: bool) -> str:
    action = "appears to need a response" if requires_response else "may not need a response"
    subject = email.subject or "this email"
    return f"{email.sender} sent a {category} email about '{subject}' that {action}."


def _sender_intent(email: EmailMessage, category: Category, requires_response: bool) -> str:
    subject = (email.subject or "").strip().lower()
    body = (email.body or "").strip().lower()
    text = f"{subject}\n{body}"

    if category == "newsletter":
        return "Sharing a newsletter or update."
    if "confirm whether" in text and "invoice" in text:
        return "Asking for confirmation about invoice status."
    if "can you" in text or "could you" in text or "please" in text:
        return "Requesting help or a follow-up."
    if requires_response:
        return "Requesting a response or clarification."
    return "Sharing information."


def _extract_action_items(
    email: EmailMessage, text: str, requires_response: bool
) -> list[ActionItem]:
    if not requires_response:
        return []

    action_items: list[ActionItem] = []
    patterns = [
        r"(?:can you|could you|please)\s+confirm whether\s+(.+?)(?:\?|\.|$)",
        r"(?:can you|could you|please)\s+(.+?)(?:\?|\.|$)",
        r"let me know\s+(.+?)(?:\?|\.|$)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            continue

        item_text = _normalize_action_item_text(match.group(1))
        if item_text:
            action_items.append(
                ActionItem(text=item_text, owner="me", due_date=None, priority="normal")
            )
            break

    if action_items:
        return action_items

    if "?" in text:
        subject = email.subject.strip() or "this email"
        action_items.append(
            ActionItem(
                text=f"Respond to the question in '{subject}'.",
                owner="me",
                due_date=None,
                priority="normal",
            )
        )

    return action_items


def _normalize_action_item_text(text: str) -> str:
    cleaned = " ".join(text.strip().split())
    cleaned = cleaned.strip(" .")
    if not cleaned:
        return ""
    return cleaned[:1].upper() + cleaned[1:] + ("." if not cleaned.endswith(".") else "")


def _suggested_reply(email: EmailMessage, settings: Settings, requires_response: bool) -> str:
    if not requires_response:
        return "No reply needed."
    return (
        f"Hi,\n\n"
        f"Thanks for your email about {email.subject or 'this'}. "
        f"I've received it and will review the details before following up.\n\n"
        f"Best,\n"
    )


def _coerce_priority(value: object, fallback: Priority) -> Priority:
    allowed: set[Priority] = {"low", "normal", "high", "urgent"}
    if isinstance(value, str) and value.lower() in allowed:
        return value.lower()  # type: ignore[return-value]
    return fallback


def _coerce_category(value: object, fallback: Category) -> Category:
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
    return fallback


def _coerce_bool(value: object, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0"}:
            return False
    return fallback


def _coerce_action_items(value: object, fallback: list[ActionItem]) -> list[ActionItem]:
    if not isinstance(value, list):
        return fallback

    items: list[ActionItem] = []
    for item in value:
        if isinstance(item, str):
            normalized = _normalize_action_item_text(item)
            if normalized:
                items.append(ActionItem(text=normalized))
            continue
        if isinstance(item, dict):
            action_item = _coerce_action_item(item)
            if action_item is not None:
                items.append(action_item)

    return items or fallback


def _coerce_action_item(value: dict[str, object]) -> ActionItem | None:
    text = _coerce_text(value.get("text"))
    normalized = _normalize_action_item_text(text)
    if not normalized:
        return None

    return ActionItem(
        text=normalized,
        owner=_coerce_action_item_owner(value.get("owner")),
        due_date=_coerce_action_item_due_date(value.get("due_date")),
        priority=_coerce_action_item_priority(value.get("priority")),
    )


def _coerce_action_item_owner(value: object) -> str:
    owner = _coerce_text(value)
    return owner or "me"


def _coerce_action_item_due_date(value: object) -> str | None:
    due_date = _coerce_text(value)
    return due_date or None


def _coerce_action_item_priority(value: object) -> Priority:
    return _coerce_priority(value, "normal")


def _coerce_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _has_usable_openai_values(data: dict[str, object]) -> bool:
    summary = data.get("summary")
    sender_intent = data.get("sender_intent")
    priority = data.get("priority")
    category = data.get("category")
    requires_response = data.get("requires_response")
    action_items = data.get("action_items")
    suggested_reply = data.get("suggested_reply")
    safety_note = data.get("safety_note")

    return any(
        (
            isinstance(summary, str) and bool(summary.strip()),
            isinstance(sender_intent, str) and bool(sender_intent.strip()),
            _is_valid_priority(priority),
            _is_valid_category(category),
            _is_bool_like(requires_response),
            _has_valid_action_items(action_items),
            isinstance(suggested_reply, str) and bool(suggested_reply.strip()),
            isinstance(safety_note, str) and bool(safety_note.strip()),
        )
    )


def _has_valid_action_items(value: object) -> bool:
    if not isinstance(value, list):
        return False
    for item in value:
        if isinstance(item, str) and item.strip():
            return True
        if isinstance(item, dict):
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                return True
    return False


def _is_valid_priority(value: object) -> bool:
    return isinstance(value, str) and value.lower() in {"low", "normal", "high", "urgent"}


def _is_valid_category(value: object) -> bool:
    return isinstance(value, str) and value.lower() in {
        "billing",
        "scheduling",
        "support",
        "sales",
        "personal",
        "newsletter",
        "other",
    }


def _is_bool_like(value: object) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, int):
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"true", "false", "yes", "no", "1", "0"}
    return False


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze an email and extract summary, intent, and action items. Does not send email."
    )
    parser.add_argument("--from", dest="sender", default="", help="Sender email address")
    parser.add_argument("--subject", default="", help="Email subject")
    parser.add_argument("--body", default=None, help="Email body. Defaults to stdin.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    body = args.body if args.body is not None else sys.stdin.read()

    email = EmailMessage(sender=args.sender, subject=args.subject, body=body.strip())
    result = analyze_email(email)
    print(json.dumps(asdict(result), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
