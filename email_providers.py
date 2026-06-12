"""IMAP provider presets for MailTriage AI."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ProviderPreset:
    key: str
    display_name: str
    imap_host: str
    imap_port: int
    ssl: bool
    default_mailbox: str
    notes: str
    app_password_recommended: bool
    app_password_required: bool
    oauth_may_be_needed_later: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


PROVIDER_PRESETS: dict[str, ProviderPreset] = {
    "icloud": ProviderPreset(
        key="icloud",
        display_name="iCloud Mail",
        imap_host="imap.mail.me.com",
        imap_port=993,
        ssl=True,
        default_mailbox="INBOX",
        notes="Use your full iCloud email address and an Apple app-specific password.",
        app_password_recommended=True,
        app_password_required=True,
        oauth_may_be_needed_later=False,
    ),
    "gmail": ProviderPreset(
        key="gmail",
        display_name="Gmail",
        imap_host="imap.gmail.com",
        imap_port=993,
        ssl=True,
        default_mailbox="INBOX",
        notes=(
            "Enable IMAP in Gmail settings. For password-based access, use Google "
            "2-Step Verification and an app password where available."
        ),
        app_password_recommended=True,
        app_password_required=False,
        oauth_may_be_needed_later=True,
    ),
    "outlook": ProviderPreset(
        key="outlook",
        display_name="Outlook / Microsoft 365",
        imap_host="outlook.office365.com",
        imap_port=993,
        ssl=True,
        default_mailbox="INBOX",
        notes=(
            "Personal Outlook accounts may work with IMAP. Microsoft 365 business "
            "tenants may require modern authentication/OAuth depending on tenant policy."
        ),
        app_password_recommended=False,
        app_password_required=False,
        oauth_may_be_needed_later=True,
    ),
    "yahoo": ProviderPreset(
        key="yahoo",
        display_name="Yahoo Mail",
        imap_host="imap.mail.yahoo.com",
        imap_port=993,
        ssl=True,
        default_mailbox="INBOX",
        notes="Use a Yahoo app password if normal password login is not accepted.",
        app_password_recommended=True,
        app_password_required=False,
        oauth_may_be_needed_later=False,
    ),
    "aol": ProviderPreset(
        key="aol",
        display_name="AOL Mail",
        imap_host="imap.aol.com",
        imap_port=993,
        ssl=True,
        default_mailbox="INBOX",
        notes="Use an AOL app password if normal password login is not accepted.",
        app_password_recommended=True,
        app_password_required=False,
        oauth_may_be_needed_later=False,
    ),
    "custom": ProviderPreset(
        key="custom",
        display_name="Custom IMAP",
        imap_host="",
        imap_port=993,
        ssl=True,
        default_mailbox="INBOX",
        notes="Enter the IMAP settings from your email provider.",
        app_password_recommended=False,
        app_password_required=False,
        oauth_may_be_needed_later=False,
    ),
}


def get_provider(provider_key: str) -> ProviderPreset:
    key = (provider_key or "").strip().lower() or "icloud"
    try:
        return PROVIDER_PRESETS[key]
    except KeyError as exc:
        raise ValueError(
            f"Unknown EMAIL_PROVIDER '{provider_key}'. Valid providers: "
            f"{', '.join(provider_choices())}"
        ) from exc


def list_providers() -> list[ProviderPreset]:
    return [PROVIDER_PRESETS[key] for key in provider_choices()]


def provider_choices() -> tuple[str, ...]:
    return ("icloud", "gmail", "outlook", "yahoo", "aol", "custom")


def mailbox_presets(provider_key: str) -> list[str]:
    key = (provider_key or "").strip().lower()
    presets = {
        "icloud": ["INBOX", "Junk", "Sent Messages", "Archive", "Trash"],
        "gmail": [
            "INBOX",
            "[Gmail]/Spam",
            "[Gmail]/Sent Mail",
            "[Gmail]/All Mail",
            "[Gmail]/Trash",
        ],
        "outlook": ["INBOX", "Junk Email", "Sent Items", "Archive", "Deleted Items"],
        "yahoo": ["INBOX", "Bulk Mail", "Sent", "Archive", "Trash"],
        "aol": ["INBOX", "Spam", "Sent", "Archive", "Trash"],
        "custom": ["INBOX", "Junk", "Spam", "Sent", "Sent Items", "Archive", "Trash"],
    }
    return presets.get(key, presets["custom"])


def default_mailbox(provider_key: str) -> str:
    try:
        return get_provider(provider_key).default_mailbox
    except ValueError:
        return "INBOX"


def authentication_help(provider_key: str) -> str:
    key = (provider_key or "").strip().lower()
    messages = {
        "icloud": (
            "IMAP authentication failed for iCloud Mail. Use your full iCloud email "
            "address and an Apple app-specific password."
        ),
        "gmail": (
            "IMAP authentication failed for Gmail. Enable IMAP in Gmail settings. "
            "For password-based access, use Google 2-Step Verification and an app "
            "password where available."
        ),
        "outlook": (
            "IMAP authentication failed for Outlook / Microsoft 365. Personal Outlook "
            "accounts may work with IMAP, but Microsoft 365 business tenants may "
            "require modern authentication/OAuth depending on tenant policy."
        ),
        "yahoo": (
            "IMAP authentication failed for Yahoo Mail. Use a Yahoo app password if "
            "normal password login is not accepted."
        ),
        "aol": (
            "IMAP authentication failed for AOL Mail. Use an AOL app password if "
            "normal password login is not accepted."
        ),
        "custom": (
            "IMAP authentication failed for Custom IMAP. Check the IMAP host, port, "
            "username, password or app password, and mailbox settings provided by "
            "your email provider."
        ),
    }
    return messages.get(
        key,
        "IMAP authentication failed. Check your email provider's IMAP settings and credentials.",
    )
