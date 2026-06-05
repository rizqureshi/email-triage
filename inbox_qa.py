"""Inbox Q&A over stored email summary cards."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter

import storage


def answer_inbox_question(
    question: str, limit: int = 20, db_path: str | None = None
) -> dict[str, object]:
    normalized_question = _normalize(question)
    if not normalized_question:
        return {
            "question": question,
            "answer": "Please ask a question about the stored summary cards.",
            "matched_count": 0,
            "matches": [],
            "safety_note": "Answered from stored summary cards only. No email was fetched or modified.",
        }

    matches = search_cards(question, limit=limit, db_path=db_path)
    if not matches:
        return {
            "question": question,
            "answer": "I couldn’t find any matching stored summary cards.",
            "matched_count": 0,
            "matches": [],
            "safety_note": "Answered from stored summary cards only. No email was fetched or modified.",
        }

    answer = _compose_answer(normalized_question, matches)
    return {
        "question": question,
        "answer": answer,
        "matched_count": len(matches),
        "matches": [_compact_match(card) for card in matches],
        "safety_note": "Answered from stored summary cards only. No email was fetched or modified.",
    }


def search_cards(
    question: str, limit: int = 20, db_path: str | None = None
) -> list[dict[str, object]]:
    normalized_question = _normalize(question)
    if not normalized_question or limit <= 0:
        return []

    stored_cards = storage.list_recent_cards(limit=max(limit * 5, limit, 20), db_path=db_path)
    if not stored_cards:
        return []

    intent = _detect_intent(normalized_question)
    terms = _question_terms(normalized_question)
    matches: list[tuple[int, dict[str, object]]] = []

    for card in stored_cards:
        score = _score_card(card, intent=intent, terms=terms)
        if score <= 0:
            continue
        matches.append((score, card))

    matches.sort(
        key=lambda item: (
            item[0],
            _priority_rank(str(item[1].get("priority") or "normal")),
            str(item[1].get("fetched_at") or ""),
        ),
        reverse=True,
    )
    return [card for _, card in matches[:limit]]


def _compose_answer(question: str, matches: list[dict[str, object]]) -> str:
    if _is_catch_up_question(question):
        total = len(matches)
        urgent = sum(1 for card in matches if card.get("priority") == "urgent")
        needs_response = sum(1 for card in matches if card.get("requires_response"))
        categories = Counter(str(card.get("category") or "other") for card in matches)
        top_category = categories.most_common(1)[0][0] if categories else "other"
        return (
            f"You have {total} recent stored summary card(s). "
            f"{urgent} are urgent, {needs_response} appear to need a response, and "
            f"the most common category is {top_category}."
        )

    if _asks_for_action_items(question):
        items = _aggregate_action_items(matches)
        if not items:
            return "I found matching emails, but there were no action items stored for them."
        return f"I found {len(items)} action item(s) across the matching emails."

    if _asks_for_response(question):
        need_response = sum(1 for card in matches if card.get("requires_response"))
        if need_response:
            return f"{need_response} matching email(s) appear to need your response."
        return "I found matching emails, but none are marked as requiring a response."

    if _asks_for_priority(question):
        top = matches[0]
        return (
            f"I found {len(matches)} matching email(s). The top result is "
            f"{top.get('subject')} from {top.get('sender')}."
        )

    top = matches[0]
    return (
        f"I found {len(matches)} matching email(s). The top match is "
        f"{top.get('subject')} from {top.get('sender')}."
    )


def _score_card(card: dict[str, object], *, intent: str, terms: list[str]) -> int:
    score = 0
    fields = _card_search_text(card)
    sender = _normalize(card.get("sender"))
    subject = _normalize(card.get("subject"))
    summary = _normalize(card.get("summary"))
    sender_intent = _normalize(card.get("sender_intent"))
    category = _normalize(card.get("category"))
    priority = _normalize(card.get("priority"))

    if intent == "catch_up":
        return 1
    if intent == "response" and card.get("requires_response"):
        score += 6
    if intent == "urgent":
        if priority != "urgent":
            return 0
        score += 100
    elif intent == "high_priority":
        if priority == "urgent":
            score += 100
        elif priority == "high":
            score += 90
    if intent == "action_items" and card.get("action_items"):
        score += 4

    for term in terms:
        if term and _matches_term(sender, term):
            score += 4
        if term and _matches_term(subject, term):
            score += 4
        if term and _matches_term(summary, term):
            score += 3
        if term and _matches_term(sender_intent, term):
            score += 3
        if term and _matches_term(category, term):
            score += 3
        if term and _matches_term(priority, term):
            score += 2
        if term and _matches_term(fields, term):
            score += 1

    if _asks_about_action_items(_normalize(card.get("summary")), terms):
        score += 1

    if card.get("requires_response") and intent == "response":
        score += 2

    return score


def _card_search_text(card: dict[str, object]) -> str:
    parts = [
        str(card.get("sender") or ""),
        str(card.get("subject") or ""),
        str(card.get("summary") or ""),
        str(card.get("sender_intent") or ""),
        str(card.get("category") or ""),
        str(card.get("priority") or ""),
    ]
    action_items = card.get("action_items", [])
    if isinstance(action_items, list):
        for item in action_items:
            if isinstance(item, dict):
                parts.extend(
                    [
                        str(item.get("text") or ""),
                        str(item.get("owner") or ""),
                        str(item.get("due_date") or ""),
                    ]
                )
    return _normalize(" ".join(parts))


def _aggregate_action_items(cards: list[dict[str, object]]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    seen: set[tuple[str, str, str | None, str]] = set()
    for card in cards:
        action_items = card.get("action_items", [])
        if not isinstance(action_items, list):
            continue
        for item in action_items:
            normalized = _normalize_action_item(item)
            if normalized is None:
                continue
            key = (
                normalized["text"],
                normalized["owner"],
                normalized["due_date"],
                normalized["priority"],
            )
            if key in seen:
                continue
            seen.add(key)
            items.append(normalized)
    return items


def _compact_match(card: dict[str, object]) -> dict[str, object]:
    return {
        "message_id": card.get("message_id"),
        "sender": card.get("sender"),
        "subject": card.get("subject"),
        "priority": card.get("priority"),
        "category": card.get("category"),
        "requires_response": bool(card.get("requires_response")),
        "summary": card.get("summary"),
        "action_items": card.get("action_items", []),
    }


def _normalize_action_item(item: object) -> dict[str, str | None] | None:
    if not isinstance(item, dict):
        text = str(item).strip()
        if not text:
            return None
        return {
            "text": text,
            "owner": "me",
            "due_date": None,
            "priority": "normal",
        }

    text = str(item.get("text") or "").strip()
    if not text:
        return None

    owner = str(item.get("owner") or "").strip() or "me"
    due_date = str(item.get("due_date") or "").strip() or None
    priority = str(item.get("priority") or "").strip() or "normal"
    return {
        "text": text,
        "owner": owner,
        "due_date": due_date,
        "priority": priority,
    }


def _detect_intent(question: str) -> str:
    if _is_catch_up_question(question):
        return "catch_up"
    if _asks_for_response(question):
        return "response"
    if _asks_for_urgent(question):
        return "urgent"
    if _asks_for_priority(question):
        return "high_priority"
    if _asks_for_action_items(question):
        return "action_items"
    return "general"


def _asks_for_response(question: str) -> bool:
    return any(
        phrase in question
        for phrase in (
            "need my response",
            "need a response",
            "need to respond",
            "need replying",
            "what emails need",
            "what needs a response",
            "what should i reply to",
            "reply to",
            "response",
            "respond",
        )
    )


def _asks_for_priority(question: str) -> bool:
    return any(
        phrase in question
        for phrase in (
            "high priority",
            "priority",
            "important emails",
        )
    )


def _asks_for_urgent(question: str) -> bool:
    return "urgent" in question


def _asks_for_action_items(question: str) -> bool:
    return "action item" in question or "action items" in question


def _is_catch_up_question(question: str) -> bool:
    return any(
        phrase in question
        for phrase in (
            "catch me up",
            "catch me up on email",
            "catch me up on inbox",
            "summarize emails",
            "what did i miss",
            "give me a briefing",
            "overview",
            "catch up",
        )
    )


def _question_terms(question: str) -> list[str]:
    stopwords = {
        "what",
        "emails",
        "email",
        "need",
        "my",
        "me",
        "do",
        "i",
        "have",
        "any",
        "show",
        "about",
        "from",
        "the",
        "a",
        "an",
        "to",
        "on",
        "of",
        "for",
        "please",
        "catch",
        "up",
        "summarize",
        "summary",
        "does",
        "did",
        "said",
        "tell",
        "give",
        "all",
        "need",
        "response",
        "respond",
    }
    terms = re.findall(r"[a-z0-9]+", question.lower())
    return [term for term in terms if term not in stopwords]


def _normalize(value: object) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value).lower()))


def _matches_term(text: str, term: str) -> bool:
    if not term:
        return False
    if term in text:
        return True
    if term.endswith("s") and term[:-1] in text:
        return True
    if f"{term}s" in text:
        return True
    return False


def _priority_rank(priority: str) -> int:
    order = {
        "urgent": 4,
        "high": 3,
        "normal": 2,
        "low": 1,
    }
    return order.get(priority, 2)


def _asks_about_action_items(summary: str, terms: list[str]) -> bool:
    if not terms:
        return False
    return "action" in summary or "todo" in summary or "follow up" in summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Answer inbox questions from stored summary cards."
    )
    parser.add_argument("question", help="Question about stored inbox summary cards.")
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of recent stored cards to search.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    answer = answer_inbox_question(args.question, limit=args.limit)
    print(json.dumps(answer, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
