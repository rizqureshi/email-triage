"""Local Streamlit GUI for the email assistant."""

from __future__ import annotations

import os
from dataclasses import asdict, is_dataclass, replace
from typing import Any

import streamlit as st

import analyzer
import daily_briefing
import doctor
import email_assistant
import fetch_imap
import inbox_qa
import storage
from config import load_imap_settings
from triage import EmailMessage


SAFETY_NOTE = "This tool does not send, delete, archive, move, or mark emails as read."
PRIORITY_OPTIONS = ["All", "low", "normal", "high", "urgent"]
CATEGORY_OPTIONS = [
    "All",
    "billing",
    "scheduling",
    "support",
    "sales",
    "personal",
    "newsletter",
    "other",
]


def main() -> None:
    st.set_page_config(page_title="Email Assistant", page_icon="@", layout="wide")
    st.title("Email Assistant")
    st.info(SAFETY_NOTE)

    tabs = st.tabs(
        [
            "Setup Check",
            "Fetch Emails",
            "Summary Cards",
            "Daily Briefing",
            "Ask Inbox",
            "Manual Analyze",
        ]
    )

    with tabs[0]:
        _render_setup_check()
    with tabs[1]:
        _render_fetch_emails()
    with tabs[2]:
        _render_summary_cards()
    with tabs[3]:
        _render_daily_briefing()
    with tabs[4]:
        _render_ask_inbox()
    with tabs[5]:
        _render_manual_analyze()


def _render_setup_check() -> None:
    st.subheader("Setup Check")
    skip_imap_login = st.checkbox("Skip IMAP login check", value=False)

    if st.button("Run setup check"):
        try:
            report = doctor.run_doctor(skip_imap_login=skip_imap_login)
        except Exception as exc:  # pragma: no cover - Streamlit error surface
            _show_error(exc)
            return

        st.text(doctor.format_doctor_report(report))
        _json_expander(report)


def _render_fetch_emails() -> None:
    st.subheader("Fetch Emails")
    max_messages = st.number_input("Max messages", min_value=1, max_value=50, value=5, step=1)
    mailbox = st.text_input("Mailbox", value="INBOX")
    save_cards = st.checkbox("Save summary cards to local database", value=False)

    if st.button("Fetch unread emails"):
        try:
            settings = load_imap_settings()
            settings = replace(
                settings,
                max_messages=int(max_messages),
                mailbox=mailbox.strip() or "INBOX",
            )
            cards = fetch_imap.fetch_inbox_summary_cards(settings)
            if save_cards:
                storage.save_summary_cards(cards)
        except Exception as exc:  # pragma: no cover - Streamlit error surface
            _show_error(exc)
            return

        st.text(email_assistant.format_cards(cards))
        _json_expander(cards)


def _render_summary_cards() -> None:
    st.subheader("Summary Cards")
    priority = st.selectbox("Priority", PRIORITY_OPTIONS)
    category = st.selectbox("Category", CATEGORY_OPTIONS)
    requires_response = st.checkbox("Requires response", value=False)
    limit = st.number_input("Limit", min_value=1, max_value=200, value=20, step=1)

    if st.button("Refresh summary cards"):
        _show_summary_cards(
            limit=int(limit),
            priority=None if priority == "All" else str(priority),
            category=None if category == "All" else str(category),
            requires_response=True if requires_response else None,
        )


def _show_summary_cards(
    *,
    limit: int,
    priority: str | None,
    category: str | None,
    requires_response: bool | None,
) -> None:
    try:
        cards = storage.list_cards(
            limit=limit,
            priority=priority,
            category=category,
            requires_response=requires_response,
        )
    except Exception as exc:  # pragma: no cover - Streamlit error surface
        _show_error(exc)
        return

    st.text(email_assistant.format_stored_cards(cards))
    _json_expander(cards)


def _render_daily_briefing() -> None:
    st.subheader("Daily Briefing")
    limit = st.number_input("Briefing limit", min_value=1, max_value=200, value=20, step=1)

    if st.button("Generate briefing"):
        try:
            briefing = daily_briefing.generate_daily_briefing(limit=int(limit))
        except Exception as exc:  # pragma: no cover - Streamlit error surface
            _show_error(exc)
            return

        st.text(email_assistant.format_briefing(briefing))
        _json_expander(briefing)


def _render_ask_inbox() -> None:
    st.subheader("Ask Inbox")
    question = st.text_input("Question")
    limit = st.number_input("Answer limit", min_value=1, max_value=200, value=20, step=1)
    use_ai = st.checkbox("Use AI for answer", value=False)
    if use_ai:
        st.caption("Only matched stored summary cards are sent to OpenAI, not raw email bodies.")

    if st.button("Ask"):
        if not question.strip():
            st.error("Enter a question first.")
            return

        try:
            answer = inbox_qa.answer_inbox_question(
                question.strip(),
                limit=int(limit),
                use_ai=use_ai,
            )
        except Exception as exc:  # pragma: no cover - Streamlit error surface
            _show_error(exc)
            return

        st.text(email_assistant.format_answer(answer))
        _json_expander(answer)


def _render_manual_analyze() -> None:
    st.subheader("Manual Analyze")
    sender = st.text_input("Sender")
    subject = st.text_input("Subject")
    body = st.text_area("Body", height=240)

    if st.button("Analyze"):
        if not body.strip():
            st.error("Paste an email body first.")
            return

        try:
            email = EmailMessage(sender=sender.strip(), subject=subject.strip(), body=body.strip())
            analysis = analyzer.analyze_email(email)
        except Exception as exc:  # pragma: no cover - Streamlit error surface
            _show_error(exc)
            return

        st.text(email_assistant.format_analysis(analysis))
        _json_expander(analysis)


def _json_expander(data: object) -> None:
    with st.expander("JSON"):
        st.json(_jsonable(data))


def _jsonable(data: object) -> object:
    if is_dataclass(data) and not isinstance(data, type):
        return asdict(data)
    if isinstance(data, list):
        return [_jsonable(item) for item in data]
    if isinstance(data, dict):
        return {key: _jsonable(value) for key, value in data.items()}
    return data


def _show_error(exc: Exception) -> None:
    st.error(_safe_error_message(exc))


def _safe_error_message(exc: Exception) -> str:
    message = str(exc)
    for secret in (os.getenv("OPENAI_API_KEY", ""), os.getenv("IMAP_PASSWORD", "")):
        if secret:
            message = message.replace(secret, "[secret]")

    if "IMAP authentication failed" in message:
        return (
            "IMAP authentication failed. For iCloud Mail, use your full iCloud email "
            "address and an Apple app-specific password."
        )
    if "IMAP_" in message and "required" in message:
        return "Missing IMAP settings. Check your .env configuration."
    if "OPENAI_API_KEY" in message:
        return "OpenAI settings need attention. Check your .env configuration."
    if not message.strip():
        return "The email assistant could not complete that action."
    return message


if __name__ == "__main__":
    main()
