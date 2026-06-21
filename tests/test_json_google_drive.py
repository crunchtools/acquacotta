"""Tests for json_google_drive_storage.py and google_drive_transport.py.

Tests the storage plugin contract and transport layer using mocked Drive API.
"""

import json
from unittest.mock import MagicMock, patch

import json_google_drive_storage as storage
from transports.google_drive_transport import GoogleDriveTransport


# =============================================================================
# Transport tests
# =============================================================================


class TestGoogleDriveTransport:
    def _mock_service(self, list_files=None, file_content=None):
        service = MagicMock()
        files_mock = MagicMock()
        service.files.return_value = files_mock

        list_result = MagicMock()
        list_result.execute.return_value = {"files": list_files or []}
        files_mock.list.return_value = list_result

        if file_content is not None:
            get_media_result = MagicMock()
            get_media_result.execute.return_value = file_content.encode("utf-8")
            files_mock.get_media.return_value = get_media_result

        create_result = MagicMock()
        create_result.execute.return_value = {"id": "new-file-id"}
        files_mock.create.return_value = create_result

        update_result = MagicMock()
        update_result.execute.return_value = {}
        files_mock.update.return_value = update_result

        return service

    def test_find_file_found(self):
        service = self._mock_service(list_files=[{"id": "file-123"}])
        t = GoogleDriveTransport(service, "folder-abc")
        assert t._find_file("pomodoros.json") == "file-123"

    def test_find_file_not_found(self):
        service = self._mock_service(list_files=[])
        t = GoogleDriveTransport(service, "folder-abc")
        assert t._find_file("pomodoros.json") is None

    def test_find_file_caches_result(self):
        service = self._mock_service(list_files=[{"id": "file-123"}])
        t = GoogleDriveTransport(service, "folder-abc")
        t._find_file("pomodoros.json")
        t._find_file("pomodoros.json")
        service.files().list.assert_called_once()

    def test_download_file_returns_content(self):
        content = '{"pomodoros": [{"id": "1"}]}'
        service = self._mock_service(list_files=[{"id": "file-123"}], file_content=content)
        t = GoogleDriveTransport(service, "folder-abc")
        result = t.download_file("pomodoros.json")
        assert result == content

    def test_download_file_not_found(self):
        service = self._mock_service(list_files=[])
        t = GoogleDriveTransport(service, "folder-abc")
        assert t.download_file("pomodoros.json") is None

    def test_upload_file_creates_new(self):
        service = self._mock_service(list_files=[])
        t = GoogleDriveTransport(service, "folder-abc")
        t.upload_file("pomodoros.json", '{"pomodoros": []}')
        service.files().create.assert_called_once()

    def test_upload_file_updates_existing(self):
        service = self._mock_service(list_files=[{"id": "file-123"}])
        t = GoogleDriveTransport(service, "folder-abc")
        t.upload_file("pomodoros.json", '{"pomodoros": []}')
        service.files().update.assert_called_once()

    def test_file_exists_true(self):
        service = self._mock_service(list_files=[{"id": "file-123"}])
        t = GoogleDriveTransport(service, "folder-abc")
        assert t.file_exists("pomodoros.json") is True

    def test_file_exists_false(self):
        service = self._mock_service(list_files=[])
        t = GoogleDriveTransport(service, "folder-abc")
        assert t.file_exists("pomodoros.json") is False

    def test_ensure_directory_creates_folder(self):
        service = self._mock_service(list_files=[])
        t = GoogleDriveTransport(service, None)
        folder_id = t.ensure_directory()
        assert folder_id == "new-file-id"
        service.files().create.assert_called_once()

    def test_ensure_directory_finds_existing(self):
        service = self._mock_service(list_files=[{"id": "existing-folder"}])
        t = GoogleDriveTransport(service, None)
        folder_id = t.ensure_directory()
        assert folder_id == "existing-folder"


# =============================================================================
# Plugin metadata
# =============================================================================


class TestPluginMetadata:
    def test_metadata_fields(self):
        m = storage.PLUGIN_METADATA
        assert m["id"] == "json-google-drive"
        assert m["type"] == "storage"
        assert "folder_id" in m["frontend_fields"]
        assert m["auth_flow"] == "google_oauth"

    def test_build_context(self):
        with patch("json_google_drive_storage.build") as mock_build:
            mock_build.return_value = "drive-service"
            ctx = storage.build_context("creds", {"folder_id": "folder-123"})
            assert ctx["service"] == "drive-service"
            assert ctx["location"] == "folder-123"
            mock_build.assert_called_once_with("drive", "v3", credentials="creds")


# =============================================================================
# Storage contract — all 11 functions
# =============================================================================


def _mock_transport(file_contents=None):
    """Create a mock transport that returns given file contents on download."""
    transport = MagicMock(spec=GoogleDriveTransport)
    transport.download_file.return_value = file_contents
    transport.upload_file.return_value = None
    return transport


class TestGetPomodoros:
    @patch("json_google_drive_storage._transport")
    def test_returns_pomodoros(self, mock_transport_fn):
        data = json.dumps({"pomodoros": [
            {"id": "1", "start_time": "2026-01-15T10:00:00Z"},
            {"id": "2", "start_time": "2026-01-20T10:00:00Z"},
        ]})
        mock_transport_fn.return_value = _mock_transport(data)
        result = storage.get_pomodoros("svc", "folder", start_date="2026-01-16")
        assert len(result) == 1
        assert result[0]["id"] == "2"

    @patch("json_google_drive_storage._transport")
    def test_empty_file(self, mock_transport_fn):
        mock_transport_fn.return_value = _mock_transport(None)
        result = storage.get_pomodoros("svc", "folder")
        assert result == []


class TestSavePomodoro:
    @patch("json_google_drive_storage._transport")
    def test_saves_new(self, mock_transport_fn):
        t = _mock_transport('{"pomodoros": []}')
        mock_transport_fn.return_value = t
        result = storage.save_pomodoro("svc", "folder", {"id": "new", "name": "Test"})
        assert result is True
        t.upload_file.assert_called_once()

    @patch("json_google_drive_storage._transport")
    def test_skips_duplicate(self, mock_transport_fn):
        t = _mock_transport('{"pomodoros": [{"id": "existing"}]}')
        mock_transport_fn.return_value = t
        result = storage.save_pomodoro("svc", "folder", {"id": "existing", "name": "Dup"})
        assert result is False
        t.upload_file.assert_not_called()


class TestSavePomodorosBatch:
    @patch("json_google_drive_storage._transport")
    def test_batch_save(self, mock_transport_fn):
        t = _mock_transport('{"pomodoros": [{"id": "1"}]}')
        mock_transport_fn.return_value = t
        count = storage.save_pomodoros_batch("svc", "folder", [{"id": "2"}, {"id": "3"}, {"id": "1"}])
        assert count == 2
        t.upload_file.assert_called_once()

    @patch("json_google_drive_storage._transport")
    def test_batch_empty(self, mock_transport_fn):
        count = storage.save_pomodoros_batch("svc", "folder", [])
        assert count == 0

    @patch("json_google_drive_storage._transport")
    def test_batch_all_duplicates(self, mock_transport_fn):
        t = _mock_transport('{"pomodoros": [{"id": "1"}, {"id": "2"}]}')
        mock_transport_fn.return_value = t
        count = storage.save_pomodoros_batch("svc", "folder", [{"id": "1"}, {"id": "2"}])
        assert count == 0
        t.upload_file.assert_not_called()


class TestUpdatePomodoro:
    @patch("json_google_drive_storage._transport")
    def test_update_found(self, mock_transport_fn):
        t = _mock_transport('{"pomodoros": [{"id": "1", "name": "Old"}]}')
        mock_transport_fn.return_value = t
        result = storage.update_pomodoro("svc", "folder", "1", {"name": "New"})
        assert result is True
        t.upload_file.assert_called_once()

    @patch("json_google_drive_storage._transport")
    def test_update_not_found(self, mock_transport_fn):
        t = _mock_transport('{"pomodoros": [{"id": "1"}]}')
        mock_transport_fn.return_value = t
        result = storage.update_pomodoro("svc", "folder", "999", {"name": "New"})
        assert result is False
        t.upload_file.assert_not_called()


class TestDeletePomodoro:
    @patch("json_google_drive_storage._transport")
    def test_delete_found(self, mock_transport_fn):
        t = _mock_transport('{"pomodoros": [{"id": "1"}, {"id": "2"}]}')
        mock_transport_fn.return_value = t
        result = storage.delete_pomodoro("svc", "folder", "1")
        assert result is True
        t.upload_file.assert_called_once()
        uploaded = t.upload_file.call_args[0][1]
        assert '"id": "1"' not in uploaded

    @patch("json_google_drive_storage._transport")
    def test_delete_not_found(self, mock_transport_fn):
        t = _mock_transport('{"pomodoros": [{"id": "1"}]}')
        mock_transport_fn.return_value = t
        result = storage.delete_pomodoro("svc", "folder", "999")
        assert result is False
        t.upload_file.assert_not_called()


class TestGetSettings:
    @patch("json_google_drive_storage._transport")
    def test_merges_with_defaults(self, mock_transport_fn):
        t = _mock_transport('{"custom_key": "custom_val"}')
        mock_transport_fn.return_value = t
        defaults = {"default_key": "default_val", "custom_key": "overridden"}
        result = storage.get_settings("svc", "folder", defaults)
        assert result["default_key"] == "default_val"
        assert result["custom_key"] == "custom_val"

    @patch("json_google_drive_storage._transport")
    def test_empty_settings_file(self, mock_transport_fn):
        t = _mock_transport(None)
        mock_transport_fn.return_value = t
        defaults = {"key": "val"}
        result = storage.get_settings("svc", "folder", defaults)
        assert result == {"key": "val"}


class TestSaveSettings:
    @patch("json_google_drive_storage._transport")
    def test_replace_all(self, mock_transport_fn):
        t = _mock_transport('{"old_key": "old_val"}')
        mock_transport_fn.return_value = t
        storage.save_settings("svc", "folder", {"new_key": "new_val"}, replace_all=True)
        uploaded = json.loads(t.upload_file.call_args[0][1])
        assert uploaded == {"new_key": "new_val"}

    @patch("json_google_drive_storage._transport")
    def test_incremental(self, mock_transport_fn):
        t = _mock_transport('{"existing": 1}')
        mock_transport_fn.return_value = t
        storage.save_settings("svc", "folder", {"new": 2}, replace_all=False)
        uploaded = json.loads(t.upload_file.call_args[0][1])
        assert uploaded == {"existing": 1, "new": 2}


class TestDeduplicatePomodoros:
    @patch("json_google_drive_storage._transport")
    def test_removes_dupes(self, mock_transport_fn):
        t = _mock_transport('{"pomodoros": [{"id": "1"}, {"id": "2"}, {"id": "1"}]}')
        mock_transport_fn.return_value = t
        result = storage.deduplicate_pomodoros("svc", "folder")
        assert result["removed"] == 1
        assert result["total"] == 2
        t.upload_file.assert_called_once()

    @patch("json_google_drive_storage._transport")
    def test_no_dupes(self, mock_transport_fn):
        t = _mock_transport('{"pomodoros": [{"id": "1"}, {"id": "2"}]}')
        mock_transport_fn.return_value = t
        result = storage.deduplicate_pomodoros("svc", "folder")
        assert result["removed"] == 0
        t.upload_file.assert_not_called()


class TestCountPomodoros:
    @patch("json_google_drive_storage._transport")
    def test_count(self, mock_transport_fn):
        t = _mock_transport('{"pomodoros": [{"id": "1"}, {"id": "2"}, {"id": "3"}]}')
        mock_transport_fn.return_value = t
        assert storage.count_pomodoros("svc", "folder") == 3

    @patch("json_google_drive_storage._transport")
    def test_count_empty(self, mock_transport_fn):
        t = _mock_transport(None)
        mock_transport_fn.return_value = t
        assert storage.count_pomodoros("svc", "folder") == 0


class TestClearPomodoros:
    @patch("json_google_drive_storage._transport")
    def test_clear(self, mock_transport_fn):
        t = _mock_transport('{"pomodoros": [{"id": "1"}, {"id": "2"}]}')
        mock_transport_fn.return_value = t
        result = storage.clear_pomodoros("svc", "folder")
        assert result["status"] == "ok"
        assert result["cleared"] == 2
        uploaded = json.loads(t.upload_file.call_args[0][1])
        assert uploaded["pomodoros"] == []
