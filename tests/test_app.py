import csv
import io
from contextlib import contextmanager
from unittest.mock import Mock

import app
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


def test_busy_key_returns_expected_key() -> None:
    assert app._busy_key("fetch") == "busy_fetch"


def test_busy_state_defaults_false_and_can_be_set(monkeypatch) -> None:
    state: dict[str, object] = {}
    monkeypatch.setattr(app, "_session_state", lambda: state)

    assert app._is_busy("fetch") is False

    app._set_busy("fetch", True)

    assert app._is_busy("fetch") is True
    assert state == {"busy_fetch": True}


def test_request_action_sets_busy_and_pending(monkeypatch) -> None:
    state: dict[str, object] = {}
    monkeypatch.setattr(app, "_session_state", lambda: state)

    app._request_action("fetch")

    assert state["busy_fetch"] is True
    assert state["pending_fetch"] is True
    assert app._is_busy("fetch") is True
    assert app._has_pending_action("fetch") is True


def test_request_action_while_busy_does_not_clear_pending(monkeypatch) -> None:
    state: dict[str, object] = {
        "busy_fetch": True,
        "pending_fetch": True,
        "result_fetch": ["existing"],
    }
    monkeypatch.setattr(app, "_session_state", lambda: state)

    app._request_action("fetch")

    assert state["busy_fetch"] is True
    assert state["pending_fetch"] is True
    assert state["result_fetch"] == ["existing"]


def test_request_validated_action_stores_error_without_busy(monkeypatch) -> None:
    state: dict[str, object] = {}
    monkeypatch.setattr(app, "_session_state", lambda: state)

    app._request_validated_action("ask", "Enter a question first.")

    assert state == {"error_ask": "Enter a question first."}


def test_execute_pending_action_stores_result_and_clears_state(monkeypatch) -> None:
    state: dict[str, object] = {"busy_fetch": True, "pending_fetch": True}
    callback = Mock(return_value=["card"])
    rerun = Mock()
    monkeypatch.setattr(app, "_session_state", lambda: state)
    monkeypatch.setattr(app.st, "spinner", _fake_spinner)
    monkeypatch.setattr(app.st, "rerun", rerun)

    app._execute_pending_action("fetch", "Fetching...", callback)

    callback.assert_called_once_with()
    assert state["result_fetch"] == ["card"]
    assert state["pending_fetch"] is False
    assert state["busy_fetch"] is False
    rerun.assert_called_once_with()


def test_execute_pending_action_stores_safe_error_and_clears_state(monkeypatch) -> None:
    state: dict[str, object] = {"busy_fetch": True, "pending_fetch": True}
    callback = Mock(side_effect=RuntimeError("bad secret-password"))
    rerun = Mock()
    monkeypatch.setenv("IMAP_PASSWORD", "secret-password")
    monkeypatch.setattr(app, "_session_state", lambda: state)
    monkeypatch.setattr(app.st, "spinner", _fake_spinner)
    monkeypatch.setattr(app.st, "rerun", rerun)

    app._execute_pending_action("fetch", "Fetching...", callback)

    callback.assert_called_once_with()
    assert "secret-password" not in str(state["error_fetch"])
    assert "[secret]" in str(state["error_fetch"])
    assert state["pending_fetch"] is False
    assert state["busy_fetch"] is False
    rerun.assert_called_once_with()


def test_execute_pending_action_does_not_run_without_pending(monkeypatch) -> None:
    state: dict[str, object] = {"busy_fetch": True, "pending_fetch": False}
    callback = Mock()
    monkeypatch.setattr(app, "_session_state", lambda: state)
    monkeypatch.setattr(app.st, "spinner", _fake_spinner)

    app._execute_pending_action("fetch", "Fetching...", callback)

    callback.assert_not_called()
    assert state["busy_fetch"] is True


def test_effective_mailbox_uses_selected_preset_when_custom_is_empty() -> None:
    assert app._effective_mailbox("[Gmail]/Spam", " ") == "[Gmail]/Spam"


def test_effective_mailbox_custom_override_wins() -> None:
    assert app._effective_mailbox("INBOX", "  Exact Folder  ") == "Exact Folder"


def test_selected_provider_key_uses_env_when_settings_cannot_load(monkeypatch) -> None:
    load_mock = Mock(side_effect=ValueError("missing credentials"))
    monkeypatch.setenv("EMAIL_PROVIDER", "gmail")
    monkeypatch.setattr(app, "load_imap_settings", load_mock)

    assert app._selected_provider_key() == "gmail"
    load_mock.assert_called_once_with()


def test_mailbox_inputs_do_not_connect_to_imap(monkeypatch) -> None:
    selectbox = Mock(return_value="[Gmail]/Spam")
    text_input = Mock(return_value="")
    monkeypatch.setattr(app.st, "selectbox", selectbox)
    monkeypatch.setattr(app.st, "text_input", text_input)
    monkeypatch.setattr(app.st, "caption", Mock())

    selected, custom = app._mailbox_inputs("fetch", "gmail")

    assert selected == "[Gmail]/Spam"
    assert custom == ""
    selectbox.assert_called_once()
    text_input.assert_called_once()


def test_search_mode_value_maps_unread_label() -> None:
    assert app._search_mode_value("Unread only") == "unread"


def test_search_mode_value_maps_recent_label() -> None:
    assert app._search_mode_value("Recent messages") == "recent"


def test_search_mode_input_returns_recent_value(monkeypatch) -> None:
    selectbox = Mock(return_value="Recent messages")
    monkeypatch.setattr(app.st, "selectbox", selectbox)

    assert app._search_mode_input("fetch") == "recent"
    selectbox.assert_called_once()


def test_fetch_email_cards_passes_search_mode_to_settings(monkeypatch) -> None:
    fetch_mock = Mock(return_value=[])
    save_mock = Mock()
    monkeypatch.setattr(app, "load_imap_settings", Mock(return_value=make_settings()))
    monkeypatch.setattr(app.fetch_imap, "fetch_inbox_summary_cards", fetch_mock)
    monkeypatch.setattr(app.storage, "save_summary_cards", save_mock)

    result = app._fetch_email_cards(7, "Sent Messages", "recent", save_cards=True)

    settings = fetch_mock.call_args.args[0]
    assert settings.max_messages == 7
    assert settings.mailbox == "Sent Messages"
    assert settings.search_mode == "recent"
    assert result == {"cards": [], "search_mode": "recent"}
    save_mock.assert_called_once_with([])


def test_run_inbox_review_passes_search_mode(monkeypatch) -> None:
    review_mock = Mock(return_value={"search_mode": "recent"})
    monkeypatch.setattr(app.review, "run_inbox_review", review_mock)

    result = app._run_inbox_review(10, "Sent Messages", "recent")

    assert result == {"search_mode": "recent"}
    review_mock.assert_called_once_with(
        max_messages=10,
        mailbox="Sent Messages",
        search_mode="recent",
    )


@contextmanager
def _fake_spinner(message: str):
    yield
