import pytest

import email_providers


def test_provider_preset_lookup() -> None:
    provider = email_providers.get_provider("gmail")

    assert provider.key == "gmail"
    assert provider.display_name == "Gmail"
    assert provider.imap_host == "imap.gmail.com"
    assert provider.imap_port == 993
    assert provider.ssl is True


def test_provider_choices_include_supported_providers() -> None:
    assert email_providers.provider_choices() == (
        "icloud",
        "gmail",
        "outlook",
        "yahoo",
        "aol",
        "custom",
    )
    assert [provider.key for provider in email_providers.list_providers()] == list(
        email_providers.provider_choices()
    )


def test_unknown_provider_error_lists_valid_choices() -> None:
    with pytest.raises(ValueError, match="Valid providers: icloud, gmail, outlook"):
        email_providers.get_provider("fastmail")


@pytest.mark.parametrize(
    ("provider_key", "expected"),
    [
        ("icloud", "IMAP authentication failed for iCloud Mail"),
        ("gmail", "IMAP authentication failed for Gmail"),
        ("outlook", "IMAP authentication failed for Outlook / Microsoft 365"),
        ("yahoo", "IMAP authentication failed for Yahoo Mail"),
        ("aol", "IMAP authentication failed for AOL Mail"),
        ("custom", "IMAP authentication failed for Custom IMAP"),
    ],
)
def test_authentication_help_returns_provider_specific_message(
    provider_key: str, expected: str
) -> None:
    assert expected in email_providers.authentication_help(provider_key)


def test_authentication_help_returns_generic_message_for_unknown_provider() -> None:
    assert email_providers.authentication_help("fastmail") == (
        "IMAP authentication failed. Check your email provider's IMAP settings and credentials."
    )


def test_mailbox_presets_for_gmail_include_spam_and_sent() -> None:
    presets = email_providers.mailbox_presets("gmail")

    assert "[Gmail]/Spam" in presets
    assert "[Gmail]/Sent Mail" in presets


def test_mailbox_presets_for_outlook_include_junk_and_sent_items() -> None:
    presets = email_providers.mailbox_presets("outlook")

    assert "Junk Email" in presets
    assert "Sent Items" in presets


def test_mailbox_presets_for_unknown_provider_use_generic_presets() -> None:
    presets = email_providers.mailbox_presets("fastmail")

    assert presets == ["INBOX", "Junk", "Spam", "Sent", "Sent Items", "Archive", "Trash"]
