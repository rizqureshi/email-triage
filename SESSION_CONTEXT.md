# Session Context

Last updated: 2026-06-03

## Project

This repo is an email triage and reply-draft assistant at:

`/Users/RizwanHome/Documents/work/git/email-triage`

The project must remain draft-only. Do not add SMTP, email sending, deleting,
moving, archiving, or mark-read behavior.

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

- `fetch_imap.py`
  - Read-only IMAP ingestion module.
  - Uses `imaplib` and `email` from the Python standard library.
  - Reads unread messages only with `UNSEEN`.
  - Uses `select(..., readonly=True)` and `BODY.PEEK[]`.
  - Converts each fetched email into `EmailMessage` and passes it to
    `triage_email()`.
  - Prints JSON results.

- `.env.example`
  - Contains OpenAI settings and IMAP settings.

- `.env`
  - Created locally and ignored by git.
  - User added a paid OpenAI API key there.
  - Do not print, inspect, or commit the key unless explicitly necessary and
    approved by the user.

- Tests
  - `tests/test_triage.py`
  - `tests/test_fetch_imap.py`
  - IMAP tests use mocks and do not connect to a real email account.

## Verification

The last successful test command was run inside the local virtual environment:

```bash
source .venv/bin/activate && python -m pytest
```

Result at that time:

```text
20 passed
```

## Suggested Next Step

Tomorrow, test the OpenAI-backed triage path using a sample email first. After
that, configure IMAP values in `.env` and test read-only unread-email ingestion.
