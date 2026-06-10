"""Local Streamlit GUI for MailTriage AI."""

from __future__ import annotations

import csv
import io
import os
from dataclasses import asdict, is_dataclass, replace
from typing import Any

import streamlit as st

import analyzer
import daily_briefing
import doctor
import email_assistant
import email_providers
import fetch_imap
import inbox_qa
import review
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
    st.set_page_config(page_title="MailTriage AI", page_icon="@", layout="wide")
    st.title("MailTriage AI")
    st.info(SAFETY_NOTE)

    tabs = st.tabs(
        [
            "Setup Check",
            "Fetch Emails",
            "Summary Cards",
            "Action Items",
            "Inbox Review",
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
        _render_action_items()
    with tabs[4]:
        _render_inbox_review()
    with tabs[5]:
        _render_daily_briefing()
    with tabs[6]:
        _render_ask_inbox()
    with tabs[7]:
        _render_manual_analyze()


def _render_setup_check() -> None:
    st.subheader("Setup Check")
    _render_provider_help()
    skip_imap_login = st.checkbox("Skip IMAP login check", value=False)

    if st.button("Run setup check"):
        try:
            report = doctor.run_doctor(skip_imap_login=skip_imap_login)
        except Exception as exc:  # pragma: no cover - Streamlit error surface
            _show_error(exc)
            return

        st.text(doctor.format_doctor_report(report))
        _json_expander(report)


def _render_provider_help() -> None:
    with st.expander("Provider Help", expanded=False):
        st.caption(
            "Provider is configured through EMAIL_PROVIDER in .env. "
            "This section shows setup guidance only."
        )
        providers = email_providers.list_providers()
        provider_labels = [provider.display_name for provider in providers]
        selected_label = st.selectbox("Provider", provider_labels)
        selected_provider = providers[provider_labels.index(str(selected_label))]
        st.write(f"Key: `{selected_provider.key}`")
        st.write(f"IMAP host: `{selected_provider.imap_host or '(custom)'}`")
        st.write(f"IMAP port: `{selected_provider.imap_port}`")
        st.write(f"Default mailbox: `{selected_provider.default_mailbox}`")
        st.write(selected_provider.notes)
        if selected_provider.oauth_may_be_needed_later:
            st.info("OAuth may be needed later for some accounts. OAuth is not implemented yet.")


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


def _render_action_items() -> None:
    st.subheader("Action Items")
    priority = st.selectbox("Action priority", PRIORITY_OPTIONS)
    owner = st.text_input("Owner")
    limit = st.number_input("Action item limit", min_value=1, max_value=500, value=50, step=1)

    if st.button("Refresh action items"):
        _show_action_items(
            limit=int(limit),
            priority=None if priority == "All" else str(priority),
            owner=owner.strip() or None,
        )


def _show_action_items(
    *,
    limit: int,
    priority: str | None,
    owner: str | None,
) -> None:
    try:
        action_items = storage.list_action_items(
            limit=limit,
            priority=priority,
            owner=owner,
        )
    except Exception as exc:  # pragma: no cover - Streamlit error surface
        _show_error(exc)
        return

    if action_items:
        st.dataframe(
            [
                {
                    "text": item.get("text"),
                    "owner": item.get("owner"),
                    "due_date": item.get("due_date"),
                    "priority": item.get("priority"),
                    "subject": item.get("subject"),
                    "sender": item.get("sender"),
                    "category": item.get("category"),
                }
                for item in action_items
            ],
            use_container_width=True,
        )
        st.download_button(
            "Download CSV",
            data=action_items_to_csv(action_items),
            file_name="mailtriage_ai_action_items.csv",
            mime="text/csv",
        )
    else:
        st.info("No stored action items found.")

    with st.expander("Source email details"):
        st.text(email_assistant.format_action_items(action_items))
    _json_expander(action_items)


def _render_inbox_review() -> None:
    st.subheader("Run Inbox Review")
    max_messages = st.number_input(
        "Review max messages", min_value=1, max_value=50, value=10, step=1
    )
    mailbox = st.text_input("Review mailbox", value="INBOX")

    if st.button("Run inbox review"):
        try:
            inbox_review = review.run_inbox_review(
                max_messages=int(max_messages),
                mailbox=mailbox.strip() or "INBOX",
            )
        except Exception as exc:  # pragma: no cover - Streamlit error surface
            _show_error(exc)
            return

        st.text(review.format_inbox_review(inbox_review))
        action_items = inbox_review.get("action_items", [])
        if isinstance(action_items, list) and action_items:
            st.dataframe(action_items, use_container_width=True)
        else:
            st.info("No stored action items found.")
        _json_expander(inbox_review)


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


def action_items_to_csv(action_items: list[dict[str, object]]) -> str:
    fieldnames = [
        "text",
        "owner",
        "due_date",
        "priority",
        "message_id",
        "sender",
        "subject",
        "category",
        "requires_response",
        "fetched_at",
    ]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for item in action_items:
        writer.writerow({field: item.get(field, "") for field in fieldnames})
    return output.getvalue()


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
        return _imap_authentication_error_message()
    if "IMAP_" in message and "required" in message:
        return "Missing IMAP settings. Check your .env configuration."
    if "OPENAI_API_KEY" in message:
        return "OpenAI settings need attention. Check your .env configuration."
    if not message.strip():
        return "MailTriage AI could not complete that action."
    return message


def _imap_authentication_error_message() -> str:
    try:
        settings = load_imap_settings()
    except Exception:
        return email_providers.authentication_help("")
    return email_providers.authentication_help(settings.provider_key)


if __name__ == "__main__":
    main()
