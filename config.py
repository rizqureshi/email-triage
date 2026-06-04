"""Configuration for the email triage assistant."""

from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


if load_dotenv is not None:
    load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Environment-driven application settings."""

    openai_api_key: str | None
    openai_model: str
    default_reply_tone: str
    max_draft_words: int

    @property
    def use_openai(self) -> bool:
        return bool(self.openai_api_key)


@dataclass(frozen=True)
class ImapSettings:
    """Environment-driven IMAP settings for read-only inbox ingestion."""

    host: str
    port: int
    username: str
    password: str
    mailbox: str
    max_messages: int


def _get_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return default

    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _get_bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    value = _get_int(name, default)
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise ValueError(f"{name} is required")
    return value.strip()


def load_settings() -> Settings:
    """Load settings from environment variables and .env."""

    api_key = os.getenv("OPENAI_API_KEY")
    if api_key is not None and api_key.strip() == "":
        api_key = None

    return Settings(
        openai_api_key=api_key,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        default_reply_tone=os.getenv("DEFAULT_REPLY_TONE", "professional"),
        max_draft_words=_get_bounded_int("MAX_DRAFT_WORDS", 180, 20, 500),
    )


def load_imap_settings() -> ImapSettings:
    """Load read-only IMAP settings for fetch_imap.py."""

    return ImapSettings(
        host=_required_env("IMAP_HOST"),
        port=_get_bounded_int("IMAP_PORT", 993, 1, 65535),
        username=_required_env("IMAP_USERNAME"),
        password=_required_env("IMAP_PASSWORD"),
        mailbox=os.getenv("IMAP_MAILBOX", "INBOX").strip() or "INBOX",
        max_messages=_get_bounded_int("IMAP_MAX_MESSAGES", 5, 1, 50),
    )
