"""Local Streamlit GUI for MailTriage AI."""

from __future__ import annotations

import csv
import io
import os
from collections.abc import Callable, MutableMapping
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
from config import (
    SEARCH_MODE_RECENT,
    SEARCH_MODE_UNREAD,
    load_imap_settings,
    search_mode_label,
)
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


def _session_state() -> MutableMapping[str, object]:
    return st.session_state


def _busy_key(name: str) -> str:
    return f"busy_{name}"


def _pending_key(name: str) -> str:
    return f"pending_{name}"


def _result_key(name: str) -> str:
    return f"result_{name}"


def _error_key(name: str) -> str:
    return f"error_{name}"


def _is_busy(name: str) -> bool:
    return bool(_session_state().get(_busy_key(name), False))


def _set_busy(name: str, value: bool) -> None:
    _session_state()[_busy_key(name)] = value


def _request_action(name: str) -> None:
    if _is_busy(name):
        return

    _set_busy(name, True)
    state = _session_state()
    state[_pending_key(name)] = True
    state.pop(_error_key(name), None)
    state.pop(_result_key(name), None)


def _request_validated_action(name: str, validation_error: str | None = None) -> None:
    if validation_error:
        _session_state()[_error_key(name)] = validation_error
        return
    _request_action(name)


def _has_pending_action(name: str) -> bool:
    return bool(_session_state().get(_pending_key(name), False))


def _clear_pending_action(name: str) -> None:
    _session_state()[_pending_key(name)] = False


def _execute_pending_action(name: str, spinner_message: str, callback: Callable[[], object]) -> None:
    if not _has_pending_action(name):
        return

    state = _session_state()
    try:
        with st.spinner(spinner_message):
            state[_result_key(name)] = callback()
            state.pop(_error_key(name), None)
    except Exception as exc:  # pragma: no cover - Streamlit error surface
        state[_error_key(name)] = _safe_error_message(exc)
    finally:
        _clear_pending_action(name)
        _set_busy(name, False)
        st.rerun()


def _render_action_state(
    name: str,
    render_result: Callable[[object], None],
    success_message: str | None = None,
) -> None:
    state = _session_state()
    error = state.get(_error_key(name))
    if error:
        st.error(str(error))

    result_key = _result_key(name)
    if result_key in state:
        render_result(state[result_key])
        if success_message:
            st.success(success_message)


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

    st.button(
        "Run setup check",
        disabled=_is_busy("setup_check"),
        on_click=_request_action,
        args=("setup_check",),
    )
    _execute_pending_action(
        "setup_check",
        "Checking setup...",
        lambda: doctor.run_doctor(skip_imap_login=skip_imap_login),
    )
    _render_action_state("setup_check", _render_doctor_result, "Setup check complete.")


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
    provider_key = _selected_provider_key()
    max_messages = st.number_input("Max messages", min_value=1, max_value=50, value=5, step=1)
    mailbox_preset, custom_mailbox = _mailbox_inputs("fetch", provider_key)
    search_mode = _search_mode_input("fetch")
    save_cards = st.checkbox("Save summary cards to local database", value=False)

    st.button(
        f"Fetch {search_mode_label(search_mode).lower()}",
        disabled=_is_busy("fetch_emails"),
        on_click=_request_action,
        args=("fetch_emails",),
    )
    fetch_message = (
        "Fetching recent messages read-only..."
        if search_mode == SEARCH_MODE_RECENT
        else "Fetching unread emails read-only..."
    )
    _execute_pending_action(
        "fetch_emails",
        fetch_message,
        lambda: _fetch_email_cards(
            int(max_messages),
            _effective_mailbox(mailbox_preset, custom_mailbox),
            search_mode,
            save_cards,
        ),
    )
    _render_action_state("fetch_emails", _render_fetch_result, "Fetch complete.")


def _render_summary_cards() -> None:
    st.subheader("Summary Cards")
    priority = st.selectbox("Priority", PRIORITY_OPTIONS)
    category = st.selectbox("Category", CATEGORY_OPTIONS)
    requires_response = st.checkbox("Requires response", value=False)
    limit = st.number_input("Limit", min_value=1, max_value=200, value=20, step=1)

    st.button(
        "Refresh summary cards",
        disabled=_is_busy("summary_cards"),
        on_click=_request_action,
        args=("summary_cards",),
    )
    _execute_pending_action(
        "summary_cards",
        "Loading stored summary cards...",
        lambda: _load_summary_cards(
            limit=int(limit),
            priority=None if priority == "All" else str(priority),
            category=None if category == "All" else str(category),
            requires_response=True if requires_response else None,
        ),
    )
    _render_action_state("summary_cards", _render_summary_cards_result, "Summary cards loaded.")


def _load_summary_cards(
    *,
    limit: int,
    priority: str | None,
    category: str | None,
    requires_response: bool | None,
) -> list[dict[str, object]]:
    return storage.list_cards(
        limit=limit,
        priority=priority,
        category=category,
        requires_response=requires_response,
    )


def _render_action_items() -> None:
    st.subheader("Action Items")
    priority = st.selectbox("Action priority", PRIORITY_OPTIONS)
    owner = st.text_input("Owner")
    limit = st.number_input("Action item limit", min_value=1, max_value=500, value=50, step=1)

    st.button(
        "Refresh action items",
        disabled=_is_busy("action_items"),
        on_click=_request_action,
        args=("action_items",),
    )
    _execute_pending_action(
        "action_items",
        "Loading stored action items...",
        lambda: _load_action_items(
            limit=int(limit),
            priority=None if priority == "All" else str(priority),
            owner=owner.strip() or None,
        ),
    )
    _render_action_state("action_items", _render_action_items_result, "Action items loaded.")


def _load_action_items(
    *,
    limit: int,
    priority: str | None,
    owner: str | None,
) -> list[dict[str, object]]:
    return storage.list_action_items(
        limit=limit,
        priority=priority,
        owner=owner,
    )


def _render_action_items_result(result: object) -> None:
    action_items = result if isinstance(result, list) else []
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
    provider_key = _selected_provider_key()
    max_messages = st.number_input(
        "Review max messages", min_value=1, max_value=50, value=10, step=1
    )
    mailbox_preset, custom_mailbox = _mailbox_inputs("review", provider_key)
    search_mode = _search_mode_input("review")

    st.button(
        "Run inbox review",
        disabled=_is_busy("inbox_review"),
        on_click=_request_action,
        args=("inbox_review",),
    )
    _execute_pending_action(
        "inbox_review",
        "Reviewing inbox read-only...",
        lambda: _run_inbox_review(
            max_messages=int(max_messages),
            mailbox=_effective_mailbox(mailbox_preset, custom_mailbox),
            search_mode=search_mode,
        ),
    )
    _render_action_state("inbox_review", _render_inbox_review_result, "Inbox review complete.")


def _render_daily_briefing() -> None:
    st.subheader("Daily Briefing")
    limit = st.number_input("Briefing limit", min_value=1, max_value=200, value=20, step=1)

    st.button(
        "Generate briefing",
        disabled=_is_busy("daily_briefing"),
        on_click=_request_action,
        args=("daily_briefing",),
    )
    _execute_pending_action(
        "daily_briefing",
        "Generating briefing from stored summary cards...",
        lambda: daily_briefing.generate_daily_briefing(limit=int(limit)),
    )
    _render_action_state("daily_briefing", _render_briefing_result, "Briefing generated.")


def _render_ask_inbox() -> None:
    st.subheader("Ask Inbox")
    question = st.text_input("Question")
    limit = st.number_input("Answer limit", min_value=1, max_value=200, value=20, step=1)
    use_ai = st.checkbox("Use AI for answer", value=False)
    if use_ai:
        st.caption("Only matched stored summary cards are sent to OpenAI, not raw email bodies.")

    st.button(
        "Ask",
        disabled=_is_busy("ask_inbox"),
        on_click=_request_validated_action,
        args=("ask_inbox", None if question.strip() else "Enter a question first."),
    )
    ask_message = (
        "Searching stored summary cards and generating AI answer..."
        if use_ai
        else "Searching stored summary cards..."
    )
    _execute_pending_action(
        "ask_inbox",
        ask_message,
        lambda: inbox_qa.answer_inbox_question(
            question.strip(),
            limit=int(limit),
            use_ai=use_ai,
        ),
    )
    _render_action_state("ask_inbox", _render_answer_result, "Answer generated.")


def _render_manual_analyze() -> None:
    st.subheader("Manual Analyze")
    sender = st.text_input("Sender")
    subject = st.text_input("Subject")
    body = st.text_area("Body", height=240)

    st.button(
        "Analyze",
        disabled=_is_busy("manual_analyze"),
        on_click=_request_validated_action,
        args=("manual_analyze", None if body.strip() else "Paste an email body first."),
    )
    _execute_pending_action(
        "manual_analyze",
        "Analyzing pasted email...",
        lambda: analyzer.analyze_email(
            EmailMessage(sender=sender.strip(), subject=subject.strip(), body=body.strip())
        ),
    )
    _render_action_state("manual_analyze", _render_analysis_result, "Analysis complete.")


def _fetch_email_cards(
    max_messages: int, mailbox: str, search_mode: str, save_cards: bool
) -> dict[str, object]:
    settings = load_imap_settings()
    settings = replace(
        settings,
        max_messages=max_messages,
        mailbox=mailbox.strip() or "INBOX",
        search_mode=search_mode,
    )
    cards = fetch_imap.fetch_inbox_summary_cards(settings)
    if save_cards:
        storage.save_summary_cards(cards)
    return {"cards": cards, "search_mode": settings.search_mode}


def _run_inbox_review(max_messages: int, mailbox: str, search_mode: str) -> dict[str, object]:
    return review.run_inbox_review(
        max_messages=max_messages,
        mailbox=mailbox,
        search_mode=search_mode,
    )


def _selected_provider_key() -> str:
    try:
        return load_imap_settings().provider_key
    except Exception:
        return os.getenv("EMAIL_PROVIDER", "icloud").strip().lower() or "icloud"


def _mailbox_inputs(prefix: str, provider_key: str) -> tuple[str, str]:
    presets = email_providers.mailbox_presets(provider_key)
    selected = st.selectbox(
        "Mailbox preset",
        presets,
        index=_mailbox_preset_index(presets, email_providers.default_mailbox(provider_key)),
        key=f"{prefix}_mailbox_preset",
    )
    custom = st.text_input(
        "Custom mailbox override",
        value="",
        key=f"{prefix}_custom_mailbox",
        placeholder="Optional exact mailbox name",
    )
    st.caption(
        "Folder names vary by provider. If the preset does not work, type the exact "
        "mailbox name from your email provider."
    )
    return str(selected), custom


def _search_mode_input(prefix: str) -> str:
    labels = [search_mode_label(SEARCH_MODE_UNREAD), search_mode_label(SEARCH_MODE_RECENT)]
    selected_label = st.selectbox("Search mode", labels, key=f"{prefix}_search_mode")
    return _search_mode_value(str(selected_label))


def _search_mode_value(label: str) -> str:
    if label == search_mode_label(SEARCH_MODE_RECENT):
        return SEARCH_MODE_RECENT
    return SEARCH_MODE_UNREAD


def _mailbox_preset_index(presets: list[str], default: str) -> int:
    try:
        return presets.index(default)
    except ValueError:
        return 0


def _effective_mailbox(selected_preset: str, custom_override: str) -> str:
    custom = custom_override.strip()
    if custom:
        return custom
    return selected_preset.strip() or "INBOX"


def _render_doctor_result(result: object) -> None:
    report = result if isinstance(result, dict) else {}
    st.text(doctor.format_doctor_report(report))
    _json_expander(report)


def _render_fetch_result(result: object) -> None:
    if isinstance(result, dict):
        cards = result.get("cards", [])
        search_mode = str(result.get("search_mode") or SEARCH_MODE_UNREAD)
    else:
        cards = result if isinstance(result, list) else []
        search_mode = SEARCH_MODE_UNREAD
    if not isinstance(cards, list):
        cards = []
    st.text(email_assistant.format_cards(cards, search_mode))
    _json_expander(result)


def _render_summary_cards_result(result: object) -> None:
    cards = result if isinstance(result, list) else []
    st.text(email_assistant.format_stored_cards(cards))
    _json_expander(cards)


def _render_inbox_review_result(result: object) -> None:
    inbox_review = result if isinstance(result, dict) else {}
    st.text(review.format_inbox_review(inbox_review))
    action_items = inbox_review.get("action_items", [])
    if isinstance(action_items, list) and action_items:
        st.dataframe(action_items, use_container_width=True)
    else:
        st.info("No stored action items found.")
    _json_expander(inbox_review)


def _render_briefing_result(result: object) -> None:
    briefing = result if isinstance(result, dict) else {}
    st.text(email_assistant.format_briefing(briefing))
    _json_expander(briefing)


def _render_answer_result(result: object) -> None:
    answer = result if isinstance(result, dict) else {}
    st.text(email_assistant.format_answer(answer))
    _json_expander(answer)


def _render_analysis_result(result: object) -> None:
    st.text(email_assistant.format_analysis(result))
    _json_expander(result)


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
