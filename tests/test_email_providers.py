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
