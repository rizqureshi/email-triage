"""Microsoft Graph delegated OAuth helpers for read-only mail access."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import msal
except ImportError:  # pragma: no cover - exercised when dependency is absent
    msal = None


DEFAULT_TENANT = "consumers"
DEFAULT_SCOPES = ("User.Read", "Mail.Read", "offline_access")
DEFAULT_TOKEN_CACHE_PATH = ".msal_token_cache.json"


@dataclass(frozen=True)
class GraphSettings:
    client_id: str
    tenant: str
    scopes: tuple[str, ...]
    token_cache_path: str


def load_graph_settings() -> GraphSettings:
    client_id = os.getenv("MS_GRAPH_CLIENT_ID", "").strip()
    if not client_id:
        raise ValueError("MS_GRAPH_CLIENT_ID is required for Outlook Graph mode.")

    scopes = tuple(os.getenv("MS_GRAPH_SCOPES", " ".join(DEFAULT_SCOPES)).split())
    return GraphSettings(
        client_id=client_id,
        tenant=os.getenv("MS_GRAPH_TENANT", DEFAULT_TENANT).strip() or DEFAULT_TENANT,
        scopes=scopes or DEFAULT_SCOPES,
        token_cache_path=DEFAULT_TOKEN_CACHE_PATH,
    )


def get_graph_access_token(settings: GraphSettings | None = None) -> str:
    settings = settings or load_graph_settings()
    if msal is None:
        raise RuntimeError("MSAL is not installed. Run pip install -r requirements.txt.")

    cache = msal.SerializableTokenCache()
    cache_path = Path(settings.token_cache_path)
    if cache_path.exists():
        cache.deserialize(cache_path.read_text(encoding="utf-8"))

    app = msal.PublicClientApplication(
        settings.client_id,
        authority=f"https://login.microsoftonline.com/{settings.tenant}",
        token_cache=cache,
    )

    result: dict[str, Any] | None = None
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(list(settings.scopes), account=accounts[0])

    if not result:
        flow = app.initiate_device_flow(scopes=list(settings.scopes))
        if "user_code" not in flow:
            raise RuntimeError("Could not start Microsoft Graph device-code login.")
        message = str(flow.get("message") or "Follow the Microsoft device login instructions.")
        print(message)
        result = app.acquire_token_by_device_flow(flow)

    if cache.has_state_changed:
        cache_path.write_text(cache.serialize(), encoding="utf-8")

    token = result.get("access_token") if isinstance(result, dict) else None
    if not token:
        error = _safe_graph_error(result)
        raise RuntimeError(f"Could not acquire Microsoft Graph access token. {error}")
    return str(token)


def _safe_graph_error(result: object) -> str:
    if not isinstance(result, dict):
        return "No token response was returned."
    description = str(result.get("error_description") or result.get("error") or "").strip()
    if not description:
        return "Microsoft did not return an access token."
    return description.replace(str(result.get("access_token") or ""), "[token]")
