from email.message import EmailMessage as StdlibEmailMessage
from unittest.mock import Mock

import pytest

import fetch_imap
from fetch_imap import ImapSettings, fetch_unread_emails, load_imap_settings
from triage import TriageResult


def make_raw_email(
    sender: str = "alex@example.com",
    subject: str = "Invoice question",
    body: str = "Can you confirm whether invoice 1042 has been paid?",
) -> bytes:
    message = StdlibEmailMessage()
    message["From"] = sender
    message["Subject"] = subject
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


def test_load_imap_settings_requires_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IMAP_HOST", raising=False)
    monkeypatch.setenv("IMAP_USERNAME", "user@example.com")
    monkeypatch.setenv("IMAP_PASSWORD", "secret")

    with pytest.raises(ValueError, match="IMAP_HOST is required"):
        load_imap_settings()


def test_fetch_unread_emails_uses_readonly_peek_and_recent_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Mock()
    client.login.return_value = ("OK", [b"Logged in"])
    client.select.return_value = ("OK", [b"3"])
    client.search.return_value = ("OK", [b"1 2 3"])
    client.fetch.side_effect = [
        ("OK", [(b"2 (BODY[] {42}", make_raw_email(subject="Second"))]),
        ("OK", [(b"3 (BODY[] {42}", make_raw_email(subject="Third"))]),
    ]
    monkeypatch.setattr(fetch_imap.imaplib, "IMAP4_SSL", Mock(return_value=client))

    emails = fetch_unread_emails(make_settings())

    fetch_imap.imaplib.IMAP4_SSL.assert_called_once_with("imap.example.com", 993)
    client.login.assert_called_once_with("user@example.com", "secret")
    client.select.assert_called_once_with("INBOX", readonly=True)
    client.search.assert_called_once_with(None, "UNSEEN")
    assert client.fetch.call_args_list[0].args == (b"2", "(BODY.PEEK[])")
    assert client.fetch.call_args_list[1].args == (b"3", "(BODY.PEEK[])")
    assert client.store.call_count == 0
    assert client.copy.call_count == 0
    assert client.logout.call_count == 1
    assert [email.subject for email in emails] == ["Second", "Third"]


def test_triage_unread_emails_printable_results(monkeypatch: pytest.MonkeyPatch) -> None:
    email = fetch_imap.EmailMessage(
        sender="alex@example.com",
        subject="Urgent help",
        body="Please handle this immediately.",
    )
    triage_result = TriageResult(
        priority="urgent",
        category="support",
        summary="Needs attention.",
        action_required=True,
        reply_draft="Hi,\n\nI will review this.\n",
        safety_note="Draft only. No email was sent.",
    )
    monkeypatch.setattr(fetch_imap, "fetch_unread_emails", Mock(return_value=[email]))
    monkeypatch.setattr(fetch_imap, "triage_email", Mock(return_value=triage_result))

    results = fetch_imap.triage_unread_emails(make_settings())

    assert results == [
        {
            "email": {
                "sender": "alex@example.com",
                "subject": "Urgent help",
                "body": "Please handle this immediately.",
            },
            "triage": {
                "priority": "urgent",
                "category": "support",
                "summary": "Needs attention.",
                "action_required": True,
                "reply_draft": "Hi,\n\nI will review this.\n",
                "safety_note": "Draft only. No email was sent.",
            },
        }
    ]
