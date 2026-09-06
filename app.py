#!/usr/bin/env python3
"""Acquacotta - Pomodoro Time Tracking Application

Sovereign Sandbox v2: Stateless Server + IndexedDB

The server is stateless - it only handles:
1. OAuth authentication with Google
2. Proxying API calls to the active storage plugin (JSON on Drive, Google Sheets, etc.)

All user data lives in the browser's IndexedDB and optionally on the user's Google Drive.
The server never stores any user pomodoro data.

Credit: kirkjerk (localStorage approach idea, extended to IndexedDB)
"""

import json
import os
from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

# Allow OAuth scope changes (users may have previously granted different scopes)
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

import requests
from flask import Flask, Response, jsonify, redirect, render_template, request, session
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.middleware.proxy_fix import ProxyFix

import json_google_drive_storage
import json_pcloud_storage
import mcp_tokens
import plugin_registry
import pomodoro_tools
import sheets_storage
import storage_api
import todos_plugin
from storage_api import StorageUnavailable
from transports import pcloud_transport

# Register built-in plugins
plugin_registry.register("storage", "sheets", sheets_storage, sheets_storage.PLUGIN_METADATA)
plugin_registry.register(
    "storage", "json-google-drive", json_google_drive_storage, json_google_drive_storage.PLUGIN_METADATA
)
plugin_registry.register("storage", "json-pcloud", json_pcloud_storage, json_pcloud_storage.PLUGIN_METADATA)

# Mandatory feature plugins — always registered, always enabled, never toggleable.
# Pomodoro carries MCP tools; Settings is UI-only (metadata registration is enough,
# like the MCP plugin below).
plugin_registry.register("extension", "pomodoro", pomodoro_tools, pomodoro_tools.PLUGIN_METADATA)
SETTINGS_PLUGIN_METADATA = {
    "id": "settings",
    "name": "Settings",
    "description": "App preferences and timer configuration",
    "version": "1.0.0",
    "type": "extension",
    "author": "Crunchtools",
    "mandatory": True,
}
plugin_registry.register("extension", "settings", SimpleNamespace(), SETTINGS_PLUGIN_METADATA)

# Todos — optional plugin, per-user enable/disable (spec 008). activate_extension sets
# the registry default to on; the per-user choice (plugin_state_todos) governs actual
# enablement on web and MCP.
plugin_registry.register("extension", "todos", todos_plugin, todos_plugin.PLUGIN_METADATA)
plugin_registry.activate_extension("todos")

# MCP access appears in the plugin list. It has no server-side module contract —
# enable/disable and per-user state live in the /api/mcp/* routes + the user's Drive, so a
# metadata-only registration is enough. `has_mcp` flags the frontend to render its
# token UI and route its toggle to the MCP endpoints instead of the generic toggle.
MCP_PLUGIN_METADATA = {
    "id": "mcp",
    "name": "MCP Access",
    "description": "Let AI agents (Claude, Kagetora, Takeda) read and manage your todos and time data over MCP.",
    "version": "1.0.0",
    "type": "integration",
    "author": "crunchtools",
    "has_mcp": True,
}
plugin_registry.register("integration", "mcp", SimpleNamespace(), MCP_PLUGIN_METADATA)
# Default backend for users with no recorded choice (post-migration standard).
DEFAULT_STORAGE_BACKEND = "json-google-drive"
# The active backend is resolved per-user (see _active_storage_id); this only sets a
# harmless registry default for the no-user case, matching DEFAULT_STORAGE_BACKEND.
plugin_registry.activate_storage(DEFAULT_STORAGE_BACKEND)

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

# Session configuration — uses Flask's built-in signed-cookie sessions (no filesystem required)
secret_key = os.environ.get("FLASK_SECRET_KEY")
if not secret_key:
    if os.environ.get("FLASK_ENV") == "development":
        secret_key = "dev-secret-key-for-local-development-only"
    else:
        raise ValueError("FLASK_SECRET_KEY environment variable must be set in production")
app.config["SECRET_KEY"] = secret_key
# Only require HTTPS cookies in production (localhost uses HTTP)
# Can be overridden via SESSION_COOKIE_SECURE env var (set to "false" for dev)
session_cookie_secure = os.environ.get("SESSION_COOKIE_SECURE", "").lower()
if session_cookie_secure in ("false", "0", "no"):
    app.config["SESSION_COOKIE_SECURE"] = False
elif session_cookie_secure in ("true", "1", "yes"):
    app.config["SESSION_COOKIE_SECURE"] = True
else:
    # Default: secure in production, not secure in development
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get("FLASK_ENV") != "development"
app.config["SESSION_COOKIE_HTTPONLY"] = True  # Prevent JavaScript access
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"  # CSRF protection


@app.errorhandler(Exception)
def handle_exception(e):
    """Return JSON for API errors instead of HTML."""
    if request.path.startswith("/api/"):
        # Log the actual error for debugging, but don't expose details to client
        app.logger.error(f"API error: {e}")
        return jsonify({"error": "An internal error occurred"}), HTTPStatus.INTERNAL_SERVER_ERROR
    # For non-API routes, re-raise to get default handling
    raise e


# Google OAuth configuration
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid",
]

# pCloud OAuth configuration. pCloud is a storage backend only — Google stays the
# identity provider — so this credential pair is optional; without it the
# json-pcloud plugin simply cannot be linked.
PCLOUD_CLIENT_ID = os.environ.get("PCLOUD_CLIENT_ID")
PCLOUD_CLIENT_SECRET = os.environ.get("PCLOUD_CLIENT_SECRET")
PCLOUD_AUTHORIZE_URL = "https://my.pcloud.com/oauth2/authorize"
PCLOUD_DEFAULT_FOLDER_PATH = pcloud_transport.ACQUACOTTA_FOLDER_PATH

# OAuth requires HTTPS by default (secure)
# For local development, set OAUTHLIB_INSECURE_TRANSPORT=1 in your environment

# Data directory for user-to-spreadsheet mapping only (no user data stored)
DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "acquacotta"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Timer duration constants (in minutes)
DEFAULT_POMODORO_DURATION = 25
DEFAULT_SHORT_BREAK = 5
DEFAULT_LONG_BREAK = 15
TIMER_PRESET_MEDIUM = 10

# Default daily goal (in minutes)
DEFAULT_DAILY_GOAL = 300  # 5 hours

# Default pomodoros before long break
DEFAULT_POMODOROS_UNTIL_LONG_BREAK = 4

DEFAULT_POMODORO_TYPES = [
    "Content",
    "Customer/Partner/Community",
    "Learn/Train",
    "Product",
    "PTO",
    "Queued",
    "Social Media",
    "Team",
    "Travel",
    "Unqueued",
]

# Default settings for Sheets
DEFAULT_SETTINGS = {
    "timer_preset_1": DEFAULT_SHORT_BREAK,
    "timer_preset_2": TIMER_PRESET_MEDIUM,
    "timer_preset_3": DEFAULT_LONG_BREAK,
    "timer_preset_4": DEFAULT_POMODORO_DURATION,
    "short_break_minutes": DEFAULT_SHORT_BREAK,
    "long_break_minutes": DEFAULT_LONG_BREAK,
    "pomodoros_until_long_break": DEFAULT_POMODOROS_UNTIL_LONG_BREAK,
    "always_use_short_break": False,
    "sound_enabled": True,
    "notifications_enabled": True,
    "pomodoro_types": DEFAULT_POMODORO_TYPES,
    "auto_start_after_break": False,
    "tick_sound_during_breaks": False,
    "bell_at_pomodoro_end": True,
    "bell_at_break_end": True,
    "show_notes_field": False,
    "pip_timer_enabled": False,
    "working_hours_start": "08:00",
    "working_hours_end": "17:00",
    "clock_format": "auto",
    "period_labels": "auto",
    "daily_minutes_goal": DEFAULT_DAILY_GOAL,
}

# OAuth state token expiry (in seconds)
OAUTH_STATE_MAX_AGE_SECONDS = 600

# Flask default port
DEFAULT_PORT = 5000


# Per-user storage preference file. Holds ONLY routing metadata (each user's chosen
# backend + the location pointer for each backend) — never user content or PII beyond
# the account email used as the key. Shape:
#   {email: {"backend": "<id>", "sheets": "<spreadsheet_id>", "json-google-drive": "<folder_id>"}}
_BACKEND_KEY = "backend"


def _user_mapping_path():
    """Path to the per-user storage-preference file (migrates the legacy name)."""
    new_path = DATA_DIR / "user_storage.json"
    if not new_path.exists():
        legacy_path = DATA_DIR / "user_spreadsheets.json"
        if legacy_path.exists():
            legacy_path.rename(new_path)
    return new_path


def _read_user_mapping():
    path = _user_mapping_path()
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _write_user_mapping(mapping):
    with open(_user_mapping_path(), "w") as f:
        json.dump(mapping, f)


def _user_entry(mapping, email):
    """The per-user dict, upgrading the legacy bare-spreadsheet-id form."""
    entry = mapping.get(email, {})
    if isinstance(entry, str):  # legacy value was always a Sheets spreadsheet id
        return {"sheets": entry}
    return entry


def get_stored_location(email, plugin_id):
    """Get the stored location id for a user's given backend, or None."""
    return _user_entry(_read_user_mapping(), email).get(plugin_id)


def save_location(email, plugin_id, location_id):
    """Persist a user's location id for a backend."""
    mapping = _read_user_mapping()
    entry = _user_entry(mapping, email)
    entry[plugin_id] = location_id
    mapping[email] = entry
    _write_user_mapping(mapping)


def get_user_backend(email):
    """Return the user's authoritative chosen storage backend id, or None if unset."""
    return _user_entry(_read_user_mapping(), email).get(_BACKEND_KEY)


def set_user_backend(email, plugin_id):
    """Persist the user's authoritative storage-backend choice."""
    mapping = _read_user_mapping()
    entry = _user_entry(mapping, email)
    entry[_BACKEND_KEY] = plugin_id
    mapping[email] = entry
    _write_user_mapping(mapping)


def _oauth_redirect_uri(path):
    """Absolute redirect URI for an OAuth callback path, honoring the proxy."""
    # Allow override via env var for development (e.g., OAUTH_REDIRECT_BASE=http://localhost:5000)
    oauth_base = os.environ.get("OAUTH_REDIRECT_BASE")
    if oauth_base:
        return f"{oauth_base.rstrip('/')}{path}"
    # Build redirect URI from X-Forwarded headers or fall back to request host
    # Take first value if multiple proxies added headers (comma-separated)
    proto = request.headers.get("X-Forwarded-Proto", request.scheme).split(",")[0].strip()
    host = request.headers.get("X-Forwarded-Host", request.host).split(",")[0].strip()
    return f"{proto}://{host}{path}"


def get_google_flow():
    """Create Google OAuth flow."""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return None
    redirect_uri = _oauth_redirect_uri("/auth/callback")

    return Flow.from_client_config(
        {
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )


def get_credentials_from_request():
    """Extract credentials from request header or body (stateless approach)."""
    import base64

    # Try X-Credentials header (for GET/DELETE)
    creds_header = request.headers.get("X-Credentials")
    if creds_header:
        try:
            creds_data = json.loads(base64.b64decode(creds_header))
            return creds_data
        except Exception as e:
            app.logger.error(f"Failed to decode X-Credentials header: {e}")
            return None

    # Try _credentials in request body (for POST/PUT)
    if request.is_json:
        body = request.get_json(silent=True)
        if body and "_credentials" in body:
            return body["_credentials"]

    return None


def get_spreadsheet_id_from_request():
    """Extract spreadsheet_id from request credentials."""
    creds = get_credentials_from_request()
    if creds:
        return creds.get("spreadsheet_id")
    return None


def get_credentials():
    """Get Google credentials from request (stateless)."""
    creds_data = get_credentials_from_request()
    if not creds_data:
        return None

    try:
        credentials = Credentials(
            token=creds_data.get("token"),
            refresh_token=creds_data.get("refresh_token"),
            token_uri=creds_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=creds_data.get("client_id"),
            client_secret=creds_data.get("client_secret"),
            scopes=creds_data.get("scopes", []),
        )

        # Only attempt refresh if we have the necessary fields
        if credentials.expired and credentials.refresh_token and credentials.client_id:
            from google.auth.transport.requests import Request

            credentials.refresh(Request())

        return credentials
    except Exception as e:
        has_token = bool(creds_data.get("token"))
        has_refresh = bool(creds_data.get("refresh_token"))
        has_client = bool(creds_data.get("client_id"))
        app.logger.error(
            f"Error creating credentials: {e} (token={has_token}, refresh_token={has_refresh}, client_id={has_client})"
        )
        return None


def _google_service(api, version):
    """Build a Google API client from the current credentials, or None if unauthenticated."""
    credentials = get_credentials()
    if not credentials:
        return None
    return build(api, version, credentials=credentials)


def _request_user_email():
    """Email of the user making the current request — from the OAuth session (during
    the callback) or the credentials the client sends (stateless API requests)."""
    if session.get("user_email"):
        return session["user_email"]
    creds = get_credentials_from_request()
    return creds.get("user_email") if creds else None


def _active_storage_id():
    """The storage backend for THIS request's user: their authoritative recorded
    choice, never a shared global. Users with no recorded choice get the default."""
    email = _request_user_email()
    if email:
        backend = get_user_backend(email)
        if backend:
            return backend
    return DEFAULT_STORAGE_BACKEND


def _active_storage_backend():
    """The storage backend module for this request's user, or None if unregistered."""
    return plugin_registry.get_plugin("storage", _active_storage_id())


def _storage_context():
    """Build storage context for the requesting user's backend, or None.

    The resolved per-user backend is carried in the context so the data layer
    dispatches to THIS user's backend — never a shared global.
    """
    backend = _active_storage_backend()
    if backend is None:
        return None
    credentials = get_credentials()
    if not credentials:
        return None
    request_creds = get_credentials_from_request()
    if not request_creds:
        return None
    ctx = backend.build_context(credentials, request_creds)
    ctx["backend"] = backend
    return ctx


def is_logged_in():
    """Check if request has valid credentials (stateless)."""
    creds = get_credentials_from_request()
    if not creds or not creds.get("token"):
        return False
    backend = _active_storage_backend()
    if backend is None:
        return True
    metadata = getattr(backend, "PLUGIN_METADATA", {})
    required_fields = metadata.get("frontend_fields", [])
    return all(creds.get(f) for f in required_fields)


# =============================================================================
# Static Pages
# =============================================================================


@app.route("/")
def index():
    """Main page with timer."""
    return render_template("index.html")


@app.route("/privacy")
def privacy():
    """Privacy policy page."""
    return render_template("privacy.html")


@app.route("/terms")
def terms():
    """Terms of service page."""
    return render_template("terms.html")


# =============================================================================
# OAuth Authentication
# =============================================================================


@app.route("/auth/google")
def auth_google():
    """Initiate Google OAuth flow."""
    try:
        flow = get_google_flow()
        if not flow:
            return jsonify({"error": "Google OAuth not configured"}), HTTPStatus.INTERNAL_SERVER_ERROR
        authorization_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",  # Always get refresh_token for stateless architecture
        )

        # Bundle PKCE code_verifier + CSRF nonce into a signed state parameter.
        # Google echoes `state` back in the callback URL, so it survives the redirect
        # chain regardless of cookie behavior. No session/cookie dependency for PKCE.
        # The client sends the location id under the field matching its backend —
        # spreadsheet_id for Sheets, folder_id for JSON-on-Drive — never conflated.
        state_payload = {
            "s": state,  # Original CSRF nonce
            "cv": flow.code_verifier,  # PKCE code_verifier
        }
        requested_spreadsheet_id = request.args.get("spreadsheet_id", "").strip()
        requested_folder_id = request.args.get("folder_id", "").strip()
        if requested_spreadsheet_id:
            state_payload["sid"] = requested_spreadsheet_id
        if requested_folder_id:
            state_payload["fid"] = requested_folder_id

        s = URLSafeTimedSerializer(app.config["SECRET_KEY"])
        signed_state = s.dumps(state_payload)

        # Replace the state parameter in the authorization URL with our signed blob
        parsed = urlparse(authorization_url)
        params = parse_qs(parsed.query)
        params["state"] = [signed_state]
        authorization_url = urlunparse(parsed._replace(query=urlencode(params, doseq=True)))

        return redirect(authorization_url)
    except Exception as e:
        import traceback

        return f"<pre>Error: {e}\n\n{traceback.format_exc()}</pre>", HTTPStatus.INTERNAL_SERVER_ERROR


def _validate_oauth_callback():
    """Validate and decode the signed OAuth state from the callback URL.

    Returns (state_data, code, error_response) — error_response is None on success.
    """
    callback_state = request.args.get("state")
    if not callback_state:
        app.logger.warning("OAuth callback: no state parameter in callback URL")
        return None, None, (jsonify({"error": "Missing OAuth state"}), HTTPStatus.BAD_REQUEST)

    s = URLSafeTimedSerializer(app.config["SECRET_KEY"])
    try:
        state_data = s.loads(callback_state, max_age=OAUTH_STATE_MAX_AGE_SECONDS)
    except SignatureExpired:
        app.logger.info("OAuth callback: state expired, restarting flow")
        return None, None, redirect("/auth/google")
    except BadSignature:
        app.logger.warning("OAuth callback: invalid state signature — possible CSRF")
        return None, None, (jsonify({"error": "Invalid OAuth state"}), HTTPStatus.BAD_REQUEST)

    code = request.args.get("code")
    if not code:
        return None, None, (jsonify({"error": "Missing authorization code"}), HTTPStatus.BAD_REQUEST)

    return state_data, code, None


def _provision_sheets(credentials, user_email, requested_id):
    """Provision a Google Sheets backend. Returns (spreadsheet_id, existed)."""
    stored_id = get_stored_location(user_email, "sheets")
    id_to_use = requested_id or stored_id

    if id_to_use:
        try:
            sheets_service = build("sheets", "v4", credentials=credentials)
            sheets_service.spreadsheets().get(spreadsheetId=id_to_use).execute()
            save_location(user_email, "sheets", id_to_use)
            return id_to_use, True
        except HttpError:
            id_to_use = None

    if not id_to_use:
        drive_service = build("drive", "v3", credentials=credentials)
        spreadsheet = (
            drive_service.files()
            .create(
                body={"name": "Acquacotta - Pomodoro Tracker", "mimeType": "application/vnd.google-apps.spreadsheet"},
                fields="id",
            )
            .execute()
        )
        new_id = spreadsheet["id"]
        save_location(user_email, "sheets", new_id)

        sheets_service = build("sheets", "v4", credentials=credentials)
        sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=new_id,
            body={
                "requests": [
                    {"updateSheetProperties": {"properties": {"sheetId": 0, "title": "Pomodoros"}, "fields": "title"}},
                    {"addSheet": {"properties": {"title": "Settings"}}},
                ]
            },
        ).execute()
        sheets_service.spreadsheets().values().update(
            spreadsheetId=new_id,
            range="Pomodoros!A1:G1",
            valueInputOption="RAW",
            body={"values": [["id", "name", "type", "start_time", "end_time", "duration_minutes", "notes"]]},
        ).execute()
        sheets_service.spreadsheets().values().update(
            spreadsheetId=new_id,
            range="Settings!A1:B1",
            valueInputOption="RAW",
            body={"values": [["key", "value"]]},
        ).execute()
        return new_id, False

    return id_to_use, True


def _provision_json_google_drive(credentials, user_email, requested_id):
    """Provision a JSON-on-Google-Drive backend. Returns (folder_id, existed)."""
    from transports.google_drive_transport import GoogleDriveTransport

    stored_id = get_stored_location(user_email, "json-google-drive")
    hint_id = requested_id or stored_id
    try:
        drive_service = build("drive", "v3", credentials=credentials)
        transport = GoogleDriveTransport(drive_service, hint_id)
        folder_id = transport.ensure_directory()
    except Exception as e:
        app.logger.error(f"Failed to provision Google Drive storage: {e}")
        raise
    existed = hint_id == folder_id and hint_id is not None
    save_location(user_email, "json-google-drive", folder_id)
    return folder_id, existed


def _pending_auth_handoff(credentials_data, settings_data, message="Completing login..."):
    """Hand an OAuth result off to storage.js via sessionStorage, then redirect.

    The callback deliberately does NOT open IndexedDB itself. storage.js is the
    single owner of the IndexedDB schema (store list + DB version); it picks up
    this pending login on load and writes it with the correct version. This
    removes the duplicated schema that previously let the callback's stale DB
    version throw VersionError and silently drop credentials, leaving the user
    logged out after a "successful" login.

    storage.js merges `credentials` into whatever is already stored, so linking
    pCloud does not evict the Google identity and vice versa.
    """
    pending_auth = {"credentials": credentials_data, "settings": settings_data}
    return f"""<!DOCTYPE html>
<html>
<head><title>Logging in...</title></head>
<body>
<p>{message}</p>
<script>
try {{
    sessionStorage.setItem('acquacotta_pending_auth', JSON.stringify({json.dumps(pending_auth)}));
}} catch (e) {{
    console.error('Failed to stash pending auth:', e);
}}
window.location.href = '/?view=settings';
</script>
</body>
</html>"""


def _provision_pcloud_folder(pcloud_client, user_email, requested_path):
    """Create the user's Acquacotta folder on pCloud. Returns (folder_path, existed).

    Only callable from the pCloud OAuth callback, which is the one place a pCloud
    token exists server-side. "Existed" means the folder already held data, so a
    returning user is not shown the first-run initial-sync prompt.
    """
    transport = pcloud_transport.PCloudTransport(pcloud_client, requested_path or PCLOUD_DEFAULT_FOLDER_PATH)
    folder_path = transport.ensure_directory()
    existed = transport.file_exists(json_pcloud_storage.POMODOROS_FILE)
    save_location(user_email, "json-pcloud", folder_path)
    return folder_path, existed


def _provision_json_pcloud(credentials, user_email, requested_id):
    """Resolve the JSON-on-pCloud backend during a Google sign-in.

    Creating the folder needs a pCloud token, and a Google sign-in doesn't carry
    one — that work happens once, in the pCloud OAuth callback. So this only
    restates the path the user already linked, letting a returning pCloud user
    sign in with Google and land back on their own folder without re-linking.
    """
    stored_path = get_stored_location(user_email, "json-pcloud")
    folder_path = requested_id or stored_path or PCLOUD_DEFAULT_FOLDER_PATH
    save_location(user_email, "json-pcloud", folder_path)
    return folder_path, bool(stored_path)


def _provision_storage(plugin_id, credentials, user_email, requested_id):
    """Provision the active storage backend. Returns (location_id, existed)."""
    provisioners = {
        "sheets": _provision_sheets,
        "json-google-drive": _provision_json_google_drive,
        "json-pcloud": _provision_json_pcloud,
    }
    provisioner = provisioners.get(plugin_id)
    if not provisioner:
        raise ValueError(f"No provisioner for storage plugin: {plugin_id}")
    return provisioner(credentials, user_email, requested_id)


@app.route("/auth/callback")
def auth_callback():
    """Handle Google OAuth callback."""
    try:
        # Decode the signed state parameter — contains PKCE code_verifier and CSRF nonce.
        # The state travels through Google's redirect (not cookies), so it's guaranteed to
        # survive regardless of browser cookie behavior, privacy extensions, or session loss.
        state_data, code, error = _validate_oauth_callback()
        if error:
            return error

        code_verifier = state_data["cv"]
        requested_spreadsheet_id = state_data.get("sid")
        requested_folder_id = state_data.get("fid")

        flow = get_google_flow()
        if not flow:
            return jsonify({"error": "Google OAuth not configured"}), HTTPStatus.INTERNAL_SERVER_ERROR

        flow.code_verifier = code_verifier
        flow.fetch_token(code=code)
        credentials = flow.credentials

        # Store credentials in session
        session["credentials"] = {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": list(credentials.scopes),
        }

        # Check if we have all required scopes (user may have authorized with old scopes)
        required_scopes = {"https://www.googleapis.com/auth/drive.file"}
        granted_scopes = set(credentials.scopes) if credentials.scopes else set()
        if not required_scopes.issubset(granted_scopes):
            # Missing required scopes - clear session and re-authorize
            session.clear()
            flow = get_google_flow()
            authorization_url, state = flow.authorization_url(
                access_type="offline",
                include_granted_scopes="false",  # Request fresh scopes
                prompt="consent",  # Force consent screen to get new scopes
            )
            # Same signed-state pattern as auth_google()
            reauth_payload = {"s": state, "cv": flow.code_verifier}
            signed_state = URLSafeTimedSerializer(app.config["SECRET_KEY"]).dumps(reauth_payload)
            parsed = urlparse(authorization_url)
            params = parse_qs(parsed.query)
            params["state"] = [signed_state]
            authorization_url = urlunparse(parsed._replace(query=urlencode(params, doseq=True)))
            return redirect(authorization_url)

        # Get user info
        oauth2_service = build("oauth2", "v2", credentials=credentials)
        user_info = oauth2_service.userinfo().get().execute()
        user_email = user_info.get("email")
        session["user_email"] = user_email
        session["user_name"] = user_info.get("name")
        session["user_picture"] = user_info.get("picture")

        # Resolve THIS user's backend (their recorded choice, or the default for a
        # first-time user) and provision it with the id matching that backend.
        # The login form only offers a Google-side id, so pCloud users have nothing
        # to state here — their linked folder path comes from their stored location.
        active_storage_id = _active_storage_id()
        requested_location_id = {
            "json-google-drive": requested_folder_id,
            "json-pcloud": None,
        }.get(active_storage_id, requested_spreadsheet_id)
        location_id, location_existed = _provision_storage(
            active_storage_id, credentials, user_email, requested_location_id
        )
        # Record the backend as this user's authoritative choice (survives sign-out).
        set_user_backend(user_email, active_storage_id)

        # Build credentials data for frontend storage (AUTH store - ephemeral)
        credentials_data = {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": list(credentials.scopes),
            "user_email": user_email,
            "user_name": user_info.get("name"),
            "user_picture": user_info.get("picture"),
        }

        # Settings data (SETTINGS store - persistent)
        # Write the plugin's frontend_fields so the browser sends them with API requests
        backend = _active_storage_backend()
        metadata = getattr(backend, "PLUGIN_METADATA", {})
        frontend_fields = metadata.get("frontend_fields", [])

        settings_data = {"storage_existed": location_existed}
        for field in frontend_fields:
            settings_data[field] = location_id

        # Clear server session - credentials will live in browser IndexedDB
        session.clear()

        return _pending_auth_handoff(credentials_data, settings_data)
    except Exception as e:
        import traceback

        return f"<pre>Error: {e}\n\n{traceback.format_exc()}</pre>", HTTPStatus.INTERNAL_SERVER_ERROR


@app.route("/auth/pcloud")
def auth_pcloud():
    """Start the pCloud link flow.

    pCloud is storage, not identity: the user is already signed in with Google,
    so the browser tells us which account is linking. That email is signed into
    the OAuth state (the same signed, short-lived blob the Google flow uses)
    rather than passed as a plain round-trip parameter, so it cannot be swapped
    for someone else's on the way back through pCloud.
    """
    if not PCLOUD_CLIENT_ID or not PCLOUD_CLIENT_SECRET:
        return jsonify({"error": "pCloud OAuth not configured"}), HTTPStatus.INTERNAL_SERVER_ERROR

    user_email = request.args.get("user_email", "").strip()
    if not user_email:
        return jsonify({"error": "Sign in with Google before linking pCloud"}), HTTPStatus.BAD_REQUEST

    state_payload = {"email": user_email}
    requested_path = request.args.get("pcloud_folder_path", "").strip()
    if requested_path:
        state_payload["path"] = requested_path
    signed_state = URLSafeTimedSerializer(app.config["SECRET_KEY"]).dumps(state_payload)

    params = {
        "client_id": PCLOUD_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": _oauth_redirect_uri("/auth/pcloud/callback"),
        "state": signed_state,
    }
    return redirect(f"{PCLOUD_AUTHORIZE_URL}?{urlencode(params)}")


@app.route("/auth/pcloud/callback")
def auth_pcloud_callback():
    """Exchange the pCloud code for a token, provision /Acquacotta, hand off."""
    try:
        if not PCLOUD_CLIENT_ID or not PCLOUD_CLIENT_SECRET:
            return jsonify({"error": "pCloud OAuth not configured"}), HTTPStatus.INTERNAL_SERVER_ERROR

        state_data, code, error = _validate_oauth_callback()
        if error:
            return error

        user_email = state_data.get("email")
        if not user_email:
            return jsonify({"error": "Invalid pCloud OAuth state"}), HTTPStatus.BAD_REQUEST

        # pCloud tells us in the callback which region minted the code; the token
        # is only valid against that region's API host, so it travels with it.
        api_host = request.args.get("hostname") or pcloud_transport.API_HOSTS_BY_LOCATION_ID.get(
            request.args.get("locationid", type=int), pcloud_transport.US_API_HOST
        )

        token_response = requests.get(
            f"https://{api_host}/oauth2_token",
            params={
                "client_id": PCLOUD_CLIENT_ID,
                "client_secret": PCLOUD_CLIENT_SECRET,
                "code": code,
            },
            timeout=pcloud_transport.REQUEST_TIMEOUT_SECONDS,
        )
        token_response.raise_for_status()
        token_data = token_response.json()
        access_token = token_data.get("access_token")
        if not access_token:
            app.logger.error(f"pCloud token exchange failed: result={token_data.get('result')}")
            return jsonify({"error": "pCloud authorization failed"}), HTTPStatus.BAD_GATEWAY

        client = pcloud_transport.PCloudClient(access_token, api_host)
        folder_path, folder_existed = _provision_pcloud_folder(client, user_email, state_data.get("path"))
        # Linking pCloud is the act of choosing it — record it as authoritative.
        set_user_backend(user_email, "json-pcloud")

        # Merged into the browser's existing credentials record, so the Google
        # identity survives; only the pCloud half is written here.
        credentials_data = {"pcloud_token": access_token, "pcloud_api_host": api_host}
        settings_data = {"storage_existed": folder_existed, "pcloud_folder_path": folder_path}
        return _pending_auth_handoff(credentials_data, settings_data, message="Linking pCloud...")
    except Exception as e:
        app.logger.error(f"pCloud OAuth callback failed: {e}")
        return jsonify({"error": "pCloud authorization failed"}), HTTPStatus.INTERNAL_SERVER_ERROR


@app.route("/auth/logout")
def auth_logout():
    """Log out and clear session."""
    session.clear()
    return redirect("/")


@app.route("/api/auth/status")
def auth_status():
    """Get current authentication status."""
    if is_logged_in():
        return jsonify(
            {
                "logged_in": True,
                "email": session.get("user_email"),
                "name": session.get("user_name"),
                "picture": session.get("user_picture"),
                "spreadsheet_id": session.get("spreadsheet_id"),
                "needs_initial_sync": session.get("needs_initial_sync", False),
            }
        )
    return jsonify(
        {
            "logged_in": False,
            "google_configured": bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
        }
    )


@app.route("/api/auth/clear-initial-sync", methods=["POST"])
def clear_initial_sync():
    """Clear the needs_initial_sync flag after frontend has synced."""
    session["needs_initial_sync"] = False
    return jsonify({"status": "ok"})


@app.route("/api/auth/spreadsheet", methods=["POST"])
def update_spreadsheet():
    """Update the spreadsheet ID for the current user."""
    if not is_logged_in():
        return jsonify({"error": "Not logged in"}), HTTPStatus.UNAUTHORIZED

    request_body = request.json
    new_id = request_body.get("spreadsheet_id", "").strip()
    if not new_id:
        return jsonify({"error": "Spreadsheet ID is required"}), HTTPStatus.BAD_REQUEST

    # Verify we can access this spreadsheet
    try:
        sheets_service = _google_service("sheets", "v4")
        sheets_service.spreadsheets().get(spreadsheetId=new_id).execute()
    except HttpError:
        return jsonify({"error": "Cannot access spreadsheet. Make sure you have edit access."}), HTTPStatus.BAD_REQUEST

    # Update session and persisted mapping
    session["spreadsheet_id"] = new_id
    if session.get("user_email"):
        save_location(session["user_email"], "sheets", new_id)

    return jsonify({"status": "ok", "spreadsheet_id": new_id})


# =============================================================================
# Storage Provisioning
# =============================================================================


@app.route("/api/storage/provision", methods=["POST"])
def api_provision_storage():
    """Provision the active storage backend using existing credentials.

    Called automatically when the frontend detects a plugin switch — the user
    has valid Google tokens but is missing the new plugin's location field
    (e.g., has spreadsheet_id but not folder_id). This endpoint provisions the
    new backend (creates the Drive folder, etc.) and returns the location fields
    the frontend should store in IndexedDB.
    """
    credentials = get_credentials()
    if not credentials:
        return jsonify({"error": "Not authenticated"}), HTTPStatus.UNAUTHORIZED

    request_creds = get_credentials_from_request()
    user_email = request_creds.get("user_email") if request_creds else None
    if not user_email:
        return jsonify({"error": "No user email in credentials"}), HTTPStatus.BAD_REQUEST

    active_id = _active_storage_id()
    if not active_id:
        return jsonify({"error": "No storage plugin active"}), HTTPStatus.BAD_REQUEST

    try:
        location_id, existed = _provision_storage(active_id, credentials, user_email, None)
    except Exception as e:
        app.logger.error(f"Storage provisioning failed: {e}")
        return jsonify({"error": f"Provisioning failed: {e}"}), HTTPStatus.INTERNAL_SERVER_ERROR

    backend = _active_storage_backend()
    metadata = getattr(backend, "PLUGIN_METADATA", {})
    frontend_fields = metadata.get("frontend_fields", [])

    provisioning_response = {"status": "ok", "existed": existed, "plugin_id": active_id}
    for field in frontend_fields:
        provisioning_response[field] = location_id

    return jsonify(provisioning_response)


# =============================================================================
# Storage Migration
# =============================================================================


@app.route("/api/migrate-to-json", methods=["POST"])
def api_migrate_to_json():
    """Migrate data from Sheets backend to JSON-on-Drive.

    Reads all pomodoros and settings from Google Sheets, writes them to
    JSON files on Google Drive, then switches the active storage backend.
    The original Sheet is preserved as a backup.
    """
    credentials = get_credentials()
    request_creds = get_credentials_from_request()
    user_email = request_creds.get("user_email") if request_creds else None

    if not credentials or not user_email:
        status = HTTPStatus.UNAUTHORIZED if not credentials else HTTPStatus.BAD_REQUEST
        msg = "Not authenticated" if not credentials else "No user email in credentials"
        return jsonify({"error": msg}), status

    if _active_storage_id() != "sheets":
        return jsonify({"error": "Migration is only available when using the Sheets backend"}), HTTPStatus.BAD_REQUEST

    try:
        # Step 1: Read all data from Sheets
        sheets_ctx = sheets_storage.build_context(credentials, request_creds)
        pomodoros = sheets_storage.get_pomodoros(sheets_ctx["service"], sheets_ctx["location"])
        user_settings = sheets_storage.get_settings(sheets_ctx["service"], sheets_ctx["location"], DEFAULT_SETTINGS)

        # Step 2: Provision JSON-on-Drive folder
        folder_id, _existed = _provision_json_google_drive(credentials, user_email, None)

        # Step 3: Write data to JSON backend (merge-safe — won't destroy existing Drive files)
        # save_pomodoros_batch deduplicates by ID; save_settings merges keys
        json_ctx = json_google_drive_storage.build_context(credentials, {"folder_id": folder_id})
        if pomodoros:
            json_google_drive_storage.save_pomodoros_batch(json_ctx["service"], json_ctx["location"], pomodoros)
        json_google_drive_storage.save_settings(
            json_ctx["service"], json_ctx["location"], user_settings, replace_all=False
        )
    except Exception as e:
        app.logger.error(f"Migration failed: {e}")
        return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR

    # Step 4: Switch this user's backend (only after successful write)
    save_location(user_email, "json-google-drive", folder_id)
    set_user_backend(user_email, "json-google-drive")

    return jsonify(
        {
            "status": "ok",
            "pomodoro_count": len(pomodoros),
            "folder_id": folder_id,
        }
    )


# =============================================================================
# Plugin API
# =============================================================================


@app.route("/api/plugins")
def api_list_plugins():
    """List all registered plugins with their status.

    Storage `active` is resolved per-request from the requesting user's own recorded
    backend choice, never a shared global.
    """
    active_storage = _active_storage_id()
    plugins = plugin_registry.list_plugins()
    for plugin in plugins:
        if plugin.get("plugin_type") == "storage":
            plugin["active"] = plugin.get("id") == active_storage
    return jsonify(
        {
            "plugins": plugins,
            "types": plugin_registry.list_plugin_types(),
            "active_storage": active_storage,
        }
    )


@app.route("/api/plugins/toggle", methods=["POST"])
def api_toggle_plugin():
    """Enable or disable a plugin."""
    toggle_request = request.get_json(silent=True)
    if not toggle_request or "plugin_id" not in toggle_request or "plugin_type" not in toggle_request:
        return jsonify({"error": "plugin_id and plugin_type required"}), HTTPStatus.BAD_REQUEST

    plugin_type = toggle_request["plugin_type"]
    plugin_id = toggle_request["plugin_id"]
    enable = toggle_request.get("enable", True)

    if plugin_type == "storage":
        # A storage backend is a per-user authoritative choice, not a global toggle:
        # enabling one records it as this user's backend (they switch by enabling another).
        email = _request_user_email()
        if not email:
            return jsonify({"error": "Not authenticated"}), HTTPStatus.UNAUTHORIZED
        if enable:
            if plugin_registry.get_plugin("storage", plugin_id) is None:
                return jsonify({"error": f"Storage plugin not registered: {plugin_id}"}), HTTPStatus.BAD_REQUEST
            set_user_backend(email, plugin_id)
    elif plugin_type == "extension":
        # Extension enablement is a per-user preference, not a process-global. The
        # client persists it as plugin_state_<id> in the user's own settings (synced
        # to their storage); the web UI resolves it per-user and the MCP server gates
        # each caller's tools on their own copy. So we intentionally do NOT flip the
        # shared registry flag here (that would reconfigure the app for every user).
        if plugin_registry.get_plugin("extension", plugin_id) is None:
            return jsonify({"error": f"Extension plugin not registered: {plugin_id}"}), HTTPStatus.BAD_REQUEST
        # Mandatory plugins (Pomodoro, Settings) can never be disabled (spec 009).
        if plugin_registry.is_mandatory("extension", plugin_id):
            return jsonify(
                {"error": f"'{plugin_id}' is a required plugin and cannot be disabled"}
            ), HTTPStatus.FORBIDDEN
    else:
        return jsonify({"error": f"Toggle not yet supported for type: {plugin_type}"}), HTTPStatus.BAD_REQUEST

    return jsonify(
        {
            "status": "ok",
            "active_storage": _active_storage_id(),
        }
    )


# =============================================================================
# Storage Proxy Endpoints
# Routes proxy data operations through the active storage plugin.
# =============================================================================


@app.route("/api/sheets/pomodoros", methods=["GET"])
def proxy_get_pomodoros():
    """Proxy read from Google Sheets - stateless, credentials from request."""
    if not is_logged_in():
        return jsonify({"error": "Not logged in"}), HTTPStatus.UNAUTHORIZED

    try:
        ctx = _storage_context()
        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")
        pomodoros = storage_api.get_pomodoros(ctx, start_date, end_date)
        return jsonify(pomodoros)
    except HttpError as e:
        return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


@app.route("/api/sheets/pomodoros/count")
def proxy_get_pomodoro_count():
    """Get count of pomodoros - efficient, only fetches IDs."""
    if not is_logged_in():
        return jsonify({"error": "Not logged in"}), HTTPStatus.UNAUTHORIZED

    try:
        ctx = _storage_context()
        count = storage_api.count_pomodoros(ctx)
        return jsonify({"count": count})
    except (HttpError, StorageUnavailable) as e:
        return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


def get_request_data():
    """Get request JSON data, stripping _credentials if present."""
    request_body = request.json
    if request_body and "_credentials" in request_body:
        request_body = {k: v for k, v in request_body.items() if k != "_credentials"}
    return request_body


@app.route("/api/sheets/pomodoros", methods=["POST"])
def proxy_create_pomodoro():
    """Proxy write to Google Sheets - stateless, credentials from request."""
    if not is_logged_in():
        return jsonify({"error": "Not logged in"}), HTTPStatus.UNAUTHORIZED

    try:
        ctx = _storage_context()
        if not ctx.get("service"):
            return jsonify({"error": "Failed to create storage service - invalid credentials"}), HTTPStatus.UNAUTHORIZED
        if not ctx.get("location"):
            return jsonify({"error": "No storage location provided"}), HTTPStatus.BAD_REQUEST
        pomodoro = get_request_data()
        storage_api.save_pomodoro(ctx, pomodoro)
        return jsonify({"status": "ok", "id": pomodoro.get("id")})
    except HttpError as e:
        return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR
    except Exception as e:
        import traceback

        app.logger.error(f"Error in proxy_create_pomodoro: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


@app.route("/api/sheets/pomodoros/batch", methods=["POST"])
def proxy_create_pomodoros_batch():
    """Batch upload pomodoros to Google Sheets - stateless."""
    if not is_logged_in():
        return jsonify({"error": "Not logged in"}), HTTPStatus.UNAUTHORIZED

    try:
        ctx = _storage_context()
        if not ctx.get("service"):
            return jsonify({"error": "Failed to create storage service"}), HTTPStatus.UNAUTHORIZED
        if not ctx.get("location"):
            return jsonify({"error": "No storage location provided"}), HTTPStatus.BAD_REQUEST
        batch_request = get_request_data()
        pomodoros = batch_request.get("pomodoros", [])
        count = storage_api.save_pomodoros_batch(ctx, pomodoros)
        return jsonify({"status": "ok", "count": count})
    except HttpError as e:
        return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR
    except Exception as e:
        import traceback

        app.logger.error(f"Error in proxy_create_pomodoros_batch: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


@app.route("/api/sheets/pomodoros/<pomodoro_id>", methods=["PUT"])
def proxy_update_pomodoro(pomodoro_id):
    """Proxy update to Google Sheets - stateless, credentials from request."""
    if not is_logged_in():
        return jsonify({"error": "Not logged in"}), HTTPStatus.UNAUTHORIZED

    try:
        ctx = _storage_context()
        update_fields = get_request_data()
        success = storage_api.update_pomodoro(ctx, pomodoro_id, update_fields)
        if success:
            return jsonify({"status": "ok"})
        return jsonify({"error": "Pomodoro not found"}), HTTPStatus.NOT_FOUND
    except HttpError as e:
        return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


@app.route("/api/sheets/pomodoros/<pomodoro_id>", methods=["DELETE"])
def proxy_delete_pomodoro(pomodoro_id):
    """Proxy delete to storage backend - stateless, credentials from request."""
    if not is_logged_in():
        return jsonify({"error": "Not logged in"}), HTTPStatus.UNAUTHORIZED

    try:
        ctx = _storage_context()
        success = storage_api.delete_pomodoro(ctx, pomodoro_id)
        if success:
            return jsonify({"status": "ok"})
        return jsonify({"error": "Pomodoro not found"}), HTTPStatus.NOT_FOUND
    except HttpError as e:
        return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


@app.route("/api/sheets/settings", methods=["GET"])
def proxy_get_settings():
    """Proxy settings read from Google Sheets - stateless."""
    if not is_logged_in():
        return jsonify({"error": "Not logged in"}), HTTPStatus.UNAUTHORIZED

    try:
        ctx = _storage_context()
        settings = storage_api.get_settings(ctx, DEFAULT_SETTINGS)
        return jsonify(settings)
    except HttpError as e:
        return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


@app.route("/api/sheets/settings", methods=["POST"])
def proxy_save_settings():
    """Proxy settings write to storage backend - stateless."""
    if not is_logged_in():
        return jsonify({"error": "Not logged in"}), HTTPStatus.UNAUTHORIZED

    try:
        ctx = _storage_context()
        settings_payload = get_request_data()
        # Check for replace_all flag (used by "Overwrite Google" button)
        replace_all = settings_payload.pop("_replace_all", False) if isinstance(settings_payload, dict) else False
        storage_api.save_settings(ctx, settings_payload, replace_all=replace_all)
        return jsonify({"status": "ok"})
    except HttpError as e:
        return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


@app.route("/api/sheets/deduplicate", methods=["POST"])
def proxy_deduplicate_pomodoros():
    """Remove duplicate pomodoros from Google Sheets - stateless."""
    if not is_logged_in():
        return jsonify({"error": "Not logged in"}), HTTPStatus.UNAUTHORIZED

    try:
        ctx = _storage_context()
        dedup_result = storage_api.deduplicate_pomodoros(ctx)
        return jsonify(dedup_result)
    except HttpError as e:
        return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


@app.route("/api/sheets/export")
def proxy_export_csv():
    """Export pomodoros as CSV from Google Sheets - stateless."""
    if not is_logged_in():
        return jsonify({"error": "Not logged in"}), HTTPStatus.UNAUTHORIZED

    try:
        ctx = _storage_context()
        pomodoros = storage_api.get_pomodoros(ctx)

        lines = ["id,name,type,start_time,end_time,duration_minutes,notes"]
        for p in pomodoros:
            name = (p["name"] or "").replace('"', '""')
            notes = (p.get("notes") or "").replace('"', '""')
            lines.append(
                f'"{p["id"]}","{name}","{p["type"]}","{p["start_time"]}",'
                f'"{p["end_time"]}",{p["duration_minutes"]},"{notes}"'
            )

        return Response(
            "\n".join(lines),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=pomodoros.csv"},
        )
    except HttpError as e:
        return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


@app.route("/api/sheets/clear", methods=["POST"])
def proxy_clear_sheets():
    """Clear all pomodoro data from Google Sheets (keeps headers) - stateless."""
    if not is_logged_in():
        return jsonify({"error": "Not logged in"}), HTTPStatus.UNAUTHORIZED

    try:
        ctx = _storage_context()
        if not ctx:
            return jsonify({"error": "No storage backend active"}), HTTPStatus.BAD_REQUEST
        clear_response = storage_api.clear_pomodoros(ctx)
        if clear_response.get("error"):
            return jsonify({"error": clear_response["error"]}), HTTPStatus.NOT_FOUND
        return jsonify(clear_response)
    except HttpError as e:
        return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR
    except Exception as e:
        app.logger.error(f"Error in proxy_clear_sheets: {e}")
        return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


@app.route("/api/todos/sync", methods=["GET"])
def api_get_todos():
    """Download todos from Google Drive — stateless."""
    if not is_logged_in():
        return jsonify({"error": "Not logged in"}), HTTPStatus.UNAUTHORIZED
    try:
        credentials = get_credentials()
        if not credentials:
            return jsonify({"error": "No credentials"}), HTTPStatus.UNAUTHORIZED
        request_creds = get_credentials_from_request()
        folder_id = request_creds.get("folder_id") if request_creds else None
        if not folder_id:
            return jsonify({"todos": [], "lists": []})
        drive_service = build("drive", "v3", credentials=credentials)
        todos_snapshot = todos_plugin.read_todos(drive_service, folder_id)
        return jsonify(todos_snapshot)
    except HttpError as e:
        return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


@app.route("/api/todos/sync", methods=["POST"])
def api_save_todos():
    """Upload todos to Google Drive (full replace) — stateless."""
    if not is_logged_in():
        return jsonify({"error": "Not logged in"}), HTTPStatus.UNAUTHORIZED
    try:
        credentials = get_credentials()
        if not credentials:
            return jsonify({"error": "No credentials"}), HTTPStatus.UNAUTHORIZED
        payload = get_request_data()
        request_creds = get_credentials_from_request()
        folder_id = request_creds.get("folder_id") if request_creds else None
        if not folder_id:
            return jsonify({"error": "No folder_id configured"}), HTTPStatus.BAD_REQUEST
        drive_service = build("drive", "v3", credentials=credentials)
        todos_payload = {"todos": payload.get("todos", []), "lists": payload.get("lists", [])}
        todos_plugin.write_todos(drive_service, folder_id, todos_payload)
        return jsonify({"status": "ok"})
    except HttpError as e:
        return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


# =============================================================================
# MCP Access — enable/disable the hosted MCP endpoint and mint per-user tokens.
#
# The token seals the user's refresh_token + folder_id (see mcp_tokens). The
# revocation state (enabled flag + epoch) lives in the user's own Drive, not on
# the server — the server stays stateless. Regenerate/disable advance the epoch
# to invalidate previously issued tokens.
# =============================================================================


def _public_base_url():
    """Best-effort public base URL from proxy headers (for the MCP endpoint)."""
    oauth_base = os.environ.get("OAUTH_REDIRECT_BASE")
    if oauth_base:
        return oauth_base.rstrip("/")
    proto = request.headers.get("X-Forwarded-Proto", request.scheme).split(",")[0].strip()
    host = request.headers.get("X-Forwarded-Host", request.host).split(",")[0].strip()
    return f"{proto}://{host}"


def _mcp_endpoint():
    return f"{_public_base_url()}/mcp"


def _mcp_drive_context():
    """Return (drive_service, folder_id, email) for the logged-in user.

    drive_service is None when credentials or the Drive folder aren't available
    (MCP access requires the JSON-on-Drive backend).
    """
    request_creds = get_credentials_from_request()
    if not request_creds:
        return None, None, None
    email = request_creds.get("user_email")
    folder_id = request_creds.get("folder_id")
    credentials = get_credentials()
    if not credentials or not folder_id:
        return None, folder_id, email
    return build("drive", "v3", credentials=credentials), folder_id, email


@app.route("/api/mcp/status", methods=["GET"])
def api_mcp_status():
    """Report whether MCP access is enabled for the requesting user."""
    drive_service, folder_id, email = _mcp_drive_context()
    if not email:
        return jsonify({"error": "Not logged in"}), HTTPStatus.UNAUTHORIZED
    enabled = bool(drive_service) and json_google_drive_storage.get_mcp_state(drive_service, folder_id)["enabled"]
    return jsonify({"enabled": enabled, "endpoint": _mcp_endpoint()})


def _mint_mcp_token():
    """Shared enable/regenerate logic. Returns (response, status)."""
    request_creds = get_credentials_from_request()
    if not request_creds:
        return jsonify({"error": "Not logged in"}), HTTPStatus.UNAUTHORIZED
    email = request_creds.get("user_email")
    refresh_token = request_creds.get("refresh_token")
    folder_id = request_creds.get("folder_id")
    if not email:
        return jsonify({"error": "No user email in credentials"}), HTTPStatus.BAD_REQUEST
    if not refresh_token:
        return jsonify(
            {"error": "No Google refresh token available — sign out and sign in again to grant offline access"}
        ), HTTPStatus.BAD_REQUEST
    if not folder_id:
        return jsonify(
            {"error": "MCP access requires the JSON-on-Google-Drive backend (no folder_id configured)"}
        ), HTTPStatus.BAD_REQUEST

    import time

    credentials = get_credentials()
    if not credentials:
        return jsonify({"error": "Not logged in"}), HTTPStatus.UNAUTHORIZED
    drive_service = build("drive", "v3", credentials=credentials)
    epoch = int(time.time())
    json_google_drive_storage.set_mcp_state(drive_service, folder_id, enabled=True, epoch=epoch)
    try:
        token = mcp_tokens.seal(email, refresh_token, folder_id, issued_at=epoch)
    except mcp_tokens.TokenError as e:
        return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR
    return jsonify({"status": "ok", "enabled": True, "token": token, "endpoint": _mcp_endpoint()})


@app.route("/api/mcp/enable", methods=["POST"])
def api_mcp_enable():
    """Enable MCP access and mint a bearer token (shown once)."""
    return _mint_mcp_token()


@app.route("/api/mcp/regenerate", methods=["POST"])
def api_mcp_regenerate():
    """Rotate the token: advance the epoch (invalidating old tokens) and mint a new one."""
    return _mint_mcp_token()


@app.route("/api/mcp/disable", methods=["POST"])
def api_mcp_disable():
    """Disable MCP access. Existing tokens stop working immediately."""
    drive_service, folder_id, email = _mcp_drive_context()
    if not email:
        return jsonify({"error": "Not logged in"}), HTTPStatus.UNAUTHORIZED
    if drive_service:
        state = json_google_drive_storage.get_mcp_state(drive_service, folder_id)
        json_google_drive_storage.set_mcp_state(drive_service, folder_id, enabled=False, epoch=state["epoch"])
    return jsonify({"status": "ok", "enabled": False})


if __name__ == "__main__":
    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    app.run(host=host, port=DEFAULT_PORT)
