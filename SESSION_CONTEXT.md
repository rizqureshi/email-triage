# Session Context

Last updated: 2026-06-10

## Project

Repo: `/Users/RizwanHome/Documents/work/git/email-triage`

The project is **MailTriage AI**, a local, customer-friendly, read-only email
assistant. Preserve the safety boundary:

- Do not add SMTP.
- Do not send emails.
- Do not delete emails.
- Do not archive emails.
- Do not move emails.
- Do not copy emails.
- Do not mark emails as read.
- Do not store raw email bodies.
- Do not print secrets such as `IMAP_PASSWORD` or `OPENAI_API_KEY`.
- Do not implement Gmail API OAuth or Microsoft Graph OAuth unless explicitly
  requested as a separate phase.

## Current Capabilities

- `email_assistant.py`
  - Customer-facing CLI wrapper.
  - Supports `doctor`, `providers`, `review`, `fetch`, `list`, `actions`,
    `briefing`, `ask`, and `analyze`.
  - Defaults to human-readable output and supports `--json` where appropriate.
  - `providers` lists static IMAP presets and does not read `.env` or connect.
  - `review` runs the one-click workflow: fetch unread emails read-only, save
    summary cards, generate briefing, and list action items.
  - `fetch` uses read-only IMAP fetching via `fetch_imap.py`.
  - `list` reads stored summary cards from SQLite only.
  - `actions` reads flattened stored action items from SQLite only.
  - `ask` uses deterministic local answers by default and optional `--ai`.
  - Friendly errors avoid printing secrets.

- `email_providers.py`
  - Defines IMAP provider presets for:
    - `icloud`
    - `gmail`
    - `outlook`
    - `yahoo`
    - `aol`
    - `custom`
  - Exposes `get_provider()`, `list_providers()`, `provider_choices()`, and
    `authentication_help()`.
  - Provider presets are IMAP-only. OAuth is intentionally deferred.

- `config.py`
  - Supports `EMAIL_PROVIDER`, defaulting to `icloud`.
  - Uses provider defaults for `IMAP_HOST`, `IMAP_PORT`, and `IMAP_MAILBOX`
    when those values are omitted.
  - Preserves explicit `IMAP_HOST`, `IMAP_PORT`, and `IMAP_MAILBOX` overrides.
  - Requires `IMAP_USERNAME` and `IMAP_PASSWORD`.
  - `EMAIL_PROVIDER=custom` requires `IMAP_HOST`.

- `app.py`
  - Local Streamlit GUI for customer demos.
  - Run with:

    ```bash
    python -m streamlit run app.py
    ```

  - Tabs: Setup Check, Fetch Emails, Summary Cards, Action Items, Inbox Review,
    Daily Briefing, Ask Inbox, Manual Analyze.
  - Setup Check includes Provider Help from `email_providers.py`.
  - Inbox Review tab calls `review.run_inbox_review()`.
  - Action Items tab includes table display, source details, JSON, and CSV
    download via `action_items_to_csv()`.
  - Error handling sanitizes secrets and uses provider-specific auth guidance
    when possible.

- `doctor.py`
  - Implements `python email_assistant.py doctor`.
  - Checks `.env`, OpenAI config, provider preset resolution, IMAP settings,
    optional IMAP login, and DB card count.
  - Reports provider key/display name, resolved IMAP host/port, username,
    mailbox, and setup notes.
  - IMAP login check is limited to SSL connect, `login`, and `logout`.
  - Uses provider-specific auth guidance from `email_providers.authentication_help()`.
  - Must never select, search, fetch, copy, delete, store, move, or mark email.

- `fetch_imap.py`
  - Read-only IMAP ingestion.
  - Uses `select(..., readonly=True)`, `UNSEEN`, and `BODY.PEEK[]`.
  - Converts unread email into summary cards.
  - Authentication failures use provider-specific guidance.

- `review.py`
  - Implements `run_inbox_review(max_messages=10, mailbox="INBOX")`.
  - Loads IMAP settings, applies max-message/mailbox overrides, fetches unread
    summary cards read-only, saves cards, generates briefing, lists action
    items, and lists urgent/high/response-needed stored cards.
  - Provides `format_inbox_review()`.

- `storage.py`
  - SQLite storage for summary cards only.
  - Default DB path: `email_triage.db`; override with `EMAIL_TRIAGE_DB_PATH`.
  - Does not store raw email bodies.
  - Helpers include `resolve_db_path()`, `count_summary_cards()`,
    `list_cards()`, and `list_action_items()`.

- `daily_briefing.py`
  - Builds briefings from stored summary cards only.

- `inbox_qa.py`
  - Answers questions over stored summary cards only.
  - AI mode sends only compact matched stored summary cards to OpenAI, not raw
    bodies or the full DB.

- `analyzer.py`
  - Manual single-email analysis.
  - Uses OpenAI when configured, otherwise deterministic fallback.

- Documentation
  - `README.md` uses the MailTriage AI product name and includes CLI, local GUI,
    provider setup, setup check, inbox review, summary card browsing, and action
    item browsing examples.
  - `DEVELOPER.md` documents architecture, safety constraints, provider presets,
    auth guidance, storage helpers, CLI commands, GUI architecture, and testing
    rules.

## Recent Work Completed

- Renamed the customer-facing app from "Email Assistant" to **MailTriage AI**.
- Added one-click Inbox Review workflow:
  - `review.py`
  - `python email_assistant.py review`
  - Streamlit Inbox Review tab
- Added multi-provider IMAP presets:
  - `email_providers.py`
  - `EMAIL_PROVIDER`
  - `python email_assistant.py providers`
  - Provider Help in the Streamlit Setup Check tab
- Added provider-specific IMAP authentication guidance for:
  - iCloud Mail
  - Gmail
  - Outlook / Microsoft 365
  - Yahoo Mail
  - AOL Mail
  - Custom IMAP
  - Generic unknown provider fallback
- Updated doctor, fetch, and Streamlit error handling to use provider-specific
  auth guidance without printing secrets.

## Verification

The plain requested command currently fails in this shell because `python` is
not on PATH globally:

```text
python -m pytest
/bin/bash: python: command not found
```

Use the local virtual environment:

```bash
.venv/bin/python -m pytest
```

Latest result:

```text
135 passed in 0.33s
```

## Current Worktree Notes

Recent work is intentionally uncommitted. Before committing, check:

```bash
git status --short
git diff
```

Recent changed/new files include:

- `.env.example`
- `DEVELOPER.md`
- `README.md`
- `SESSION_CONTEXT.md`
- `app.py`
- `config.py`
- `doctor.py`
- `email_assistant.py`
- `email_providers.py`
- `fetch_imap.py`
- `review.py`
- `tests/test_app.py`
- `tests/test_doctor.py`
- `tests/test_email_assistant.py`
- `tests/test_email_providers.py`
- `tests/test_fetch_imap.py`
- `tests/test_review.py`

There are local env files open/possibly present (`.env`, `.env-icloud`,
`.env copy`). Do not inspect, print, or commit secrets from them unless the user
explicitly asks and approves.

## Suggested Resume Step

Tomorrow:

1. Review `git status --short` and `git diff`.
2. Run:

   ```bash
   .venv/bin/python -m pytest
   ```

3. Try local non-network commands:

   ```bash
   python email_assistant.py providers
   python email_assistant.py doctor --skip-imap-login
   python email_assistant.py list --limit 5
   python email_assistant.py actions --limit 10
   ```

4. Launch the GUI only if useful:

   ```bash
   python -m streamlit run app.py
   ```

Only run real IMAP fetch/login checks when the user explicitly approves
connecting to the inbox.
