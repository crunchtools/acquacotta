"""Pytest fixtures for Acquacotta tests.

Sovereign Sandbox v2: Tests for stateless server architecture.
The server only handles OAuth and proxies requests to Google Sheets.
All data storage happens in the browser's IndexedDB.
"""

import base64
import json
import os
from unittest.mock import MagicMock, patch

import pytest

# Set environment variables before importing app
os.environ["FLASK_SECRET_KEY"] = "test-secret-key"

import app as app_module


@pytest.fixture
def temp_data_dir(tmp_path):
    """Create a temporary data directory for testing."""
    data_dir = tmp_path / "acquacotta"
    data_dir.mkdir()
    return data_dir


@pytest.fixture
def app(temp_data_dir):
    """Create and configure a test Flask application."""
    # Patch DATA_DIR for the session storage
    with patch.object(app_module, "DATA_DIR", temp_data_dir):
        test_app = app_module.app
        test_app.config.update(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
                "SESSION_TYPE": "filesystem",
                "SESSION_FILE_DIR": str(temp_data_dir / "sessions"),
            }
        )

        yield test_app


@pytest.fixture
def client(app):
    """Create a test client for the Flask application."""
    return app.test_client()


@pytest.fixture
def sample_pomodoro():
    """Return sample pomodoro data for testing."""
    return {
        "id": "test-uuid-1234",
        "name": "Test Task",
        "type": "Content",
        "start_time": "2024-01-15T10:00:00Z",
        "end_time": "2024-01-15T10:25:00Z",
        "duration_minutes": app_module.DEFAULT_POMODORO_DURATION,
        "notes": "Test notes",
    }


@pytest.fixture
def sample_settings():
    """Return sample settings data for testing."""
    return {
        "timer_preset_1": app_module.DEFAULT_SHORT_BREAK,
        "timer_preset_2": app_module.TIMER_PRESET_MEDIUM,
        "timer_preset_3": app_module.DEFAULT_LONG_BREAK,
        "timer_preset_4": app_module.DEFAULT_POMODORO_DURATION,
        "short_break_minutes": app_module.DEFAULT_SHORT_BREAK,
        "long_break_minutes": app_module.DEFAULT_LONG_BREAK,
        "pomodoro_types": ["Content", "Product", "Team"],
    }


@pytest.fixture
def mock_sheets_service():
    """Create a mock Google Sheets service."""
    service = MagicMock()

    # Mock spreadsheets().values().get()
    values_mock = MagicMock()
    spreadsheets_mock = MagicMock()
    spreadsheets_mock.values.return_value = values_mock
    service.spreadsheets.return_value = spreadsheets_mock

    return service


class AuthenticatedTestClient:
    """Wrapper around Flask test client that includes credentials in all requests.

    The stateless architecture expects credentials in X-Credentials header (for GET/DELETE)
    or _credentials in request body (for POST/PUT). This wrapper automatically adds them.
    """

    def __init__(self, client, credentials):
        self._client = client
        self._credentials = credentials
        self._credentials_header = base64.b64encode(json.dumps(credentials).encode()).decode()

    def _add_credentials_header(self, kwargs):
        """Add X-Credentials header to request."""
        headers = kwargs.get("headers", {})
        headers["X-Credentials"] = self._credentials_header
        kwargs["headers"] = headers
        return kwargs

    def get(self, *args, **kwargs):
        return self._client.get(*args, **self._add_credentials_header(kwargs))

    def post(self, *args, **kwargs):
        return self._client.post(*args, **self._add_credentials_header(kwargs))

    def put(self, *args, **kwargs):
        return self._client.put(*args, **self._add_credentials_header(kwargs))

    def delete(self, *args, **kwargs):
        return self._client.delete(*args, **self._add_credentials_header(kwargs))

    def session_transaction(self):
        """Proxy session_transaction for tests that need to manipulate session."""
        return self._client.session_transaction()


@pytest.fixture
def authenticated_session(app):
    """Create a session with mock authentication.

    Returns a wrapped test client that automatically includes credentials
    in request headers, matching the stateless architecture.
    """
    credentials = {
        "token": "fake-token",
        "refresh_token": "fake-refresh-token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "fake-client-id",
        "client_secret": "fake-client-secret",
        "scopes": ["https://www.googleapis.com/auth/drive.file"],
        "spreadsheet_id": "fake-spreadsheet-id",
        "folder_id": "fake-folder-id",
    }

    with app.test_client() as client:
        # Set session variables for endpoints that return session data (e.g., /api/auth/status)
        with client.session_transaction() as sess:
            sess["credentials"] = credentials
            sess["user_email"] = "test@example.com"
            sess["user_name"] = "Test User"
            sess["spreadsheet_id"] = "fake-spreadsheet-id"

        # Wrap client to automatically include credentials in requests
        yield AuthenticatedTestClient(client, credentials)
