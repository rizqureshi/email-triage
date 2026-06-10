"""One-click inbox review workflow."""

from __future__ import annotations

from dataclasses import replace

import daily_briefing
import fetch_imap
import storage
from config import load_imap_settings


SAFETY_NOTE = (
    "Review fetched unread emails read-only, saved local summary cards, and did not "
    "send, delete, archive, move, or mark any email as read."
)


def run_inbox_review(
    max_messages: int = 10,
    mailbox: str = "INBOX",
) -> dict[str, object]:
    settings = load_imap_settings()
    settings = replace(
        settings,
        max_messages=max_messages,
        mailbox=mailbox.strip() or "INBOX",
    )

    cards = fetch_imap.fetch_inbox_summary_cards(settings)
    storage.save_summary_cards(cards)
    briefing = daily_briefing.generate_daily_briefing()
    action_items = storage.list_action_items()
    urgent_emails = storage.list_cards(priority="urgent")
    high_priority_emails = storage.list_cards(priority="high")
    response_needed_emails = storage.list_cards(requires_response=True)

    return {
        "fetched_count": len(cards),
        "saved_count": len(cards),
        "briefing": briefing,
        "action_items": action_items,
        "urgent_emails": urgent_emails,
        "high_priority_emails": high_priority_emails,
        "response_needed_emails": response_needed_emails,
        "safety_note": SAFETY_NOTE,
    }


def format_inbox_review(review: dict[str, object]) -> str:
    briefing = review.get("briefing", {})
    if not isinstance(briefing, dict):
        briefing = {}

    action_items = _list_value(review.get("action_items"))
    urgent_emails = _list_value(review.get("urgent_emails"))
    high_priority_emails = _list_value(review.get("high_priority_emails"))
    response_needed_emails = _list_value(review.get("response_needed_emails"))

    lines = [
        "Inbox Review",
        f"Fetched: {review.get('fetched_count', 0)}",
        f"Saved: {review.get('saved_count', 0)}",
        f"Urgent: {len(urgent_emails)}",
        f"High priority: {len(high_priority_emails)}",
        f"Need response: {len(response_needed_emails)}",
        f"Action items: {len(action_items)}",
        "",
        "Suggested Focus:",
    ]

    _append_list(lines, briefing.get("suggested_focus", []))

    lines.extend(["", "Top Action Items:"])
    top_action_items = briefing.get("top_action_items", [])
    if not top_action_items:
        top_action_items = action_items[:10]
    _append_action_items(lines, top_action_items)

    lines.extend(["", "Important Emails:"])
    _append_cards(lines, briefing.get("important_emails", []))

    lines.extend(["", str(review.get("safety_note") or SAFETY_NOTE)])
    return "\n".join(lines)


def _list_value(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    return []


def _append_list(lines: list[str], items: object) -> None:
    if isinstance(items, list) and items:
        for item in items:
            lines.append(f"- {item}")
    else:
        lines.append("- None")


def _append_action_items(lines: list[str], items: object) -> None:
    if isinstance(items, list) and items:
        for item in items:
            if isinstance(item, dict):
                lines.append(f"- {_format_action_item(item)}")
            else:
                lines.append(f"- {item}")
    else:
        lines.append("- None")


def _append_cards(lines: list[str], cards: object) -> None:
    if isinstance(cards, list) and cards:
        for card in cards:
            if not isinstance(card, dict):
                lines.append(f"- {card}")
                continue
            lines.append(
                f"- {card.get('subject') or '(no subject)'} from "
                f"{card.get('sender') or '(unknown sender)'} "
                f"({card.get('priority') or 'normal'}, {card.get('category') or 'other'})"
            )
    else:
        lines.append("- None")


def _format_action_item(item: dict[str, object]) -> str:
    text = str(item.get("text") or "").strip() or "(no action text)"
    owner = str(item.get("owner") or "").strip()
    due_date = str(item.get("due_date") or "").strip()
    priority = str(item.get("priority") or "").strip()
    details = []
    if owner:
        details.append(f"owner: {owner}")
    if due_date:
        details.append(f"due: {due_date}")
    if priority:
        details.append(f"priority: {priority}")
    if details:
        return f"{text} ({', '.join(details)})"
    return text
