from unittest.mock import Mock

import pytest

import analyzer
from config import Settings
from triage import EmailMessage


def make_settings(api_key: str | None = None) -> Settings:
    return Settings(
        openai_api_key=api_key,
        openai_model="test-model",
        default_reply_tone="professional",
        max_draft_words=180,
    )


def test_local_analysis_without_openai_api_key() -> None:
    email = EmailMessage(
        sender="alex@example.com",
        subject="Invoice question",
        body="Can you confirm whether invoice 1042 has been paid?",
    )

    result = analyzer.analyze_email(email, make_settings())

    assert result.category == "billing"
    assert result.priority == "normal"
    assert result.requires_response is True
    assert result.summary
    assert result.sender_intent
    assert result.suggested_reply
    assert result.safety_note == "Draft only. No email was sent."


def test_action_item_extraction_for_confirmation_request() -> None:
    email = EmailMessage(
        sender="alex@example.com",
        subject="Invoice question",
        body="Can you confirm whether invoice 1042 has been paid?",
    )

    result = analyzer.analyze_email(email, make_settings())

    assert [item.text for item in result.action_items] == [
        "Invoice 1042 has been paid."
    ]
    assert [item.owner for item in result.action_items] == ["me"]
    assert [item.due_date for item in result.action_items] == [None]
    assert [item.priority for item in result.action_items] == ["normal"]
    assert result.requires_response is True


def test_newsletter_has_no_required_response() -> None:
    email = EmailMessage(
        sender="news@example.com",
        subject="Weekly newsletter",
        body="This digest includes updates and an unsubscribe link.",
    )

    result = analyzer.analyze_email(email, make_settings())

    assert result.category == "newsletter"
    assert result.priority == "low"
    assert result.requires_response is False
    assert result.action_items == []
    assert result.suggested_reply == "No reply needed."


def test_output_includes_safety_note() -> None:
    email = EmailMessage(
        sender="alex@example.com",
        subject="Follow up",
        body="Please review this when you have a moment.",
    )

    result = analyzer.analyze_email(email, make_settings())

    assert result.safety_note == "Draft only. No email was sent."


@pytest.mark.parametrize(
    "output_text",
    [
        None,
        "",
        "{not json",
        "{}",
    ],
)
def test_invalid_or_missing_model_output_falls_back_safely(
    monkeypatch: pytest.MonkeyPatch, output_text: str | None
) -> None:
    class FakeResponse:
        def __init__(self, output_text: str | None) -> None:
            self.output_text = output_text

    class FakeResponses:
        def create(self, **_: object) -> FakeResponse:
            return FakeResponse(output_text)

    class FakeClient:
        responses = FakeResponses()

    monkeypatch.setattr(analyzer, "_create_openai_client", Mock(return_value=FakeClient()))

    email = EmailMessage(
        sender="alex@example.com",
        subject="Invoice question",
        body="Can you confirm whether invoice 1042 has been paid?",
    )

    result = analyzer.analyze_email(email, make_settings(api_key="sk-test"))

    assert result.category == "billing"
    assert result.requires_response is True
    assert result.action_items
    assert result.safety_note == "Draft only. No email was sent."


def test_model_action_items_parse_new_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        output_text = """
        {
          "summary": "Follow up is needed.",
          "sender_intent": "Requesting confirmation.",
          "priority": "high",
          "category": "billing",
          "requires_response": true,
          "action_items": [
            {
              "text": "Confirm payment status",
              "owner": "finance",
              "due_date": "2026-06-05",
              "priority": "urgent"
            },
            {
              "text": "Send follow-up",
              "owner": "",
              "due_date": "",
              "priority": "maybe"
            }
          ],
          "suggested_reply": "Thanks for the note.",
          "safety_note": "Draft only. No email was sent."
        }
        """

    class FakeResponses:
        def create(self, **_: object) -> FakeResponse:
            return FakeResponse()

    class FakeClient:
        responses = FakeResponses()

    monkeypatch.setattr(analyzer, "_create_openai_client", Mock(return_value=FakeClient()))

    email = EmailMessage(
        sender="alex@example.com",
        subject="Invoice question",
        body="Can you confirm whether invoice 1042 has been paid?",
    )

    result = analyzer.analyze_email(email, make_settings(api_key="sk-test"))

    assert [item.text for item in result.action_items] == [
        "Confirm payment status.",
        "Send follow-up.",
    ]
    assert [item.owner for item in result.action_items] == ["finance", "me"]
    assert [item.due_date for item in result.action_items] == ["2026-06-05", None]
    assert [item.priority for item in result.action_items] == ["urgent", "normal"]
