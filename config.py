"""Configuration for the email triage assistant."""

from __future__ import annotations

import os
from dataclasses import dataclass

import email_providers

SEARCH_MODE_UNREAD = "unread"
SEARCH_MODE_RECENT = "recent"
SEARCH_MODE_CHOICES = (SEARCH_MODE_UNREAD, SEARCH_MODE_RECENT)

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
    search_mode: str = SEARCH_MODE_UNREAD
    provider_key: str = "custom"
    provider_display_name: str = "Custom IMAP"


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


def _optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return None
    return value.strip()


def _get_search_mode(name: str = "IMAP_SEARCH_MODE") -> str:
    value = os.getenv(name, SEARCH_MODE_UNREAD).strip().lower() or SEARCH_MODE_UNREAD
    if value not in SEARCH_MODE_CHOICES:
        choices = ", ".join(SEARCH_MODE_CHOICES)
        raise ValueError(f"{name} must be one of: {choices}")
    return value


def search_mode_label(search_mode: str) -> str:
    if search_mode == SEARCH_MODE_RECENT:
        return "Recent messages"
    return "Unread only"


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

    provider = email_providers.get_provider(os.getenv("EMAIL_PROVIDER", "icloud"))
    host = _optional_env("IMAP_HOST") or provider.imap_host
    if not host:
        raise ValueError("IMAP_HOST is required for EMAIL_PROVIDER=custom")

    return ImapSettings(
        host=host,
        port=_get_bounded_int("IMAP_PORT", provider.imap_port, 1, 65535),
        username=_required_env("IMAP_USERNAME"),
        password=_required_env("IMAP_PASSWORD"),
        mailbox=os.getenv("IMAP_MAILBOX", provider.default_mailbox).strip()
        or provider.default_mailbox,
        max_messages=_get_bounded_int("IMAP_MAX_MESSAGES", 5, 1, 50),
        search_mode=_get_search_mode(),
        provider_key=provider.key,
        provider_display_name=provider.display_name,
    )
