# Email Triage

AI-assisted email triage and reply drafting for local review.

This project is intentionally draft-only. It does not send emails automatically,
connect to SMTP, or call any provider's send endpoint.
Inbox ingestion is read-only: it fetches unread messages, analyzes them, and
prints summary cards without changing mailbox state.

## What It Does

- Classifies an email by priority and category.
- Summarizes the likely intent.
- Produces a suggested reply draft for human review.
- Extracts action items and a structured email analysis.
- Works with a local heuristic fallback when no OpenAI API key is configured.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Add your API key to `.env` if you want model-backed triage and drafting:

```bash
OPENAI_API_KEY=your_key_here
```

If no API key is present, `triage.py` still runs using deterministic local
rules.

For read-only IMAP inbox ingestion, add your mailbox credentials to `.env`
using the values in `.env.example`.

## Usage

Run with inline email text:

```bash
python triage.py --from "alex@example.com" --subject "Invoice question" \
  --body "Hi, can you confirm whether invoice 1042 has been paid?"
```

Or pipe a message body from a file:

```bash
python triage.py --from "alex@example.com" --subject "Follow up" < email.txt
```

The output is JSON containing the triage result and a reply draft. Review and
edit the draft before sending it yourself in your email client.

### Email Analysis

Run the newer read-only analyzer when you want a richer summary, sender intent,
action item extraction, and a suggested reply:

```bash
python analyzer.py --from "alex@example.com" --subject "Invoice question" \
  --body "Can you confirm whether invoice 1042 has been paid?"
```

The analyzer returns JSON with:

- `summary`
- `sender_intent`
- `priority`
- `category`
- `requires_response`
- `action_items`
- `suggested_reply`
- `safety_note`

### Read-Only Inbox Ingestion

To fetch unread inbox messages and print summary cards:

```bash
python fetch_imap.py
```

You can override the mailbox or fetch limit for one run:

```bash
python fetch_imap.py --mailbox INBOX --max-messages 5
```

This command is read-only. It uses `readonly=True` mailbox selection, fetches
unread messages, and does not delete, move, archive, or mark anything as read.

## Files

- `config.py` loads environment-based settings.
- `triage.py` contains the email model, triage logic, and CLI.
- `analyzer.py` contains the read-only email intelligence CLI.
- `schemas.py` defines the shared analysis dataclasses.
- `.env.example` documents supported environment variables.
- `requirements.txt` lists runtime dependencies.

## Safety

This assistant never sends emails. It only creates text drafts. Keep that
boundary intact as the project grows.
