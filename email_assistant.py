"""Customer-friendly CLI wrapper for MailTriage AI."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass, replace
from typing import Sequence

import analyzer
import daily_briefing
import doctor
import email_providers
import fetch_imap
import inbox_qa
import review
import storage
from config import load_imap_settings
from triage import EmailMessage


SAFETY_NOTE = "No email was sent or modified."
PRIORITY_CHOICES = ("low", "normal", "high", "urgent")
CATEGORY_CHOICES = ("billing", "scheduling", "support", "sales", "personal", "newsletter", "other")


def print_json(data: object) -> None:
    print(json.dumps(_jsonable(data), indent=2))


def format_cards(cards: list[dict[str, object]]) -> str:
    if not cards:
        return "No unread emails were found.\n\nNo email was sent or modified."

    lines = [f"Fetched {len(cards)} summary card(s).", ""]
    for index, card in enumerate(cards, start=1):
        lines.extend(
            [
                f"{index}. {card.get('subject') or '(no subject)'}",
                f"   From: {card.get('sender') or '(unknown sender)'}",
                f"   Priority: {card.get('priority') or 'normal'}",
                f"   Category: {card.get('category') or 'other'}",
                f"   Requires response: {_yes_no(card.get('requires_response'))}",
                f"   Summary: {card.get('summary') or '(no summary)'}",
            ]
        )
        action_items = card.get("action_items", [])
        if isinstance(action_items, list) and action_items:
            lines.append("   Action items:")
            for item in action_items:
                lines.append(f"   - {_format_action_item(item)}")
        else:
            lines.append("   Action items: None")
        lines.append("")

    lines.append(SAFETY_NOTE)
    return "\n".join(lines)


def format_stored_cards(cards: list[dict[str, object]]) -> str:
    if not cards:
        return "No stored summary cards found.\n\nNo email was fetched or modified."

    lines = [f"Stored summary cards: {len(cards)}", ""]
    for index, card in enumerate(cards, start=1):
        lines.extend(_format_card_lines(index, card))
        lines.append("")

    lines.append("No email was fetched or modified.")
    return "\n".join(lines)


def format_action_items(action_items: list[dict[str, object]]) -> str:
    if not action_items:
        return "No stored action items found.\n\nNo email was fetched or modified."

    lines = [f"Stored action items: {len(action_items)}", ""]
    for index, item in enumerate(action_items, start=1):
        due_date = item.get("due_date") or "none"
        lines.extend(
            [
                f"{index}. {item.get('text') or '(no action text)'}",
                f"   Owner: {item.get('owner') or 'me'}",
                f"   Priority: {item.get('priority') or 'normal'}",
                f"   Due date: {due_date}",
                f"   Source: {item.get('subject') or '(no subject)'}",
                f"   From: {item.get('sender') or '(unknown sender)'}",
                f"   Category: {item.get('category') or 'other'}",
                f"   Requires response: {_yes_no(item.get('requires_response'))}",
            ]
        )
        lines.append("")

    lines.append("No email was fetched or modified.")
    return "\n".join(lines)


def format_briefing(briefing: dict[str, object]) -> str:
    lines = [
        "Daily Briefing",
        f"Total emails reviewed: {briefing.get('total_emails_reviewed', 0)}",
        f"Urgent: {briefing.get('urgent_count', 0)}",
        f"High priority: {briefing.get('high_priority_count', 0)}",
        f"Need response: {briefing.get('requires_response_count', 0)}",
        "",
        "Categories:",
    ]

    categories = briefing.get("categories", {})
    if isinstance(categories, dict) and categories:
        for category, count in sorted(categories.items()):
            lines.append(f"- {category}: {count}")
    else:
        lines.append("- None")

    lines.extend(["", "Suggested Focus:"])
    _append_list(lines, briefing.get("suggested_focus", []))

    lines.extend(["", "Top Action Items:"])
    _append_action_items(lines, briefing.get("top_action_items", []))

    lines.extend(["", "Important Emails:"])
    _append_cards(lines, briefing.get("important_emails", []))

    lines.extend(["", str(briefing.get("safety_note") or "No email was fetched or modified.")])
    return "\n".join(lines)


def format_answer(answer: dict[str, object]) -> str:
    lines = [
        str(answer.get("answer") or ""),
        "",
        f"Answer mode: {answer.get('answer_mode') or 'deterministic'}",
        f"Matched count: {answer.get('matched_count', 0)}",
        "",
        "Matches:",
    ]
    matches = answer.get("matches", [])
    if isinstance(matches, list) and matches:
        for index, match in enumerate(matches, start=1):
            if not isinstance(match, dict):
                continue
            lines.extend(
                [
                    f"{index}. {match.get('subject') or '(no subject)'}",
                    f"   From: {match.get('sender') or '(unknown sender)'}",
                    f"   Priority: {match.get('priority') or 'normal'}",
                    f"   Category: {match.get('category') or 'other'}",
                    f"   Requires response: {_yes_no(match.get('requires_response'))}",
                    f"   Summary: {match.get('summary') or '(no summary)'}",
                ]
            )
            action_items = match.get("action_items", [])
            if isinstance(action_items, list) and action_items:
                lines.append("   Action items:")
                for item in action_items:
                    lines.append(f"   - {_format_action_item(item)}")
            lines.append("")
    else:
        lines.append("- None")

    lines.append(str(answer.get("safety_note") or "Answered from stored summary cards only."))
    return "\n".join(lines)


def format_analysis(analysis: object) -> str:
    data = _jsonable(analysis)
    if not isinstance(data, dict):
        return str(data)

    lines = [
        "Email Analysis",
        f"Summary: {data.get('summary') or '(no summary)'}",
        f"Sender intent: {data.get('sender_intent') or '(unknown)'}",
        f"Priority: {data.get('priority') or 'normal'}",
        f"Category: {data.get('category') or 'other'}",
        f"Requires response: {_yes_no(data.get('requires_response'))}",
        "",
        "Action items:",
    ]
    _append_action_items(lines, data.get("action_items", []))
    lines.extend(
        [
            "",
            "Suggested reply:",
            str(data.get("suggested_reply") or "No reply needed."),
            "",
            str(data.get("safety_note") or "Draft only. No email was sent."),
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "fetch":
            return _run_fetch(args)
        if args.command == "briefing":
            return _run_briefing(args)
        if args.command == "ask":
            return _run_ask(args)
        if args.command == "analyze":
            return _run_analyze(args)
        if args.command == "doctor":
            return _run_doctor(args)
        if args.command == "list":
            return _run_list(args)
        if args.command == "actions":
            return _run_actions(args)
        if args.command == "review":
            return _run_review(args)
        if args.command == "providers":
            return _run_providers(args)
        if args.command == "mailboxes":
            return _run_mailboxes(args)
    except ValueError as exc:
        _print_friendly_error(exc)
        return 2
    except RuntimeError as exc:
        _print_friendly_error(exc)
        return 2

    parser.print_help()
    return 2


def _run_fetch(args: argparse.Namespace) -> int:
    settings = load_imap_settings()
    if args.max_messages is not None:
        settings = replace(settings, max_messages=args.max_messages)
    if args.mailbox is not None:
        settings = replace(settings, mailbox=args.mailbox)

    cards = fetch_imap.fetch_inbox_summary_cards(settings)
    if args.save:
        storage.init_db()
        storage.save_summary_cards(cards)

    if args.json:
        print_json(cards)
    else:
        print(format_cards(cards))
    return 0


def _run_briefing(args: argparse.Namespace) -> int:
    briefing = daily_briefing.generate_daily_briefing(limit=args.limit)
    if args.json:
        print_json(briefing)
    else:
        print(format_briefing(briefing))
    return 0


def _run_ask(args: argparse.Namespace) -> int:
    answer = inbox_qa.answer_inbox_question(
        args.question,
        limit=args.limit,
        use_ai=args.ai,
    )
    if args.json:
        print_json(answer)
    else:
        print(format_answer(answer))
    return 0


def _run_analyze(args: argparse.Namespace) -> int:
    body = args.body if args.body is not None else sys.stdin.read()
    email = EmailMessage(sender=args.sender, subject=args.subject, body=body.strip())
    analysis = analyzer.analyze_email(email)
    if args.json:
        print_json(analysis)
    else:
        print(format_analysis(analysis))
    return 0


def _run_doctor(args: argparse.Namespace) -> int:
    report = doctor.run_doctor(skip_imap_login=args.skip_imap_login)
    if args.json:
        print_json(report)
    else:
        print(doctor.format_doctor_report(report))
    return 0


def _run_list(args: argparse.Namespace) -> int:
    cards = storage.list_cards(
        limit=args.limit,
        priority=args.priority,
        category=args.category,
        requires_response=True if args.requires_response else None,
    )
    if args.json:
        print_json(cards)
    else:
        print(format_stored_cards(cards))
    return 0


def _run_actions(args: argparse.Namespace) -> int:
    action_items = storage.list_action_items(
        limit=args.limit,
        priority=args.priority,
        owner=args.owner,
    )
    if args.json:
        print_json(action_items)
    else:
        print(format_action_items(action_items))
    return 0


def _run_review(args: argparse.Namespace) -> int:
    inbox_review = review.run_inbox_review(
        max_messages=args.max_messages,
        mailbox=args.mailbox,
    )
    if args.json:
        print_json(inbox_review)
    else:
        print(review.format_inbox_review(inbox_review))
    return 0


def _run_providers(args: argparse.Namespace) -> int:
    providers = [provider.to_dict() for provider in email_providers.list_providers()]
    if args.json:
        print_json(providers)
    else:
        print(format_providers(providers))
    return 0


def format_providers(providers: list[dict[str, object]]) -> str:
    lines = ["Supported IMAP Providers", ""]
    for provider in providers:
        lines.extend(
            [
                f"- {provider.get('display_name')} ({provider.get('key')})",
                f"  Host: {provider.get('imap_host') or '(custom)'}",
                f"  Port: {provider.get('imap_port')}",
                f"  Mailbox: {provider.get('default_mailbox')}",
                f"  Notes: {provider.get('notes')}",
            ]
        )
        if provider.get("oauth_may_be_needed_later"):
            lines.append("  OAuth note: OAuth may be needed later for some accounts.")
        lines.append("")
    lines.append("No email was fetched or modified.")
    return "\n".join(lines)


def _run_mailboxes(args: argparse.Namespace) -> int:
    mailboxes = email_providers.mailbox_presets(args.provider)
    data = {
        "provider": args.provider,
        "mailboxes": mailboxes,
        "safety_note": "No email was fetched or modified.",
    }
    if args.json:
        print_json(data)
    else:
        print(format_mailboxes(data))
    return 0


def format_mailboxes(data: dict[str, object]) -> str:
    provider = str(data.get("provider") or "icloud")
    lines = [f"Suggested mailboxes for {provider}:", ""]
    mailboxes = data.get("mailboxes", [])
    if isinstance(mailboxes, list):
        for mailbox in mailboxes:
            lines.append(f"- {mailbox}")
    lines.extend(
        [
            "",
            "Mailbox/folder names vary by provider. If a preset does not work, use the exact mailbox name shown by your email provider.",
            str(data.get("safety_note") or "No email was fetched or modified."),
        ]
    )
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="MailTriage AI read-only CLI for fetching, briefing, asking, and analyzing."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser("fetch", help="Fetch unread emails as summary cards.")
    fetch_parser.add_argument("--max-messages", type=fetch_imap._parse_max_messages, default=None)
    fetch_parser.add_argument("--mailbox", default=None)
    fetch_parser.add_argument("--save", action="store_true")
    fetch_parser.add_argument("--json", action="store_true")

    briefing_parser = subparsers.add_parser(
        "briefing", help="Generate a briefing from stored summary cards."
    )
    briefing_parser.add_argument("--limit", type=int, default=20)
    briefing_parser.add_argument("--json", action="store_true")

    ask_parser = subparsers.add_parser("ask", help="Ask a question over stored summary cards.")
    ask_parser.add_argument("question")
    ask_parser.add_argument("--limit", type=int, default=20)
    ask_parser.add_argument("--ai", action="store_true")
    ask_parser.add_argument("--json", action="store_true")

    analyze_parser = subparsers.add_parser("analyze", help="Analyze one email without sending it.")
    analyze_parser.add_argument("--from", dest="sender", default="", help="Sender email address")
    analyze_parser.add_argument("--subject", default="", help="Email subject")
    analyze_parser.add_argument("--body", default=None, help="Email body. Defaults to stdin.")
    analyze_parser.add_argument("--json", action="store_true")

    doctor_parser = subparsers.add_parser("doctor", help="Check local setup without touching email.")
    doctor_parser.add_argument("--json", action="store_true")
    doctor_parser.add_argument("--skip-imap-login", action="store_true")

    list_parser = subparsers.add_parser("list", help="Browse stored summary cards.")
    list_parser.add_argument("--priority", choices=PRIORITY_CHOICES)
    list_parser.add_argument("--category", choices=CATEGORY_CHOICES)
    list_parser.add_argument("--requires-response", action="store_true")
    list_parser.add_argument("--limit", type=int, default=20)
    list_parser.add_argument("--json", action="store_true")

    actions_parser = subparsers.add_parser("actions", help="Browse stored action items.")
    actions_parser.add_argument("--priority", choices=PRIORITY_CHOICES)
    actions_parser.add_argument("--owner", default=None)
    actions_parser.add_argument("--limit", type=int, default=50)
    actions_parser.add_argument("--json", action="store_true")

    review_parser = subparsers.add_parser(
        "review", help="Fetch, save, brief, and summarize action items in one step."
    )
    review_parser.add_argument("--max-messages", type=fetch_imap._parse_max_messages, default=10)
    review_parser.add_argument("--mailbox", default="INBOX")
    review_parser.add_argument("--json", action="store_true")

    providers_parser = subparsers.add_parser(
        "providers", help="List supported IMAP provider presets."
    )
    providers_parser.add_argument("--json", action="store_true")

    mailboxes_parser = subparsers.add_parser(
        "mailboxes", help="List suggested mailbox names without connecting to IMAP."
    )
    mailboxes_parser.add_argument(
        "--provider",
        choices=email_providers.provider_choices(),
        default="icloud",
    )
    mailboxes_parser.add_argument("--json", action="store_true")

    return parser


def _jsonable(data: object) -> object:
    if is_dataclass(data) and not isinstance(data, type):
        return asdict(data)
    if isinstance(data, list):
        return [_jsonable(item) for item in data]
    if isinstance(data, dict):
        return {key: _jsonable(value) for key, value in data.items()}
    return data


def _append_list(lines: list[str], items: object) -> None:
    if isinstance(items, list) and items:
        for item in items:
            lines.append(f"- {item}")
    else:
        lines.append("- None")


def _append_action_items(lines: list[str], items: object) -> None:
    if isinstance(items, list) and items:
        for item in items:
            lines.append(f"- {_format_action_item(item)}")
    else:
        lines.append("- None")


def _append_cards(lines: list[str], cards: object) -> None:
    if isinstance(cards, list) and cards:
        for card in cards:
            if isinstance(card, dict):
                lines.append(
                    f"- {card.get('subject') or '(no subject)'} from "
                    f"{card.get('sender') or '(unknown sender)'} "
                    f"({card.get('priority') or 'normal'}, {card.get('category') or 'other'})"
                )
    else:
        lines.append("- None")


def _format_card_lines(index: int, card: dict[str, object]) -> list[str]:
    lines = [
        f"{index}. {card.get('subject') or '(no subject)'}",
        f"   From: {card.get('sender') or '(unknown sender)'}",
        f"   Priority: {card.get('priority') or 'normal'}",
        f"   Category: {card.get('category') or 'other'}",
        f"   Requires response: {_yes_no(card.get('requires_response'))}",
        f"   Summary: {card.get('summary') or '(no summary)'}",
    ]
    action_items = card.get("action_items", [])
    if isinstance(action_items, list) and action_items:
        lines.append("   Action items:")
        for item in action_items:
            lines.append(f"   - {_format_action_item(item)}")
    else:
        lines.append("   Action items: None")
    return lines


def _format_action_item(item: object) -> str:
    if not isinstance(item, dict):
        return str(item)

    text = str(item.get("text") or "").strip() or "(no action text)"
    owner = str(item.get("owner") or "").strip()
    due_date = str(item.get("due_date") or "").strip()
    priority = str(item.get("priority") or "").strip()
    details = []
    if owner:
        details.append(f"owner: {owner}")
    if due_date:
        details.append(f"due: {due_date}")
    if priority:
        details.append(f"priority: {priority}")
    if details:
        return f"{text} ({', '.join(details)})"
    return text


def _yes_no(value: object) -> str:
    return "yes" if bool(value) else "no"


def _print_friendly_error(exc: Exception) -> None:
    message = str(exc)
    if "IMAP authentication failed" in message:
        safe_message = (
            "IMAP authentication failed. Check your username and app-specific password."
        )
    elif "IMAP_" in message and "required" in message:
        safe_message = "Missing IMAP settings. Check your .env configuration."
    elif "No such file" in message or "unable to open database" in message:
        safe_message = "No stored summary cards were found yet. Run fetch with --save first."
    else:
        safe_message = "MailTriage AI could not complete that command."

    print(f"Error: {safe_message}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
