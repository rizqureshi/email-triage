# Session Context

Last updated: 2026-06-04

## Project

This repo is an email triage and reply-draft assistant at:

`/Users/RizwanHome/Documents/work/git/email-triage`

The project must remain draft-only and read-only. Do not add SMTP, email
sending, deleting, moving, archiving, or mark-read behavior.

## What Exists

- `triage.py`
  - Defines `EmailMessage` and `TriageResult`.
  - Triages email by priority and category.
  - Generates reply drafts only.
  - Uses OpenAI when `OPENAI_API_KEY` is configured.
  - Falls back to local rule-based triage if no API key is configured or model
    JSON output is unusable.
  - Includes `_coerce_bool()` so string values like `"false"` do not become
    truthy by accident.

- `config.py`
  - Loads `.env` values when `python-dotenv` is installed.
  - Validates `MAX_DRAFT_WORDS` as an integer between 20 and 500.
  - Includes read-only IMAP settings via `load_imap_settings()`.
  - Validates `IMAP_PORT` between 1 and 65535 and `IMAP_MAX_MESSAGES` between
    1 and 50.

- `fetch_imap.py`
  - Read-only IMAP ingestion module.
  - Uses `imaplib` and `email` from the Python standard library.
  - Reads unread messages only with `UNSEEN`.
  - Uses `select(..., readonly=True)` and `BODY.PEEK[]`.
  - Converts each fetched email into `EmailMessage` and passes it to
    `analyze_email()`.
  - Prints JSON summary cards.
  - Supports `--save` to persist summary cards to local SQLite.

- `storage.py`
  - SQLite storage for summary cards only.
  - Stores `message_id`, sender, subject, summary, sender intent, priority,
    category, requires_response, action item JSON, suggested reply, safety note,
    and fetched timestamp.
  - Default database path is `email_triage.db`, override via
    `EMAIL_TRIAGE_DB_PATH`.

- `daily_briefing.py`
  - Builds a briefing from stored summary cards only.
  - Summarizes urgent/high counts, response count, categories, top action items,
    important emails, and suggested focus.

- `inbox_qa.py`
  - Answers questions over stored summary cards only.
  - Supports catch-up, response, urgent, high-priority, billing, action-item,
    and sender queries with deterministic rules.
  - Does not call OpenAI and does not fetch from IMAP.

- `analyzer.py`
  - Read-only email intelligence CLI.
  - Uses OpenAI when `OPENAI_API_KEY` is configured.
  - Falls back to local rules if model output is missing, invalid, or unusable.

- `schemas.py`
  - Defines `ActionItem` and `EmailAnalysis`.
  - `ActionItem` now includes `text`, `owner`, `due_date`, and `priority`.

- `.env.example`
  - Contains OpenAI settings, IMAP settings, and `EMAIL_TRIAGE_DB_PATH`.

- `.env`
  - Created locally and ignored by git.
  - User added a paid OpenAI API key there.
  - Do not print, inspect, or commit the key unless explicitly necessary and
    approved by the user.

- Tests
  - `tests/test_analyzer.py`
  - `tests/test_triage.py`
  - `tests/test_fetch_imap.py`
  - `tests/test_storage.py`
  - `tests/test_daily_briefing.py`
  - `tests/test_inbox_qa.py`
  - All IMAP and storage tests use mocks/fakes and do not connect to a real
    email account.

## Verification

The last successful test command was run inside the local virtual environment:

```bash
source .venv/bin/activate && python -m pytest
```

Result at that time:

```text
60 passed
```

## Suggested Next Step

Tomorrow, try the read-only flow end to end: run `python fetch_imap.py --save`
to store summary cards, then `python daily_briefing.py --limit 20` and
`python inbox_qa.py "Catch me up"` against the saved SQLite data.
