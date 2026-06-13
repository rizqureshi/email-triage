# Session Context

Last updated: 2026-06-12

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
  - Supports `doctor`, `providers`, `mailboxes`, `review`, `fetch`, `list`,
    `actions`, `briefing`, `ask`, and `analyze`.
  - Defaults to human-readable output and supports `--json` where appropriate.
  - `providers` lists static IMAP presets and does not read `.env` or connect.
  - `mailboxes` lists provider-specific mailbox/folder suggestions and does not
    connect to IMAP.
  - `fetch` uses read-only IMAP fetching via `fetch_imap.py`.
  - `fetch --search-mode unread|recent` supports unread-only or recent-message
    search.
  - `review` runs the one-click workflow: fetch emails read-only, save summary
    cards, generate briefing, and list action items.
  - `review --search-mode unread|recent` supports the same search modes.
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
  - Exposes `get_provider()`, `list_providers()`, `provider_choices()`,
    `authentication_help()`, `mailbox_presets()`, and `default_mailbox()`.
  - Provider presets are IMAP-only. OAuth is intentionally deferred.

- `config.py`
  - Supports `EMAIL_PROVIDER`, defaulting to `icloud`.
  - Supports `IMAP_SEARCH_MODE`, defaulting to `unread`.
  - Valid search modes are `unread` and `recent`.
  - Uses provider defaults for `IMAP_HOST`, `IMAP_PORT`, and `IMAP_MAILBOX`
    when those values are omitted.
  - Preserves explicit `IMAP_HOST`, `IMAP_PORT`, and `IMAP_MAILBOX` overrides.
  - Requires `IMAP_USERNAME` and `IMAP_PASSWORD`.
  - `EMAIL_PROVIDER=custom` requires `IMAP_HOST`.

- `app.py`
  - Local Streamlit GUI for customer demos.
  - Run with:

    ```bash
    .venv/bin/python -m streamlit run app.py
    ```

  - Tabs: Setup Check, Fetch Emails, Summary Cards, Action Items, Inbox Review,
    Daily Briefing, Ask Inbox, Manual Analyze.
  - Setup Check includes Provider Help from `email_providers.py`.
  - Fetch Emails and Inbox Review include provider-aware mailbox presets, custom
    mailbox override, and Search mode dropdowns.
  - Inbox Review tab calls `review.run_inbox_review()`.
  - Action Items tab includes table display, source details, JSON, and CSV
    download via `action_items_to_csv()`.
  - Error handling sanitizes secrets and uses provider-specific auth guidance
    when possible.
  - Button actions use session-state pending/busy handling to disable buttons
    before long-running work starts.

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
  - Uses `select(..., readonly=True)` and `BODY.PEEK[]`.
  - Search mode `unread` maps to IMAP `UNSEEN`.
  - Search mode `recent` maps to IMAP `ALL` and then limits to the most recent
    `max_messages` IDs.
  - Safely quotes mailbox names only at IMAP `select`, so folders like
    `Sent Messages` work while user-facing folder names remain unquoted.
  - Empty search results such as `[]`, `[b""]`, `[b" "]`, and `[None]` are
    treated as no matching messages.
  - Converts fetched email into summary cards.
  - Authentication failures use provider-specific guidance.

- `review.py`
  - Implements `run_inbox_review(max_messages=10, mailbox="INBOX",
    search_mode="unread")`.
  - Loads IMAP settings, applies max-message/mailbox/search-mode overrides,
    fetches summary cards read-only, saves cards, generates briefing, lists
    action items, and lists urgent/high/response-needed stored cards.
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
    provider setup, setup check, inbox review, search modes, mailbox/folder
    selection, summary card browsing, and action item browsing examples.
  - `DEVELOPER.md` documents architecture, safety constraints, provider presets,
    auth guidance, storage helpers, CLI commands, GUI architecture, mailbox
    quoting, search modes, and testing rules.

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
- Added provider-specific IMAP authentication guidance for iCloud, Gmail,
  Outlook / Microsoft 365, Yahoo, AOL, custom IMAP, and unknown providers.
- Added provider-aware mailbox/folder presets and custom mailbox override in
  the Streamlit Fetch Emails and Inbox Review tabs.
- Added CLI mailbox suggestions:

  ```bash
  python email_assistant.py mailboxes --provider gmail
  ```

- Fixed iCloud folder names with spaces by safely quoting mailbox names during
  IMAP `select`.
- Fixed empty IMAP search results such as `[None]` so folders with no matching
  messages return an empty result instead of crashing.
- Added Search Mode support:
  - `IMAP_SEARCH_MODE=unread|recent`
  - CLI `--search-mode unread|recent` for `fetch` and `review`
  - Streamlit Search mode dropdowns
  - `unread` -> `UNSEEN`
  - `recent` -> `ALL`, then limit to newest IDs locally
- Improved Streamlit busy-state handling so buttons are disabled before
  long-running actions execute.
- Updated README, DEVELOPER, `.env.example`, and tests for the above.

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
188 passed in 0.33s
```

## Current Worktree Notes

Before this context update, `git status --short` was clean.

After this update, the only expected modified file is:

- `SESSION_CONTEXT.md`

There are local env files present/open (`.env`, `.env-icloud`,
`.env-icloud copy`, `.env-gmail`). Do not inspect, print, or commit secrets
from them unless the user explicitly asks and approves.

## Suggested Resume Step

Tomorrow:

1. Review:

   ```bash
   git status --short
   git diff
   ```

2. Run:

   ```bash
   .venv/bin/python -m pytest
   ```

3. Try local non-network commands:

   ```bash
   .venv/bin/python email_assistant.py providers
   .venv/bin/python email_assistant.py mailboxes --provider icloud
   .venv/bin/python email_assistant.py doctor --skip-imap-login
   .venv/bin/python email_assistant.py list --limit 5
   .venv/bin/python email_assistant.py actions --limit 10
   ```

4. If testing real IMAP with explicit user approval, useful examples are:

   ```bash
   .venv/bin/python email_assistant.py fetch --mailbox "INBOX" --search-mode unread
   .venv/bin/python email_assistant.py fetch --mailbox "Sent Messages" --search-mode recent
   .venv/bin/python email_assistant.py review --mailbox "Sent Messages" --search-mode recent
   ```

5. Launch the GUI only if useful:

   ```bash
   .venv/bin/python -m streamlit run app.py
   ```

Only run real IMAP fetch/login checks when the user explicitly approves
connecting to the inbox.
