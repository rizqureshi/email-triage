"""SQLite storage for read-only email summary cards."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = "email_triage.db"


def resolve_db_path(db_path: str | None = None) -> str:
    """Resolve the SQLite path without creating files or directories."""

    return _resolve_db_path(db_path)


def init_db(db_path: str | None = None) -> None:
    path = _resolve_db_path(db_path)
    _ensure_parent_directory(path)

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS email_cards (
                message_id TEXT PRIMARY KEY,
                sender TEXT,
                subject TEXT,
                summary TEXT,
                sender_intent TEXT,
                priority TEXT,
                category TEXT,
                requires_response INTEGER,
                action_items_json TEXT,
                suggested_reply TEXT,
                safety_note TEXT,
                fetched_at TEXT
            )
            """
        )


def save_summary_card(card: dict[str, object], db_path: str | None = None) -> None:
    init_db(db_path)
    path = _resolve_db_path(db_path)
    with sqlite3.connect(path) as connection:
        _upsert_card(connection, card)


def save_summary_cards(cards: list[dict[str, object]], db_path: str | None = None) -> None:
    init_db(db_path)
    path = _resolve_db_path(db_path)
    with sqlite3.connect(path) as connection:
        for card in cards:
            _upsert_card(connection, card)


def count_summary_cards(db_path: str | None = None) -> int:
    """Count stored summary cards without creating a missing database."""

    path = _resolve_db_path(db_path)
    if not Path(path).exists():
        return 0

    with sqlite3.connect(path) as connection:
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='email_cards'"
        ).fetchone()
        if table is None:
            return 0

        row = connection.execute("SELECT COUNT(*) FROM email_cards").fetchone()

    if row is None:
        return 0
    return int(row[0])


def list_cards(
    limit: int = 20,
    priority: str | None = None,
    category: str | None = None,
    requires_response: bool | None = None,
    db_path: str | None = None,
) -> list[dict[str, object]]:
    """List stored summary cards with optional filters."""

    path = _resolve_db_path(db_path)
    if limit <= 0 or not Path(path).exists():
        return []

    conditions: list[str] = []
    params: list[object] = []
    if priority is not None:
        conditions.append("priority = ?")
        params.append(priority)
    if category is not None:
        conditions.append("category = ?")
        params.append(category)
    if requires_response is not None:
        conditions.append("requires_response = ?")
        params.append(int(requires_response))

    where_clause = ""
    if conditions:
        where_clause = f"WHERE {' AND '.join(conditions)}"

    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='email_cards'"
        ).fetchone()
        if table is None:
            return []

        rows = connection.execute(
            f"""
            SELECT
                message_id,
                sender,
                subject,
                summary,
                sender_intent,
                priority,
                category,
                requires_response,
                action_items_json,
                suggested_reply,
                safety_note,
                fetched_at
            FROM email_cards
            {where_clause}
            ORDER BY fetched_at DESC, message_id DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()

    return [_row_to_card(row) for row in rows]


def list_action_items(
    limit: int = 50,
    priority: str | None = None,
    owner: str | None = None,
    due_date: str | None = None,
    db_path: str | None = None,
) -> list[dict[str, object]]:
    """List action items flattened from stored summary cards."""

    if limit <= 0:
        return []

    cards = _query_cards(db_path=db_path)
    items: list[dict[str, object]] = []
    owner_filter = owner.strip().lower() if isinstance(owner, str) and owner.strip() else None
    due_date_filter = due_date.strip() if isinstance(due_date, str) and due_date.strip() else None

    for card in cards:
        action_items = card.get("action_items", [])
        if not isinstance(action_items, list):
            continue

        for action_item in action_items:
            if not isinstance(action_item, dict):
                continue

            item = _action_item_with_source(action_item, card)
            if priority is not None and item["priority"] != priority:
                continue
            if owner_filter is not None and str(item["owner"]).lower() != owner_filter:
                continue
            if due_date_filter is not None and item["due_date"] != due_date_filter:
                continue

            items.append(item)
            if len(items) >= limit:
                return items

    return items


def list_recent_cards(limit: int = 20, db_path: str | None = None) -> list[dict[str, object]]:
    path = _resolve_db_path(db_path)
    if limit <= 0:
        return []

    init_db(path)
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT
                message_id,
                sender,
                subject,
                summary,
                sender_intent,
                priority,
                category,
                requires_response,
                action_items_json,
                suggested_reply,
                safety_note,
                fetched_at
            FROM email_cards
            ORDER BY fetched_at DESC, message_id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [_row_to_card(row) for row in rows]


def list_cards_requiring_response(
    limit: int = 20, db_path: str | None = None
) -> list[dict[str, object]]:
    path = _resolve_db_path(db_path)
    if limit <= 0:
        return []

    init_db(path)
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT
                message_id,
                sender,
                subject,
                summary,
                sender_intent,
                priority,
                category,
                requires_response,
                action_items_json,
                suggested_reply,
                safety_note,
                fetched_at
            FROM email_cards
            WHERE requires_response = 1
            ORDER BY fetched_at DESC, message_id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [_row_to_card(row) for row in rows]


def _resolve_db_path(db_path: str | None) -> str:
    if db_path is not None and db_path.strip():
        return db_path.strip()

    env_path = os.getenv("EMAIL_TRIAGE_DB_PATH", "").strip()
    if env_path:
        return env_path

    return DEFAULT_DB_PATH


def _query_cards(db_path: str | None = None) -> list[dict[str, object]]:
    path = _resolve_db_path(db_path)
    if not Path(path).exists():
        return []

    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='email_cards'"
        ).fetchone()
        if table is None:
            return []

        rows = connection.execute(
            """
            SELECT
                message_id,
                sender,
                subject,
                summary,
                sender_intent,
                priority,
                category,
                requires_response,
                action_items_json,
                suggested_reply,
                safety_note,
                fetched_at
            FROM email_cards
            ORDER BY fetched_at DESC, message_id DESC
            """
        ).fetchall()

    return [_row_to_card(row) for row in rows]


def _ensure_parent_directory(path: str) -> None:
    parent = Path(path).expanduser().resolve().parent
    parent.mkdir(parents=True, exist_ok=True)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _require_text(value: object, field_name: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ValueError(f"{field_name} is required")


def _card_payload(card: dict[str, object]) -> dict[str, object]:
    action_items = card.get("action_items", [])
    if not isinstance(action_items, list):
        action_items = []

    return {
        "sender": _optional_text(card.get("sender")),
        "subject": _optional_text(card.get("subject")),
        "summary": _optional_text(card.get("summary")),
        "sender_intent": _optional_text(card.get("sender_intent")),
        "priority": _optional_text(card.get("priority")),
        "category": _optional_text(card.get("category")),
        "requires_response": bool(card.get("requires_response")),
        "action_items_json": json.dumps([_normalize_action_item(item) for item in action_items]),
        "suggested_reply": _optional_text(card.get("suggested_reply")),
        "safety_note": _optional_text(card.get("safety_note")),
    }


def _upsert_card(connection: sqlite3.Connection, card: dict[str, object]) -> None:
    message_id = _require_text(card.get("message_id"), "message_id")
    payload = _card_payload(card)
    fetched_at = _utc_now()

    connection.execute(
        """
        INSERT INTO email_cards (
            message_id,
            sender,
            subject,
            summary,
            sender_intent,
            priority,
            category,
            requires_response,
            action_items_json,
            suggested_reply,
            safety_note,
            fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(message_id) DO UPDATE SET
            sender = excluded.sender,
            subject = excluded.subject,
            summary = excluded.summary,
            sender_intent = excluded.sender_intent,
            priority = excluded.priority,
            category = excluded.category,
            requires_response = excluded.requires_response,
            action_items_json = excluded.action_items_json,
            suggested_reply = excluded.suggested_reply,
            safety_note = excluded.safety_note,
            fetched_at = excluded.fetched_at
        """,
        (
            message_id,
            payload["sender"],
            payload["subject"],
            payload["summary"],
            payload["sender_intent"],
            payload["priority"],
            payload["category"],
            int(bool(payload["requires_response"])),
            payload["action_items_json"],
            payload["suggested_reply"],
            payload["safety_note"],
            fetched_at,
        ),
    )


def _optional_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return str(value)


def _normalize_action_item(item: object) -> dict[str, Any]:
    if isinstance(item, dict):
        return {
            "text": _optional_text(item.get("text")),
            "owner": _optional_text(item.get("owner")) or "me",
            "due_date": _optional_text(item.get("due_date")) or None,
            "priority": _optional_text(item.get("priority")) or "normal",
        }
    return {
        "text": _optional_text(item),
        "owner": "me",
        "due_date": None,
        "priority": "normal",
    }


def _action_item_with_source(
    action_item: dict[str, object],
    card: dict[str, object],
) -> dict[str, object]:
    normalized = _normalize_action_item(action_item)
    return {
        "text": normalized["text"],
        "owner": normalized["owner"],
        "due_date": normalized["due_date"],
        "priority": normalized["priority"],
        "message_id": card.get("message_id", ""),
        "sender": card.get("sender", ""),
        "subject": card.get("subject", ""),
        "category": card.get("category", ""),
        "requires_response": bool(card.get("requires_response")),
        "fetched_at": card.get("fetched_at", ""),
    }


def _row_to_card(row: sqlite3.Row) -> dict[str, object]:
    return {
        "message_id": row["message_id"],
        "sender": row["sender"],
        "subject": row["subject"],
        "summary": row["summary"],
        "sender_intent": row["sender_intent"],
        "priority": row["priority"],
        "category": row["category"],
        "requires_response": bool(row["requires_response"]),
        "action_items": _decode_action_items(row["action_items_json"]),
        "suggested_reply": row["suggested_reply"],
        "safety_note": row["safety_note"],
        "fetched_at": row["fetched_at"],
    }


def _decode_action_items(value: object) -> list[dict[str, object]]:
    if not isinstance(value, str) or not value.strip():
        return []

    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return []

    if not isinstance(decoded, list):
        return []

    items: list[dict[str, object]] = []
    for item in decoded:
        if not isinstance(item, dict):
            continue
        items.append(
            {
                "text": _optional_text(item.get("text")),
                "owner": _optional_text(item.get("owner")) or "me",
                "due_date": _optional_text(item.get("due_date")) or None,
                "priority": _optional_text(item.get("priority")) or "normal",
            }
        )
    return items
