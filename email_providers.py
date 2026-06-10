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
