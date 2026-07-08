#!/usr/bin/env python3
"""Acquacotta MCP server — hosted, per-user, API-gateway access to plugin data.

A separate process from the Flask web app, speaking MCP over Streamable HTTP.
It stores nothing: every request carries a sealed bearer token (see
:mod:`mcp_tokens`) that it decrypts in memory to reach one user's own Google
Drive storage, through the exact same plugin functions the web app uses.

Auth: `Authorization: Bearer aqc_v1.<blob>` → unseal → check the per-user
Google Drive service → check the per-user revocation epoch (in the user's Drive) → dispatch.

Run: ``python3 mcp_server.py`` (host/port from MCP_HOST / MCP_PORT).
Behind the in-container Apache, `/mcp` proxies here; nothing else changes.
"""

import os

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_headers
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

import json_google_drive_storage
import mcp_tokens
import plugin_registry
import pomodoro_tools
import sheets_storage
import todos_plugin

# OAuth scopes needed to exchange a refresh token for Drive access.
SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid",
]

# Register the plugins the MCP server exposes. Drive-backed storage is the MCP
# backend (tokens carry a folder_id); todos is an active extension. This mirrors
# the web app's registration but is self-contained so we never import Flask.
plugin_registry.register("storage", "sheets", sheets_storage, sheets_storage.PLUGIN_METADATA)
plugin_registry.register(
    "storage", "json-google-drive", json_google_drive_storage, json_google_drive_storage.PLUGIN_METADATA
)
plugin_registry.register("extension", "todos", todos_plugin, todos_plugin.PLUGIN_METADATA)
plugin_registry.activate_storage("json-google-drive")
plugin_registry.activate_extension("todos")

mcp = FastMCP(
    "acquacotta",
    instructions=(
        "Acquacotta productivity cockpit — per-user access to the caller's own todos and "
        "pomodoro time-tracking data, stored in their Google Drive. Use list_todos/create_todo/"
        "complete_todo/update_todo to manage tasks, and get_pomodoros/get_time_summary to read "
        "tracked time. All calls act only on the authenticated user's data."
    ),
)


def _build_drive_service(refresh_token):
    """Exchange a refresh token for a live Google Drive service (nothing persisted)."""
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise ToolError("Server is missing Google OAuth configuration")
    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )
    try:
        credentials.refresh(Request())
    except Exception as exc:  # surface a clean re-auth hint to the agent
        raise ToolError(
            "Google credentials expired or revoked — re-enable MCP access in Acquacotta to mint a fresh token"
        ) from exc
    return build("drive", "v3", credentials=credentials)


def require_ctx():
    """Authenticate the current request and return {'service','folder_id','email'}.

    Raises ToolError (never touching storage) on any missing/invalid/revoked token.
    """
    # include_all=True is required: FastMCP 3.x strips `authorization` from the
    # default header view (2.x kept it), so ask for the full set explicitly.
    headers = get_http_headers(include_all=True)
    auth = headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise ToolError("Missing bearer token — set Authorization: Bearer <acquacotta MCP token>")
    token = auth[len("bearer ") :].strip()

    try:
        payload = mcp_tokens.unseal(token)
    except mcp_tokens.TokenError as exc:
        raise ToolError(f"Invalid token: {exc}") from exc

    drive_service = _build_drive_service(payload["refresh_token"])
    state = json_google_drive_storage.get_mcp_state(drive_service, payload["folder_id"])
    if mcp_tokens.is_revoked(payload, state):
        raise ToolError("Token revoked — MCP access is disabled or this token was superseded")

    return {"service": drive_service, "folder_id": payload["folder_id"], "email": payload["email"]}


# Core tools (pomodoros) are always available; plugin-contributed tools (todos,
# and future plugins) register only while their plugin is active.
pomodoro_tools.register_mcp_tools(mcp, require_ctx)
for registrar in plugin_registry.get_mcp_tool_registrars():
    registrar(mcp, require_ctx)


def main():
    host = os.environ.get("MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("MCP_PORT", "5001"))
    # FastMCP's DNS-rebinding host/origin protection assumes a localhost-browser
    # threat model: it rejects any Host header that isn't localhost with a 421.
    # Acquacotta runs the server bound to 127.0.0.1 behind a trusted reverse proxy
    # that terminates TLS and forwards the public Host, and every data operation
    # requires a bearer token — so Apache + token auth are the real controls and
    # this check only breaks the proxied /mcp path. Disable it.
    mcp.run(transport="streamable-http", host=host, port=port, host_origin_protection=False)


if __name__ == "__main__":
    main()
