from unittest.mock import Mock

import pytest
import requests

import fetch_graph
from schemas import EmailAnalysis
from triage import EmailMessage


def make_graph_message(
    message_id: str = "message-1",
    body_preview: str = "Short preview",
    body: str = "",
) -> dict[str, object]:
    return {
        "id": message_id,
        "subject": "Invoice question",
        "from": {"emailAddress": {"name": "Alex", "address": "alex@example.com"}},
        "sender": {"emailAddress": {"address": "sender@example.com"}},
        "bodyPreview": body_preview,
        "body": {"content": body},
        "isRead": False,
    }


def test_fetch_graph_source_has_no_mail_modifying_graph_calls() -> None:
    source = fetch_graph.__loader__.get_source(fetch_graph.__name__)  # type: ignore[union-attr]

    assert "sendMail" not in source
    assert "markAsRead" not in source
    assert "requests.post" not in source
    assert "requests.patch" not in source
    assert "requests.delete" not in source
    assert "/move" not in source
    assert "/copy" not in source


def test_graph_folder_id_for_mailbox_maps_common_aliases() -> None:
    assert fetch_graph.graph_folder_id_for_mailbox("INBOX") == "inbox"
    assert fetch_graph.graph_folder_id_for_mailbox("Sent Items") == "sentitems"
    assert fetch_graph.graph_folder_id_for_mailbox("Sent Messages") == "sentitems"
    assert fetch_graph.graph_folder_id_for_mailbox("Junk Email") == "junkemail"
    assert fetch_graph.graph_folder_id_for_mailbox("Trash") == "deleteditems"
    assert fetch_graph.graph_folder_id_for_mailbox("Archive") == "archive"


def test_graph_folder_id_for_unknown_mailbox_is_friendly() -> None:
    with pytest.raises(ValueError, match="not mapped yet"):
        fetch_graph.graph_folder_id_for_mailbox("Projects")


def test_graph_query_params_unread_mode() -> None:
    params = fetch_graph._graph_query_params(max_messages=7, search_mode="unread")

    assert params["$top"] == 7
    assert params["$filter"] == "isRead eq false"
    assert params["$orderby"] == "receivedDateTime desc"
    assert "bodyPreview" in str(params["$select"])


def test_graph_query_params_recent_mode_has_no_unread_filter() -> None:
    params = fetch_graph._graph_query_params(max_messages=5, search_mode="recent")

    assert params["$top"] == 5
    assert "$filter" not in params


def test_fetch_graph_messages_builds_inbox_url_and_unread_filter(monkeypatch) -> None:
    response = Mock()
    response.json.return_value = {"value": [make_graph_message()]}
    response.raise_for_status.return_value = None
    get_mock = Mock(return_value=response)
    monkeypatch.setattr(fetch_graph.graph_auth, "get_graph_access_token", Mock(return_value="token"))
    monkeypatch.setattr(fetch_graph.requests, "get", get_mock)

    messages = fetch_graph.fetch_graph_messages(
        mailbox="Inbox",
        max_messages=3,
        search_mode="unread",
    )

    assert get_mock.call_args.args[0].endswith("/me/mailFolders/inbox/messages")
    assert get_mock.call_args.kwargs["params"]["$top"] == 3
    assert get_mock.call_args.kwargs["params"]["$filter"] == "isRead eq false"
    assert get_mock.call_args.kwargs["headers"] == {"Authorization": "Bearer token"}
    assert isinstance(messages[0][1], EmailMessage)
    assert messages[0][1].sender == "Alex <alex@example.com>"
    assert messages[0][1].body == "Short preview"


def test_fetch_graph_messages_recent_sent_items(monkeypatch) -> None:
    response = Mock()
    response.json.return_value = {"value": []}
    response.raise_for_status.return_value = None
    get_mock = Mock(return_value=response)
    monkeypatch.setattr(fetch_graph.graph_auth, "get_graph_access_token", Mock(return_value="token"))
    monkeypatch.setattr(fetch_graph.requests, "get", get_mock)

    messages = fetch_graph.fetch_graph_messages(
        mailbox="Sent Items",
        max_messages=10,
        search_mode="recent",
    )

    assert messages == []
    assert get_mock.call_args.args[0].endswith("/me/mailFolders/sentitems/messages")
    assert "$filter" not in get_mock.call_args.kwargs["params"]


def test_graph_message_uses_limited_body_when_preview_missing() -> None:
    long_body = "x" * 9000

    _, email = fetch_graph._graph_message_to_email(
        make_graph_message(body_preview="", body=long_body)
    )

    assert len(email.body) == 8000


def test_fetch_graph_messages_sanitizes_token_in_errors(monkeypatch) -> None:
    monkeypatch.setattr(
        fetch_graph.graph_auth,
        "get_graph_access_token",
        Mock(return_value="secret-token"),
    )
    monkeypatch.setattr(
        fetch_graph.requests,
        "get",
        Mock(side_effect=requests.RequestException("failed secret-token")),
    )

    with pytest.raises(RuntimeError) as exc_info:
        fetch_graph.fetch_graph_messages()

    message = str(exc_info.value)
    assert "secret-token" not in message
    assert "[token]" in message


def test_fetch_graph_summary_cards_analyzes_messages(monkeypatch) -> None:
    analysis = EmailAnalysis(
        summary="Summary",
        sender_intent="Question",
        priority="normal",
        category="billing",
        requires_response=True,
        action_items=[],
        suggested_reply="Draft",
        safety_note="Draft only. No email was sent.",
    )
    monkeypatch.setattr(
        fetch_graph,
        "fetch_graph_messages",
        Mock(return_value=[("message-1", EmailMessage("alex@example.com", "Subject", "Body"))]),
    )
    monkeypatch.setattr(fetch_graph, "analyze_email", Mock(return_value=analysis))

    cards = fetch_graph.fetch_graph_summary_cards()

    assert cards[0]["message_id"] == "message-1"
    assert cards[0]["sender"] == "alex@example.com"
    assert cards[0]["summary"] == "Summary"
