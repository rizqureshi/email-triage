import json
import sys
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
    assert result["answer_mode"] == "deterministic"
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

    assert [match["priority"] for match in matches] == ["urgent"]
    assert matches[0]["subject"] == "Urgent issue"


def test_high_priority_email_query(tmp_path: Path) -> None:
    db_path = seed_cards(tmp_path)

    matches = inbox_qa.search_cards("What high priority emails do I have?", db_path=str(db_path))

    assert [match["priority"] for match in matches] == ["urgent", "high"]


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
        Mock(return_value=Mock(question="Catch me up", limit=10, ai=False)),
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


def test_cli_ai_flag_is_parsed(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["inbox_qa.py", "Catch me up", "--ai"])

    args = inbox_qa._parse_args()

    assert args.question == "Catch me up"
    assert args.ai is True


def test_cli_passes_ai_flag_to_answer(monkeypatch, capsys) -> None:
    answer_mock = Mock(return_value={"question": "Catch me up", "answer": "ok"})
    monkeypatch.setattr(
        inbox_qa,
        "_parse_args",
        Mock(return_value=Mock(question="Catch me up", limit=10, ai=True)),
    )
    monkeypatch.setattr(inbox_qa, "answer_inbox_question", answer_mock)

    exit_code = inbox_qa.main()
    capsys.readouterr()

    assert exit_code == 0
    answer_mock.assert_called_once_with("Catch me up", limit=10, use_ai=True)


def test_ai_without_api_key_falls_back_safely(tmp_path: Path, monkeypatch) -> None:
    db_path = seed_cards(tmp_path)
    monkeypatch.setattr(
        inbox_qa.config,
        "load_settings",
        Mock(return_value=Mock(openai_api_key=None, openai_model="gpt-test")),
    )
    client_mock = Mock()
    monkeypatch.setattr(inbox_qa, "_create_openai_client", client_mock)

    result = inbox_qa.answer_inbox_question(
        "What emails need my response?", db_path=str(db_path), use_ai=True
    )

    assert result["answer_mode"] == "deterministic_fallback"
    assert "need your response" in result["answer"]
    client_mock.assert_not_called()


def test_ai_calls_openai_client_when_key_is_present(tmp_path: Path, monkeypatch) -> None:
    db_path = seed_cards(tmp_path)
    create_mock = Mock()
    fake_client = Mock()
    fake_client.responses.create.return_value = Mock(
        output_text="You should reply to James and confirm the invoice status."
    )
    create_mock.return_value = fake_client
    monkeypatch.setattr(
        inbox_qa.config,
        "load_settings",
        Mock(return_value=Mock(openai_api_key="test-key", openai_model="gpt-test")),
    )
    monkeypatch.setattr(inbox_qa, "_create_openai_client", create_mock)

    result = inbox_qa.answer_inbox_question(
        "What emails need my response?", db_path=str(db_path), use_ai=True
    )

    assert result["answer_mode"] == "ai"
    assert result["answer"] == "You should reply to James and confirm the invoice status."
    create_mock.assert_called_once_with("test-key")
    fake_client.responses.create.assert_called_once()
    assert fake_client.responses.create.call_args.kwargs["model"] == "gpt-test"


def test_ai_failure_falls_back_to_deterministic_answer(tmp_path: Path, monkeypatch) -> None:
    db_path = seed_cards(tmp_path)
    fake_client = Mock()
    fake_client.responses.create.side_effect = RuntimeError("api unavailable")
    monkeypatch.setattr(
        inbox_qa.config,
        "load_settings",
        Mock(return_value=Mock(openai_api_key="test-key", openai_model="gpt-test")),
    )
    monkeypatch.setattr(inbox_qa, "_create_openai_client", Mock(return_value=fake_client))

    result = inbox_qa.answer_inbox_question("Any billing emails?", db_path=str(db_path), use_ai=True)

    assert result["answer_mode"] == "deterministic_fallback"
    assert "matching email(s)" in result["answer"]


def test_ai_sends_only_compact_matches_to_openai(monkeypatch) -> None:
    card_with_body = make_card(
        "<raw@example.com>",
        "raw@example.com",
        "Raw body check",
        "high",
        "support",
        True,
        "Stored summary only.",
    )
    card_with_body["body"] = "This raw email body must not be sent."
    card_with_body["raw_body"] = "This raw body must not be sent either."
    fake_client = Mock()
    fake_client.responses.create.return_value = Mock(output_text="Use the stored summary.")
    monkeypatch.setattr(inbox_qa, "search_cards", Mock(return_value=[card_with_body]))
    monkeypatch.setattr(
        inbox_qa.config,
        "load_settings",
        Mock(return_value=Mock(openai_api_key="test-key", openai_model="gpt-test")),
    )
    monkeypatch.setattr(inbox_qa, "_create_openai_client", Mock(return_value=fake_client))

    result = inbox_qa.answer_inbox_question("What needs attention?", use_ai=True)

    user_message = fake_client.responses.create.call_args.kwargs["input"][1]
    payload = json.loads(user_message["content"])
    sent_match = payload["matches"][0]
    assert result["answer_mode"] == "ai"
    assert "body" not in sent_match
    assert "raw_body" not in sent_match
    assert sent_match == inbox_qa._compact_match(card_with_body)
