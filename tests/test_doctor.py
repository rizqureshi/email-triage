import imaplib
import json
import sqlite3
from pathlib import Path
from unittest.mock import Mock

import pytest

import doctor
import email_providers
import email_assistant
import storage


class FakeImapClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def login(self, username: str, password: str) -> tuple[str, list[bytes]]:
        self.calls.append(("login", username, password))
        return ("OK", [b"logged in"])

    def logout(self) -> tuple[str, list[bytes]]:
        self.calls.append(("logout",))
        return ("OK", [b"logged out"])

    def select(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("doctor must not select a mailbox")

    def search(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("doctor must not search email")

    def fetch(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("doctor must not fetch email")

    def store(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("doctor must not modify flags")

    def copy(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("doctor must not copy email")

    def delete(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("doctor must not delete email")


def set_minimal_imap_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMAP_HOST", "imap.mail.me.com")
    monkeypatch.setenv("IMAP_PORT", "993")
    monkeypatch.setenv("IMAP_USERNAME", "user@example.com")
    monkeypatch.setenv("IMAP_PASSWORD", "secret-password")
    monkeypatch.setenv("IMAP_MAILBOX", "INBOX")
    monkeypatch.setenv("IMAP_MAX_MESSAGES", "5")


def clear_app_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in [
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "EMAIL_PROVIDER",
        "IMAP_HOST",
        "IMAP_PORT",
        "IMAP_USERNAME",
        "IMAP_PASSWORD",
        "IMAP_MAILBOX",
        "IMAP_MAX_MESSAGES",
        "EMAIL_TRIAGE_DB_PATH",
    ]:
        monkeypatch.delenv(name, raising=False)


def test_doctor_output_when_env_exists(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    clear_app_env(monkeypatch)
    set_minimal_imap_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("IMAP_PASSWORD=secret-password\n")

    report = doctor.run_doctor(skip_imap_login=True)
    output = doctor.format_doctor_report(report)

    assert report["environment"] == {"env_file_exists": True}
    assert "✓ .env file found" in output
    assert "secret-password" not in output


def test_doctor_output_when_env_is_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    clear_app_env(monkeypatch)
    set_minimal_imap_env(monkeypatch)
    monkeypatch.chdir(tmp_path)

    report = doctor.run_doctor(skip_imap_login=True)
    output = doctor.format_doctor_report(report)

    assert report["environment"] == {"env_file_exists": False}
    assert ".env file not found" in output


def test_missing_openai_key_is_optional_not_fatal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    clear_app_env(monkeypatch)
    set_minimal_imap_env(monkeypatch)
    monkeypatch.chdir(tmp_path)

    report = doctor.run_doctor(skip_imap_login=True)
    output = doctor.format_doctor_report(report)

    assert report["openai"]["api_key_configured"] is False
    assert report["openai"]["model"] == "gpt-4.1-mini"
    assert "Optional: only needed for AI-powered answers." in output


def test_missing_imap_settings_produces_friendly_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    clear_app_env(monkeypatch)
    monkeypatch.setenv("EMAIL_PROVIDER", "custom")
    monkeypatch.chdir(tmp_path)

    report = doctor.run_doctor(skip_imap_login=True)
    output = doctor.format_doctor_report(report)

    assert report["imap"]["settings_loaded"] is False
    assert "IMAP_HOST is required" in str(report["imap"]["error"])
    assert "Add it to .env." in str(report["imap"]["error"])
    assert "IMAP settings could not be loaded" in output


def test_doctor_report_includes_provider_info_without_password(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    clear_app_env(monkeypatch)
    monkeypatch.setenv("EMAIL_PROVIDER", "gmail")
    monkeypatch.setenv("IMAP_USERNAME", "user@gmail.com")
    monkeypatch.setenv("IMAP_PASSWORD", "secret-password")
    monkeypatch.chdir(tmp_path)

    report = doctor.run_doctor(skip_imap_login=True)
    output = doctor.format_doctor_report(report)

    assert report["imap"]["provider_key"] == "gmail"
    assert report["imap"]["provider_display_name"] == "Gmail"
    assert report["imap"]["host"] == "imap.gmail.com"
    assert report["imap"]["port"] == 993
    assert "Provider: Gmail (gmail)" in output
    assert "Setup notes: Enable IMAP in Gmail settings" in output
    assert "secret-password" not in output


def test_doctor_unknown_provider_error_lists_valid_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    clear_app_env(monkeypatch)
    monkeypatch.setenv("EMAIL_PROVIDER", "fastmail")
    monkeypatch.chdir(tmp_path)

    report = doctor.run_doctor(skip_imap_login=True)
    output = doctor.format_doctor_report(report)

    assert report["imap"]["settings_loaded"] is False
    assert "Unknown EMAIL_PROVIDER 'fastmail'" in str(report["imap"]["error"])
    assert "icloud, gmail, outlook, yahoo, aol, custom" in str(report["imap"]["error"])
    assert "Unknown EMAIL_PROVIDER 'fastmail'" in output


def test_skip_imap_login_does_not_attempt_connection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    clear_app_env(monkeypatch)
    set_minimal_imap_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    imap_ssl = Mock()
    monkeypatch.setattr(doctor.imaplib, "IMAP4_SSL", imap_ssl)

    report = doctor.run_doctor(skip_imap_login=True)

    assert report["imap"]["login_checked"] is False
    imap_ssl.assert_not_called()


def test_imap_login_success_uses_login_logout_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    clear_app_env(monkeypatch)
    set_minimal_imap_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    client = FakeImapClient()
    monkeypatch.setattr(doctor.imaplib, "IMAP4_SSL", Mock(return_value=client))

    report = doctor.run_doctor()

    assert report["imap"]["login_checked"] is True
    assert report["imap"]["login_successful"] is True
    assert client.calls == [
        ("login", "user@example.com", "secret-password"),
        ("logout",),
    ]


@pytest.mark.parametrize(
    ("provider_key", "expected_message"),
    [
        ("gmail", "IMAP authentication failed for Gmail"),
        ("outlook", "IMAP authentication failed for Outlook / Microsoft 365"),
    ],
)
def test_imap_authentication_failure_uses_provider_guidance_without_exposing_password(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    provider_key: str,
    expected_message: str,
) -> None:
    clear_app_env(monkeypatch)
    set_minimal_imap_env(monkeypatch)
    monkeypatch.setenv("EMAIL_PROVIDER", provider_key)
    monkeypatch.delenv("IMAP_HOST", raising=False)
    monkeypatch.chdir(tmp_path)
    client = FakeImapClient()
    client.login = Mock(side_effect=imaplib.IMAP4.error("bad secret-password"))
    client.logout = Mock(return_value=("OK", [b"logged out"]))
    monkeypatch.setattr(doctor.imaplib, "IMAP4_SSL", Mock(return_value=client))

    report = doctor.run_doctor()
    output = doctor.format_doctor_report(report)

    assert report["imap"]["login_successful"] is False
    assert expected_message in str(report["imap"]["error"])
    assert str(report["imap"]["error"]) == email_providers.authentication_help(provider_key)
    assert "secret-password" not in json.dumps(report)
    assert "secret-password" not in output
    assert client.select.call_count == 0 if isinstance(client.select, Mock) else True


def test_database_missing_returns_exists_false_and_count_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    clear_app_env(monkeypatch)
    db_path = tmp_path / "missing.db"
    monkeypatch.setenv("EMAIL_TRIAGE_DB_PATH", str(db_path))
    monkeypatch.chdir(tmp_path)

    report = doctor.run_doctor(skip_imap_login=True)

    assert report["database"]["path"] == str(db_path)
    assert report["database"]["exists"] is False
    assert report["database"]["stored_summary_cards"] == 0
    assert not db_path.exists()


def test_database_with_stored_cards_returns_correct_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    clear_app_env(monkeypatch)
    set_minimal_imap_env(monkeypatch)
    db_path = tmp_path / "email_triage.db"
    monkeypatch.setenv("EMAIL_TRIAGE_DB_PATH", str(db_path))
    monkeypatch.chdir(tmp_path)
    storage.init_db(str(db_path))
    storage.save_summary_cards(
        [
            {"message_id": "<1@example.com>", "summary": "First"},
            {"message_id": "<2@example.com>", "summary": "Second"},
        ],
        str(db_path),
    )

    report = doctor.run_doctor(skip_imap_login=True)
    output = doctor.format_doctor_report(report)

    assert report["database"]["exists"] is True
    assert report["database"]["stored_summary_cards"] == 2
    assert "Stored summary cards: 2" in output
    assert "First" not in output
    assert "<1@example.com>" not in output


def test_json_command_prints_valid_json(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    report = doctor.run_doctor(skip_imap_login=True)
    monkeypatch.setattr(email_assistant.doctor, "run_doctor", Mock(return_value=report))

    exit_code = email_assistant.main(["doctor", "--json", "--skip-imap-login"])
    captured = capsys.readouterr()

    assert exit_code == 0
    parsed = json.loads(captured.out)
    assert parsed["safety_note"] == doctor.SAFETY_NOTE
    assert "IMAP_PASSWORD" not in captured.out
    email_assistant.doctor.run_doctor.assert_called_once_with(skip_imap_login=True)


def test_human_command_contains_useful_checkmarks(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    report = {
        "environment": {"env_file_exists": True},
        "openai": {"api_key_configured": True, "model": "gpt-4.1-mini", "error": None},
        "imap": {
            "settings_loaded": True,
            "provider_key": "icloud",
            "provider_display_name": "iCloud Mail",
            "provider_notes": "Use an app password.",
            "host": "imap.mail.me.com",
            "port": 993,
            "username": "user@example.com",
            "mailbox": "INBOX",
            "max_messages": 5,
            "login_checked": True,
            "login_successful": True,
            "error": None,
        },
        "database": {
            "path": "email_triage.db",
            "exists": True,
            "stored_summary_cards": 12,
        },
        "safety_note": doctor.SAFETY_NOTE,
    }
    monkeypatch.setattr(email_assistant.doctor, "run_doctor", Mock(return_value=report))

    exit_code = email_assistant.main(["doctor"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "MailTriage AI Doctor" in captured.out
    assert "✓ IMAP login successful" in captured.out
    assert "✓ Stored summary cards: 12" in captured.out
    assert "✓ Doctor did not fetch" in captured.out


def test_count_summary_cards_returns_zero_for_missing_database(tmp_path: Path) -> None:
    db_path = tmp_path / "missing.db"

    assert storage.count_summary_cards(str(db_path)) == 0
    assert not db_path.exists()


def test_count_summary_cards_returns_zero_when_table_is_missing(tmp_path: Path) -> None:
    db_path = tmp_path / "empty.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE other_table (id INTEGER)")

    assert storage.count_summary_cards(str(db_path)) == 0


def test_count_summary_cards_counts_email_cards(tmp_path: Path) -> None:
    db_path = tmp_path / "email_triage.db"
    storage.init_db(str(db_path))
    storage.save_summary_cards(
        [
            {"message_id": "<1@example.com>", "summary": "First"},
            {"message_id": "<2@example.com>", "summary": "Second"},
            {"message_id": "<3@example.com>", "summary": "Third"},
        ],
        str(db_path),
    )

    assert storage.count_summary_cards(str(db_path)) == 3
