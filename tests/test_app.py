import csv
import io

import app


def test_action_items_to_csv() -> None:
    csv_text = app.action_items_to_csv(
        [
            {
                "text": "Confirm payment status.",
                "owner": "finance",
                "due_date": "2026-06-05",
                "priority": "urgent",
                "message_id": "<1@example.com>",
                "sender": "alex@example.com",
                "subject": "Invoice question",
                "category": "billing",
                "requires_response": True,
                "fetched_at": "2026-06-04T10:00:00Z",
            }
        ]
    )

    rows = list(csv.DictReader(io.StringIO(csv_text)))

    assert rows == [
        {
            "text": "Confirm payment status.",
            "owner": "finance",
            "due_date": "2026-06-05",
            "priority": "urgent",
            "message_id": "<1@example.com>",
            "sender": "alex@example.com",
            "subject": "Invoice question",
            "category": "billing",
            "requires_response": "True",
            "fetched_at": "2026-06-04T10:00:00Z",
        }
    ]
