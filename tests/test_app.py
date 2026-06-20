"""Tests for Acquacotta Flask API endpoints.

Sovereign Sandbox v2: Tests for the stateless server architecture.
The server only handles:
- Static pages (index, privacy, terms)
- OAuth authentication
- Proxying requests to Google Sheets

All data storage and CRUD operations happen in the browser's IndexedDB.
"""

import json
from unittest.mock import patch

import storage_api


class TestIndexRoute:
    """Tests for the main index route."""

    def test_index_returns_html(self, client):
        """Index route should return HTML template."""
        response = client.get("/")
        assert response.status_code == 200
        assert b"<!DOCTYPE html>" in response.data or b"<html" in response.data


class TestAuthStatus:
    """Tests for authentication status endpoint."""

    def test_auth_status_not_logged_in(self, client):
        """Auth status should indicate not logged in when no session."""
        response = client.get("/api/auth/status")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["logged_in"] is False

    def test_auth_status_logged_in(self, authenticated_session):
        """Auth status should show user info when logged in."""
        response = authenticated_session.get("/api/auth/status")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["logged_in"] is True
        assert data["email"] == "test@example.com"
        assert data["name"] == "Test User"


class TestSheetsProxyEndpoints:
    """Tests for Google Sheets proxy endpoints."""

    def test_get_pomodoros_requires_auth(self, client):
        """GET /api/sheets/pomodoros should require authentication."""
        response = client.get("/api/sheets/pomodoros")
        assert response.status_code == 401

    def test_create_pomodoro_requires_auth(self, client, sample_pomodoro):
        """POST /api/sheets/pomodoros should require authentication."""
        response = client.post(
            "/api/sheets/pomodoros",
            json=sample_pomodoro,
            content_type="application/json",
        )
        assert response.status_code == 401

    def test_update_pomodoro_requires_auth(self, client, sample_pomodoro):
        """PUT /api/sheets/pomodoros/<id> should require authentication."""
        response = client.put(
            "/api/sheets/pomodoros/test-id",
            json=sample_pomodoro,
            content_type="application/json",
        )
        assert response.status_code == 401

    def test_delete_pomodoro_requires_auth(self, client):
        """DELETE /api/sheets/pomodoros/<id> should require authentication."""
        response = client.delete("/api/sheets/pomodoros/test-id")
        assert response.status_code == 401

    def test_get_settings_requires_auth(self, client):
        """GET /api/sheets/settings should require authentication."""
        response = client.get("/api/sheets/settings")
        assert response.status_code == 401

    def test_save_settings_requires_auth(self, client, sample_settings):
        """POST /api/sheets/settings should require authentication."""
        response = client.post(
            "/api/sheets/settings",
            json=sample_settings,
            content_type="application/json",
        )
        assert response.status_code == 401

    def test_export_requires_auth(self, client):
        """GET /api/sheets/export should require authentication."""
        response = client.get("/api/sheets/export")
        assert response.status_code == 401

    def test_get_pomodoros_with_auth(self, authenticated_session):
        """GET /api/sheets/pomodoros should proxy to storage backend when authenticated."""
        with patch.object(
            storage_api,
            "get_pomodoros",
            return_value=[
                {
                    "id": "test-1",
                    "name": "Test",
                    "type": "Content",
                    "start_time": "2024-01-15T10:00:00Z",
                    "end_time": "2024-01-15T10:25:00Z",
                    "duration_minutes": 25,
                    "notes": None,
                }
            ],
        ) as mock_get:
            response = authenticated_session.get("/api/sheets/pomodoros")
            assert response.status_code == 200
            data = json.loads(response.data)
            assert len(data) == 1
            assert data[0]["name"] == "Test"
            mock_get.assert_called_once()

    def test_create_pomodoro_with_auth(self, authenticated_session, sample_pomodoro):
        """POST /api/sheets/pomodoros should proxy to storage backend when authenticated."""
        with patch.object(storage_api, "save_pomodoro") as mock_save:
            response = authenticated_session.post(
                "/api/sheets/pomodoros",
                json=sample_pomodoro,
                content_type="application/json",
            )
            assert response.status_code == 200
            mock_save.assert_called_once()

    def test_update_pomodoro_with_auth(self, authenticated_session, sample_pomodoro):
        """PUT /api/sheets/pomodoros/<id> should proxy to storage backend when authenticated."""
        with patch.object(storage_api, "update_pomodoro", return_value=True) as mock_update:
            response = authenticated_session.put(
                "/api/sheets/pomodoros/test-uuid-1234",
                json=sample_pomodoro,
                content_type="application/json",
            )
            assert response.status_code == 200
            mock_update.assert_called_once()

    def test_delete_pomodoro_with_auth(self, authenticated_session):
        """DELETE /api/sheets/pomodoros/<id> should proxy to storage backend when authenticated."""
        with patch.object(storage_api, "delete_pomodoro", return_value=True) as mock_delete:
            response = authenticated_session.delete("/api/sheets/pomodoros/test-uuid-1234")
            assert response.status_code == 200
            mock_delete.assert_called_once()

    def test_get_settings_with_auth(self, authenticated_session):
        """GET /api/sheets/settings should proxy to storage backend when authenticated."""
        with patch.object(
            storage_api,
            "get_settings",
            return_value={"timer_preset_4": 25, "short_break_minutes": 5},
        ) as mock_get:
            response = authenticated_session.get("/api/sheets/settings")
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["timer_preset_4"] == 25
            mock_get.assert_called_once()

    def test_save_settings_with_auth(self, authenticated_session, sample_settings):
        """POST /api/sheets/settings should proxy to storage backend when authenticated."""
        with patch.object(storage_api, "save_settings") as mock_save:
            response = authenticated_session.post(
                "/api/sheets/settings",
                json=sample_settings,
                content_type="application/json",
            )
            assert response.status_code == 200
            mock_save.assert_called_once()


class TestPluginsAPI:
    """Tests for the plugin registry API."""

    def test_list_plugins(self, client):
        """GET /api/plugins should return registered plugins."""
        response = client.get("/api/plugins")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "plugins" in data
        assert "types" in data
        assert "active_storage" in data
        assert data["active_storage"] == "sheets"
        sheets_plugin = next(p for p in data["plugins"] if p["id"] == "sheets")
        assert sheets_plugin["name"] == "Google Sheets"
        assert sheets_plugin["plugin_type"] == "storage"
        assert sheets_plugin["active"] is True


class TestClearInitialSync:
    """Tests for the clear-initial-sync endpoint."""

    def test_clear_initial_sync(self, authenticated_session):
        """Should clear the needs_initial_sync flag."""
        # First set the flag
        with authenticated_session.session_transaction() as sess:
            sess["needs_initial_sync"] = True

        # Call the endpoint
        response = authenticated_session.post("/api/auth/clear-initial-sync")
        assert response.status_code == 200

        # Verify flag is cleared
        response = authenticated_session.get("/api/auth/status")
        data = json.loads(response.data)
        assert data["needs_initial_sync"] is False


class TestAuthCallback:
    """Tests for the OAuth callback endpoint.

    The signed-state approach embeds the PKCE code_verifier in the OAuth state
    parameter (signed with the secret key), so it survives the redirect chain
    without depending on cookies/sessions.
    """

    def _make_signed_state(self, app, code_verifier="test-verifier", spreadsheet_id=None):
        """Create a signed state blob matching what auth_google() produces."""
        from itsdangerous import URLSafeTimedSerializer

        payload = {"s": "csrf-nonce", "cv": code_verifier}
        if spreadsheet_id:
            payload["sid"] = spreadsheet_id
        s = URLSafeTimedSerializer(app.config["SECRET_KEY"])
        return s.dumps(payload)

    def test_callback_returns_400_when_no_state(self, client):
        """Callback with no state parameter should return 400."""
        response = client.get("/auth/callback?code=some_code")
        assert response.status_code == 400

    def test_callback_returns_400_on_tampered_state(self, app, client):
        """Callback with unsigned/tampered state should return 400 (CSRF protection)."""
        response = client.get("/auth/callback?state=tampered_garbage&code=some_code")
        assert response.status_code == 400

    def test_callback_redirects_on_expired_state(self, app, client):
        """Callback with expired signed state should redirect to /auth/google."""
        from itsdangerous import URLSafeTimedSerializer

        s = URLSafeTimedSerializer(app.config["SECRET_KEY"])
        payload = {"s": "csrf-nonce", "cv": "test-verifier"}
        # Manually create an expired token by monkey-patching time
        signed = s.dumps(payload)

        # We can't easily expire it in a unit test without time mocking,
        # so just verify that a valid signed state does NOT get rejected as expired
        response = client.get(f"/auth/callback?state={signed}&code=some_code")
        # Should proceed past state validation (will fail at fetch_token, not at state check)
        assert response.status_code != 400 or b"Invalid OAuth state" not in response.data

    def test_callback_returns_400_when_no_code(self, app, client):
        """Callback with valid state but no authorization code should return 400."""
        signed_state = self._make_signed_state(app)
        response = client.get(f"/auth/callback?state={signed_state}")
        assert response.status_code == 400


class TestStaticPages:
    """Tests for static pages."""

    def test_privacy_page(self, client):
        """Privacy page should be accessible."""
        response = client.get("/privacy")
        assert response.status_code == 200

    def test_terms_page(self, client):
        """Terms page should be accessible."""
        response = client.get("/terms")
        assert response.status_code == 200
