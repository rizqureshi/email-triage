from unittest.mock import Mock

import review
from config import ImapSettings


def make_settings() -> ImapSettings:
    return ImapSettings(
        host="imap.example.com",
        port=993,
        username="user@example.com",
        password="secret-password",
        mailbox="INBOX",
        max_messages=5,
    )


def make_card(
    message_id: str = "<1@example.com>",
    subject: str = "Invoice question",
    priority: str = "high",
    requires_response: bool = True,
) -> dict[str, object]:
    return {
        "message_id": message_id,
        "sender": "alex@example.com",
        "subject": subject,
        "priority": priority,
        "category": "billing",
        "requires_response": requires_response,
        "summary": "Alex asks whether invoice 1042 has been paid.",
        "action_items": [
            {
                "text": "Confirm payment status.",
                "owner": "finance",
                "due_date": "2026-06-05",
                "priority": priority,
            }
        ],
    }


def make_action_item() -> dict[str, object]:
    return {
        "text": "Confirm payment status.",
        "owner": "finance",
        "due_date": "2026-06-05",
        "priority": "high",
        "subject": "Invoice question",
        "sender": "alex@example.com",
    }


def make_briefing() -> dict[str, object]:
    return {
        "total_emails_reviewed": 1,
        "urgent_count": 1,
        "high_priority_count": 1,
        "requires_response_count": 1,
        "suggested_focus": ["Handle 1 urgent email(s) first."],
        "top_action_items": [make_action_item()],
        "important_emails": [make_card()],
        "safety_note": "Briefing generated from stored summary cards only.",
    }


def test_run_inbox_review_fetches_saves_and_builds_report(monkeypatch) -> None:
    fetched_cards = [make_card()]
    urgent_cards = [make_card(priority="urgent", subject="Urgent issue")]
    high_cards = [make_card(priority="high")]
    response_cards = [make_card(requires_response=True)]
    action_items = [make_action_item()]
    fetch_mock = Mock(return_value=fetched_cards)
    save_mock = Mock()
    briefing_mock = Mock(return_value=make_briefing())
    actions_mock = Mock(return_value=action_items)

    def list_cards_side_effect(**kwargs):
        if kwargs.get("priority") == "urgent":
            return urgent_cards
        if kwargs.get("priority") == "high":
            return high_cards
        if kwargs.get("requires_response") is True:
            return response_cards
        return []

    list_cards_mock = Mock(side_effect=list_cards_side_effect)
    fetch_unread_mock = Mock()
    monkeypatch.setattr(review, "load_imap_settings", Mock(return_value=make_settings()))
    monkeypatch.setattr(review.fetch_imap, "fetch_inbox_summary_cards", fetch_mock)
    monkeypatch.setattr(review.fetch_imap, "fetch_unread_emails", fetch_unread_mock)
    monkeypatch.setattr(review.storage, "save_summary_cards", save_mock)
    monkeypatch.setattr(review.daily_briefing, "generate_daily_briefing", briefing_mock)
    monkeypatch.setattr(review.storage, "list_action_items", actions_mock)
    monkeypatch.setattr(review.storage, "list_cards", list_cards_mock)

    result = review.run_inbox_review(max_messages=12, mailbox="Projects")

    settings = fetch_mock.call_args.args[0]
    assert settings.max_messages == 12
    assert settings.mailbox == "Projects"
    save_mock.assert_called_once_with(fetched_cards)
    briefing_mock.assert_called_once_with()
    actions_mock.assert_called_once_with()
    assert result["fetched_count"] == 1
    assert result["saved_count"] == 1
    assert result["briefing"] == make_briefing()
    assert result["action_items"] == action_items
    assert result["urgent_emails"] == urgent_cards
    assert result["high_priority_emails"] == high_cards
    assert result["response_needed_emails"] == response_cards
    assert "did not send, delete, archive, move, or mark any email as read" in result["safety_note"]
    fetch_unread_mock.assert_not_called()
    assert list_cards_mock.call_args_list[0].kwargs == {"priority": "urgent"}
    assert list_cards_mock.call_args_list[1].kwargs == {"priority": "high"}
    assert list_cards_mock.call_args_list[2].kwargs == {"requires_response": True}


def test_run_inbox_review_defaults_blank_mailbox_to_inbox(monkeypatch) -> None:
    fetch_mock = Mock(return_value=[])
    monkeypatch.setattr(review, "load_imap_settings", Mock(return_value=make_settings()))
    monkeypatch.setattr(review.fetch_imap, "fetch_inbox_summary_cards", fetch_mock)
    monkeypatch.setattr(review.storage, "save_summary_cards", Mock())
    monkeypatch.setattr(review.daily_briefing, "generate_daily_briefing", Mock(return_value={}))
    monkeypatch.setattr(review.storage, "list_action_items", Mock(return_value=[]))
    monkeypatch.setattr(review.storage, "list_cards", Mock(return_value=[]))

    review.run_inbox_review(max_messages=10, mailbox=" ")

    settings = fetch_mock.call_args.args[0]
    assert settings.mailbox == "INBOX"


def test_format_inbox_review_includes_counts_and_sections() -> None:
    report = review.format_inbox_review(
        {
            "fetched_count": 1,
            "saved_count": 1,
            "briefing": make_briefing(),
            "action_items": [make_action_item()],
            "urgent_emails": [make_card(priority="urgent")],
            "high_priority_emails": [make_card(priority="high")],
            "response_needed_emails": [make_card(requires_response=True)],
            "safety_note": review.SAFETY_NOTE,
        }
    )

    assert "Inbox Review" in report
    assert "Fetched: 1" in report
    assert "Urgent: 1" in report
    assert "High priority: 1" in report
    assert "Need response: 1" in report
    assert "Action items: 1" in report
    assert "Suggested Focus:" in report
    assert "Top Action Items:" in report
    assert "Important Emails:" in report
    assert review.SAFETY_NOTE in report
