import pytest

from config import Settings, load_settings
from triage import EmailMessage, _coerce_bool, triage_email


def make_settings(api_key: str | None = None) -> Settings:
    return Settings(
        openai_api_key=api_key,
        openai_model="test-model",
        default_reply_tone="professional",
        max_draft_words=180,
    )


def test_local_rule_based_triage_without_openai_api_key() -> None:
    email = EmailMessage(
        sender="alex@example.com",
        subject="Invoice question",
        body="Can you confirm whether invoice 1042 has been paid?",
    )

    result = triage_email(email, make_settings())

    assert result.category == "billing"
    assert result.priority == "normal"
    assert result.action_required is True
    assert result.reply_draft
    assert result.safety_note == "Draft only. No email was sent."


@pytest.mark.parametrize(
    ("subject", "body", "expected_priority"),
    [
        ("Urgent issue", "Please handle this immediately.", "urgent"),
        ("Project deadline", "This is blocked and due today.", "high"),
    ],
)
def test_urgent_and_high_priority_detection(
    subject: str, body: str, expected_priority: str
) -> None:
    email = EmailMessage(sender="alex@example.com", subject=subject, body=body)

    result = triage_email(email, make_settings())

    assert result.priority == expected_priority
    assert result.action_required is True


def test_newsletter_detection() -> None:
    email = EmailMessage(
        sender="news@example.com",
        subject="Weekly newsletter",
        body="This digest includes updates and an unsubscribe link.",
    )

    result = triage_email(email, make_settings())

    assert result.priority == "low"
    assert result.category == "newsletter"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, True),
        (False, False),
        ("true", True),
        ("false", False),
        ("yes", True),
        ("no", False),
        ("1", True),
        ("0", False),
        (None, False),
    ],
)
def test_coerce_bool(value: object, expected: bool) -> None:
    assert _coerce_bool(value) is expected


@pytest.mark.parametrize("value", ["19", "501", "not-a-number"])
def test_invalid_max_draft_words_values(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MAX_DRAFT_WORDS", value)

    with pytest.raises(ValueError, match="MAX_DRAFT_WORDS"):
        load_settings()
