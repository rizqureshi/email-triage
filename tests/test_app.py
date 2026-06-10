import csv
import io

import app


def test_action_items_to_csv() -> None:
    csv_text = app.action_items_to_csv(
        [
            {
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
        ]
    )

    rows = list(csv.DictReader(io.StringIO(csv_text)))

    assert rows == [
        {
            "text": "Confirm payment status.",
            "owner": "finance",
            "due_date": "2026-06-05",
            "priority": "urgent",
            "message_id": "<1@example.com>",
            "sender": "alex@example.com",
            "subject": "Invoice question",
            "category": "billing",
            "requires_response": "True",
            "fetched_at": "2026-06-04T10:00:00Z",
        }
    ]


def test_safe_error_message_does_not_expose_imap_password(monkeypatch) -> None:
    monkeypatch.setenv("IMAP_PASSWORD", "secret-password")

    message = app._safe_error_message(RuntimeError("bad secret-password"))

    assert "secret-password" not in message
    assert "[secret]" in message


def test_safe_error_message_returns_provider_specific_auth_guidance(monkeypatch) -> None:
    monkeypatch.setenv("EMAIL_PROVIDER", "gmail")
    monkeypatch.delenv("IMAP_HOST", raising=False)
    monkeypatch.setenv("IMAP_USERNAME", "user@gmail.com")
    monkeypatch.setenv("IMAP_PASSWORD", "secret-password")

    message = app._safe_error_message(RuntimeError("IMAP authentication failed: bad secret-password"))

    assert "IMAP authentication failed for Gmail" in message
    assert "secret-password" not in message


def test_safe_error_message_auth_fallback_is_generic(monkeypatch) -> None:
    monkeypatch.setattr(app, "load_imap_settings", lambda: (_ for _ in ()).throw(ValueError("bad")))

    message = app._safe_error_message(RuntimeError("IMAP authentication failed"))

    assert message == (
        "IMAP authentication failed. Check your email provider's IMAP settings and credentials."
    )
