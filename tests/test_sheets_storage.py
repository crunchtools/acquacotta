"""Tests for Google Sheets storage backend (gspread mocks)."""

from unittest.mock import MagicMock, patch

import sheets_storage


def _mock_client(worksheets=None):
    """Create a mock gspread Client with a spreadsheet containing named worksheets."""
    gc = MagicMock()
    ws_map = worksheets or {}
    spreadsheet = MagicMock()
    spreadsheet.worksheet.side_effect = lambda name: ws_map.get(name, MagicMock())
    gc.open_by_key.return_value = spreadsheet
    return gc


def _mock_worksheet(**kwargs):
    """Create a mock gspread Worksheet with configurable return values."""
    ws = MagicMock()
    if "get_return" in kwargs:
        ws.get.return_value = kwargs["get_return"]
    if "col_values_return" in kwargs:
        ws.col_values.return_value = kwargs["col_values_return"]
    if "row_values_return" in kwargs:
        ws.row_values.return_value = kwargs["row_values_return"]
    return ws


class TestBuildContext:
    """Tests for build_context."""

    @patch("sheets_storage.gspread")
    def test_build_context_returns_dict(self, mock_gspread):
        creds = MagicMock()
        mock_gc = MagicMock()
        mock_gspread.authorize.return_value = mock_gc

        result = sheets_storage.build_context(creds, {"spreadsheet_id": "test-id"})

        assert result["service"] is mock_gc
        assert result["location"] == "test-id"
        mock_gspread.authorize.assert_called_once_with(creds)


class TestGetPomodoros:
    """Tests for getting pomodoros from Google Sheets."""

    def test_get_pomodoros_empty(self):
        ws = _mock_worksheet(get_return=[])
        gc = _mock_client({"Pomodoros": ws})

        result = sheets_storage.get_pomodoros(gc, "test-id")
        assert result == []

    def test_get_pomodoros_with_data(self):
        ws = _mock_worksheet(get_return=[
            ["id-1", "Task 1", "Content", "2024-01-15T10:00:00Z", "2024-01-15T10:25:00Z", "25", "Notes 1"],
            ["id-2", "Task 2", "Product", "2024-01-15T11:00:00Z", "2024-01-15T11:25:00Z", "25", ""],
        ])
        gc = _mock_client({"Pomodoros": ws})

        result = sheets_storage.get_pomodoros(gc, "test-id")

        assert len(result) == 2
        assert result[0]["id"] == "id-2"
        assert result[0]["name"] == "Task 2"
        assert result[0]["type"] == "Product"
        assert result[0]["duration_minutes"] == 25
        assert result[1]["id"] == "id-1"
        assert result[1]["notes"] == "Notes 1"

    def test_get_pomodoros_skips_incomplete_rows(self):
        ws = _mock_worksheet(get_return=[
            ["id-1", "Task 1", "Content", "2024-01-15T10:00:00Z", "2024-01-15T10:25:00Z", "25"],
            ["id-2", "Task 2"],
            ["id-3", "Task 3", "Team", "2024-01-15T12:00:00Z", "2024-01-15T12:25:00Z", "25", "Notes"],
        ])
        gc = _mock_client({"Pomodoros": ws})

        result = sheets_storage.get_pomodoros(gc, "test-id")
        assert len(result) == 2
        assert result[0]["id"] == "id-3"
        assert result[1]["id"] == "id-1"

    def test_get_pomodoros_with_date_filter(self):
        ws = _mock_worksheet(get_return=[
            ["id-1", "Task 1", "Content", "2024-01-14T10:00:00Z", "2024-01-14T10:25:00Z", "25", ""],
            ["id-2", "Task 2", "Product", "2024-01-15T11:00:00Z", "2024-01-15T11:25:00Z", "25", ""],
            ["id-3", "Task 3", "Team", "2024-01-16T12:00:00Z", "2024-01-16T12:25:00Z", "25", ""],
        ])
        gc = _mock_client({"Pomodoros": ws})

        result = sheets_storage.get_pomodoros(
            gc, "test-id",
            start_date="2024-01-15T00:00:00Z",
            end_date="2024-01-15T23:59:59Z",
        )

        assert len(result) == 1
        assert result[0]["id"] == "id-2"


class TestSavePomodoro:
    """Tests for saving pomodoros to Google Sheets."""

    def test_save_pomodoro(self):
        ws = _mock_worksheet(col_values_return=["id", "existing-1"])
        gc = _mock_client({"Pomodoros": ws})

        pomodoro = {
            "id": "new-id",
            "name": "New Task",
            "type": "Content",
            "start_time": "2024-01-15T10:00:00Z",
            "end_time": "2024-01-15T10:25:00Z",
            "duration_minutes": 25,
            "notes": "Test notes",
        }

        result = sheets_storage.save_pomodoro(gc, "test-id", pomodoro)

        assert result is True
        ws.append_row.assert_called_once()
        call_args = ws.append_row.call_args[0][0]
        assert call_args[0] == "new-id"
        assert call_args[1] == "New Task"

    def test_save_pomodoro_duplicate(self):
        ws = _mock_worksheet(col_values_return=["id", "existing-id"])
        gc = _mock_client({"Pomodoros": ws})

        pomodoro = {"id": "existing-id", "name": "Task", "type": "Content",
                    "start_time": "2024-01-15T10:00:00Z", "end_time": "2024-01-15T10:25:00Z",
                    "duration_minutes": 25}

        result = sheets_storage.save_pomodoro(gc, "test-id", pomodoro)

        assert result is False
        ws.append_row.assert_not_called()

    def test_save_pomodoro_without_notes(self):
        ws = _mock_worksheet(col_values_return=["id"])
        gc = _mock_client({"Pomodoros": ws})

        pomodoro = {
            "id": "new-id",
            "name": "Task",
            "type": "Content",
            "start_time": "2024-01-15T10:00:00Z",
            "end_time": "2024-01-15T10:25:00Z",
            "duration_minutes": 25,
        }

        sheets_storage.save_pomodoro(gc, "test-id", pomodoro)

        call_args = ws.append_row.call_args[0][0]
        assert call_args[6] == ""


class TestSavePomodorosBatch:
    """Tests for batch saving pomodoros."""

    def test_save_pomodoros_batch(self):
        ws = _mock_worksheet(col_values_return=["id"])
        gc = _mock_client({"Pomodoros": ws})

        pomodoros = [
            {"id": "id-1", "name": "Task 1", "type": "Content",
             "start_time": "2024-01-15T10:00:00Z", "end_time": "2024-01-15T10:25:00Z",
             "duration_minutes": 25, "notes": ""},
            {"id": "id-2", "name": "Task 2", "type": "Product",
             "start_time": "2024-01-15T11:00:00Z", "end_time": "2024-01-15T11:25:00Z",
             "duration_minutes": 25, "notes": "Note"},
        ]

        result = sheets_storage.save_pomodoros_batch(gc, "test-id", pomodoros)

        assert result == 2
        ws.append_rows.assert_called_once()
        call_args = ws.append_rows.call_args[0][0]
        assert len(call_args) == 2
        assert call_args[0][0] == "id-1"
        assert call_args[1][0] == "id-2"

    def test_save_pomodoros_batch_empty(self):
        gc = MagicMock()

        result = sheets_storage.save_pomodoros_batch(gc, "test-id", [])

        assert result == 0
        gc.open_by_key.assert_not_called()

    def test_save_pomodoros_batch_skips_duplicates(self):
        ws = _mock_worksheet(col_values_return=["id", "id-1"])
        gc = _mock_client({"Pomodoros": ws})

        pomodoros = [
            {"id": "id-1", "name": "Task 1", "type": "Content",
             "start_time": "2024-01-15T10:00:00Z", "end_time": "2024-01-15T10:25:00Z",
             "duration_minutes": 25, "notes": ""},
            {"id": "id-2", "name": "Task 2", "type": "Product",
             "start_time": "2024-01-15T11:00:00Z", "end_time": "2024-01-15T11:25:00Z",
             "duration_minutes": 25, "notes": ""},
        ]

        result = sheets_storage.save_pomodoros_batch(gc, "test-id", pomodoros)

        assert result == 1
        call_args = ws.append_rows.call_args[0][0]
        assert len(call_args) == 1
        assert call_args[0][0] == "id-2"


class TestUpdatePomodoro:
    """Tests for updating pomodoros in Google Sheets."""

    def test_update_pomodoro_found(self):
        ws = _mock_worksheet(
            col_values_return=["id", "id-1", "id-2", "target-id"],
            row_values_return=["target-id", "Old Name", "Content",
                               "2024-01-15T10:00:00Z", "2024-01-15T10:25:00Z", "25", "Old notes"],
        )
        gc = _mock_client({"Pomodoros": ws})

        result = sheets_storage.update_pomodoro(
            gc, "test-id", "target-id",
            {"name": "New Name", "type": "Product", "notes": "New notes"},
        )

        assert result is True
        ws.update.assert_called_once()
        call_kwargs = ws.update.call_args[1]
        assert call_kwargs["range_name"] == "A4:G4"
        updated_row = call_kwargs["values"][0]
        assert updated_row[1] == "New Name"
        assert updated_row[2] == "Product"
        assert updated_row[6] == "New notes"

    def test_update_pomodoro_not_found(self):
        ws = _mock_worksheet(col_values_return=["id", "id-1", "id-2"])
        gc = _mock_client({"Pomodoros": ws})

        result = sheets_storage.update_pomodoro(
            gc, "test-id", "nonexistent-id", {"name": "New Name"},
        )

        assert result is False


class TestDeletePomodoro:
    """Tests for deleting pomodoros from Google Sheets."""

    def test_delete_pomodoro_found(self):
        ws = _mock_worksheet(col_values_return=["id", "id-1", "target-id", "id-3"])
        gc = _mock_client({"Pomodoros": ws})

        result = sheets_storage.delete_pomodoro(gc, "test-id", "target-id")

        assert result is True
        ws.delete_rows.assert_called_once_with(3)

    def test_delete_pomodoro_not_found(self):
        ws = _mock_worksheet(col_values_return=["id", "id-1", "id-2"])
        gc = _mock_client({"Pomodoros": ws})

        result = sheets_storage.delete_pomodoro(gc, "test-id", "nonexistent-id")

        assert result is False


class TestGetSettings:
    """Tests for getting settings from Google Sheets."""

    def test_get_settings_empty(self):
        ws = _mock_worksheet(get_return=[])
        gc = _mock_client({"Settings": ws})

        defaults = {"timer_preset_1": 5, "timer_preset_2": 10}
        result = sheets_storage.get_settings(gc, "test-id", defaults)

        assert result == defaults

    def test_get_settings_with_data(self):
        ws = _mock_worksheet(get_return=[
            ["timer_preset_1", "15"],
            ["pomodoro_types", '["Content", "Product"]'],
        ])
        gc = _mock_client({"Settings": ws})

        defaults = {"timer_preset_1": 5, "timer_preset_2": 10, "pomodoro_types": []}
        result = sheets_storage.get_settings(gc, "test-id", defaults)

        assert result["timer_preset_1"] == 15
        assert result["timer_preset_2"] == 10
        assert result["pomodoro_types"] == ["Content", "Product"]


class TestSaveSettings:
    """Tests for saving settings to Google Sheets."""

    def test_save_settings_new(self):
        ws = _mock_worksheet(get_return=[])
        gc = _mock_client({"Settings": ws})

        settings = {"timer_preset_1": 10, "timer_preset_2": 20}
        sheets_storage.save_settings(gc, "test-id", settings)

        ws.append_rows.assert_called_once()

    def test_save_settings_update_existing(self):
        ws = _mock_worksheet(get_return=[["timer_preset_1", "5"]])
        gc = _mock_client({"Settings": ws})

        settings = {"timer_preset_1": 10}
        sheets_storage.save_settings(gc, "test-id", settings)

        ws.batch_update.assert_called_once()

    def test_save_settings_mixed(self):
        ws = _mock_worksheet(get_return=[["timer_preset_1", "5"]])
        gc = _mock_client({"Settings": ws})

        settings = {"timer_preset_1": 10, "timer_preset_2": 20}
        sheets_storage.save_settings(gc, "test-id", settings)

        ws.batch_update.assert_called_once()
        ws.append_rows.assert_called_once()

    def test_save_settings_replace_all(self):
        ws = MagicMock()
        gc = _mock_client({"Settings": ws})

        settings = {"timer_preset_1": 10}
        sheets_storage.save_settings(gc, "test-id", settings, replace_all=True)

        ws.batch_clear.assert_called_once_with(["A2:B"])
        ws.update.assert_called_once()


class TestCountPomodoros:
    """Tests for counting pomodoros."""

    def test_count_pomodoros(self):
        ws = _mock_worksheet(col_values_return=["id", "id-1", "id-2", "id-3"])
        gc = _mock_client({"Pomodoros": ws})

        result = sheets_storage.count_pomodoros(gc, "test-id")
        assert result == 3

    def test_count_pomodoros_empty(self):
        ws = _mock_worksheet(col_values_return=["id"])
        gc = _mock_client({"Pomodoros": ws})

        result = sheets_storage.count_pomodoros(gc, "test-id")
        assert result == 0


class TestClearPomodoros:
    """Tests for clearing pomodoros."""

    def test_clear_pomodoros(self):
        ws = _mock_worksheet(col_values_return=["id", "id-1", "id-2", "id-3"])
        gc = _mock_client({"Pomodoros": ws})

        result = sheets_storage.clear_pomodoros(gc, "test-id")

        assert result == {"status": "ok", "cleared": 3}
        ws.delete_rows.assert_called_once_with(2, 4)

    def test_clear_pomodoros_empty(self):
        ws = _mock_worksheet(col_values_return=["id"])
        gc = _mock_client({"Pomodoros": ws})

        result = sheets_storage.clear_pomodoros(gc, "test-id")

        assert result == {"status": "ok", "cleared": 0}
        ws.delete_rows.assert_not_called()


class TestDeduplicatePomodoros:
    """Tests for deduplicating pomodoros."""

    def test_deduplicate_no_duplicates(self):
        ws = _mock_worksheet(col_values_return=["id", "id-1", "id-2", "id-3"])
        gc = _mock_client({"Pomodoros": ws})

        result = sheets_storage.deduplicate_pomodoros(gc, "test-id")

        assert result == {"removed": 0, "total": 3}
        ws.delete_rows.assert_not_called()

    def test_deduplicate_with_duplicates(self):
        ws = _mock_worksheet(col_values_return=["id", "id-1", "id-2", "id-1", "id-3"])
        gc = _mock_client({"Pomodoros": ws})

        result = sheets_storage.deduplicate_pomodoros(gc, "test-id")

        assert result["removed"] == 1
        assert result["total"] == 3
        ws.delete_rows.assert_called_once_with(4)
