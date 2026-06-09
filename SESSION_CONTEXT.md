# Session Context

Last updated: 2026-06-07

## Project

This repo is an email assistant at:

`/Users/RizwanHome/Documents/work/git/email-triage`

The project must remain draft-only and read-only. Do not add SMTP, email
sending, deleting, moving, archiving, or mark-read behavior. Do not store raw
email bodies. Do not print secrets such as IMAP passwords or OpenAI API keys.

## What Exists

- `email_assistant.py`
  - New customer-facing CLI wrapper.
  - Supports subcommands: `fetch`, `briefing`, `ask`, and `analyze`.
  - Defaults to human-readable output and supports `--json`.
  - `fetch` wraps read-only IMAP summary-card fetching and supports
    `--max-messages`, `--mailbox`, `--save`, and `--json`.
  - `briefing` wraps `daily_briefing.generate_daily_briefing()`.
  - `ask` wraps `inbox_qa.answer_inbox_question()` and supports optional `--ai`.
  - `analyze` wraps `analyzer.analyze_email()` and reads stdin when `--body` is
    omitted.
  - Friendly error handling avoids printing secrets.

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
  - Does not store raw email bodies.

- `daily_briefing.py`
  - Builds a briefing from stored summary cards only.
  - Summarizes urgent/high counts, response count, categories, top action items,
    important emails, and suggested focus.

- `inbox_qa.py`
  - Answers questions over stored summary cards only.
  - Supports catch-up, response, urgent, high-priority, billing, action-item,
    and sender queries with deterministic rules.
  - Default behavior is deterministic and free: `use_ai=False`.
  - Optional Phase 2 AI mode is available with `use_ai=True` or CLI `--ai`.
  - AI mode first calls `search_cards()` and sends only `_compact_match(card)`
    data for matched stored summary cards to OpenAI.
  - AI mode does not send raw email bodies or the full database.
  - If OpenAI is unavailable, missing, or fails, it falls back safely with
    `answer_mode="deterministic_fallback"`.

- `analyzer.py`
  - Read-only email intelligence CLI.
  - Uses OpenAI when `OPENAI_API_KEY` is configured.
  - Falls back to local rules if model output is missing, invalid, or unusable.

- `schemas.py`
  - Defines `ActionItem` and `EmailAnalysis`.
  - `ActionItem` includes `text`, `owner`, `due_date`, and `priority`.

- Documentation
  - `README.md` is now a customer-friendly quick start focused on
    `email_assistant.py`.
  - `DEVELOPER.md` contains architecture, data flow, module docs, individual
    script usage, storage details, OpenAI boundaries, safety constraints,
    testing notes, and suggested future improvements.

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
  - `tests/test_email_assistant.py`
  - All IMAP/OpenAI-related tests use mocks/fakes and do not connect to a real
    email account or call the real OpenAI API.

## Recent Work Completed

- Implemented optional OpenAI-powered Inbox Q&A over retrieved stored summary
  cards only.
- Added `answer_mode` values: `deterministic`, `ai`, and
  `deterministic_fallback`.
- Added `--ai` support to `inbox_qa.py`.
- Added `email_assistant.py` as the recommended customer-facing CLI wrapper.
- Added tests for the AI Inbox Q&A path and the new CLI wrapper.
- Split documentation into customer README and technical DEVELOPER guide.

## Verification

The requested command currently fails in this shell because `python` is not on
PATH:

```text
python -m pytest
/bin/bash: python: command not found
```

The last successful test command was run inside the local virtual environment:

```bash
.venv/bin/python -m pytest
```

Result:

```text
77 passed
```

## Current Worktree Notes

Recent work may still be uncommitted. Before committing, check:

```bash
git status --short
git diff
```

Expected changed/new files from the latest work include:

- `README.md`
- `DEVELOPER.md`
- `email_assistant.py`
- `tests/test_email_assistant.py`
- `inbox_qa.py`
- `tests/test_inbox_qa.py`
- `SESSION_CONTEXT.md`

## Suggested Next Step

Tomorrow, review the accumulated diff, run `.venv/bin/python -m pytest`, and
commit the completed phases if everything still looks good.

After committing, try the read-only flow end to end:

```bash
python email_assistant.py fetch --max-messages 5 --save
python email_assistant.py briefing --limit 20
python email_assistant.py ask "Catch me up"
python email_assistant.py ask "What emails need my response?" --ai
```

Only run `fetch` when the user explicitly approves connecting to the real inbox.
