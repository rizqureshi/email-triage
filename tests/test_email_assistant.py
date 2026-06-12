import json
from unittest.mock import Mock

import pytest

import email_assistant
from config import ImapSettings
from schemas import ActionItem, EmailAnalysis
from triage import EmailMessage


def make_card() -> dict[str, object]:
    return {
        "message_id": "<1@example.com>",
        "sender": "alex@example.com",
        "subject": "Invoice question",
        "priority": "high",
        "category": "billing",
        "requires_response": True,
        "summary": "Alex asks whether invoice 1042 has been paid.",
        "action_items": [
            {
                "text": "Confirm payment status.",
                "owner": "finance",
                "due_date": "2026-06-05",
                "priority": "high",
            }
        ],
    }


def make_settings() -> ImapSettings:
    return ImapSettings(
        host="imap.example.com",
        port=993,
        username="user@example.com",
        password="secret-password",
        mailbox="INBOX",
        max_messages=5,
    )


def make_briefing() -> dict[str, object]:
    return {
        "total_emails_reviewed": 2,
        "urgent_count": 1,
        "high_priority_count": 1,
        "requires_response_count": 2,
        "categories": {"billing": 1, "support": 1},
        "suggested_focus": ["Handle 1 urgent email(s) first."],
        "top_action_items": [{"text": "Reply to James.", "owner": "me", "priority": "urgent"}],
        "important_emails": [make_card()],
        "safety_note": "Briefing generated from stored summary cards only.",
    }


def make_answer() -> dict[str, object]:
    return {
        "question": "Catch me up",
        "answer": "You have two emails to review.",
        "matched_count": 1,
        "matches": [make_card()],
        "answer_mode": "deterministic",
        "safety_note": "Answered from stored summary cards only.",
    }


def make_analysis() -> EmailAnalysis:
    return EmailAnalysis(
        summary="Alex asks about an invoice.",
        sender_intent="Requesting confirmation.",
        priority="high",
        category="billing",
        requires_response=True,
        action_items=[ActionItem(text="Confirm payment status.", owner="finance")],
        suggested_reply="Hi,\n\nI will check this.\n",
        safety_note="Draft only. No email was sent.",
    )


def make_action_item() -> dict[str, object]:
    return {
        "text": "Confirm payment status.",
        "owner": "finance",
        "due_date": "2026-06-05",
        "priority": "urgent",
        "message_id": "<1@example.com>",
        "sender": "alex@example.com",
        "subject": "Invoice question",
        "category": "billing",
        "requires_response": True,
        "fetched_at": "2026-06-04T10:00:00Z",
    }


def make_review() -> dict[str, object]:
    return {
        "fetched_count": 1,
        "saved_count": 1,
        "briefing": make_briefing(),
        "action_items": [make_action_item()],
        "urgent_emails": [make_card()],
        "high_priority_emails": [make_card()],
        "response_needed_emails": [make_card()],
        "safety_note": (
            "Review fetched unread emails read-only, saved local summary cards, and did not "
            "send, delete, archive, move, or mark any email as read."
        ),
    }


def test_fetch_command_calls_fetch_imap_and_prints_human_output(monkeypatch, capsys) -> None:
    fetch_mock = Mock(return_value=[make_card()])
    save_mock = Mock()
    init_mock = Mock()
    monkeypatch.setattr(email_assistant, "load_imap_settings", Mock(return_value=make_settings()))
    monkeypatch.setattr(email_assistant.fetch_imap, "fetch_inbox_summary_cards", fetch_mock)
    monkeypatch.setattr(email_assistant.storage, "init_db", init_mock)
    monkeypatch.setattr(email_assistant.storage, "save_summary_cards", save_mock)

    exit_code = email_assistant.main(["fetch", "--max-messages", "3", "--mailbox", "Archive", "--save"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Fetched 1 summary card(s)." in captured.out
    assert "Invoice question" in captured.out
    settings = fetch_mock.call_args.args[0]
    assert settings.max_messages == 3
    assert settings.mailbox == "Archive"
    init_mock.assert_called_once_with()
    save_mock.assert_called_once_with([make_card()])


def test_fetch_mailbox_override_is_passed(monkeypatch, capsys) -> None:
    fetch_mock = Mock(return_value=[])
    monkeypatch.setattr(email_assistant, "load_imap_settings", Mock(return_value=make_settings()))
    monkeypatch.setattr(email_assistant.fetch_imap, "fetch_inbox_summary_cards", fetch_mock)

    exit_code = email_assistant.main(["fetch", "--mailbox", "Junk"])
    capsys.readouterr()

    assert exit_code == 0
    assert fetch_mock.call_args.args[0].mailbox == "Junk"


def test_fetch_json_prints_valid_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(email_assistant, "load_imap_settings", Mock(return_value=make_settings()))
    monkeypatch.setattr(
        email_assistant.fetch_imap,
        "fetch_inbox_summary_cards",
        Mock(return_value=[make_card()]),
    )

    exit_code = email_assistant.main(["fetch", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert json.loads(captured.out)[0]["subject"] == "Invoice question"


def test_briefing_command_prints_human_output(monkeypatch, capsys) -> None:
    briefing_mock = Mock(return_value=make_briefing())
    monkeypatch.setattr(email_assistant.daily_briefing, "generate_daily_briefing", briefing_mock)

    exit_code = email_assistant.main(["briefing", "--limit", "10"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Daily Briefing" in captured.out
    assert "Total emails reviewed: 2" in captured.out
    briefing_mock.assert_called_once_with(limit=10)


def test_briefing_json_prints_valid_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        email_assistant.daily_briefing,
        "generate_daily_briefing",
        Mock(return_value=make_briefing()),
    )

    exit_code = email_assistant.main(["briefing", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert json.loads(captured.out)["urgent_count"] == 1


def test_ask_command_calls_inbox_qa(monkeypatch, capsys) -> None:
    answer_mock = Mock(return_value=make_answer())
    monkeypatch.setattr(email_assistant.inbox_qa, "answer_inbox_question", answer_mock)

    exit_code = email_assistant.main(["ask", "Catch me up", "--limit", "7"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "You have two emails to review." in captured.out
    answer_mock.assert_called_once_with("Catch me up", limit=7, use_ai=False)


def test_ask_ai_passes_use_ai_true(monkeypatch, capsys) -> None:
    answer = make_answer()
    answer["answer_mode"] = "ai"
    answer_mock = Mock(return_value=answer)
    monkeypatch.setattr(email_assistant.inbox_qa, "answer_inbox_question", answer_mock)

    exit_code = email_assistant.main(["ask", "What emails need my response?", "--ai"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Answer mode: ai" in captured.out
    answer_mock.assert_called_once_with(
        "What emails need my response?", limit=20, use_ai=True
    )


def test_ask_json_prints_valid_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        email_assistant.inbox_qa,
        "answer_inbox_question",
        Mock(return_value=make_answer()),
    )

    exit_code = email_assistant.main(["ask", "Catch me up", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert json.loads(captured.out)["answer"] == "You have two emails to review."


def test_list_command_filters_by_high_priority_and_requires_response(monkeypatch, capsys) -> None:
    list_mock = Mock(return_value=[make_card()])
    fetch_mock = Mock()
    settings_mock = Mock()
    monkeypatch.setattr(email_assistant.storage, "list_cards", list_mock)
    monkeypatch.setattr(email_assistant.fetch_imap, "fetch_inbox_summary_cards", fetch_mock)
    monkeypatch.setattr(email_assistant, "load_imap_settings", settings_mock)

    exit_code = email_assistant.main(["list", "--priority", "high", "--requires-response"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Stored summary cards: 1" in captured.out
    assert "Invoice question" in captured.out
    assert "Requires response: yes" in captured.out
    list_mock.assert_called_once_with(
        limit=20,
        priority="high",
        category=None,
        requires_response=True,
    )
    fetch_mock.assert_not_called()
    settings_mock.assert_not_called()


def test_list_command_filters_by_category(monkeypatch, capsys) -> None:
    list_mock = Mock(return_value=[make_card()])
    monkeypatch.setattr(email_assistant.storage, "list_cards", list_mock)

    exit_code = email_assistant.main(["list", "--category", "billing", "--limit", "7"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Category: billing" in captured.out
    list_mock.assert_called_once_with(
        limit=7,
        priority=None,
        category="billing",
        requires_response=None,
    )


def test_list_json_prints_valid_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(email_assistant.storage, "list_cards", Mock(return_value=[make_card()]))

    exit_code = email_assistant.main(["list", "--priority", "urgent", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    parsed = json.loads(captured.out)
    assert parsed[0]["subject"] == "Invoice question"
    email_assistant.storage.list_cards.assert_called_once_with(
        limit=20,
        priority="urgent",
        category=None,
        requires_response=None,
    )


def test_list_no_cards_found(monkeypatch, capsys) -> None:
    monkeypatch.setattr(email_assistant.storage, "list_cards", Mock(return_value=[]))

    exit_code = email_assistant.main(["list"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "No stored summary cards found." in captured.out
    assert "No email was fetched or modified." in captured.out


def test_actions_command_prints_human_readable_output(monkeypatch, capsys) -> None:
    list_mock = Mock(return_value=[make_action_item()])
    fetch_mock = Mock()
    analyze_mock = Mock()
    settings_mock = Mock()
    monkeypatch.setattr(email_assistant.storage, "list_action_items", list_mock)
    monkeypatch.setattr(email_assistant.fetch_imap, "fetch_inbox_summary_cards", fetch_mock)
    monkeypatch.setattr(email_assistant.analyzer, "analyze_email", analyze_mock)
    monkeypatch.setattr(email_assistant, "load_imap_settings", settings_mock)

    exit_code = email_assistant.main(
        ["actions", "--priority", "urgent", "--owner", "finance", "--limit", "10"]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Stored action items: 1" in captured.out
    assert "Confirm payment status." in captured.out
    assert "Owner: finance" in captured.out
    assert "Source: Invoice question" in captured.out
    list_mock.assert_called_once_with(limit=10, priority="urgent", owner="finance")
    fetch_mock.assert_not_called()
    analyze_mock.assert_not_called()
    settings_mock.assert_not_called()


def test_actions_json_prints_valid_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        email_assistant.storage,
        "list_action_items",
        Mock(return_value=[make_action_item()]),
    )

    exit_code = email_assistant.main(["actions", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    parsed = json.loads(captured.out)
    assert parsed[0]["text"] == "Confirm payment status."
    email_assistant.storage.list_action_items.assert_called_once_with(
        limit=50,
        priority=None,
        owner=None,
    )


def test_actions_no_items_found(monkeypatch, capsys) -> None:
    monkeypatch.setattr(email_assistant.storage, "list_action_items", Mock(return_value=[]))

    exit_code = email_assistant.main(["actions"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "No stored action items found." in captured.out
    assert "No email was fetched or modified." in captured.out


def test_review_command_prints_human_readable_output(monkeypatch, capsys) -> None:
    review_mock = Mock(return_value=make_review())
    monkeypatch.setattr(email_assistant.review, "run_inbox_review", review_mock)

    exit_code = email_assistant.main(["review"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Inbox Review" in captured.out
    assert "Fetched: 1" in captured.out
    assert "Action items: 1" in captured.out
    review_mock.assert_called_once_with(max_messages=10, mailbox="INBOX")


def test_review_json_prints_valid_json(monkeypatch, capsys) -> None:
    review_mock = Mock(return_value=make_review())
    monkeypatch.setattr(email_assistant.review, "run_inbox_review", review_mock)

    exit_code = email_assistant.main(["review", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    parsed = json.loads(captured.out)
    assert parsed["fetched_count"] == 1
    assert parsed["action_items"][0]["text"] == "Confirm payment status."


def test_review_options_are_passed(monkeypatch, capsys) -> None:
    review_mock = Mock(return_value=make_review())
    monkeypatch.setattr(email_assistant.review, "run_inbox_review", review_mock)

    exit_code = email_assistant.main(
        ["review", "--max-messages", "7", "--mailbox", "Projects"]
    )
    capsys.readouterr()

    assert exit_code == 0
    review_mock.assert_called_once_with(max_messages=7, mailbox="Projects")


def test_review_mailbox_override_is_passed(monkeypatch, capsys) -> None:
    review_mock = Mock(return_value=make_review())
    monkeypatch.setattr(email_assistant.review, "run_inbox_review", review_mock)

    exit_code = email_assistant.main(["review", "--mailbox", "Junk"])
    capsys.readouterr()

    assert exit_code == 0
    review_mock.assert_called_once_with(max_messages=10, mailbox="Junk")


def test_providers_command_prints_supported_providers(capsys) -> None:
    exit_code = email_assistant.main(["providers"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Supported IMAP Providers" in captured.out
    assert "iCloud Mail (icloud)" in captured.out
    assert "Gmail (gmail)" in captured.out
    assert "No email was fetched or modified." in captured.out


def test_providers_json_prints_valid_json(capsys) -> None:
    exit_code = email_assistant.main(["providers", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    parsed = json.loads(captured.out)
    assert parsed[0]["key"] == "icloud"
    assert parsed[1]["imap_host"] == "imap.gmail.com"


def test_mailboxes_command_prints_provider_presets(capsys) -> None:
    exit_code = email_assistant.main(["mailboxes", "--provider", "gmail"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Suggested mailboxes for gmail" in captured.out
    assert "[Gmail]/Spam" in captured.out
    assert "No email was fetched or modified." in captured.out


def test_mailboxes_json_prints_valid_json(capsys) -> None:
    exit_code = email_assistant.main(["mailboxes", "--provider", "outlook", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    parsed = json.loads(captured.out)
    assert parsed["provider"] == "outlook"
    assert "Junk Email" in parsed["mailboxes"]


def test_analyze_command_calls_analyzer(monkeypatch, capsys) -> None:
    analyze_mock = Mock(return_value=make_analysis())
    monkeypatch.setattr(email_assistant.analyzer, "analyze_email", analyze_mock)

    exit_code = email_assistant.main(
        [
            "analyze",
            "--from",
            "alex@example.com",
            "--subject",
            "Invoice question",
            "--body",
            "Can you confirm whether invoice 1042 has been paid?",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Email Analysis" in captured.out
    email = analyze_mock.call_args.args[0]
    assert isinstance(email, EmailMessage)
    assert email.sender == "alex@example.com"
    assert email.subject == "Invoice question"
    assert "invoice 1042" in email.body


def test_analyze_reads_body_from_stdin(monkeypatch, capsys) -> None:
    analyze_mock = Mock(return_value=make_analysis())
    monkeypatch.setattr(email_assistant.analyzer, "analyze_email", analyze_mock)
    monkeypatch.setattr(email_assistant.sys, "stdin", Mock(read=Mock(return_value="Body from stdin\n")))

    exit_code = email_assistant.main(
        ["analyze", "--from", "alex@example.com", "--subject", "Stdin subject", "--json"]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert json.loads(captured.out)["summary"] == "Alex asks about an invoice."
    email = analyze_mock.call_args.args[0]
    assert email.body == "Body from stdin"


@pytest.mark.parametrize(
    "exc",
    [
        ValueError("IMAP_PASSWORD is required and secret-password is invalid"),
        RuntimeError("IMAP authentication failed for secret-password"),
    ],
)
def test_error_handling_does_not_expose_secrets(monkeypatch, capsys, exc: Exception) -> None:
    monkeypatch.setattr(email_assistant, "load_imap_settings", Mock(side_effect=exc))

    exit_code = email_assistant.main(["fetch"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "Error:" in captured.err
    assert "secret-password" not in captured.err
    assert captured.out == ""
