"""Daily briefing built from stored email summary cards."""

from __future__ import annotations

import argparse
import json
from collections import Counter

import storage


def generate_daily_briefing(limit: int = 20, db_path: str | None = None) -> dict[str, object]:
    cards = storage.list_recent_cards(limit=limit, db_path=db_path)
    if not cards:
        return {
            "total_emails_reviewed": 0,
            "urgent_count": 0,
            "high_priority_count": 0,
            "requires_response_count": 0,
            "categories": {},
            "top_action_items": [],
            "important_emails": [],
            "suggested_focus": [
                "No stored summary cards were found yet.",
                "Run `python fetch_imap.py --max-messages 5 --save` to collect inbox cards.",
            ],
            "safety_note": "Briefing generated from stored summary cards only. No email was fetched or modified.",
        }

    total_emails_reviewed = len(cards)
    urgent_count = sum(1 for card in cards if card.get("priority") == "urgent")
    high_priority_count = sum(1 for card in cards if card.get("priority") == "high")
    requires_response_count = sum(1 for card in cards if card.get("requires_response"))
    categories = Counter(
        str(card.get("category") or "other").strip() or "other"
        for card in cards
    )

    top_action_items = _aggregate_action_items(cards)
    important_emails = _important_emails(cards)
    suggested_focus = _suggested_focus(
        urgent_count=urgent_count,
        high_priority_count=high_priority_count,
        requires_response_count=requires_response_count,
        categories=categories,
        important_emails=important_emails,
        top_action_items=top_action_items,
    )

    return {
        "total_emails_reviewed": total_emails_reviewed,
        "urgent_count": urgent_count,
        "high_priority_count": high_priority_count,
        "requires_response_count": requires_response_count,
        "categories": dict(categories),
        "top_action_items": top_action_items,
        "important_emails": important_emails,
        "suggested_focus": suggested_focus,
        "safety_note": "Briefing generated from stored summary cards only. No email was fetched or modified.",
    }


def _aggregate_action_items(cards: list[dict[str, object]]) -> list[dict[str, object]]:
    counts: dict[tuple[str, str, str | None], dict[str, object]] = {}
    for card in cards:
        action_items = card.get("action_items", [])
        if not isinstance(action_items, list):
            continue
        for item in action_items:
            normalized = _normalize_action_item(item)
            if normalized is None:
                continue
            key = (normalized["text"], normalized["owner"], normalized["due_date"])
            existing = counts.get(key)
            if existing is None:
                counts[key] = {
                    "text": normalized["text"],
                    "owner": normalized["owner"],
                    "due_date": normalized["due_date"],
                    "priority": normalized["priority"],
                    "count": 1,
                }
                continue

            existing["count"] = int(existing["count"]) + 1
            if _priority_rank(str(normalized["priority"])) > _priority_rank(
                str(existing["priority"])
            ):
                existing["priority"] = normalized["priority"]

    aggregated = list(counts.values())

    aggregated.sort(
        key=lambda item: (
            -_priority_rank(str(item["priority"])),
            -int(item["count"]),
            str(item["text"]).lower(),
        )
    )
    return aggregated[:10]


def _important_emails(cards: list[dict[str, object]]) -> list[dict[str, object]]:
    ranked = sorted(
        cards,
        key=lambda card: (
            _priority_rank(str(card.get("priority") or "normal")),
            bool(card.get("requires_response")),
            str(card.get("fetched_at") or ""),
        ),
        reverse=True,
    )

    entries: list[dict[str, object]] = []
    for card in ranked[:10]:
        entries.append(
            {
                "message_id": card.get("message_id"),
                "sender": card.get("sender"),
                "subject": card.get("subject"),
                "priority": card.get("priority"),
                "category": card.get("category"),
                "requires_response": bool(card.get("requires_response")),
                "summary": card.get("summary"),
            }
        )
    return entries


def _suggested_focus(
    *,
    urgent_count: int,
    high_priority_count: int,
    requires_response_count: int,
    categories: Counter[str],
    important_emails: list[dict[str, object]],
    top_action_items: list[dict[str, object]],
) -> list[str]:
    focus: list[str] = []

    if urgent_count:
        focus.append(f"Handle {urgent_count} urgent email(s) first.")
    elif high_priority_count:
        focus.append(f"Work through {high_priority_count} high-priority email(s) next.")
    else:
        focus.append("Review lower-priority items when time allows.")

    if requires_response_count:
        focus.append(f"{requires_response_count} email(s) appear to need a response.")

    if categories:
        top_category, count = categories.most_common(1)[0]
        focus.append(f"Most of the inbox is in {top_category} ({count} email(s)).")

    if top_action_items:
        focus.append(f"Track the top action item: {top_action_items[0]['text']}")

    if important_emails:
        focus.append(f"Start with {important_emails[0]['subject']} from {important_emails[0]['sender']}.")

    return focus[:5]


def _normalize_action_item(item: object) -> dict[str, str | None] | None:
    if not isinstance(item, dict):
        text = str(item).strip()
        if not text:
            return None
        return {
            "text": text,
            "owner": "me",
            "due_date": None,
            "priority": "normal",
        }

    text = str(item.get("text") or "").strip()
    if not text:
        return None

    owner = str(item.get("owner") or "").strip() or "me"
    due_date_raw = str(item.get("due_date") or "").strip()
    due_date = due_date_raw or None
    priority = str(item.get("priority") or "").strip() or "normal"

    return {
        "text": text,
        "owner": owner,
        "due_date": due_date,
        "priority": priority,
    }


def _priority_rank(priority: str) -> int:
    order = {
        "urgent": 4,
        "high": 3,
        "normal": 2,
        "low": 1,
    }
    return order.get(priority, 1)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a daily briefing from stored summary cards."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of recent stored cards to include.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    briefing = generate_daily_briefing(limit=args.limit)
    print(json.dumps(briefing, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
