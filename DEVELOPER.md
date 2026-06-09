# Developer Guide

Technical notes for the email assistant prototype.

## Architecture Overview

The project is a local, read-only email assistant. `email_assistant.py` is the
customer-facing CLI wrapper. The lower-level scripts remain available for
development, testing, and focused workflows.

`app.py` provides a local Streamlit GUI for customer demos. It reuses the same
backend modules as the CLI rather than duplicating business logic.

The core boundary is that the assistant can read, analyze, summarize, store
summary cards, and draft text for human review. It must not modify the mailbox
or send email.

## Data Flow

1. `fetch_imap.py` connects to IMAP, selects the mailbox with `readonly=True`,
   searches unread messages, and fetches message content with `BODY.PEEK[]`.
2. Each fetched email is converted into a `triage.EmailMessage`.
3. `analyzer.py` analyzes the email using OpenAI when configured, otherwise a
   deterministic local fallback.
4. `fetch_imap.py` combines message metadata and analysis into a compact summary
   card.
5. `storage.py` optionally saves summary cards to SQLite.
6. `daily_briefing.py` reads stored cards and builds a briefing.
7. `inbox_qa.py` searches stored cards and answers inbox questions with
   deterministic rules by default, or with OpenAI when explicitly requested.
8. `doctor.py` checks local setup and IMAP login safety without fetching or
   modifying mailbox data.
9. `app.py` presents the same setup, fetch, browse, briefing, Q&A, and manual
   analysis workflows in a local browser UI.

Raw email bodies are used for immediate analysis but are not stored in SQLite.

## Modules

- `config.py`
  - Loads `.env` values when `python-dotenv` is installed.
  - Defines OpenAI and IMAP settings.
  - Validates bounded integer settings such as `MAX_DRAFT_WORDS`,
    `IMAP_PORT`, and `IMAP_MAX_MESSAGES`.

- `schemas.py`
  - Defines shared dataclasses such as `ActionItem` and `EmailAnalysis`.

- `triage.py`
  - Contains the legacy single-email triage model, local rules, OpenAI path, and
    reply-draft generation.

- `analyzer.py`
  - Performs richer single-email analysis: summary, sender intent, priority,
    category, response need, action items, suggested reply, and safety note.
  - Uses OpenAI when `OPENAI_API_KEY` is configured and falls back to local rules
    on missing, invalid, or unusable model output.

- `fetch_imap.py`
  - Fetches unread email via IMAP in read-only mode.
  - Uses `readonly=True`, `UNSEEN`, and `BODY.PEEK[]`.
  - Produces summary cards and can save them with `--save`.

- `storage.py`
  - Persists summary cards to local SQLite.
  - Does not store raw email bodies.
  - Exposes `resolve_db_path()` and `count_summary_cards()` for diagnostics
    without creating a missing database.
  - Exposes `list_cards()` for parameterized, filtered reads over stored
    summary cards.

- `daily_briefing.py`
  - Builds a briefing from stored summary cards only.

- `inbox_qa.py`
  - Answers questions over stored summary cards.
  - Uses deterministic rules by default.
  - Uses OpenAI only when `use_ai=True` or the CLI `--ai` flag is supplied.

- `email_assistant.py`
  - Customer-facing CLI wrapper with `fetch`, `list`, `briefing`, `ask`,
    `analyze`, and `doctor` subcommands.
  - Defaults to human-readable output and supports `--json`.
  - The `list` command reads only from SQLite storage and must not call IMAP.

- `app.py`
  - Local Streamlit GUI for customer demos.
  - Reuses `doctor.py`, `fetch_imap.py`, `storage.py`, `daily_briefing.py`,
    `inbox_qa.py`, `analyzer.py`, and `email_assistant.py` formatting helpers.
  - Keeps backend behavior in the existing modules; the UI layer should stay
    thin and customer-friendly.
  - Must sanitize displayed errors and never show `OPENAI_API_KEY` or
    `IMAP_PASSWORD`.

- `doctor.py`
  - Builds the setup-check report for `python email_assistant.py doctor`.
  - Checks `.env`, OpenAI configuration, IMAP settings, optional IMAP login, and
    database/card count.
  - Must not print secrets such as `OPENAI_API_KEY` or `IMAP_PASSWORD`.
  - The IMAP login check is intentionally limited to SSL connect, `login`, and
    `logout`.

## Individual Script Usage

The recommended customer entry point is `email_assistant.py`, but individual
scripts are useful during development.

Run legacy triage:

```bash
python triage.py --from "alex@example.com" --subject "Invoice question" \
  --body "Hi, can you confirm whether invoice 1042 has been paid?"
```

Run single-email analysis:

```bash
python analyzer.py --from "alex@example.com" --subject "Invoice question" \
  --body "Can you confirm whether invoice 1042 has been paid?"
```

Fetch unread messages in read-only mode:

```bash
python fetch_imap.py --mailbox INBOX --max-messages 5
python fetch_imap.py --max-messages 5 --save
```

Generate a briefing from saved cards:

```bash
python daily_briefing.py --limit 20
```

Ask questions over saved cards:

```bash
python inbox_qa.py "Catch me up"
python inbox_qa.py "What emails need my response?"
python inbox_qa.py "Any billing emails?"
python inbox_qa.py "Catch me up" --ai
```

Check customer setup:

```bash
python email_assistant.py doctor
python email_assistant.py doctor --skip-imap-login
python email_assistant.py doctor --json
```

Browse stored summary cards:

```bash
python email_assistant.py list --priority urgent
python email_assistant.py list --priority high --requires-response
python email_assistant.py list --category billing
python email_assistant.py list --requires-response
```

Run the local GUI:

```bash
python -m streamlit run app.py
```

## Storage

The default SQLite database is:

```text
email_triage.db
```

Override it with:

```bash
EMAIL_TRIAGE_DB_PATH=/path/to/email_triage.db
```

`storage.py` creates an `email_cards` table with these fields:

- `message_id`
- `sender`
- `subject`
- `summary`
- `sender_intent`
- `priority`
- `category`
- `requires_response`
- `action_items_json`
- `suggested_reply`
- `safety_note`
- `fetched_at`

No raw email bodies are stored.

## OpenAI Usage

- `analyzer.py` uses OpenAI when `OPENAI_API_KEY` is configured.
- `triage.py` also has an OpenAI-backed path when configured.
- `inbox_qa.py` uses OpenAI only when `--ai` or `use_ai=True` is requested.
- Inbox Q&A sends only compact matched summary cards from `_compact_match()`.
- Inbox Q&A does not send raw email bodies or the full SQLite database.
- If OpenAI is unavailable or output is unusable, the code falls back to local
  deterministic behavior.

## Safety Constraints

For future development:

- Do not add SMTP without explicit approval.
- Do not send emails automatically.
- Do not delete emails.
- Do not archive emails.
- Do not move emails.
- Do not mark emails as read.
- Do not store raw email bodies.
- Do not print secrets such as IMAP passwords or OpenAI API keys.
- `doctor.py` must never fetch, select, search, modify, copy, delete, move, or
  mark email. Its IMAP check may only connect over SSL, login, and logout.
- `email_assistant.py list` must read only from SQLite storage. It must not call
  IMAP or any mailbox-modifying code.
- `app.py` must not add new mailbox behavior. It should call existing backend
  functions and preserve their read-only safety constraints.

## Testing

Run:

```bash
python -m pytest
```

Tests should use mocks and fakes. They should not call real IMAP servers or the
OpenAI API. Doctor tests must mock IMAP and OpenAI-related paths. GUI tests, if
added, should cover helper functions only and should not run real Streamlit
browser sessions.

Current test areas include analyzer behavior, read-only IMAP fetching, storage,
daily briefing generation, Inbox Q&A, setup diagnostics, and the
customer-facing CLI wrapper.

## Suggested Future Improvements

- Package the project as an installable CLI.
- Improve date normalization for action items.
- Add optional vector or semantic search later.
