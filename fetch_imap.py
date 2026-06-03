"""Read-only IMAP ingestion for email triage.

This module fetches unread email content and passes it to triage_email. It does
not delete, move, archive, mark read, or send emails.
"""

from __future__ import annotations

import imaplib
import json
import os
from dataclasses import asdict, dataclass
from email import policy
from email.header import decode_header, make_header
from email.message import Message
from email.parser import BytesParser

from triage import EmailMessage, triage_email


@dataclass(frozen=True)
class ImapSettings:
    host: str
    port: int
    username: str
    password: str
    mailbox: str
    max_messages: int


def load_imap_settings() -> ImapSettings:
    host = _required_env("IMAP_HOST")
    username = _required_env("IMAP_USERNAME")
    password = _required_env("IMAP_PASSWORD")

    return ImapSettings(
        host=host,
        port=_get_int_env("IMAP_PORT", 993),
        username=username,
        password=password,
        mailbox=os.getenv("IMAP_MAILBOX", "INBOX") or "INBOX",
        max_messages=_get_int_env("IMAP_MAX_MESSAGES", 5),
    )


def fetch_unread_emails(settings: ImapSettings) -> list[EmailMessage]:
    emails: list[EmailMessage] = []
    client = imaplib.IMAP4_SSL(settings.host, settings.port)

    try:
        client.login(settings.username, settings.password)
        _ensure_ok(client.select(settings.mailbox, readonly=True), "select mailbox")
        search_status, search_data = client.search(None, "UNSEEN")
        _ensure_ok((search_status, search_data), "search unread messages")

        message_ids = _recent_message_ids(search_data, settings.max_messages)
        for message_id in message_ids:
            status, fetch_data = client.fetch(message_id, "(BODY.PEEK[])")
            _ensure_ok((status, fetch_data), f"fetch message {message_id.decode()}")

            raw_message = _raw_message_from_fetch(fetch_data)
            if raw_message is None:
                continue

            emails.append(_parse_email(raw_message))
    finally:
        try:
            client.logout()
        except imaplib.IMAP4.error:
            pass

    return emails


def triage_unread_emails(settings: ImapSettings | None = None) -> list[dict[str, object]]:
    settings = settings or load_imap_settings()
    results: list[dict[str, object]] = []

    for email in fetch_unread_emails(settings):
        triage_result = triage_email(email)
        results.append(
            {
                "email": asdict(email),
                "triage": asdict(triage_result),
            }
        )

    return results


def main() -> int:
    print(json.dumps(triage_unread_emails(), indent=2))
    return 0


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise ValueError(f"{name} is required")
    return value


def _get_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default

    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _ensure_ok(response: tuple[str, list[bytes] | list[tuple[bytes, bytes]]], action: str) -> None:
    status, _ = response
    if status != "OK":
        raise RuntimeError(f"Could not {action}: IMAP returned {status}")


def _recent_message_ids(search_data: list[bytes], max_messages: int) -> list[bytes]:
    if not search_data:
        return []

    message_ids = search_data[0].split()
    return message_ids[-max_messages:]


def _raw_message_from_fetch(fetch_data: list[object]) -> bytes | None:
    for item in fetch_data:
        if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], bytes):
            return item[1]
    return None


def _parse_email(raw_message: bytes) -> EmailMessage:
    parsed = BytesParser(policy=policy.default).parsebytes(raw_message)
    return EmailMessage(
        sender=_decode_header(parsed.get("From", "")),
        subject=_decode_header(parsed.get("Subject", "")),
        body=_extract_body(parsed),
    )


def _decode_header(value: str) -> str:
    if not value:
        return ""
    return str(make_header(decode_header(value)))


def _extract_body(message: Message) -> str:
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get_content_disposition() == "attachment":
                continue
            if part.get_content_type() == "text/plain":
                return _part_content(part)

        for part in message.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get_content_disposition() == "attachment":
                continue
            if part.get_content_type() == "text/html":
                return _part_content(part)

        return ""

    return _part_content(message)


def _part_content(message: Message) -> str:
    try:
        return message.get_content().strip()
    except (AttributeError, LookupError, UnicodeDecodeError):
        payload = message.get_payload(decode=True)
        if not isinstance(payload, bytes):
            return str(message.get_payload()).strip()
        charset = message.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace").strip()


if __name__ == "__main__":
    raise SystemExit(main())
