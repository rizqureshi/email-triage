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
