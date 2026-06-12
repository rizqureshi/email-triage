# Developer Guide

Technical notes for the MailTriage AI prototype.

## Architecture Overview

MailTriage AI is a local, read-only email assistant. `email_assistant.py` is
the customer-facing CLI wrapper. The lower-level scripts remain available for
development, testing, and focused workflows.

`app.py` provides a local Streamlit GUI for customer demos. It reuses the same
backend modules as the CLI rather than duplicating business logic.

The core boundary is that the assistant can read, analyze, summarize, store
summary cards, and draft text for human review. It must not modify the mailbox
or send email.

## Data Flow

1. `fetch_imap.py` connects to IMAP, selects the mailbox with `readonly=True`,
   searches unread messages, and fetches message content with `BODY.PEEK[]`.
2. `config.py` resolves IMAP settings using `EMAIL_PROVIDER` and provider
   presets from `email_providers.py`, while preserving explicit `.env`
   overrides.
3. Each fetched email is converted into a `triage.EmailMessage`.
4. `analyzer.py` analyzes the email using OpenAI when configured, otherwise a
   deterministic local fallback.
5. `fetch_imap.py` combines message metadata and analysis into a compact summary
   card.
6. `storage.py` optionally saves summary cards to SQLite.
7. `review.py` orchestrates the one-step inbox review: fetch unread cards,
   save them, generate a briefing, list action items, and list urgent,
   high-priority, and response-needed stored cards.
8. `daily_briefing.py` reads stored cards and builds a briefing.
9. `inbox_qa.py` searches stored cards and answers inbox questions with
   deterministic rules by default, or with OpenAI when explicitly requested.
10. `doctor.py` checks local setup and IMAP login safety without fetching or
   modifying mailbox data.
11. `app.py` presents the same setup, fetch, browse, inbox review, briefing,
    Q&A, and manual analysis workflows in a local browser UI.

Raw email bodies are used for immediate analysis but are not stored in SQLite.

## Modules

- `config.py`
  - Loads `.env` values when `python-dotenv` is installed.
  - Defines OpenAI and IMAP settings.
  - Resolves `EMAIL_PROVIDER`, defaulting to `icloud`.
  - Uses provider defaults for `IMAP_HOST`, `IMAP_PORT`, and `IMAP_MAILBOX`
    when those values are omitted.
  - Keeps explicit `IMAP_HOST`, `IMAP_PORT`, and `IMAP_MAILBOX` overrides.
  - Validates bounded integer settings such as `MAX_DRAFT_WORDS`,
    `IMAP_PORT`, and `IMAP_MAX_MESSAGES`.

- `email_providers.py`
  - Defines provider presets for `icloud`, `gmail`, `outlook`, `yahoo`, `aol`,
    and `custom`.
  - Exposes `get_provider()`, `list_providers()`, and `provider_choices()`.
  - Exposes `authentication_help()` for provider-specific IMAP authentication
    failure guidance.
  - Presets include display name, IMAP host/port, SSL flag, default mailbox,
    setup notes, app-password guidance, and whether OAuth may be needed later.

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
  - Exposes `list_action_items()` for flattened action-item reads from stored
    summary cards only.

- `daily_briefing.py`
  - Builds a briefing from stored summary cards only.

- `review.py`
  - Provides `run_inbox_review(max_messages=10, mailbox="INBOX")`.
  - Loads IMAP settings, applies fetch overrides, calls the existing read-only
    fetch path, saves summary cards, generates a briefing, and gathers action
    items plus urgent, high-priority, and response-needed stored cards.
  - Provides `format_inbox_review()` for terminal-friendly reporting.
  - Must remain an orchestrator over existing safe modules; do not add mailbox
    mutation logic here.

- `inbox_qa.py`
  - Answers questions over stored summary cards.
  - Uses deterministic rules by default.
  - Uses OpenAI only when `use_ai=True` or the CLI `--ai` flag is supplied.

- `email_assistant.py`
  - Customer-facing CLI wrapper with `review`, `fetch`, `list`, `actions`,
    `briefing`, `ask`, `analyze`, and `doctor` subcommands.
  - Defaults to human-readable output and supports `--json`.
  - The `review` command is the one-step customer workflow: fetch unread,
    save summary cards, brief, and show action items.
  - The `list` command reads only from SQLite storage and must not call IMAP.
  - The `actions` command reads only from SQLite storage and must not call IMAP
    or OpenAI.

- `app.py`
  - Local Streamlit GUI for customer demos.
  - Reuses `doctor.py`, `fetch_imap.py`, `storage.py`, `daily_briefing.py`,
    `review.py`, `inbox_qa.py`, `analyzer.py`, and `email_assistant.py`
    formatting helpers.
  - Includes an Inbox Review tab backed by `review.run_inbox_review()`.
  - Includes an Action Items tab backed by `storage.list_action_items()` and a
    standard-library CSV export helper.
  - Keeps backend behavior in the existing modules; the UI layer should stay
    thin and customer-friendly.
  - Must sanitize displayed errors and never show `OPENAI_API_KEY` or
    `IMAP_PASSWORD`.
  - Uses provider-specific authentication help when IMAP login fails, without
    connecting to IMAP from the error helper.
  - Long-running buttons use the pending-action + busy-state pattern: button
    `on_click` sets busy/pending before action execution, the next render shows
    the button disabled, results/errors are stored in `st.session_state`, and
    busy state is cleared in a `finally` block.

- `doctor.py`
  - Builds the setup-check report for `python email_assistant.py doctor`.
  - Checks `.env`, OpenAI configuration, provider preset resolution, IMAP
    settings, optional IMAP login, and database/card count.
  - Reports selected provider key, display name, resolved host/port, username,
    mailbox, and setup notes.
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

List supported provider presets:

```bash
python email_assistant.py providers
python email_assistant.py providers --json
```

Browse stored summary cards:

```bash
python email_assistant.py list --priority urgent
python email_assistant.py list --priority high --requires-response
python email_assistant.py list --category billing
python email_assistant.py list --requires-response
```

Browse stored action items:

```bash
python email_assistant.py actions
python email_assistant.py actions --priority urgent
python email_assistant.py actions --json
```

Run the one-click inbox review workflow:

```bash
python email_assistant.py review
python email_assistant.py review --max-messages 10
python email_assistant.py review --json
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

## Provider Presets

`EMAIL_PROVIDER` defaults to `icloud`. Supported values are:

- `icloud`
- `gmail`
- `outlook`
- `yahoo`
- `aol`
- `custom`

For known providers, `IMAP_HOST`, `IMAP_PORT`, and `IMAP_MAILBOX` can be
omitted and the preset defaults are used. Explicit `.env` values still override
the preset. For `EMAIL_PROVIDER=custom`, `IMAP_HOST` is required.

Provider presets are IMAP-only. Gmail API OAuth and Microsoft Graph OAuth are
deferred intentionally so this step can preserve the existing read-only IMAP
behavior. Future OAuth work should be introduced as a separate provider/auth
layer with explicit tests and safety review.

Provider-specific authentication help lives in `email_providers.py`. `doctor.py`,
`fetch_imap.py`, and the Streamlit GUI use that helper so iCloud, Gmail,
Outlook / Microsoft 365, Yahoo, AOL, and custom IMAP users see relevant
guidance without exposing passwords.

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
- Provider presets must remain IMAP read-only presets. Do not add Gmail API
  OAuth or Microsoft Graph OAuth in this layer.
- Do not add SMTP for any provider preset.
- `review.py` and `email_assistant.py review` must use the existing read-only
  fetch behavior in `fetch_imap.py`. They must not send, delete, archive, move,
  or mark emails as read.
- `doctor.py` must never fetch, select, search, modify, copy, delete, move, or
  mark email. Its IMAP check may only connect over SSL, login, and logout.
- `email_assistant.py list` must read only from SQLite storage. It must not call
  IMAP or any mailbox-modifying code.
- `email_assistant.py actions` and the GUI Action Items tab must read only from
  SQLite storage. They must not call IMAP, OpenAI, or any mailbox-modifying code.
- The GUI Inbox Review tab must call `review.run_inbox_review()` and preserve
  the same read-only safety constraints.
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
daily briefing generation, Inbox Q&A, inbox review orchestration, setup
diagnostics, and the customer-facing CLI wrapper.

## Suggested Future Improvements

- Package the project as an installable CLI.
- Improve date normalization for action items.
- Add optional vector or semantic search later.
