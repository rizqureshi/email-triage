# MailTriage AI

MailTriage AI is a local, read-only email assistant for turning unread inbox
messages into summary cards, daily briefings, and practical answers about your
inbox.

This is a prototype for personal review. It helps you understand email faster;
it does not act on your mailbox for you.

## What It Does

- Fetches unread emails in read-only mode.
- Summarizes messages into compact stored summary cards.
- Highlights priority, category, response needs, and action items.
- Runs a one-step inbox review that fetches, saves, briefs, and lists actions.
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

- `EMAIL_PROVIDER=icloud`
- `IMAP_HOST=imap.mail.me.com`
- Your full iCloud email address as `IMAP_USERNAME`
- An Apple app-specific password as `IMAP_PASSWORD`

Do not use your normal Apple Account password.

OpenAI is optional. Add this only if you want model-backed analysis and optional
AI answers:

```bash
OPENAI_API_KEY=your_key_here
```

## Supported Providers

MailTriage AI supports IMAP presets for:

- iCloud Mail
- Gmail
- Outlook / Microsoft 365
- Yahoo Mail
- AOL Mail
- Custom IMAP

Start with iCloud or Gmail for easiest testing. Gmail may require enabling IMAP
and using an app password. Outlook / Microsoft 365 may require OAuth later
depending on the account or tenant policy. Custom IMAP can work for business
mailboxes if the provider supports IMAP over SSL.

List provider setup notes:

```bash
python email_assistant.py providers
python email_assistant.py providers --json
```

Authentication help is provider-specific. Run `python email_assistant.py doctor`
if login fails.

Example iCloud setup:

```bash
EMAIL_PROVIDER=icloud
IMAP_USERNAME=your_email@example.com
IMAP_PASSWORD=your_app_password
```

Example Gmail setup:

```bash
EMAIL_PROVIDER=gmail
IMAP_USERNAME=your_email@gmail.com
IMAP_PASSWORD=your_google_app_password
```

Example Outlook setup:

```bash
EMAIL_PROVIDER=outlook
IMAP_USERNAME=your_email@outlook.com
IMAP_PASSWORD=your_password_or_app_password_if_supported
```

Example custom IMAP setup:

```bash
EMAIL_PROVIDER=custom
IMAP_HOST=imap.example.com
IMAP_PORT=993
IMAP_USERNAME=you@example.com
IMAP_PASSWORD=your_password_or_app_password
```

## Recommended Usage

Use `email_assistant.py` as the main command:

```bash
python email_assistant.py doctor
python email_assistant.py providers
python email_assistant.py review
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

Run the easiest one-step workflow:

```bash
python email_assistant.py review
python email_assistant.py review --max-messages 10
python email_assistant.py review --json
```

Inbox review fetches unread emails read-only, saves local summary cards,
generates a briefing, and shows action items. It does not send or modify email.

## Mailbox / Folder Selection

The GUI offers provider-aware mailbox presets plus a custom mailbox override for
Fetch Emails and Inbox Review. Folder names vary by provider. If a preset does
not work, use the exact mailbox name shown by your email provider.

Folders with spaces, such as `Sent Messages`, are supported. MailTriage AI
safely quotes mailbox names internally while keeping the displayed folder name
readable.

Search modes:

- `unread` fetches only unread messages.
- `recent` fetches the most recent messages in the selected mailbox.

Sent folders usually do not contain unread messages, so use `--search-mode recent`
for Sent folders.

CLI examples:

```bash
python email_assistant.py fetch --mailbox "INBOX" --search-mode unread
python email_assistant.py fetch --mailbox "Sent Messages" --search-mode recent
python email_assistant.py review --mailbox "Sent Messages" --search-mode recent
python email_assistant.py fetch --mailbox "[Gmail]/Sent Mail" --search-mode recent
python email_assistant.py fetch --mailbox "Junk"
python email_assistant.py review --mailbox "[Gmail]/Spam"
python email_assistant.py fetch --mailbox "Sent Items"
python email_assistant.py mailboxes --provider gmail
```

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
