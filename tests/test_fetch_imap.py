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


def make_provider_settings(provider_key: str) -> ImapSettings:
    return ImapSettings(
        host="imap.example.com",
        port=993,
        username="user@example.com",
        password="secret",
        mailbox="INBOX",
        max_messages=2,
        provider_key=provider_key,
    )


def test_load_imap_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EMAIL_PROVIDER", raising=False)
    monkeypatch.setenv("IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("IMAP_USERNAME", "user@example.com")
    monkeypatch.setenv("IMAP_PASSWORD", "secret")
    monkeypatch.delenv("IMAP_PORT", raising=False)
    monkeypatch.delenv("IMAP_MAILBOX", raising=False)
    monkeypatch.delenv("IMAP_MAX_MESSAGES", raising=False)
    monkeypatch.delenv("IMAP_SEARCH_MODE", raising=False)

    settings = load_imap_settings()

    assert settings.port == 993
    assert settings.mailbox == "INBOX"
    assert settings.max_messages == 5
    assert settings.search_mode == "unread"
    assert settings.provider_key == "icloud"


def test_load_imap_settings_uses_provider_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_PROVIDER", "gmail")
    monkeypatch.delenv("IMAP_HOST", raising=False)
    monkeypatch.delenv("IMAP_PORT", raising=False)
    monkeypatch.delenv("IMAP_MAILBOX", raising=False)
    monkeypatch.setenv("IMAP_USERNAME", "user@gmail.com")
    monkeypatch.setenv("IMAP_PASSWORD", "secret")

    settings = load_imap_settings()

    assert settings.provider_key == "gmail"
    assert settings.provider_display_name == "Gmail"
    assert settings.host == "imap.gmail.com"
    assert settings.port == 993
    assert settings.mailbox == "INBOX"


def test_load_imap_settings_uses_recent_search_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_PROVIDER", "gmail")
    monkeypatch.setenv("IMAP_USERNAME", "user@gmail.com")
    monkeypatch.setenv("IMAP_PASSWORD", "secret")
    monkeypatch.setenv("IMAP_SEARCH_MODE", "recent")

    settings = load_imap_settings()

    assert settings.search_mode == "recent"


def test_load_imap_settings_rejects_invalid_search_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("IMAP_USERNAME", "user@example.com")
    monkeypatch.setenv("IMAP_PASSWORD", "secret")
    monkeypatch.setenv("IMAP_SEARCH_MODE", "everything")

    with pytest.raises(ValueError, match="IMAP_SEARCH_MODE must be one of: unread, recent"):
        load_imap_settings()


def test_explicit_imap_host_overrides_provider_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_PROVIDER", "gmail")
    monkeypatch.setenv("IMAP_HOST", "imap.override.example.com")
    monkeypatch.setenv("IMAP_USERNAME", "user@gmail.com")
    monkeypatch.setenv("IMAP_PASSWORD", "secret")

    settings = load_imap_settings()

    assert settings.provider_key == "gmail"
    assert settings.host == "imap.override.example.com"


def test_custom_provider_requires_imap_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_PROVIDER", "custom")
    monkeypatch.delenv("IMAP_HOST", raising=False)
    monkeypatch.setenv("IMAP_USERNAME", "user@example.com")
    monkeypatch.setenv("IMAP_PASSWORD", "secret")

    with pytest.raises(ValueError, match="IMAP_HOST is required for EMAIL_PROVIDER=custom"):
        load_imap_settings()


def test_unknown_provider_fails_with_valid_choices(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_PROVIDER", "fastmail")
    monkeypatch.setenv("IMAP_USERNAME", "user@example.com")
    monkeypatch.setenv("IMAP_PASSWORD", "secret")

    with pytest.raises(ValueError, match="Unknown EMAIL_PROVIDER 'fastmail'"):
        load_imap_settings()


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
    monkeypatch.delenv("IMAP_USERNAME", raising=False)
    monkeypatch.setenv("IMAP_PASSWORD", "secret")

    with pytest.raises(ValueError, match="IMAP_USERNAME is required"):
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


@pytest.mark.parametrize(
    ("mailbox", "expected"),
    [
        ("INBOX", "INBOX"),
        ("Junk", "Junk"),
        ("Sent Messages", '"Sent Messages"'),
        ("[Gmail]/Sent Mail", '"[Gmail]/Sent Mail"'),
        ('"Sent Messages"', '"Sent Messages"'),
        ('Folder "A"', '"Folder \\"A\\""'),
        ("", "INBOX"),
        ("  Sent Messages  ", '"Sent Messages"'),
    ],
)
def test_quote_mailbox_name(mailbox: str, expected: str) -> None:
    assert fetch_imap._quote_mailbox_name(mailbox) == expected


@pytest.mark.parametrize(
    ("search_data", "expected"),
    [
        ([], []),
        ([None], []),
        ([b""], []),
        ([b" "], []),
        ([b"1 2 3"], [b"2", b"3"]),
        (["1 2 3"], [b"2", b"3"]),
        ([object()], []),
    ],
)
def test_recent_message_ids_handles_empty_and_malformed_search_results(
    search_data: list[object], expected: list[bytes]
) -> None:
    assert fetch_imap._recent_message_ids(search_data, 2) == expected


@pytest.mark.parametrize(
    ("search_mode", "expected"),
    [("unread", "UNSEEN"), ("recent", "ALL"), ("unknown", "UNSEEN")],
)
def test_search_criteria_for_mode(search_mode: str, expected: str) -> None:
    assert fetch_imap._search_criteria_for_mode(search_mode) == expected


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


def test_fetch_unread_emails_recent_mode_uses_all_and_recent_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Mock()
    client.login.return_value = ("OK", [b"Logged in"])
    client.select.return_value = ("OK", [b"4"])
    client.search.return_value = ("OK", [b"1 2 3 4"])
    client.fetch.side_effect = [
        ("OK", [(b"3 (BODY[] {42}", make_raw_email(subject="Third", message_id="<3@example.com>"))]),
        ("OK", [(b"4 (BODY[] {42}", make_raw_email(subject="Fourth", message_id="<4@example.com>"))]),
    ]
    monkeypatch.setattr(fetch_imap.imaplib, "IMAP4_SSL", Mock(return_value=client))
    monkeypatch.setattr(fetch_imap.ssl, "create_default_context", Mock(return_value=object()))
    settings = make_settings()
    settings = ImapSettings(
        host=settings.host,
        port=settings.port,
        username=settings.username,
        password=settings.password,
        mailbox=settings.mailbox,
        max_messages=2,
        search_mode="recent",
    )

    emails = fetch_imap.fetch_unread_emails(settings)

    client.search.assert_called_once_with(None, "ALL")
    assert client.fetch.call_args_list[0].args == (b"3", "(BODY.PEEK[])")
    assert client.fetch.call_args_list[1].args == (b"4", "(BODY.PEEK[])")
    client.store.assert_not_called()
    client.copy.assert_not_called()
    client.logout.assert_called_once()
    assert [email.subject for _, email in emails] == ["Third", "Fourth"]


def test_fetch_unread_emails_quotes_mailbox_names_with_spaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Mock()
    client.login.return_value = ("OK", [b"Logged in"])
    client.select.return_value = ("OK", [b"0"])
    client.search.return_value = ("OK", [b""])
    monkeypatch.setattr(fetch_imap.imaplib, "IMAP4_SSL", Mock(return_value=client))
    monkeypatch.setattr(fetch_imap.ssl, "create_default_context", Mock(return_value=object()))
    settings = make_settings()
    settings = ImapSettings(
        host=settings.host,
        port=settings.port,
        username=settings.username,
        password=settings.password,
        mailbox="Sent Messages",
        max_messages=settings.max_messages,
    )

    emails = fetch_imap.fetch_unread_emails(settings)

    assert emails == []
    client.select.assert_called_once_with('"Sent Messages"', readonly=True)
    client.search.assert_called_once_with(None, "UNSEEN")
    client.fetch.assert_not_called()
    client.store.assert_not_called()
    client.copy.assert_not_called()
    client.logout.assert_called_once()


@pytest.mark.parametrize("search_data", [[None], [b""]])
def test_fetch_unread_emails_empty_search_results_do_not_fetch(
    monkeypatch: pytest.MonkeyPatch, search_data: list[object]
) -> None:
    client = Mock()
    client.login.return_value = ("OK", [b"Logged in"])
    client.select.return_value = ("OK", [b"0"])
    client.search.return_value = ("OK", search_data)
    monkeypatch.setattr(fetch_imap.imaplib, "IMAP4_SSL", Mock(return_value=client))
    monkeypatch.setattr(fetch_imap.ssl, "create_default_context", Mock(return_value=object()))

    emails = fetch_imap.fetch_unread_emails(make_settings())

    assert emails == []
    client.fetch.assert_not_called()
    client.store.assert_not_called()
    client.copy.assert_not_called()
    client.logout.assert_called_once()


def test_fetch_unread_emails_invalid_mailbox_error_includes_mailbox_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Mock()
    client.login.return_value = ("OK", [b"Logged in"])
    client.select.return_value = ("NO", [b"No such mailbox"])
    monkeypatch.setattr(fetch_imap.imaplib, "IMAP4_SSL", Mock(return_value=client))
    monkeypatch.setattr(fetch_imap.ssl, "create_default_context", Mock(return_value=object()))
    settings = make_settings()
    settings = ImapSettings(
        host=settings.host,
        port=settings.port,
        username=settings.username,
        password=settings.password,
        mailbox="Junk",
        max_messages=settings.max_messages,
    )

    with pytest.raises(RuntimeError, match="Could not select mailbox 'Junk'"):
        fetch_imap.fetch_unread_emails(settings)

    client.select.assert_called_once_with("Junk", readonly=True)
    client.search.assert_not_called()
    client.fetch.assert_not_called()
    client.logout.assert_called_once()


def test_fetch_unread_emails_select_parse_error_is_friendly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Mock()
    client.login.return_value = ("OK", [b"Logged in"])
    client.select.side_effect = fetch_imap.imaplib.IMAP4.error("BAD [b'Parse Error']")
    monkeypatch.setattr(fetch_imap.imaplib, "IMAP4_SSL", Mock(return_value=client))
    monkeypatch.setattr(fetch_imap.ssl, "create_default_context", Mock(return_value=object()))
    settings = make_settings()
    settings = ImapSettings(
        host=settings.host,
        port=settings.port,
        username=settings.username,
        password=settings.password,
        mailbox="Sent Messages",
        max_messages=settings.max_messages,
    )

    with pytest.raises(RuntimeError) as exc_info:
        fetch_imap.fetch_unread_emails(settings)

    message = str(exc_info.value)
    assert "Could not select mailbox 'Sent Messages'" in message
    assert "Folder names vary by provider" in message
    assert "BAD [b'Parse Error']" in message
    assert "secret" not in message
    client.select.assert_called_once_with('"Sent Messages"', readonly=True)
    client.search.assert_not_called()
    client.fetch.assert_not_called()
    client.store.assert_not_called()
    client.copy.assert_not_called()
    client.logout.assert_called_once()


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


def test_fetch_unread_emails_authentication_failure_uses_provider_guidance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Mock()
    client.login.side_effect = fetch_imap.imaplib.IMAP4.error("AUTH failed")
    monkeypatch.setattr(fetch_imap.imaplib, "IMAP4_SSL", Mock(return_value=client))
    monkeypatch.setattr(fetch_imap.ssl, "create_default_context", Mock(return_value=object()))

    with pytest.raises(RuntimeError, match="IMAP authentication failed for Gmail"):
        fetch_imap.fetch_unread_emails(make_provider_settings("gmail"))

    client.select.assert_not_called()
    client.search.assert_not_called()
    client.fetch.assert_not_called()
    client.store.assert_not_called()
    client.copy.assert_not_called()
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
