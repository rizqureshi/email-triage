"""Read-only IMAP inbox ingestion for email intelligence summary cards."""

from __future__ import annotations

import argparse
import json
import imaplib
import re
import ssl
from dataclasses import asdict, replace
from email import policy
from email.header import decode_header, make_header
from email.message import Message
from email.parser import BytesParser
from html import unescape
from html.parser import HTMLParser

from analyzer import analyze_email
from config import ImapSettings, load_imap_settings
from email_providers import authentication_help
from schemas import EmailAnalysis
import storage
from triage import EmailMessage


def fetch_unread_emails(settings: ImapSettings) -> list[tuple[str, EmailMessage]]:
    """Fetch unread emails using IMAP without modifying the mailbox."""

    emails: list[tuple[str, EmailMessage]] = []
    client = imaplib.IMAP4_SSL(settings.host, settings.port, ssl_context=ssl.create_default_context())

    try:
        try:
            client.login(settings.username, settings.password)
        except imaplib.IMAP4.error as exc:
            raise RuntimeError(authentication_help(settings.provider_key)) from exc
        _ensure_ok(client.select(settings.mailbox, readonly=True), "select mailbox")
        search_status, search_data = client.search(None, "UNSEEN")
        _ensure_ok((search_status, search_data), "search unread messages")

        message_ids = _recent_message_ids(search_data, settings.max_messages)
        for message_id in message_ids:
            status, fetch_data = client.fetch(message_id, "(BODY.PEEK[])")
            _ensure_ok((status, fetch_data), f"fetch message {message_id.decode(errors='ignore')}")

            raw_message = _raw_message_from_fetch(fetch_data)
            if raw_message is None:
                continue

            emails.append(_parse_email(message_id, raw_message))
    finally:
        try:
            client.logout()
        except imaplib.IMAP4.error:
            pass

    return emails


def fetch_inbox_summary_cards(settings: ImapSettings | None = None) -> list[dict[str, object]]:
    """Fetch unread emails and convert them into summary cards."""

    settings = settings or load_imap_settings()
    cards: list[dict[str, object]] = []

    for message_id, email in fetch_unread_emails(settings):
        analysis = analyze_email(email)
        cards.append(_summary_card(message_id, email, analysis))

    return cards


def triage_unread_emails(settings: ImapSettings | None = None) -> list[dict[str, object]]:
    """Backward-compatible alias for the inbox summary card output."""

    return fetch_inbox_summary_cards(settings)


def _summary_card(message_id: str, email: EmailMessage, analysis: EmailAnalysis) -> dict[str, object]:
    card = {
        "message_id": message_id,
        "sender": email.sender,
        "subject": email.subject,
    }
    card.update(asdict(analysis))
    return card


def _parse_email(message_id: bytes, raw_message: bytes) -> tuple[str, EmailMessage]:
    parsed = BytesParser(policy=policy.default).parsebytes(raw_message)
    return (
        _normalize_message_id(message_id, parsed.get("Message-ID", "")),
        EmailMessage(
            sender=_decode_header(str(parsed.get("From", ""))),
            subject=_decode_header(str(parsed.get("Subject", ""))),
            body=_limit_body(_extract_body(parsed)),
        ),
    )


def _normalize_message_id(message_id: bytes, header_value: object) -> str:
    header_text = _decode_header(str(header_value))
    if header_text.strip():
        return header_text.strip()
    return message_id.decode(errors="ignore")


def _decode_header(value: str) -> str:
    if not value:
        return ""
    return str(make_header(decode_header(value)))


def _limit_body(text: str, limit: int = 8000) -> str:
    normalized = text.strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rstrip()


def _extract_body(message: Message) -> str:
    if message.is_multipart():
        plain_text = _extract_first_text_part(message, "text/plain")
        if plain_text:
            return plain_text

        html_text = _extract_first_text_part(message, "text/html")
        if html_text:
            return _html_to_text(html_text)

        return ""

    if message.get_content_type() == "text/html":
        return _html_to_text(_part_content(message))

    return _part_content(message)


def _extract_first_text_part(message: Message, content_type: str) -> str:
    for part in message.walk():
        if part.get_content_maintype() == "multipart":
            continue
        if _is_attachment(part):
            continue
        if part.get_content_type() == content_type:
            text = _part_content(part)
            if text.strip():
                return text
    return ""


def _is_attachment(part: Message) -> bool:
    disposition = part.get_content_disposition()
    if disposition == "attachment":
        return True
    filename = part.get_filename()
    return bool(filename) and part.get_content_maintype() != "text"


def _html_to_text(html: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(html)
    parser.close()
    text = unescape(parser.get_text())
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip()


class _HTMLTextExtractor(HTMLParser):
    block_tags = {
        "article",
        "div",
        "li",
        "p",
        "section",
        "tr",
        "td",
        "th",
        "br",
        "table",
        "ul",
        "ol",
        "header",
        "footer",
    }
    ignored_tags = {"script", "style"}

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.ignored_tags:
            self._skip_depth += 1
            return
        if tag in self.block_tags:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.ignored_tags and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if tag in self.block_tags:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        cleaned = data.strip()
        if cleaned:
            self._parts.append(cleaned)

    def get_text(self) -> str:
        return " ".join(self._parts)


def _part_content(message: Message) -> str:
    try:
        return str(message.get_content()).strip()
    except (AttributeError, LookupError, UnicodeDecodeError):
        payload = message.get_payload(decode=True)
        if not isinstance(payload, bytes):
            return str(message.get_payload()).strip()
        charset = message.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace").strip()


def _raw_message_from_fetch(fetch_data: list[object]) -> bytes | None:
    for item in fetch_data:
        if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], bytes):
            return item[1]
    return None


def _recent_message_ids(search_data: list[bytes], max_messages: int) -> list[bytes]:
    if not search_data:
        return []

    message_ids = search_data[0].split()
    return message_ids[-max_messages:]


def _ensure_ok(response: tuple[str, list[bytes] | list[tuple[bytes, bytes]]], action: str) -> None:
    status, _ = response
    if status != "OK":
        raise RuntimeError(f"Could not {action}: IMAP returned {status}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch unread emails over IMAP and print read-only summary cards."
    )
    parser.add_argument(
        "--max-messages",
        type=_parse_max_messages,
        default=None,
        help="Override IMAP_MAX_MESSAGES for this run.",
    )
    parser.add_argument(
        "--mailbox",
        default=None,
        help="Override IMAP_MAILBOX for this run.",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save summary cards to the local SQLite database.",
    )
    return parser.parse_args()


def _parse_max_messages(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("max-messages must be an integer") from exc

    if parsed < 1 or parsed > 50:
        raise argparse.ArgumentTypeError("max-messages must be between 1 and 50")

    return parsed


def main() -> int:
    args = _parse_args()
    settings = load_imap_settings()
    if args.max_messages is not None:
        settings = replace(settings, max_messages=args.max_messages)
    if args.mailbox is not None:
        settings = replace(settings, mailbox=args.mailbox)

    cards = fetch_inbox_summary_cards(settings)
    if args.save:
        storage.init_db()
        storage.save_summary_cards(cards)

    print(json.dumps(cards, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
