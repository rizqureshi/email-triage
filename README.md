# Email Triage

AI-assisted email triage and reply drafting for local review.

This project is intentionally draft-only. It does not send emails automatically,
connect to SMTP, or call any provider's send endpoint.

## What It Does

- Classifies an email by priority and category.
- Summarizes the likely intent.
- Produces a suggested reply draft for human review.
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

## Files

- `config.py` loads environment-based settings.
- `triage.py` contains the email model, triage logic, and CLI.
- `.env.example` documents supported environment variables.
- `requirements.txt` lists runtime dependencies.

## Safety

This assistant never sends emails. It only creates text drafts. Keep that
boundary intact as the project grows.
