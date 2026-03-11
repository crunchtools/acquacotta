#!/usr/bin/env python3
"""Acquacotta - Pomodoro Time Tracking Application

Sovereign Sandbox v2: Stateless Server + IndexedDB

The server is stateless - it only handles:
1. OAuth authentication with Google
2. Proxying API calls to Google Sheets

All user data lives in the browser's IndexedDB and optionally in their Google Sheets.
The server never stores any user pomodoro data.

Credit: kirkjerk (localStorage approach idea, extended to IndexedDB)
"""

import json
import os
from http import HTTPStatus
from pathlib import Path

# Allow OAuth scope changes (users may have previously granted different scopes)
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

from flask import Flask, Response, jsonify, redirect, render_template, request, session
from flask_session import Session
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from werkzeug.middleware.proxy_fix import ProxyFix

import sheets_storage

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

# Session configuration
secret_key = os.environ.get("FLASK_SECRET_KEY")
if not secret_key:
    if os.environ.get("FLASK_ENV") == "development":
        secret_key = "dev-secret-key-for-local-development-only"
    else:
        raise ValueError("FLASK_SECRET_KEY environment variable must be set in production")
app.config["SECRET_KEY"] = secret_key
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = "/tmp/flask_session"
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
Session(app)


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
    "working_hours_start": "08:00",
    "working_hours_end": "17:00",
    "clock_format": "auto",
    "period_labels": "auto",
    "daily_minutes_goal": DEFAULT_DAILY_GOAL,
}

# Flask default port
DEFAULT_PORT = 5000


def get_user_spreadsheet_mapping_path():
    """Get path to the user-to-spreadsheet mapping file."""
    return DATA_DIR / "user_spreadsheets.json"


def get_stored_spreadsheet_id(email):
    """Get stored spreadsheet_id for a user email."""
    mapping_path = get_user_spreadsheet_mapping_path()
    if mapping_path.exists():
        with open(mapping_path) as f:
            mapping = json.load(f)
            return mapping.get(email)
    return None


def save_spreadsheet_id(email, spreadsheet_id):
    """Save spreadsheet_id for a user email."""
    mapping_path = get_user_spreadsheet_mapping_path()
    mapping = {}
    if mapping_path.exists():
        with open(mapping_path) as f:
            mapping = json.load(f)
    mapping[email] = spreadsheet_id
    with open(mapping_path, "w") as f:
        json.dump(mapping, f)


def get_google_flow():
    """Create Google OAuth flow."""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return None
    # Allow override via env var for development (e.g., OAUTH_REDIRECT_BASE=http://localhost:5000)
    oauth_base = os.environ.get("OAUTH_REDIRECT_BASE")
    if oauth_base:
        redirect_uri = f"{oauth_base.rstrip('/')}/auth/callback"
    else:
        # Build redirect URI from X-Forwarded headers or fall back to request host
        # Take first value if multiple proxies added headers (comma-separated)
        proto = request.headers.get("X-Forwarded-Proto", request.scheme).split(",")[0].strip()
        host = request.headers.get("X-Forwarded-Host", request.host).split(",")[0].strip()
        redirect_uri = f"{proto}://{host}/auth/callback"

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

        # Refresh token if expired
        if credentials.expired and credentials.refresh_token:
            from google.auth.transport.requests import Request

            credentials.refresh(Request())

        return credentials
    except Exception as e:
        app.logger.error(f"Error creating credentials: {e}")
        return None


def get_sheets_service():
    """Get Google Sheets API service."""
    credentials = get_credentials()
    if not credentials:
        return None
    return build("sheets", "v4", credentials=credentials)


def get_drive_service():
    """Get Google Drive API service."""
    credentials = get_credentials()
    if not credentials:
        return None
    return build("drive", "v3", credentials=credentials)


def is_logged_in():
    """Check if request has valid credentials (stateless)."""
    creds = get_credentials_from_request()
    return creds is not None and creds.get("token") and creds.get("spreadsheet_id")


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
            prompt="consent",
        )
        session["oauth_state"] = state
        # Store user-provided spreadsheet ID to use after callback
        requested_spreadsheet_id = request.args.get("spreadsheet_id", "").strip()
        if requested_spreadsheet_id:
            session["requested_spreadsheet_id"] = requested_spreadsheet_id
        return redirect(authorization_url)
    except Exception as e:
        import traceback

        return f"<pre>Error: {e}\n\n{traceback.format_exc()}</pre>", HTTPStatus.INTERNAL_SERVER_ERROR


@app.route("/auth/callback")
def auth_callback():
    """Handle Google OAuth callback."""
    try:
        # Validate OAuth state to prevent CSRF attacks
        callback_state = request.args.get("state")
        stored_state = session.pop("oauth_state", None)  # Pop to ensure one-time use
        if not callback_state or callback_state != stored_state:
            app.logger.warning("OAuth state mismatch - possible CSRF attack")
            return jsonify({"error": "Invalid OAuth state"}), HTTPStatus.BAD_REQUEST

        flow = get_google_flow()
        if not flow:
            return jsonify({"error": "Google OAuth not configured"}), HTTPStatus.INTERNAL_SERVER_ERROR

        flow.fetch_token(authorization_response=request.url)
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
            session["oauth_state"] = state  # Use consistent key name
            return redirect(authorization_url)

        # Get user info
        oauth2_service = build("oauth2", "v2", credentials=credentials)
        user_info = oauth2_service.userinfo().get().execute()
        user_email = user_info.get("email")
        session["user_email"] = user_email
        session["user_name"] = user_info.get("name")
        session["user_picture"] = user_info.get("picture")

        # Priority: 1) User-provided spreadsheet ID, 2) Previously stored ID, 3) Create new
        requested_spreadsheet_id = session.pop("requested_spreadsheet_id", None)
        stored_spreadsheet_id = get_stored_spreadsheet_id(user_email)

        spreadsheet_id_to_use = requested_spreadsheet_id or stored_spreadsheet_id

        if spreadsheet_id_to_use:
            # Verify we can access this spreadsheet
            # Note: Use credentials directly here since we're in OAuth callback, not using request-based auth
            try:
                sheets_service = build("sheets", "v4", credentials=credentials)
                sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id_to_use).execute()
                session["spreadsheet_id"] = spreadsheet_id_to_use
                session["spreadsheet_existed"] = True
                # Save/update the mapping for future logins
                save_spreadsheet_id(user_email, spreadsheet_id_to_use)
            except HttpError:
                # Can't access spreadsheet (deleted, permissions changed, wrong ID)
                spreadsheet_id_to_use = None

        if not spreadsheet_id_to_use:
            # Create new spreadsheet using Drive API (required for drive.file scope)
            # Note: Use credentials directly here since we're in OAuth callback, not using request-based auth
            drive_service = build("drive", "v3", credentials=credentials)
            file_metadata = {
                "name": "Acquacotta - Pomodoro Tracker",
                "mimeType": "application/vnd.google-apps.spreadsheet",
            }
            spreadsheet = (
                drive_service.files()
                .create(
                    body=file_metadata,
                    fields="id",
                )
                .execute()
            )
            new_spreadsheet_id = spreadsheet["id"]
            spreadsheet_existed = False

            # Save the mapping for future logins
            save_spreadsheet_id(user_email, new_spreadsheet_id)

            # Now use Sheets API to set up the sheets (we have access since we created the file)
            sheets_service = build("sheets", "v4", credentials=credentials)

            # Rename default Sheet1 to Pomodoros and add Settings sheet
            sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=new_spreadsheet_id,
                body={
                    "requests": [
                        {
                            "updateSheetProperties": {
                                "properties": {"sheetId": 0, "title": "Pomodoros"},
                                "fields": "title",
                            }
                        },
                        {"addSheet": {"properties": {"title": "Settings"}}},
                    ]
                },
            ).execute()

            # Add headers to Pomodoros sheet
            sheets_service.spreadsheets().values().update(
                spreadsheetId=new_spreadsheet_id,
                range="Pomodoros!A1:G1",
                valueInputOption="RAW",
                body={"values": [["id", "name", "type", "start_time", "end_time", "duration_minutes", "notes"]]},
            ).execute()

            # Add headers to Settings sheet
            sheets_service.spreadsheets().values().update(
                spreadsheetId=new_spreadsheet_id,
                range="Settings!A1:B1",
                valueInputOption="RAW",
                body={"values": [["key", "value"]]},
            ).execute()
        else:
            new_spreadsheet_id = spreadsheet_id_to_use
            spreadsheet_existed = True

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
        settings_data = {
            "spreadsheet_id": new_spreadsheet_id,
            "spreadsheet_existed": spreadsheet_existed,
        }

        # Clear server session - credentials will live in browser IndexedDB
        session.clear()

        # Return HTML page that stores credentials in IndexedDB then redirects
        # Note: DB_VERSION must match storage.js (currently 2)
        return f"""<!DOCTYPE html>
<html>
<head><title>Logging in...</title></head>
<body>
<p>Completing login...</p>
<script>
const credentials = {json.dumps(credentials_data)};
const settings = {json.dumps(settings_data)};
const DB_VERSION = 2;  // Must match storage.js

// Store in IndexedDB
const dbRequest = indexedDB.open('acquacotta', DB_VERSION);
dbRequest.onupgradeneeded = (e) => {{
    const db = e.target.result;
    // Create all stores that storage.js expects
    if (!db.objectStoreNames.contains('pomodoros')) {{
        const pomodorosStore = db.createObjectStore('pomodoros', {{ keyPath: 'id' }});
        pomodorosStore.createIndex('start_time', 'start_time', {{ unique: false }});
        pomodorosStore.createIndex('type', 'type', {{ unique: false }});
        pomodorosStore.createIndex('synced', 'synced', {{ unique: false }});
    }}
    if (!db.objectStoreNames.contains('settings')) {{
        db.createObjectStore('settings', {{ keyPath: 'key' }});
    }}
    if (!db.objectStoreNames.contains('sync_queue')) {{
        const syncStore = db.createObjectStore('sync_queue', {{ keyPath: 'id', autoIncrement: true }});
        syncStore.createIndex('created_at', 'created_at', {{ unique: false }});
    }}
    if (!db.objectStoreNames.contains('sync_status')) {{
        db.createObjectStore('sync_status', {{ keyPath: 'key' }});
    }}
    if (!db.objectStoreNames.contains('auth')) {{
        db.createObjectStore('auth', {{ keyPath: 'key' }});
    }}
}};
dbRequest.onsuccess = (e) => {{
    const db = e.target.result;
    // Store auth credentials (ephemeral)
    const authTx = db.transaction('auth', 'readwrite');
    authTx.objectStore('auth').put({{ key: 'credentials', ...credentials }});
    authTx.oncomplete = () => {{
        // Store settings (persistent) - spreadsheet_id lives here
        const settingsTx = db.transaction('settings', 'readwrite');
        const settingsStore = settingsTx.objectStore('settings');
        settingsStore.put({{ key: 'spreadsheet_id', value: settings.spreadsheet_id, synced: true }});
        settingsStore.put({{ key: 'spreadsheet_existed', value: settings.spreadsheet_existed, synced: true }});
        settingsTx.oncomplete = () => {{
            window.location.href = '/?view=settings';
        }};
        settingsTx.onerror = (err) => {{
            console.error('Settings transaction error:', err);
            window.location.href = '/?view=settings';
        }};
    }};
    authTx.onerror = (err) => {{
        console.error('Auth transaction error:', err);
        window.location.href = '/?view=settings';
    }};
}};
dbRequest.onerror = (e) => {{
    console.error('Failed to open IndexedDB:', e.target.error);
    window.location.href = '/?view=settings';
}};
</script>
</body>
</html>"""
    except Exception as e:
        import traceback

        return f"<pre>Error: {e}\n\n{traceback.format_exc()}</pre>", HTTPStatus.INTERNAL_SERVER_ERROR


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
        sheets_service = get_sheets_service()
        sheets_service.spreadsheets().get(spreadsheetId=new_id).execute()
    except HttpError:
        return jsonify({"error": "Cannot access spreadsheet. Make sure you have edit access."}), HTTPStatus.BAD_REQUEST

    # Update session and persisted mapping
    session["spreadsheet_id"] = new_id
    if session.get("user_email"):
        save_spreadsheet_id(session["user_email"], new_id)

    return jsonify({"status": "ok", "spreadsheet_id": new_id})


# =============================================================================
# Google Sheets Proxy Endpoints
# The server proxies all data operations to Google Sheets.
# No user data is stored on the server.
# =============================================================================


@app.route("/api/sheets/pomodoros", methods=["GET"])
def proxy_get_pomodoros():
    """Proxy read from Google Sheets - stateless, credentials from request."""
    if not is_logged_in():
        return jsonify({"error": "Not logged in"}), HTTPStatus.UNAUTHORIZED

    try:
        service = get_sheets_service()
        spreadsheet_id = get_spreadsheet_id_from_request()
        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")
        pomodoros = sheets_storage.get_pomodoros(service, spreadsheet_id, start_date, end_date)
        return jsonify(pomodoros)
    except HttpError as e:
        return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


@app.route("/api/sheets/pomodoros/count")
def proxy_get_pomodoro_count():
    """Get count of pomodoros in Google Sheets - efficient, only fetches IDs."""
    if not is_logged_in():
        return jsonify({"error": "Not logged in"}), HTTPStatus.UNAUTHORIZED

    try:
        service = get_sheets_service()
        spreadsheet_id = get_spreadsheet_id_from_request()
        # Only fetch the ID column to count rows efficiently
        sheets_response = (
            service.spreadsheets()
            .values()
            .get(
                spreadsheetId=spreadsheet_id,
                range="Pomodoros!A:A",
            )
            .execute()
        )
        rows = sheets_response.get("values", [])
        # Subtract 1 for header row, ensure non-negative
        count = max(0, len(rows) - 1)
        return jsonify({"count": count})
    except HttpError as e:
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
        service = get_sheets_service()
        if not service:
            return jsonify({"error": "Failed to create Sheets service - invalid credentials"}), HTTPStatus.UNAUTHORIZED
        spreadsheet_id = get_spreadsheet_id_from_request()
        if not spreadsheet_id:
            return jsonify({"error": "No spreadsheet ID provided"}), HTTPStatus.BAD_REQUEST
        pomodoro = get_request_data()
        sheets_storage.save_pomodoro(service, spreadsheet_id, pomodoro)
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
        service = get_sheets_service()
        if not service:
            return jsonify({"error": "Failed to create Sheets service"}), HTTPStatus.UNAUTHORIZED
        spreadsheet_id = get_spreadsheet_id_from_request()
        if not spreadsheet_id:
            return jsonify({"error": "No spreadsheet ID provided"}), HTTPStatus.BAD_REQUEST
        batch_request = get_request_data()
        pomodoros = batch_request.get("pomodoros", [])
        count = sheets_storage.save_pomodoros_batch(service, spreadsheet_id, pomodoros)
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
        service = get_sheets_service()
        spreadsheet_id = get_spreadsheet_id_from_request()
        update_fields = get_request_data()
        success = sheets_storage.update_pomodoro(service, spreadsheet_id, pomodoro_id, update_fields)
        if success:
            return jsonify({"status": "ok"})
        return jsonify({"error": "Pomodoro not found"}), HTTPStatus.NOT_FOUND
    except HttpError as e:
        return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


@app.route("/api/sheets/pomodoros/<pomodoro_id>", methods=["DELETE"])
def proxy_delete_pomodoro(pomodoro_id):
    """Proxy delete to Google Sheets - stateless, credentials from request."""
    if not is_logged_in():
        return jsonify({"error": "Not logged in"}), HTTPStatus.UNAUTHORIZED

    try:
        service = get_sheets_service()
        spreadsheet_id = get_spreadsheet_id_from_request()
        success = sheets_storage.delete_pomodoro(service, spreadsheet_id, pomodoro_id)
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
        service = get_sheets_service()
        spreadsheet_id = get_spreadsheet_id_from_request()
        settings = sheets_storage.get_settings(service, spreadsheet_id, DEFAULT_SETTINGS)
        return jsonify(settings)
    except HttpError as e:
        return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


@app.route("/api/sheets/settings", methods=["POST"])
def proxy_save_settings():
    """Proxy settings write to Google Sheets - stateless."""
    if not is_logged_in():
        return jsonify({"error": "Not logged in"}), HTTPStatus.UNAUTHORIZED

    try:
        service = get_sheets_service()
        spreadsheet_id = get_spreadsheet_id_from_request()
        settings_payload = get_request_data()
        # Check for replace_all flag (used by "Overwrite Google" button)
        replace_all = settings_payload.pop("_replace_all", False) if isinstance(settings_payload, dict) else False
        sheets_storage.save_settings(service, spreadsheet_id, settings_payload, replace_all=replace_all)
        return jsonify({"status": "ok"})
    except HttpError as e:
        return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


@app.route("/api/sheets/deduplicate", methods=["POST"])
def proxy_deduplicate_pomodoros():
    """Remove duplicate pomodoros from Google Sheets - stateless."""
    if not is_logged_in():
        return jsonify({"error": "Not logged in"}), HTTPStatus.UNAUTHORIZED

    try:
        service = get_sheets_service()
        spreadsheet_id = get_spreadsheet_id_from_request()
        dedup_result = sheets_storage.deduplicate_pomodoros(service, spreadsheet_id)
        return jsonify(dedup_result)
    except HttpError as e:
        return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


@app.route("/api/sheets/export")
def proxy_export_csv():
    """Export pomodoros as CSV from Google Sheets - stateless."""
    if not is_logged_in():
        return jsonify({"error": "Not logged in"}), HTTPStatus.UNAUTHORIZED

    try:
        service = get_sheets_service()
        spreadsheet_id = get_spreadsheet_id_from_request()
        pomodoros = sheets_storage.get_pomodoros(service, spreadsheet_id)

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
        service = get_sheets_service()
        spreadsheet_id = get_spreadsheet_id_from_request()

        # Get the sheet ID for Pomodoros sheet
        spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        pomodoros_sheet_id = None
        for sheet in spreadsheet["sheets"]:
            if sheet["properties"]["title"] == "Pomodoros":
                pomodoros_sheet_id = sheet["properties"]["sheetId"]
                break

        if pomodoros_sheet_id is None:
            return jsonify({"error": "Pomodoros sheet not found"}), HTTPStatus.NOT_FOUND

        # Get current row count
        values = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range="Pomodoros!A:A").execute()
        row_count = len(values.get("values", []))

        if row_count <= 1:
            # Only header or empty, nothing to clear
            return jsonify({"status": "ok", "cleared": 0})

        # Delete all data rows (keep header at row 1)
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "deleteDimension": {
                            "range": {
                                "sheetId": pomodoros_sheet_id,
                                "dimension": "ROWS",
                                "startIndex": 1,  # After header
                                "endIndex": row_count,
                            }
                        }
                    }
                ]
            },
        ).execute()

        return jsonify({"status": "ok", "cleared": row_count - 1})
    except HttpError as e:
        return jsonify({"error": str(e)}), HTTPStatus.INTERNAL_SERVER_ERROR


if __name__ == "__main__":
    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    app.run(host=host, port=DEFAULT_PORT)
