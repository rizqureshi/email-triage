from unittest.mock import Mock

import pytest

import graph_auth


def test_load_graph_settings_requires_client_id(monkeypatch) -> None:
    monkeypatch.delenv("MS_GRAPH_CLIENT_ID", raising=False)

    with pytest.raises(ValueError, match="MS_GRAPH_CLIENT_ID is required"):
        graph_auth.load_graph_settings()


def test_load_graph_settings_defaults(monkeypatch) -> None:
    monkeypatch.setenv("MS_GRAPH_CLIENT_ID", "client-id")
    monkeypatch.delenv("MS_GRAPH_TENANT", raising=False)
    monkeypatch.delenv("MS_GRAPH_SCOPES", raising=False)

    settings = graph_auth.load_graph_settings()

    assert settings.client_id == "client-id"
    assert settings.tenant == "consumers"
    assert settings.scopes == ("User.Read", "Mail.Read", "offline_access")
    assert settings.token_cache_path == ".msal_token_cache.json"


def test_load_graph_settings_parses_scopes(monkeypatch) -> None:
    monkeypatch.setenv("MS_GRAPH_CLIENT_ID", "client-id")
    monkeypatch.setenv("MS_GRAPH_TENANT", "common")
    monkeypatch.setenv("MS_GRAPH_SCOPES", "User.Read Mail.Read")

    settings = graph_auth.load_graph_settings()

    assert settings.tenant == "common"
    assert settings.scopes == ("User.Read", "Mail.Read")


def test_get_graph_access_token_uses_silent_token_without_printing_token(
    monkeypatch, tmp_path, capsys
) -> None:
    cache = Mock()
    cache.has_state_changed = False
    app = Mock()
    app.get_accounts.return_value = [{"username": "user@example.com"}]
    app.acquire_token_silent.return_value = {"access_token": "secret-token"}
    fake_msal = Mock(
        SerializableTokenCache=Mock(return_value=cache),
        PublicClientApplication=Mock(return_value=app),
    )
    monkeypatch.setattr(graph_auth, "msal", fake_msal)
    settings = graph_auth.GraphSettings(
        client_id="client-id",
        tenant="consumers",
        scopes=("User.Read", "Mail.Read"),
        token_cache_path=str(tmp_path / ".msal_token_cache.json"),
    )

    token = graph_auth.get_graph_access_token(settings)
    captured = capsys.readouterr()

    assert token == "secret-token"
    assert "secret-token" not in captured.out
    app.initiate_device_flow.assert_not_called()


def test_get_graph_access_token_device_flow_prints_instructions_not_token(
    monkeypatch, tmp_path, capsys
) -> None:
    cache = Mock()
    cache.has_state_changed = False
    app = Mock()
    app.get_accounts.return_value = []
    app.initiate_device_flow.return_value = {
        "user_code": "ABCD",
        "message": "Go to Microsoft and enter ABCD.",
    }
    app.acquire_token_by_device_flow.return_value = {"access_token": "secret-token"}
    fake_msal = Mock(
        SerializableTokenCache=Mock(return_value=cache),
        PublicClientApplication=Mock(return_value=app),
    )
    monkeypatch.setattr(graph_auth, "msal", fake_msal)
    settings = graph_auth.GraphSettings(
        client_id="client-id",
        tenant="consumers",
        scopes=("User.Read", "Mail.Read"),
        token_cache_path=str(tmp_path / ".msal_token_cache.json"),
    )

    token = graph_auth.get_graph_access_token(settings)
    captured = capsys.readouterr()

    assert token == "secret-token"
    assert "Go to Microsoft" in captured.out
    assert "secret-token" not in captured.out
