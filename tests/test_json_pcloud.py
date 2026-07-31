"""Tests for json_pcloud_storage.py and pcloud_transport.py.

Tests the storage plugin contract and transport layer using a mocked pCloud client.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

import json_pcloud_storage as storage
from transports.pcloud_transport import (
    PCLOUD_FILE_NOT_FOUND,
    PCloudClient,
    PCloudError,
    PCloudTransport,
)


class TestPCloudTransport:
    def _mock_client(self, stat_result=None, file_content=None):
        """A client whose stat() answers with `stat_result` and whose file link
        resolves to `file_content`."""
        client = MagicMock(spec=PCloudClient)

        def call(method, params=None, files=None, tolerate=()):
            if method == "stat":
                return stat_result if stat_result is not None else {"result": PCLOUD_FILE_NOT_FOUND}
            if method == "getfilelink":
                return {"result": 0, "hosts": ["c1.pcloud.com"], "path": "/dl/token/file"}
            return {"result": 0}

        client.call.side_effect = call
        client.fetch_content.return_value = file_content
        return client

    def _found(self, file_id="123"):
        return {"result": 0, "metadata": {"fileid": file_id}}

    def test_find_file_found(self):
        client = self._mock_client(stat_result=self._found("file-123"))
        t = PCloudTransport(client, "/Acquacotta")
        assert t._find_file("pomodoros.json") == "file-123"

    def test_find_file_not_found(self):
        client = self._mock_client()
        t = PCloudTransport(client, "/Acquacotta")
        assert t._find_file("pomodoros.json") is None

    def test_find_file_uses_folder_path(self):
        client = self._mock_client(stat_result=self._found())
        t = PCloudTransport(client, "/Acquacotta/")
        t._find_file("pomodoros.json")
        _method, params = client.call.call_args[0]
        assert params["path"] == "/Acquacotta/pomodoros.json"

    def test_download_file_returns_content(self):
        content = '{"pomodoros": [{"id": "1"}]}'
        client = self._mock_client(stat_result=self._found(), file_content=content)
        t = PCloudTransport(client, "/Acquacotta")
        assert t.download_file("pomodoros.json") == content
        client.fetch_content.assert_called_once_with("https://c1.pcloud.com/dl/token/file")

    def test_download_file_not_found(self):
        client = self._mock_client()
        t = PCloudTransport(client, "/Acquacotta")
        assert t.download_file("pomodoros.json") is None

    def test_upload_file_posts_multipart(self):
        client = self._mock_client()
        t = PCloudTransport(client, "/Acquacotta")
        t.upload_file("pomodoros.json", '{"pomodoros": []}')
        _method, kwargs = client.call.call_args[0][0], client.call.call_args[1]
        assert kwargs["params"]["path"] == "/Acquacotta"
        # Overwrite, never sidestep into pomodoros_1.json
        assert kwargs["params"]["renameifexists"] == 0
        filename, payload, _mimetype = kwargs["files"]["file"]
        assert filename == "pomodoros.json"
        assert payload == b'{"pomodoros": []}'

    def test_file_exists_true(self):
        client = self._mock_client(stat_result=self._found())
        t = PCloudTransport(client, "/Acquacotta")
        assert t.file_exists("pomodoros.json") is True

    def test_file_exists_false(self):
        client = self._mock_client()
        t = PCloudTransport(client, "/Acquacotta")
        assert t.file_exists("pomodoros.json") is False

    def test_ensure_directory_creates_folder(self):
        client = self._mock_client()
        t = PCloudTransport(client, "/Acquacotta")
        assert t.ensure_directory() == "/Acquacotta"
        method, params = client.call.call_args[0]
        assert method == "createfolderifnotexists"
        assert params["path"] == "/Acquacotta"

    def test_defaults_to_acquacotta_folder(self):
        client = self._mock_client()
        t = PCloudTransport(client, None)
        assert t.ensure_directory() == "/Acquacotta"


class TestPCloudClient:
    def _response(self, payload):
        response = MagicMock()
        response.json.return_value = payload
        return response

    def test_call_raises_on_error_result(self):
        client = PCloudClient("tok")
        with patch.object(client, "_session") as session:
            session.get.return_value = self._response({"result": 2000, "error": "Log in failed"})
            with pytest.raises(PCloudError) as exc:
                client.call("stat", {"path": "/x"})
        assert exc.value.code == 2000

    def test_call_tolerates_listed_codes(self):
        client = PCloudClient("tok")
        with patch.object(client, "_session") as session:
            session.get.return_value = self._response({"result": PCLOUD_FILE_NOT_FOUND})
            data = client.call("stat", {"path": "/x"}, tolerate=(PCLOUD_FILE_NOT_FOUND,))
        assert data["result"] == PCLOUD_FILE_NOT_FOUND

    def test_sends_bearer_token(self):
        client = PCloudClient("tok-abc")
        assert client._session.headers["Authorization"] == "Bearer tok-abc"

    def test_defaults_to_us_host(self):
        assert PCloudClient("tok").api_host == "api.pcloud.com"

    def test_honors_eu_host(self):
        assert PCloudClient("tok", "eapi.pcloud.com").api_host == "eapi.pcloud.com"


class TestPluginMetadata:
    def test_metadata_fields(self):
        m = storage.PLUGIN_METADATA
        assert m["id"] == "json-pcloud"
        assert m["type"] == "storage"
        assert "pcloud_folder_path" in m["frontend_fields"]
        assert m["auth_flow"] == "pcloud_oauth"

    def test_build_context(self):
        ctx = storage.build_context(
            "google-creds",
            {
                "pcloud_token": "tok",
                "pcloud_api_host": "eapi.pcloud.com",
                "pcloud_folder_path": "/Acquacotta",
            },
        )
        assert isinstance(ctx["service"], PCloudClient)
        assert ctx["service"].api_host == "eapi.pcloud.com"
        assert ctx["location"] == "/Acquacotta"


def _mock_transport(file_contents=None):
    """Create a mock transport that returns given file contents on download."""
    transport = MagicMock(spec=PCloudTransport)
    transport.download_file.return_value = file_contents
    transport.upload_file.return_value = None
    return transport


class TestGetPomodoros:
    @patch("json_pcloud_storage._transport")
    def test_returns_pomodoros(self, mock_transport_fn):
        data = json.dumps(
            {
                "pomodoros": [
                    {"id": "1", "start_time": "2026-01-15T10:00:00Z"},
                    {"id": "2", "start_time": "2026-01-20T10:00:00Z"},
                ]
            }
        )
        mock_transport_fn.return_value = _mock_transport(data)
        result = storage.get_pomodoros("client", "/Acquacotta", start_date="2026-01-16")
        assert len(result) == 1
        assert result[0]["id"] == "2"

    @patch("json_pcloud_storage._transport")
    def test_empty_file(self, mock_transport_fn):
        mock_transport_fn.return_value = _mock_transport(None)
        assert storage.get_pomodoros("client", "/Acquacotta") == []


class TestSavePomodoro:
    @patch("json_pcloud_storage._transport")
    def test_saves_new(self, mock_transport_fn):
        t = _mock_transport('{"pomodoros": []}')
        mock_transport_fn.return_value = t
        assert storage.save_pomodoro("client", "/Acquacotta", {"id": "new"}) is True
        t.upload_file.assert_called_once()

    @patch("json_pcloud_storage._transport")
    def test_skips_duplicate(self, mock_transport_fn):
        t = _mock_transport('{"pomodoros": [{"id": "existing"}]}')
        mock_transport_fn.return_value = t
        assert storage.save_pomodoro("client", "/Acquacotta", {"id": "existing"}) is False
        t.upload_file.assert_not_called()


class TestSavePomodorosBatch:
    @patch("json_pcloud_storage._transport")
    def test_batch_writes_once(self, mock_transport_fn):
        t = _mock_transport('{"pomodoros": [{"id": "1"}]}')
        mock_transport_fn.return_value = t
        count = storage.save_pomodoros_batch("client", "/Acquacotta", [{"id": "2"}, {"id": "3"}, {"id": "1"}])
        assert count == 2
        # SC-003: one API write for the whole batch, not one per item
        t.upload_file.assert_called_once()

    @patch("json_pcloud_storage._transport")
    def test_batch_empty(self, mock_transport_fn):
        assert storage.save_pomodoros_batch("client", "/Acquacotta", []) == 0

    @patch("json_pcloud_storage._transport")
    def test_batch_all_duplicates(self, mock_transport_fn):
        t = _mock_transport('{"pomodoros": [{"id": "1"}, {"id": "2"}]}')
        mock_transport_fn.return_value = t
        assert storage.save_pomodoros_batch("client", "/Acquacotta", [{"id": "1"}, {"id": "2"}]) == 0
        t.upload_file.assert_not_called()


class TestUpdatePomodoro:
    @patch("json_pcloud_storage._transport")
    def test_update_found(self, mock_transport_fn):
        t = _mock_transport('{"pomodoros": [{"id": "1", "name": "Old"}]}')
        mock_transport_fn.return_value = t
        assert storage.update_pomodoro("client", "/Acquacotta", "1", {"name": "New"}) is True
        t.upload_file.assert_called_once()

    @patch("json_pcloud_storage._transport")
    def test_update_not_found(self, mock_transport_fn):
        t = _mock_transport('{"pomodoros": [{"id": "1"}]}')
        mock_transport_fn.return_value = t
        assert storage.update_pomodoro("client", "/Acquacotta", "999", {"name": "New"}) is False
        t.upload_file.assert_not_called()


class TestDeletePomodoro:
    @patch("json_pcloud_storage._transport")
    def test_delete_found(self, mock_transport_fn):
        t = _mock_transport('{"pomodoros": [{"id": "1"}, {"id": "2"}]}')
        mock_transport_fn.return_value = t
        assert storage.delete_pomodoro("client", "/Acquacotta", "1") is True
        assert '"id": "1"' not in t.upload_file.call_args[0][1]

    @patch("json_pcloud_storage._transport")
    def test_delete_not_found(self, mock_transport_fn):
        t = _mock_transport('{"pomodoros": [{"id": "1"}]}')
        mock_transport_fn.return_value = t
        assert storage.delete_pomodoro("client", "/Acquacotta", "999") is False
        t.upload_file.assert_not_called()


class TestSettings:
    @patch("json_pcloud_storage._transport")
    def test_merges_with_defaults(self, mock_transport_fn):
        mock_transport_fn.return_value = _mock_transport('{"custom_key": "custom_val"}')
        defaults = {"default_key": "default_val", "custom_key": "overridden"}
        result = storage.get_settings("client", "/Acquacotta", defaults)
        assert result["default_key"] == "default_val"
        assert result["custom_key"] == "custom_val"

    @patch("json_pcloud_storage._transport")
    def test_empty_settings_file(self, mock_transport_fn):
        mock_transport_fn.return_value = _mock_transport(None)
        assert storage.get_settings("client", "/Acquacotta", {"key": "val"}) == {"key": "val"}

    @patch("json_pcloud_storage._transport")
    def test_save_replace_all(self, mock_transport_fn):
        t = _mock_transport('{"old_key": "old_val"}')
        mock_transport_fn.return_value = t
        storage.save_settings("client", "/Acquacotta", {"new_key": "new_val"}, replace_all=True)
        assert json.loads(t.upload_file.call_args[0][1]) == {"new_key": "new_val"}

    @patch("json_pcloud_storage._transport")
    def test_save_incremental(self, mock_transport_fn):
        t = _mock_transport('{"existing": 1}')
        mock_transport_fn.return_value = t
        storage.save_settings("client", "/Acquacotta", {"new": 2}, replace_all=False)
        assert json.loads(t.upload_file.call_args[0][1]) == {"existing": 1, "new": 2}


class TestMaintenanceOperations:
    @patch("json_pcloud_storage._transport")
    def test_deduplicate_removes_dupes(self, mock_transport_fn):
        t = _mock_transport('{"pomodoros": [{"id": "1"}, {"id": "2"}, {"id": "1"}]}')
        mock_transport_fn.return_value = t
        result = storage.deduplicate_pomodoros("client", "/Acquacotta")
        assert result == {"removed": 1, "total": 2}
        t.upload_file.assert_called_once()

    @patch("json_pcloud_storage._transport")
    def test_deduplicate_no_dupes(self, mock_transport_fn):
        t = _mock_transport('{"pomodoros": [{"id": "1"}, {"id": "2"}]}')
        mock_transport_fn.return_value = t
        assert storage.deduplicate_pomodoros("client", "/Acquacotta")["removed"] == 0
        t.upload_file.assert_not_called()

    @patch("json_pcloud_storage._transport")
    def test_count(self, mock_transport_fn):
        mock_transport_fn.return_value = _mock_transport('{"pomodoros": [{"id": "1"}, {"id": "2"}]}')
        assert storage.count_pomodoros("client", "/Acquacotta") == 2

    @patch("json_pcloud_storage._transport")
    def test_count_empty(self, mock_transport_fn):
        mock_transport_fn.return_value = _mock_transport(None)
        assert storage.count_pomodoros("client", "/Acquacotta") == 0

    @patch("json_pcloud_storage._transport")
    def test_clear(self, mock_transport_fn):
        t = _mock_transport('{"pomodoros": [{"id": "1"}, {"id": "2"}]}')
        mock_transport_fn.return_value = t
        assert storage.clear_pomodoros("client", "/Acquacotta") == {"status": "ok", "cleared": 2}
        assert json.loads(t.upload_file.call_args[0][1])["pomodoros"] == []


class TestMcpState:
    @patch("json_pcloud_storage._transport")
    def test_defaults_when_absent(self, mock_transport_fn):
        mock_transport_fn.return_value = _mock_transport(None)
        assert storage.get_mcp_state("client", "/Acquacotta") == {"enabled": False, "epoch": 0}

    @patch("json_pcloud_storage._transport")
    def test_reads_stored_state(self, mock_transport_fn):
        mock_transport_fn.return_value = _mock_transport('{"enabled": true, "epoch": 123}')
        assert storage.get_mcp_state("client", "/Acquacotta") == {"enabled": True, "epoch": 123}

    @patch("json_pcloud_storage._transport")
    def test_tolerates_corrupt_json(self, mock_transport_fn):
        mock_transport_fn.return_value = _mock_transport("{not json")
        assert storage.get_mcp_state("client", "/Acquacotta") == {"enabled": False, "epoch": 0}

    @patch("json_pcloud_storage._transport")
    def test_set_writes_state_file(self, mock_transport_fn):
        t = _mock_transport(None)
        mock_transport_fn.return_value = t
        storage.set_mcp_state("client", "/Acquacotta", enabled=True, epoch=456)
        name, content = t.upload_file.call_args[0]
        assert name == "mcp_access.json"
        assert json.loads(content) == {"enabled": True, "epoch": 456}
