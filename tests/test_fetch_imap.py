from email import policy
from email.message import EmailMessage as StdlibEmailMessage
from email.parser import BytesParser
from unittest.mock import Mock

import pytest

import fetch_imap
from config import ImapSettings, load_imap_settings
from schemas import ActionItem, EmailAnalysis
from triage import EmailMessage


def make_raw_email(
    sender: str = "alex@example.com",
    subject: str = "Invoice question",
    body: str = "Can you confirm whether invoice 1042 has been paid?",
    message_id: str = "<message-1@example.com>",
) -> bytes:
    message = StdlibEmailMessage()
    message["From"] = sender
    message["Subject"] = subject
    message["Message-ID"] = message_id
    message.set_content(body)
    return message.as_bytes()


def make_settings() -> ImapSettings:
    return ImapSettings(
        host="imap.example.com",
        port=993,
        username="user@example.com",
        password="secret",
        mailbox="INBOX",
        max_messages=2,
    )


def test_load_imap_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("IMAP_USERNAME", "user@example.com")
    monkeypatch.setenv("IMAP_PASSWORD", "secret")
    monkeypatch.delenv("IMAP_PORT", raising=False)
    monkeypatch.delenv("IMAP_MAILBOX", raising=False)
    monkeypatch.delenv("IMAP_MAX_MESSAGES", raising=False)

    settings = load_imap_settings()

    assert settings.port == 993
    assert settings.mailbox == "INBOX"
    assert settings.max_messages == 5


@pytest.mark.parametrize("value", ["0", "65536", "not-a-number"])
def test_load_imap_settings_invalid_port(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("IMAP_USERNAME", "user@example.com")
    monkeypatch.setenv("IMAP_PASSWORD", "secret")
    monkeypatch.setenv("IMAP_PORT", value)

    with pytest.raises(ValueError, match="IMAP_PORT"):
        load_imap_settings()


@pytest.mark.parametrize("value", ["0", "51", "not-a-number"])
def test_load_imap_settings_invalid_max_messages(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("IMAP_USERNAME", "user@example.com")
    monkeypatch.setenv("IMAP_PASSWORD", "secret")
    monkeypatch.setenv("IMAP_MAX_MESSAGES", value)

    with pytest.raises(ValueError, match="IMAP_MAX_MESSAGES"):
        load_imap_settings()


def test_load_imap_settings_requires_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IMAP_HOST", raising=False)
    monkeypatch.setenv("IMAP_USERNAME", "user@example.com")
    monkeypatch.setenv("IMAP_PASSWORD", "secret")

    with pytest.raises(ValueError, match="IMAP_HOST is required"):
        load_imap_settings()


def test_extract_body_prefers_text_plain() -> None:
    message = BytesParser(policy=policy.default).parsebytes(make_raw_email())

    assert fetch_imap._extract_body(message) == (
        "Can you confirm whether invoice 1042 has been paid?"
    )


def test_extract_body_ignores_attachments() -> None:
    message = StdlibEmailMessage()
    message["From"] = "alex@example.com"
    message["Subject"] = "Report"
    message.set_content("Please see the notes below.")
    message.add_attachment(
        b"secret attachment text",
        maintype="application",
        subtype="octet-stream",
        filename="report.bin",
    )

    parsed = BytesParser(policy=policy.default).parsebytes(message.as_bytes())

    body = fetch_imap._extract_body(parsed)

    assert body == "Please see the notes below."
    assert "secret attachment text" not in body


def test_html_fallback_produces_readable_text() -> None:
    message = StdlibEmailMessage()
    message["From"] = "alex@example.com"
    message["Subject"] = "HTML only"
    message.set_content("<html><body><p>Hello <strong>world</strong></p></body></html>", subtype="html")

    parsed = BytesParser(policy=policy.default).parsebytes(message.as_bytes())

    body = fetch_imap._extract_body(parsed)

    assert "Hello" in body
    assert "world" in body
    assert "<strong>" not in body


def test_summary_card_conversion_from_email_analysis() -> None:
    email = EmailMessage(
        sender="alex@example.com",
        subject="Invoice question",
        body="Can you confirm whether invoice 1042 has been paid?",
    )
    analysis = EmailAnalysis(
        summary="A billing follow-up is needed.",
        sender_intent="Requesting confirmation.",
        priority="high",
        category="billing",
        requires_response=True,
        action_items=[ActionItem(text="Confirm payment status.", owner="finance")],
        suggested_reply="Thanks for the note.",
        safety_note="Draft only. No email was sent.",
    )

    card = fetch_imap._summary_card("<message-1@example.com>", email, analysis)

    assert card == {
        "message_id": "<message-1@example.com>",
        "sender": "alex@example.com",
        "subject": "Invoice question",
        "summary": "A billing follow-up is needed.",
        "sender_intent": "Requesting confirmation.",
        "priority": "high",
        "category": "billing",
        "requires_response": True,
        "action_items": [
            {
                "text": "Confirm payment status.",
                "owner": "finance",
                "due_date": None,
                "priority": "normal",
            }
        ],
        "suggested_reply": "Thanks for the note.",
        "safety_note": "Draft only. No email was sent.",
    }


def test_fetch_unread_emails_uses_readonly_peek_and_recent_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ssl_context = object()
    client = Mock()
    client.login.return_value = ("OK", [b"Logged in"])
    client.select.return_value = ("OK", [b"3"])
    client.search.return_value = ("OK", [b"1 2 3"])
    client.fetch.side_effect = [
        ("OK", [(b"2 (BODY[] {42}", make_raw_email(subject="Second", message_id="<2@example.com>"))]),
        ("OK", [(b"3 (BODY[] {42}", make_raw_email(subject="Third", message_id="<3@example.com>"))]),
    ]
    monkeypatch.setattr(fetch_imap.imaplib, "IMAP4_SSL", Mock(return_value=client))
    monkeypatch.setattr(fetch_imap.ssl, "create_default_context", Mock(return_value=ssl_context))

    emails = fetch_imap.fetch_unread_emails(make_settings())

    fetch_imap.imaplib.IMAP4_SSL.assert_called_once_with(
        "imap.example.com", 993, ssl_context=ssl_context
    )
    client.login.assert_called_once_with("user@example.com", "secret")
    client.select.assert_called_once_with("INBOX", readonly=True)
    client.search.assert_called_once_with(None, "UNSEEN")
    assert client.fetch.call_args_list[0].args == (b"2", "(BODY.PEEK[])")
    assert client.fetch.call_args_list[1].args == (b"3", "(BODY.PEEK[])")
    assert client.store.call_count == 0
    assert client.copy.call_count == 0
    assert client.logout.call_count == 1
    assert [message_id for message_id, _ in emails] == [
        "<2@example.com>",
        "<3@example.com>",
    ]
    assert [email.subject for _, email in emails] == ["Second", "Third"]


def test_fetch_unread_emails_authentication_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Mock()
    client.login.side_effect = fetch_imap.imaplib.IMAP4.error("AUTH failed")
    monkeypatch.setattr(fetch_imap.imaplib, "IMAP4_SSL", Mock(return_value=client))
    monkeypatch.setattr(fetch_imap.ssl, "create_default_context", Mock(return_value=object()))

    with pytest.raises(RuntimeError, match="IMAP authentication failed"):
        fetch_imap.fetch_unread_emails(make_settings())

    client.select.assert_not_called()
    client.search.assert_not_called()
    client.logout.assert_called_once()


def test_fetch_inbox_summary_cards_printable_results(monkeypatch: pytest.MonkeyPatch) -> None:
    email = EmailMessage(
        sender="alex@example.com",
        subject="Urgent help",
        body="Please handle this immediately.",
    )
    analysis = EmailAnalysis(
        summary="Needs attention.",
        sender_intent="Requesting help.",
        priority="urgent",
        category="support",
        requires_response=True,
        action_items=[ActionItem(text="Reply to sender.", owner="me")],
        suggested_reply="Hi,\n\nI will review this.\n",
        safety_note="Draft only. No email was sent.",
    )

    monkeypatch.setattr(
        fetch_imap, "fetch_unread_emails", Mock(return_value=[("<message-1@example.com>", email)])
    )
    monkeypatch.setattr(fetch_imap, "analyze_email", Mock(return_value=analysis))

    results = fetch_imap.fetch_inbox_summary_cards(make_settings())

    assert results == [
        {
            "message_id": "<message-1@example.com>",
            "sender": "alex@example.com",
            "subject": "Urgent help",
            "summary": "Needs attention.",
            "sender_intent": "Requesting help.",
            "priority": "urgent",
            "category": "support",
            "requires_response": True,
            "action_items": [
                {
                    "text": "Reply to sender.",
                    "owner": "me",
                    "due_date": None,
                    "priority": "normal",
                }
            ],
            "suggested_reply": "Hi,\n\nI will review this.\n",
            "safety_note": "Draft only. No email was sent.",
        }
    ]
