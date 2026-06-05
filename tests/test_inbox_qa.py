import json
from pathlib import Path
from unittest.mock import Mock

import inbox_qa
import storage


def make_card(
    message_id: str,
    sender: str,
    subject: str,
    priority: str,
    category: str,
    requires_response: bool,
    summary: str,
    action_items: list[dict[str, object]] | None = None,
    sender_intent: str = "Requesting help.",
) -> dict[str, object]:
    return {
        "message_id": message_id,
        "sender": sender,
        "subject": subject,
        "summary": summary,
        "sender_intent": sender_intent,
        "priority": priority,
        "category": category,
        "requires_response": requires_response,
        "action_items": [
            {
                "text": "Confirm payment status.",
                "owner": "me",
                "due_date": None,
                "priority": priority,
            }
        ]
        if action_items is None
        else action_items,
        "suggested_reply": "Thanks for the note.",
        "safety_note": "Draft only. No email was sent.",
    }


def seed_cards(tmp_path: Path) -> Path:
    db_path = tmp_path / "inbox.db"
    storage.init_db(str(db_path))
    storage.save_summary_cards(
        [
            make_card(
                "<1@example.com>",
                "alex@example.com",
                "Invoice question",
                "high",
                "billing",
                True,
                "Can you confirm whether invoice 1042 has been paid?",
                [
                    {
                        "text": "Confirm payment status.",
                        "owner": "finance",
                        "due_date": "2026-06-05",
                        "priority": "high",
                    }
                ],
                "Requesting confirmation.",
            ),
            make_card(
                "<2@example.com>",
                "james@example.com",
                "Urgent issue",
                "urgent",
                "support",
                True,
                "Please handle this immediately.",
                [
                    {
                        "text": "Reply to James.",
                        "owner": "me",
                        "due_date": None,
                        "priority": "urgent",
                    }
                ],
                "Requesting help.",
            ),
            make_card(
                "<3@example.com>",
                "newsletter@example.com",
                "Weekly update",
                "low",
                "newsletter",
                False,
                "This digest includes updates and an unsubscribe link.",
                [],
                "Sharing an update.",
            ),
        ],
        str(db_path),
    )
    return db_path


def test_empty_question_returns_useful_response() -> None:
    result = inbox_qa.answer_inbox_question("")

    assert result["matched_count"] == 0
    assert result["matches"] == []
    assert "Please ask a question" in result["answer"]


def test_no_stored_cards(tmp_path: Path) -> None:
    db_path = tmp_path / "empty.db"

    result = inbox_qa.answer_inbox_question("Catch me up", db_path=str(db_path))

    assert result["matched_count"] == 0
    assert result["matches"] == []
    assert "couldn’t find any matching stored summary cards" in result["answer"]


def test_catch_me_up_overview(tmp_path: Path) -> None:
    db_path = seed_cards(tmp_path)

    result = inbox_qa.answer_inbox_question("Catch me up", db_path=str(db_path))

    assert result["matched_count"] == 3
    assert "recent stored summary card(s)" in result["answer"]
    assert result["matches"][0]["priority"] == "urgent"


def test_emails_requiring_response(tmp_path: Path) -> None:
    db_path = seed_cards(tmp_path)

    result = inbox_qa.answer_inbox_question("What emails need my response?", db_path=str(db_path))

    assert result["matched_count"] == 2
    assert all(match["requires_response"] is True for match in result["matches"])
    assert "need your response" in result["answer"]


def test_urgent_email_query(tmp_path: Path) -> None:
    db_path = seed_cards(tmp_path)

    matches = inbox_qa.search_cards("What urgent emails do I have?", db_path=str(db_path))

    assert [match["priority"] for match in matches] == ["urgent", "high"]
    assert matches[0]["subject"] == "Urgent issue"


def test_billing_category_query(tmp_path: Path) -> None:
    db_path = seed_cards(tmp_path)

    result = inbox_qa.answer_inbox_question("Any billing emails?", db_path=str(db_path))

    assert result["matched_count"] == 1
    assert result["matches"][0]["category"] == "billing"
    assert "matching email(s)" in result["answer"]


def test_action_item_query(tmp_path: Path) -> None:
    db_path = seed_cards(tmp_path)

    result = inbox_qa.answer_inbox_question("What action items do I have?", db_path=str(db_path))

    assert result["matched_count"] == 2
    assert all(match["action_items"] for match in result["matches"])
    assert "action item" in result["answer"]


def test_sender_name_query(tmp_path: Path) -> None:
    db_path = seed_cards(tmp_path)

    result = inbox_qa.answer_inbox_question("What did James say?", db_path=str(db_path))

    assert result["matched_count"] == 1
    assert result["matches"][0]["sender"] == "james@example.com"


def test_cli_prints_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        inbox_qa,
        "_parse_args",
        Mock(return_value=Mock(question="Catch me up", limit=10)),
    )
    monkeypatch.setattr(
        inbox_qa,
        "answer_inbox_question",
        Mock(return_value={"question": "Catch me up", "answer": "ok"}),
    )

    exit_code = inbox_qa.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert json.loads(captured.out) == {"question": "Catch me up", "answer": "ok"}
