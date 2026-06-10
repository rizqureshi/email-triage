# Email Assistant

A local, read-only email assistant for turning unread inbox messages into
summary cards, daily briefings, and practical answers about your inbox.

This is a prototype for personal review. It helps you understand email faster;
it does not act on your mailbox for you.

## What It Does

- Fetches unread emails in read-only mode.
- Summarizes messages into compact stored summary cards.
- Highlights priority, category, response needs, and action items.
- Generates a daily briefing from saved cards.
- Answers questions like "Catch me up" or "What emails need my response?"
- Analyzes a single pasted email and suggests a reply draft for review.

## Safety Promise

The tool:

- Does not send emails.
- Does not delete emails.
- Does not archive emails.
- Does not move emails.
- Does not mark emails as read.
- Fetches unread emails read-only.

Inbox fetching uses read-only IMAP access and avoids mailbox-changing commands.

## Setup

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with your iCloud IMAP settings. For iCloud Mail, use:

- `IMAP_HOST=imap.mail.me.com`
- Your full iCloud email address as `IMAP_USERNAME`
- An Apple app-specific password as `IMAP_PASSWORD`

Do not use your normal Apple Account password.

OpenAI is optional. Add this only if you want model-backed analysis and optional
AI answers:

```bash
OPENAI_API_KEY=your_key_here
```

## Recommended Usage

Use `email_assistant.py` as the main command:

```bash
python email_assistant.py doctor
python email_assistant.py fetch --max-messages 5 --save
python email_assistant.py list --priority urgent
python email_assistant.py actions
python email_assistant.py briefing --limit 20
python email_assistant.py ask "Catch me up"
python email_assistant.py ask "What emails need my response?" --ai
python email_assistant.py analyze --from "alex@example.com" --subject "Invoice question" \
  --body "Can you confirm whether invoice 1042 has been paid?"
```

Default output is human-readable. Add `--json` to any command for
machine-readable output.

The `--ai` flag is optional. Without it, Inbox Q&A uses deterministic local
rules. With `--ai`, Inbox Q&A sends only matched stored summary cards to OpenAI,
not raw email bodies and not the full database.

Browse saved summary cards without fetching mail:

```bash
python email_assistant.py list --priority urgent
python email_assistant.py list --priority high --requires-response
python email_assistant.py list --category billing
python email_assistant.py list --requires-response
```

Browse saved action items without fetching mail:

```bash
python email_assistant.py actions
python email_assistant.py actions --priority urgent
python email_assistant.py actions --json
```

## Local GUI

Run the browser-based demo app locally:

```bash
python -m streamlit run app.py
```

Streamlit opens the app in your local browser. The GUI uses the same local
`.env` settings and the same read-only backend modules as the CLI. It does not
send or modify emails. The CLI remains available for scripting and terminal
workflows.

## Check Your Setup

Run doctor before your first fetch or when troubleshooting:

```bash
python email_assistant.py doctor
```

Doctor validates local configuration, checks whether `.env` and the local
database exist, and can test IMAP login without fetching or modifying email. It
never prints secrets.

Use `--skip-imap-login` if you only want local configuration checks:

```bash
python email_assistant.py doctor --skip-imap-login
```

Use `--json` for machine-readable output:

```bash
python email_assistant.py doctor --json
```

## Troubleshooting

**IMAP authentication failed**

Use your full iCloud email address and an Apple app-specific password. Do not
use your normal Apple Account password.

**No cards found**

Run a fetch first and save the summary cards:

```bash
python email_assistant.py fetch --max-messages 5 --save
```

**OpenAI is not used**

Set `OPENAI_API_KEY` in `.env` if AI-backed analysis or `ask --ai` answers are
desired.

## Developer Details

For architecture, module documentation, individual scripts, storage details,
testing, and future development notes, see [DEVELOPER.md](DEVELOPER.md).
