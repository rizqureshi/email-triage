"""Read-only Microsoft Graph mail ingestion for MailTriage AI."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import requests

from analyzer import analyze_email
from config import SEARCH_MODE_RECENT, SEARCH_MODE_UNREAD
import graph_auth
from schemas import EmailAnalysis
from triage import EmailMessage


GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GRAPH_SELECT_FIELDS = (
    "id",
    "subject",
    "from",
    "sender",
    "bodyPreview",
    "body",
    "receivedDateTime",
    "sentDateTime",
    "isRead",
)


def fetch_graph_messages(
    mailbox: str = "Inbox",
    max_messages: int = 10,
    search_mode: str = SEARCH_MODE_UNREAD,
) -> list[tuple[str, EmailMessage]]:
    token = graph_auth.get_graph_access_token()
    folder_id = graph_folder_id_for_mailbox(mailbox)
    url = _messages_url(folder_id)
    params = _graph_query_params(
        max_messages=max_messages,
        search_mode=search_mode,
        folder_id=folder_id,
    )
    headers = {"Authorization": f"Bearer {token}"}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Microsoft Graph mail fetch failed: {_safe_request_error(exc, token)}") from exc

    payload = response.json()
    values = payload.get("value", [])
    if not isinstance(values, list):
        return []
    return [_graph_message_to_email(message) for message in values if isinstance(message, dict)]


def fetch_graph_summary_cards(
    mailbox: str = "Inbox",
    max_messages: int = 10,
    search_mode: str = SEARCH_MODE_UNREAD,
) -> list[dict[str, object]]:
    cards: list[dict[str, object]] = []
    for message_id, email in fetch_graph_messages(
        mailbox=mailbox,
        max_messages=max_messages,
        search_mode=search_mode,
    ):
        analysis = analyze_email(email)
        cards.append(_summary_card(message_id, email, analysis))
    return cards


def graph_folder_id_for_mailbox(mailbox: str) -> str:
    normalized = " ".join((mailbox or "Inbox").strip().lower().split())
    aliases = {
        "inbox": "inbox",
        "sent": "sentitems",
        "sent items": "sentitems",
        "sent messages": "sentitems",
        "junk": "junkemail",
        "junk email": "junkemail",
        "spam": "junkemail",
        "deleted items": "deleteditems",
        "trash": "deleteditems",
        "archive": "archive",
    }
    if normalized in aliases:
        return aliases[normalized]
    raise ValueError(
        f"Microsoft Graph folder '{mailbox}' is not mapped yet. Try Inbox, Sent Items, "
        "Junk Email, Deleted Items, or Archive."
    )


def _messages_url(folder_id: str) -> str:
    return f"{GRAPH_BASE_URL}/me/mailFolders/{folder_id}/messages"


def _graph_query_params(
    max_messages: int,
    search_mode: str,
    folder_id: str = "inbox",
) -> dict[str, object]:
    params: dict[str, object] = {
        "$top": max_messages,
        "$select": ",".join(GRAPH_SELECT_FIELDS),
        "$orderby": _graph_orderby_for_folder(folder_id),
    }
    if search_mode == SEARCH_MODE_UNREAD:
        params["$filter"] = "isRead eq false"
    elif search_mode != SEARCH_MODE_RECENT:
        params["$filter"] = "isRead eq false"
    return params


def _graph_orderby_for_folder(folder_id: str) -> str:
    if folder_id == "sentitems":
        return "sentDateTime desc"
    return "receivedDateTime desc"


def _graph_message_to_email(message: dict[str, Any]) -> tuple[str, EmailMessage]:
    message_id = str(message.get("id") or "")
    body = str(message.get("bodyPreview") or "").strip()
    if not body:
        body_value = message.get("body", {})
        if isinstance(body_value, dict):
            body = str(body_value.get("content") or "")
    return (
        message_id,
        EmailMessage(
            sender=_graph_sender(message),
            subject=str(message.get("subject") or ""),
            body=_limit_body(body),
        ),
    )


def _graph_sender(message: dict[str, Any]) -> str:
    for key in ("from", "sender"):
        value = message.get(key)
        if not isinstance(value, dict):
            continue
        email_address = value.get("emailAddress")
        if not isinstance(email_address, dict):
            continue
        name = str(email_address.get("name") or "").strip()
        address = str(email_address.get("address") or "").strip()
        if name and address:
            return f"{name} <{address}>"
        if address:
            return address
        if name:
            return name
    return ""


def _limit_body(text: str, limit: int = 8000) -> str:
    normalized = text.strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rstrip()


def _summary_card(message_id: str, email: EmailMessage, analysis: EmailAnalysis) -> dict[str, object]:
    card = {
        "message_id": message_id,
        "sender": email.sender,
        "subject": email.subject,
    }
    card.update(asdict(analysis))
    return card


def _safe_request_error(exc: requests.RequestException, token: str) -> str:
    message = str(exc)
    if token:
        message = message.replace(token, "[token]")
    return message
