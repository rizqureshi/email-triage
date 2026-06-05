import json
from pathlib import Path
from unittest.mock import Mock

import daily_briefing
import storage


def make_card(
    message_id: str,
    priority: str,
    category: str,
    requires_response: bool,
    summary: str,
    action_text: str,
    sender: str = "alex@example.com",
    subject: str = "Invoice question",
) -> dict[str, object]:
    return {
        "message_id": message_id,
        "sender": sender,
        "subject": subject,
        "summary": summary,
        "sender_intent": "Requesting confirmation.",
        "priority": priority,
        "category": category,
        "requires_response": requires_response,
        "action_items": [
            {
                "text": action_text,
                "owner": "me",
                "due_date": None,
                "priority": priority,
            }
        ],
        "suggested_reply": "Thanks for the note.",
        "safety_note": "Draft only. No email was sent.",
    }


def test_empty_database_briefing(tmp_path: Path) -> None:
    db_path = tmp_path / "briefing.db"

    briefing = daily_briefing.generate_daily_briefing(db_path=str(db_path))

    assert briefing == {
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


def test_briefing_with_urgent_and_high_emails(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "briefing.db"
    storage.init_db(str(db_path))
    monkeypatch.setattr(
        storage,
        "_utc_now",
        Mock(side_effect=[
            "2026-06-04T10:00:00Z",
            "2026-06-04T11:00:00Z",
        ]),
    )
    storage.save_summary_cards(
        [
            make_card(
                "<1@example.com>",
                "urgent",
                "billing",
                True,
                "Needs immediate attention.",
                "Confirm payment status.",
                subject="Urgent invoice",
            ),
            make_card(
                "<2@example.com>",
                "high",
                "support",
                True,
                "Needs follow-up soon.",
                "Respond to the issue.",
                subject="Support issue",
            ),
        ],
        str(db_path),
    )

    briefing = daily_briefing.generate_daily_briefing(db_path=str(db_path))

    assert briefing["total_emails_reviewed"] == 2
    assert briefing["urgent_count"] == 1
    assert briefing["high_priority_count"] == 1
    assert briefing["requires_response_count"] == 2
    assert briefing["important_emails"][0]["priority"] == "urgent"
    assert briefing["important_emails"][0]["subject"] == "Urgent invoice"
    assert briefing["suggested_focus"][0] == "Handle 1 urgent email(s) first."


def test_action_item_aggregation_and_category_counts(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "briefing.db"
    storage.init_db(str(db_path))
    monkeypatch.setattr(
        storage,
        "_utc_now",
        Mock(side_effect=[
            "2026-06-04T10:00:00Z",
            "2026-06-04T11:00:00Z",
            "2026-06-04T12:00:00Z",
        ]),
    )
    storage.save_summary_cards(
        [
            make_card("<1@example.com>", "high", "billing", True, "One", "Confirm payment status."),
            make_card("<2@example.com>", "urgent", "billing", True, "Two", "Confirm payment status."),
            make_card("<3@example.com>", "normal", "newsletter", False, "Three", "Read update."),
        ],
        str(db_path),
    )

    briefing = daily_briefing.generate_daily_briefing(db_path=str(db_path))

    assert briefing["categories"] == {"billing": 2, "newsletter": 1}
    assert briefing["top_action_items"][0]["text"] == "Confirm payment status."
    assert briefing["top_action_items"][0]["count"] == 2
    assert briefing["top_action_items"][0]["priority"] == "urgent"


def test_cli_prints_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        daily_briefing,
        "_parse_args",
        Mock(return_value=Mock(limit=20)),
    )
    monkeypatch.setattr(
        daily_briefing,
        "generate_daily_briefing",
        Mock(return_value={"total_emails_reviewed": 0, "safety_note": "ok"}),
    )

    exit_code = daily_briefing.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert json.loads(captured.out) == {"total_emails_reviewed": 0, "safety_note": "ok"}
