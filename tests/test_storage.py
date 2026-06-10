import json
import sqlite3
from pathlib import Path
from unittest.mock import Mock

import pytest

import fetch_imap
import storage
from config import ImapSettings


def make_card(
    message_id: str = "<message-1@example.com>",
    requires_response: bool = True,
    summary: str = "Needs attention.",
    priority: str = "high",
    category: str = "billing",
    action_items: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "message_id": message_id,
        "sender": "alex@example.com",
        "subject": "Invoice question",
        "summary": summary,
        "sender_intent": "Requesting confirmation.",
        "priority": priority,
        "category": category,
        "requires_response": requires_response,
        "action_items": action_items
        if action_items is not None
        else [
            {
                "text": "Confirm payment status.",
                "owner": "finance",
                "due_date": "2026-06-05",
                "priority": "urgent",
            }
        ],
        "suggested_reply": "Thanks for the note.",
        "safety_note": "Draft only. No email was sent.",
    }


def test_init_db_creates_schema_and_uses_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "custom.db"
    monkeypatch.setenv("EMAIL_TRIAGE_DB_PATH", str(db_path))

    storage.init_db()

    assert db_path.exists()
    with sqlite3.connect(db_path) as connection:
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='email_cards'"
        ).fetchone()

    assert table == ("email_cards",)


def test_save_summary_card_persists_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "email_triage.db"
    storage.init_db(str(db_path))

    storage.save_summary_card(make_card(), str(db_path))

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT
                message_id,
                sender,
                subject,
                summary,
                sender_intent,
                priority,
                category,
                requires_response,
                action_items_json,
                suggested_reply,
                safety_note,
                fetched_at
            FROM email_cards
            WHERE message_id = ?
            """,
            ("<message-1@example.com>",),
        ).fetchone()

    assert row is not None
    assert row[0] == "<message-1@example.com>"
    assert row[1] == "alex@example.com"
    assert row[7] == 1
    assert json.loads(row[8]) == make_card()["action_items"]
    assert row[11]


def test_save_duplicate_message_id_replaces_existing_row(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "email_triage.db"
    storage.init_db(str(db_path))
    monkeypatch.setattr(
        storage,
        "_utc_now",
        Mock(side_effect=["2026-06-04T10:00:00Z", "2026-06-04T11:00:00Z"]),
    )

    storage.save_summary_card(make_card(summary="First"), str(db_path))
    storage.save_summary_card(make_card(summary="Updated"), str(db_path))

    cards = storage.list_recent_cards(db_path=str(db_path))

    assert len(cards) == 1
    assert cards[0]["summary"] == "Updated"
    assert cards[0]["fetched_at"] == "2026-06-04T11:00:00Z"


def test_list_recent_cards(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "email_triage.db"
    storage.init_db(str(db_path))
    monkeypatch.setattr(
        storage,
        "_utc_now",
        Mock(side_effect=["2026-06-04T10:00:00Z", "2026-06-04T11:00:00Z"]),
    )

    storage.save_summary_card(make_card(message_id="<1@example.com>", summary="Older"), str(db_path))
    storage.save_summary_card(make_card(message_id="<2@example.com>", summary="Newer"), str(db_path))

    cards = storage.list_recent_cards(limit=1, db_path=str(db_path))

    assert [card["message_id"] for card in cards] == ["<2@example.com>"]
    assert cards[0]["summary"] == "Newer"


def test_list_cards_requiring_response(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "email_triage.db"
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

    storage.save_summary_card(make_card(message_id="<1@example.com>", requires_response=True), str(db_path))
    storage.save_summary_card(make_card(message_id="<2@example.com>", requires_response=False), str(db_path))
    storage.save_summary_card(make_card(message_id="<3@example.com>", requires_response=True), str(db_path))

    cards = storage.list_cards_requiring_response(limit=10, db_path=str(db_path))

    assert [card["message_id"] for card in cards] == ["<3@example.com>", "<1@example.com>"]
    assert all(card["requires_response"] is True for card in cards)


def test_list_cards_filters_by_urgent_priority(tmp_path: Path) -> None:
    db_path = tmp_path / "email_triage.db"
    storage.save_summary_cards(
        [
            make_card(message_id="<1@example.com>", priority="urgent"),
            make_card(message_id="<2@example.com>", priority="high"),
        ],
        str(db_path),
    )

    cards = storage.list_cards(priority="urgent", db_path=str(db_path))

    assert [card["message_id"] for card in cards] == ["<1@example.com>"]


def test_list_cards_filters_by_high_priority(tmp_path: Path) -> None:
    db_path = tmp_path / "email_triage.db"
    storage.save_summary_cards(
        [
            make_card(message_id="<1@example.com>", priority="urgent"),
            make_card(message_id="<2@example.com>", priority="high"),
            make_card(message_id="<3@example.com>", priority="normal"),
        ],
        str(db_path),
    )

    cards = storage.list_cards(priority="high", db_path=str(db_path))

    assert [card["message_id"] for card in cards] == ["<2@example.com>"]


def test_list_cards_filters_by_category(tmp_path: Path) -> None:
    db_path = tmp_path / "email_triage.db"
    storage.save_summary_cards(
        [
            make_card(message_id="<1@example.com>", category="billing"),
            make_card(message_id="<2@example.com>", category="support"),
        ],
        str(db_path),
    )

    cards = storage.list_cards(category="billing", db_path=str(db_path))

    assert [card["message_id"] for card in cards] == ["<1@example.com>"]


def test_list_cards_filters_requiring_response(tmp_path: Path) -> None:
    db_path = tmp_path / "email_triage.db"
    storage.save_summary_cards(
        [
            make_card(message_id="<1@example.com>", requires_response=True),
            make_card(message_id="<2@example.com>", requires_response=False),
        ],
        str(db_path),
    )

    cards = storage.list_cards(requires_response=True, db_path=str(db_path))

    assert [card["message_id"] for card in cards] == ["<1@example.com>"]
    assert all(card["requires_response"] is True for card in cards)


def test_list_action_items_returns_items_from_stored_cards(tmp_path: Path) -> None:
    db_path = tmp_path / "email_triage.db"
    storage.save_summary_card(
        make_card(
            message_id="<1@example.com>",
            action_items=[
                {
                    "text": "Confirm payment status.",
                    "owner": "finance",
                    "due_date": "2026-06-05",
                    "priority": "urgent",
                },
                {
                    "text": "Send receipt.",
                    "owner": "me",
                    "due_date": None,
                    "priority": "normal",
                },
            ],
        ),
        str(db_path),
    )

    items = storage.list_action_items(db_path=str(db_path))

    assert [item["text"] for item in items] == ["Confirm payment status.", "Send receipt."]
    assert items[0]["message_id"] == "<1@example.com>"
    assert items[0]["sender"] == "alex@example.com"
    assert items[0]["subject"] == "Invoice question"
    assert items[0]["category"] == "billing"
    assert items[0]["requires_response"] is True
    assert items[0]["fetched_at"]


def test_list_action_items_priority_filter_works(tmp_path: Path) -> None:
    db_path = tmp_path / "email_triage.db"
    storage.save_summary_card(
        make_card(
            action_items=[
                {"text": "Handle now.", "owner": "me", "priority": "urgent"},
                {"text": "Handle later.", "owner": "me", "priority": "normal"},
            ],
        ),
        str(db_path),
    )

    items = storage.list_action_items(priority="urgent", db_path=str(db_path))

    assert [item["text"] for item in items] == ["Handle now."]


def test_list_action_items_owner_filter_works(tmp_path: Path) -> None:
    db_path = tmp_path / "email_triage.db"
    storage.save_summary_card(
        make_card(
            action_items=[
                {"text": "Finance task.", "owner": "finance", "priority": "high"},
                {"text": "My task.", "owner": "me", "priority": "high"},
            ],
        ),
        str(db_path),
    )

    items = storage.list_action_items(owner="FINANCE", db_path=str(db_path))

    assert [item["text"] for item in items] == ["Finance task."]


def test_fetch_imap_save_behavior_uses_storage_and_still_prints_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = ImapSettings(
        host="imap.example.com",
        port=993,
        username="user@example.com",
        password="secret",
        mailbox="INBOX",
        max_messages=2,
    )
    cards = [make_card()]

    monkeypatch.setattr(fetch_imap, "load_imap_settings", Mock(return_value=settings))
    monkeypatch.setattr(fetch_imap, "fetch_inbox_summary_cards", Mock(return_value=cards))
    monkeypatch.setattr(fetch_imap, "_parse_args", Mock(return_value=Mock(max_messages=7, mailbox="ARCHIVE", save=True)))
    monkeypatch.setattr(fetch_imap.storage, "init_db", Mock())
    monkeypatch.setattr(fetch_imap.storage, "save_summary_cards", Mock())

    exit_code = fetch_imap.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert fetch_imap.load_imap_settings.called
    assert fetch_imap.fetch_inbox_summary_cards.call_count == 1
    called_settings = fetch_imap.fetch_inbox_summary_cards.call_args.args[0]
    assert called_settings.max_messages == 7
    assert called_settings.mailbox == "ARCHIVE"
    fetch_imap.storage.init_db.assert_called_once()
    fetch_imap.storage.save_summary_cards.assert_called_once_with(cards)
    assert json.loads(captured.out) == cards
