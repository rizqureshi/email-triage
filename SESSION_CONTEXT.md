# Session Context

Last updated: 2026-06-10

## Project

Repo: `/Users/RizwanHome/Documents/work/git/email-triage`

The project is MailTriage AI, a local, customer-friendly, read-only email assistant. Preserve
the safety boundary:

- Do not add SMTP.
- Do not send emails.
- Do not delete emails.
- Do not archive emails.
- Do not move emails.
- Do not mark emails as read.
- Do not store raw email bodies.
- Do not print secrets such as `IMAP_PASSWORD` or `OPENAI_API_KEY`.

## Current Capabilities

- `email_assistant.py`
  - Customer-facing CLI wrapper.
  - Supports `doctor`, `fetch`, `list`, `actions`, `briefing`, `ask`, and
    `analyze`.
  - Defaults to human-readable output and supports `--json` where appropriate.
  - `fetch` uses read-only IMAP fetching via `fetch_imap.py`.
  - `list` reads stored summary cards from SQLite only.
  - `actions` reads flattened stored action items from SQLite only.
  - `ask` uses deterministic local answers by default and optional `--ai`.
  - Friendly errors avoid printing secrets.

- `app.py`
  - Local Streamlit GUI for customer demos.
  - Run with:

    ```bash
    python -m streamlit run app.py
    ```

  - Tabs: Setup Check, Fetch Emails, Summary Cards, Action Items, Daily
    Briefing, Ask Inbox, Manual Analyze.
  - Reuses backend modules and `email_assistant.py` formatting helpers.
  - Action Items tab includes table display, source details, JSON, and CSV
    download via `action_items_to_csv()`.

- `doctor.py`
  - Implements `python email_assistant.py doctor`.
  - Checks `.env`, OpenAI config, IMAP settings, optional IMAP login, and DB
    card count.
  - IMAP login check is limited to SSL connect, `login`, and `logout`.
  - Must never select, search, fetch, copy, delete, store, move, or mark email.

- `fetch_imap.py`
  - Read-only IMAP ingestion.
  - Uses `select(..., readonly=True)`, `UNSEEN`, and `BODY.PEEK[]`.
  - Converts unread email into summary cards.

- `storage.py`
  - SQLite storage for summary cards only.
  - Default DB path: `email_triage.db`; override with `EMAIL_TRIAGE_DB_PATH`.
  - Does not store raw email bodies.
  - Helpers now include:
    - `resolve_db_path()`
    - `count_summary_cards()`
    - `list_cards()`
    - `list_action_items()`

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
  - `README.md` includes CLI, local GUI, setup check, summary card browsing,
    and action item browsing examples.
  - `DEVELOPER.md` documents architecture, safety constraints, storage helpers,
    CLI commands, GUI architecture, and testing rules.

## Work Completed Today

Implemented setup diagnostics:

- Added `doctor.py`.
- Added `python email_assistant.py doctor`.
- Added `--json` and `--skip-imap-login`.
- Added database count helper.
- Added mocked doctor tests and docs.

Implemented stored card browsing:

- Added `storage.list_cards()`.
- Added `python email_assistant.py list`.
- Added filters for priority, category, requires-response, limit, and JSON.
- Added tests and docs.

Implemented local Streamlit GUI:

- Added `streamlit` dependency in `requirements.txt`.
- Added `app.py`.
- GUI tabs cover setup, fetch, summary cards, daily briefing, inbox Q&A, and
  manual analyze.
- Added docs for `python -m streamlit run app.py`.

Implemented Action Items dashboard:

- Added `storage.list_action_items()`.
- Added `python email_assistant.py actions`.
- Added priority/owner/limit/JSON options.
- Added Action Items tab to `app.py`.
- Added CSV export helper and test.
- Added tests and docs.

## Verification

The plain requested command may fail in this shell because `python` is not on
PATH globally. Use the local virtual environment:

```bash
source .venv/bin/activate && python -m pytest
```

Latest result:

```text
106 passed in 0.26s
```

Also compiled the touched app modules successfully:

```bash
source .venv/bin/activate && python -m py_compile app.py email_assistant.py storage.py
```

## Current Worktree Notes

Recent work is intentionally uncommitted. Before committing, check:

```bash
git status --short
git diff
```

Current changed/new files should include:

- `DEVELOPER.md`
- `README.md`
- `app.py`
- `email_assistant.py`
- `requirements.txt`
- `storage.py`
- `tests/test_app.py`
- `tests/test_doctor.py`
- `tests/test_email_assistant.py`
- `tests/test_storage.py`
- `doctor.py`
- `SESSION_CONTEXT.md`

## Suggested Resume Step

Tomorrow:

1. Review `git diff`.
2. Run:

   ```bash
   source .venv/bin/activate && python -m pytest
   ```

3. Try local non-network commands:

   ```bash
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
