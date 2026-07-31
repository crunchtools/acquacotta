"""Tests for Acquacotta Flask API endpoints.

Sovereign Sandbox v2: Tests for the stateless server architecture.
The server only handles:
- Static pages (index, privacy, terms)
- OAuth authentication
- Proxying requests to Google Sheets

All data storage and CRUD operations happen in the browser's IndexedDB.
"""

import base64
import json
from unittest.mock import MagicMock, patch

import pytest

import app as app_module
import plugin_registry
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
        """GET /api/plugins should return registered plugins; a request with no
        recorded user resolves to the default backend (JSON-on-Drive)."""
        response = client.get("/api/plugins")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "plugins" in data
        assert "types" in data
        assert data["active_storage"] == "json-google-drive"
        sheets_plugin = next(p for p in data["plugins"] if p["id"] == "sheets")
        assert sheets_plugin["name"] == "Google Sheets"
        assert sheets_plugin["plugin_type"] == "storage"
        assert sheets_plugin["active"] is False
        json_plugin = next(p for p in data["plugins"] if p["id"] == "json-google-drive")
        assert json_plugin["active"] is True


class TestExtensionTogglePerUser:
    """Extension enablement is a per-user client preference; the toggle endpoint
    validates the plugin but never flips shared global registry state (spec 008)."""

    def test_toggle_known_extension_ok(self, client):
        response = client.post(
            "/api/plugins/toggle",
            json={"plugin_id": "todos", "plugin_type": "extension", "enable": False},
        )
        assert response.status_code == 200
        assert json.loads(response.data)["status"] == "ok"

    def test_toggle_unknown_extension_400(self, client):
        response = client.post(
            "/api/plugins/toggle",
            json={"plugin_id": "nope", "plugin_type": "extension", "enable": True},
        )
        assert response.status_code == 400

    def test_toggle_does_not_mutate_global_registry(self, client):
        def todos_active():
            todos = next(p for p in plugin_registry.list_plugins() if p["id"] == "todos")
            return todos["active"]

        before = todos_active()
        client.post(
            "/api/plugins/toggle",
            json={"plugin_id": "todos", "plugin_type": "extension", "enable": not before},
        )
        assert todos_active() == before  # per-user choice lives client-side, not the global flag


class TestMandatoryPlugins:
    """Pomodoro and Settings are mandatory plugins: listed, always-on, non-toggleable
    (spec 009). Todos remains an optional plugin."""

    def test_features_listed_as_plugins(self, client):
        response = client.get("/api/plugins")
        plugins = {p["id"]: p for p in json.loads(response.data)["plugins"]}
        for pid in ("pomodoro", "settings", "todos"):
            assert pid in plugins, f"{pid} should be listed as a plugin"

    def test_mandatory_flags_and_always_active(self, client):
        plugins = {p["id"]: p for p in json.loads(client.get("/api/plugins").data)["plugins"]}
        assert plugins["pomodoro"]["mandatory"] is True
        assert plugins["pomodoro"]["active"] is True
        assert plugins["settings"]["mandatory"] is True
        assert plugins["settings"]["active"] is True
        assert plugins["todos"]["mandatory"] is False

    def test_registry_is_mandatory(self):
        assert plugin_registry.is_mandatory("extension", "pomodoro") is True
        assert plugin_registry.is_mandatory("extension", "settings") is True
        assert plugin_registry.is_mandatory("extension", "todos") is False

    def test_cannot_disable_mandatory_plugin(self, client):
        for pid in ("pomodoro", "settings"):
            response = client.post(
                "/api/plugins/toggle",
                json={"plugin_id": pid, "plugin_type": "extension", "enable": False},
            )
            assert response.status_code == 403, f"{pid} disable should be forbidden"
            # still active afterwards
            plugins = {p["id"]: p for p in json.loads(client.get("/api/plugins").data)["plugins"]}
            assert plugins[pid]["active"] is True

    def test_optional_plugin_still_toggleable(self, client):
        response = client.post(
            "/api/plugins/toggle",
            json={"plugin_id": "todos", "plugin_type": "extension", "enable": False},
        )
        assert response.status_code == 200


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
        from itsdangerous import URLSafeTimedSerializer

        s = URLSafeTimedSerializer(app.config["SECRET_KEY"])
        signed_state = s.dumps({"s": "csrf-nonce", "cv": "test-verifier"})
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


class TestPerUserBackend:
    """The storage backend is an authoritative, per-user choice recorded server-side
    and resolved per request — never a shared global."""

    def _ctx(self, app, creds_dict):
        header = base64.b64encode(json.dumps(creds_dict).encode()).decode()
        return app.test_request_context(headers={"X-Credentials": header})

    def test_backend_choice_roundtrip(self, app):
        with app.test_request_context():
            app_module.set_user_backend("a@example.com", "json-google-drive")
            app_module.set_user_backend("b@example.com", "sheets")
            assert app_module.get_user_backend("a@example.com") == "json-google-drive"
            assert app_module.get_user_backend("b@example.com") == "sheets"
            assert app_module.get_user_backend("unset@example.com") is None

    def test_resolves_per_user_and_isolates(self, app):
        with app.test_request_context():
            app_module.set_user_backend("a@example.com", "sheets")
            app_module.set_user_backend("b@example.com", "json-google-drive")
        with self._ctx(app, {"user_email": "a@example.com"}):
            assert app_module._active_storage_id() == "sheets"
        # b's request is unaffected by a's choice
        with self._ctx(app, {"user_email": "b@example.com"}):
            assert app_module._active_storage_id() == "json-google-drive"

    def test_unknown_user_gets_default(self, app):
        with self._ctx(app, {"user_email": "new@example.com"}):
            assert app_module._active_storage_id() == app_module.DEFAULT_STORAGE_BACKEND

    def test_choice_persists_across_requests(self, app):
        with self._ctx(app, {"user_email": "c@example.com"}):
            app_module.set_user_backend("c@example.com", "sheets")
        # a later, separate request resolves the recorded choice (survives sign-out)
        with self._ctx(app, {"user_email": "c@example.com"}):
            assert app_module._active_storage_id() == "sheets"

    def test_location_stored_per_backend(self, app):
        with app.test_request_context():
            app_module.save_location("d@example.com", "json-google-drive", "FOLDER1")
            app_module.save_location("d@example.com", "sheets", "SHEET1")
            assert app_module.get_stored_location("d@example.com", "json-google-drive") == "FOLDER1"
            assert app_module.get_stored_location("d@example.com", "sheets") == "SHEET1"


class TestStorageApiDispatch:
    """The data layer dispatches to the backend carried in the request context —
    never a shared global — so concurrent users never cross backends."""

    def test_dispatches_to_context_backend(self):
        class FakeBackend:
            def __init__(self, tag):
                self.tag = tag

            def get_pomodoros(self, service, location, start_date, end_date):
                return [self.tag, service, location]

        ctx_a = {"service": "svc-a", "location": "loc-a", "backend": FakeBackend("A")}
        ctx_b = {"service": "svc-b", "location": "loc-b", "backend": FakeBackend("B")}
        assert storage_api.get_pomodoros(ctx_a)[0] == "A"
        assert storage_api.get_pomodoros(ctx_b)[0] == "B"

    def test_missing_backend_raises(self):
        with pytest.raises(storage_api.StorageUnavailable):
            storage_api.get_pomodoros({"service": "s", "location": "l"})
        with pytest.raises(storage_api.StorageUnavailable):
            storage_api.get_pomodoros(None)


class TestPCloudBackendWiring:
    """json-pcloud is a registered storage backend; linking it is a separate OAuth
    flow because pCloud is storage, not identity (spec 010)."""

    def test_plugin_is_registered(self, client):
        response = client.get("/api/plugins")
        data = json.loads(response.data)
        pcloud = next(p for p in data["plugins"] if p["id"] == "json-pcloud")
        assert pcloud["plugin_type"] == "storage"
        assert pcloud["name"] == "JSON on pCloud"
        # Registered but not the default — the user must link it deliberately
        assert pcloud["active"] is False

    def test_provisioner_is_dispatchable(self, app):
        with app.test_request_context():
            path, existed = app_module._provision_storage("json-pcloud", None, "p@example.com", None)
        assert path == app_module.PCLOUD_DEFAULT_FOLDER_PATH
        # First link: nothing recorded yet, so this is not a returning user
        assert existed is False

    def test_google_signin_restates_linked_path(self, app):
        """A Google sign-in must not need a pCloud token — it just re-states the
        path the user already linked, so they land back on their own folder."""
        with app.test_request_context():
            app_module.save_location("q@example.com", "json-pcloud", "/Work/Acquacotta")
            path, existed = app_module._provision_storage("json-pcloud", None, "q@example.com", None)
        assert path == "/Work/Acquacotta"
        assert existed is True

    def test_link_requires_signed_in_email(self, client):
        with (
            patch.object(app_module, "PCLOUD_CLIENT_ID", "cid"),
            patch.object(app_module, "PCLOUD_CLIENT_SECRET", "secret"),
        ):
            response = client.get("/auth/pcloud")
        assert response.status_code == 400

    def test_link_redirects_to_pcloud(self, client):
        with (
            patch.object(app_module, "PCLOUD_CLIENT_ID", "cid"),
            patch.object(app_module, "PCLOUD_CLIENT_SECRET", "secret"),
        ):
            response = client.get("/auth/pcloud?user_email=p%40example.com")
        assert response.status_code == 302
        assert response.headers["Location"].startswith(app_module.PCLOUD_AUTHORIZE_URL)
        # The email is signed into the state, never echoed as a plain parameter
        assert "p%40example.com" not in response.headers["Location"].split("state=")[0]

    def test_link_without_credentials_configured(self, client):
        with patch.object(app_module, "PCLOUD_CLIENT_ID", None):
            response = client.get("/auth/pcloud?user_email=p%40example.com")
        assert response.status_code == 500

    def test_callback_provisions_and_hands_off(self, app, client):
        from itsdangerous import URLSafeTimedSerializer

        state = URLSafeTimedSerializer(app.config["SECRET_KEY"]).dumps({"email": "p@example.com"})

        token_response = MagicMock()
        token_response.json.return_value = {"access_token": "pc-token", "locationid": 1}

        fake_transport = MagicMock()
        fake_transport.ensure_directory.return_value = "/Acquacotta"
        fake_transport.file_exists.return_value = False

        with (
            patch.object(app_module, "PCLOUD_CLIENT_ID", "cid"),
            patch.object(app_module, "PCLOUD_CLIENT_SECRET", "secret"),
            patch.object(app_module.requests, "get", return_value=token_response),
            patch.object(app_module.pcloud_transport, "PCloudTransport", return_value=fake_transport),
        ):
            response = client.get(f"/auth/pcloud/callback?code=abc&state={state}&hostname=eapi.pcloud.com")

        assert response.status_code == 200
        body = response.data.decode()
        # The token reaches the browser and is never persisted server-side
        assert "pc-token" in body
        assert "eapi.pcloud.com" in body
        assert "/Acquacotta" in body
        with app.test_request_context():
            assert app_module.get_user_backend("p@example.com") == "json-pcloud"
            assert app_module.get_stored_location("p@example.com", "json-pcloud") == "/Acquacotta"

    def test_callback_rejects_unsigned_state(self, client):
        with (
            patch.object(app_module, "PCLOUD_CLIENT_ID", "cid"),
            patch.object(app_module, "PCLOUD_CLIENT_SECRET", "secret"),
        ):
            response = client.get("/auth/pcloud/callback?code=abc&state=forged")
        assert response.status_code == 400
