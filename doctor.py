"""Guided setup diagnostics for the customer-facing CLI."""

from __future__ import annotations

import imaplib
import os
import ssl
from pathlib import Path
from typing import Any

import storage
from config import ImapSettings, load_imap_settings, load_settings


SAFETY_NOTE = "Doctor did not fetch, send, delete, archive, move, or mark any email as read."
ICLOUD_AUTH_MESSAGE = (
    "IMAP authentication failed. For iCloud Mail, use your full iCloud email address "
    "and an Apple app-specific password."
)


def run_doctor(skip_imap_login: bool = False) -> dict[str, object]:
    """Run local setup diagnostics without fetching or modifying email."""

    report: dict[str, object] = {
        "environment": {
            "env_file_exists": Path(".env").is_file(),
        },
        "openai": _check_openai(),
        "imap": _check_imap(skip_imap_login),
        "database": _check_database(),
        "safety_note": SAFETY_NOTE,
    }
    return report


def format_doctor_report(report: dict[str, object]) -> str:
    """Format a human-readable doctor report."""

    environment = _section(report, "environment")
    openai = _section(report, "openai")
    imap = _section(report, "imap")
    database = _section(report, "database")

    lines = [
        "Email Assistant Doctor",
        "",
        "Environment:",
    ]
    if environment.get("env_file_exists"):
        lines.append("✓ .env file found")
    else:
        lines.append("! .env file not found in the current directory")
        lines.append("  Suggested fix: create .env from the README examples before fetching mail.")

    lines.extend(["", "OpenAI:"])
    if openai.get("api_key_configured"):
        lines.append("✓ OPENAI_API_KEY configured")
    else:
        lines.append("! OPENAI_API_KEY not configured")
        lines.append("  Optional: only needed for AI-powered answers.")

    model = openai.get("model")
    if model:
        lines.append(f"✓ OPENAI_MODEL: {model}")
    else:
        lines.append("! OPENAI_MODEL not configured")
        lines.append("  Suggested fix: set OPENAI_MODEL, for example gpt-4.1-mini.")

    if openai.get("error"):
        lines.append(f"! OpenAI settings warning: {openai['error']}")

    lines.extend(["", "IMAP:"])
    if imap.get("settings_loaded"):
        lines.append("✓ IMAP settings loaded")
        lines.append(f"  Host: {imap.get('host')}")
        lines.append(f"  Port: {imap.get('port')}")
        lines.append(f"  Username: {imap.get('username')}")
        lines.append(f"  Mailbox: {imap.get('mailbox')}")
        lines.append(f"  Max messages: {imap.get('max_messages')}")
    else:
        lines.append("! IMAP settings could not be loaded")
        lines.append(f"  Suggested fix: {imap.get('error') or 'check IMAP_* values in .env.'}")

    if imap.get("login_checked"):
        if imap.get("login_successful"):
            lines.append("✓ IMAP login successful")
        else:
            lines.append("! IMAP login failed")
            lines.append(f"  Suggested fix: {imap.get('error') or 'check your IMAP credentials.'}")
    else:
        lines.append("! IMAP login skipped")
        if imap.get("error") and imap.get("settings_loaded"):
            lines.append(f"  Reason: {imap['error']}")

    lines.extend(["", "Database:"])
    if database.get("exists"):
        lines.append("✓ Database exists")
        lines.append(f"✓ Stored summary cards: {database.get('stored_summary_cards', 0)}")
    else:
        lines.append("! Database does not exist yet")
        lines.append("  This is normal before your first fetch with --save.")
        lines.append("✓ Stored summary cards: 0")

    lines.extend(["", "Safety:", f"✓ {report.get('safety_note') or SAFETY_NOTE}"])
    return "\n".join(lines)


def _check_openai() -> dict[str, object]:
    try:
        settings = load_settings()
    except ValueError as exc:
        return {
            "api_key_configured": False,
            "model": os.getenv("OPENAI_MODEL", "").strip() or None,
            "error": _sanitize_error(exc),
        }

    return {
        "api_key_configured": bool(settings.openai_api_key),
        "model": settings.openai_model,
        "error": None,
    }


def _check_imap(skip_imap_login: bool) -> dict[str, object]:
    imap_report: dict[str, object] = {
        "settings_loaded": False,
        "host": None,
        "port": None,
        "username": None,
        "mailbox": None,
        "max_messages": None,
        "login_checked": False,
        "login_successful": False,
        "error": None,
    }

    try:
        settings = load_imap_settings()
    except ValueError as exc:
        imap_report["error"] = _friendly_imap_settings_error(exc)
        return imap_report

    imap_report.update(
        {
            "settings_loaded": True,
            "host": settings.host,
            "port": settings.port,
            "username": settings.username,
            "mailbox": settings.mailbox,
            "max_messages": settings.max_messages,
        }
    )

    if skip_imap_login:
        return imap_report

    imap_report["login_checked"] = True
    try:
        _check_imap_login(settings)
    except imaplib.IMAP4.error:
        imap_report["error"] = ICLOUD_AUTH_MESSAGE
        return imap_report
    except OSError as exc:
        imap_report["error"] = f"Could not connect to IMAP server: {_sanitize_error(exc)}"
        return imap_report

    imap_report["login_successful"] = True
    return imap_report


def _check_imap_login(settings: ImapSettings) -> None:
    client = imaplib.IMAP4_SSL(
        settings.host,
        settings.port,
        ssl_context=ssl.create_default_context(),
    )
    try:
        client.login(settings.username, settings.password)
    finally:
        try:
            client.logout()
        except imaplib.IMAP4.error:
            pass


def _check_database() -> dict[str, object]:
    path = storage.resolve_db_path()
    return {
        "path": path,
        "exists": Path(path).exists(),
        "stored_summary_cards": storage.count_summary_cards(path),
    }


def _section(report: dict[str, object], name: str) -> dict[str, Any]:
    section = report.get(name, {})
    if isinstance(section, dict):
        return section
    return {}


def _friendly_imap_settings_error(exc: Exception) -> str:
    message = _sanitize_error(exc)
    if "IMAP_" in message and "required" in message:
        return f"{message}. Add it to .env."
    return f"{message}. Check your IMAP settings in .env."


def _sanitize_error(exc: Exception) -> str:
    message = str(exc)
    secret_values = [
        os.getenv("OPENAI_API_KEY", ""),
        os.getenv("IMAP_PASSWORD", ""),
    ]
    for secret in secret_values:
        if secret:
            message = message.replace(secret, "[secret]")
    return message
