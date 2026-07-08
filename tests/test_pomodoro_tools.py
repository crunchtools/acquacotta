"""Tests for pomodoro_tools time-summary and query aggregation."""

import pytest

import pomodoro_tools


@pytest.fixture
def pomodoros(monkeypatch):
    """Patch the storage read with a fixed set of pomodoros."""
    records = [
        {"id": "1", "type": "Product", "duration_minutes": 25, "start_time": "2026-07-01T09:00:00Z"},
        {"id": "2", "type": "Product", "duration_minutes": 25, "start_time": "2026-07-01T10:00:00Z"},
        {"id": "3", "type": "Content", "duration_minutes": 50, "start_time": "2026-07-02T09:00:00Z"},
        {"id": "4", "duration_minutes": 10, "start_time": "2026-07-02T11:00:00Z"},  # uncategorized
    ]

    def fake_get(_drive, _folder, start_date=None, end_date=None):
        return list(records)

    monkeypatch.setattr(pomodoro_tools.drive_storage, "get_pomodoros", fake_get)
    return records


class TestTimeSummary:
    def test_totals_across_categories(self, pomodoros):
        summary = pomodoro_tools.time_summary(None, "folder")
        assert summary["total_minutes"] == 110
        assert summary["total_count"] == 4
        assert summary["by_category"]["Product"] == {"minutes": 50, "count": 2}
        assert summary["by_category"]["Content"] == {"minutes": 50, "count": 1}
        assert summary["by_category"]["Uncategorized"] == {"minutes": 10, "count": 1}

    def test_category_filter(self, pomodoros):
        summary = pomodoro_tools.time_summary(None, "folder", category="Product")
        assert summary["total_minutes"] == 50
        assert summary["total_count"] == 2
        assert set(summary["by_category"]) == {"Product"}


class TestQueryPomodoros:
    def test_type_filter(self, pomodoros):
        result = pomodoro_tools.query_pomodoros(None, "folder", type="Content")
        assert [p["id"] for p in result] == ["3"]

    def test_no_filter_returns_all(self, pomodoros):
        result = pomodoro_tools.query_pomodoros(None, "folder")
        assert len(result) == 4


class TestRecordPomodoro:
    @pytest.fixture
    def saved(self, monkeypatch):
        """Capture whatever record_pomodoro persists."""
        captured = []
        monkeypatch.setattr(pomodoro_tools.drive_storage, "save_pomodoro", lambda _d, _f, p: captured.append(p))
        return captured

    def test_builds_record_and_derives_start(self, saved):
        record = pomodoro_tools.record_pomodoro(
            None, "folder", "Deep work", "Product", 30, end_time="2026-07-08T12:30:00Z"
        )
        assert saved == [record]
        assert record["name"] == "Deep work"
        assert record["type"] == "Product"
        assert record["duration_minutes"] == 30
        assert record["start_time"] == "2026-07-08T12:00:00Z"
        assert record["end_time"] == "2026-07-08T12:30:00Z"
        assert record["synced"] is False
        assert record["id"]

    def test_defaults_end_time_to_now(self, saved):
        record = pomodoro_tools.record_pomodoro(None, "folder", "X", "Product", 25)
        assert record["start_time"] < record["end_time"]

    def test_rejects_blank_name(self, saved):
        with pytest.raises(ValueError):
            pomodoro_tools.record_pomodoro(None, "folder", "  ", "Product", 25)

    def test_rejects_nonpositive_duration(self, saved):
        with pytest.raises(ValueError):
            pomodoro_tools.record_pomodoro(None, "folder", "X", "Product", 0)


class TestCompareTimeSummary:
    def test_delta_is_a_minus_b(self, monkeypatch):
        by_range = {
            "2026-07-01": [{"type": "Product", "duration_minutes": 60}],
            "2026-06-01": [{"type": "Product", "duration_minutes": 100}],
        }
        monkeypatch.setattr(
            pomodoro_tools.drive_storage, "get_pomodoros", lambda _d, _f, start, _end: list(by_range[start])
        )
        out = pomodoro_tools.compare_time_summary(
            None, "folder", "2026-07-01", "2026-07-31", "2026-06-01", "2026-06-30"
        )
        assert out["period_a"]["total_minutes"] == 60
        assert out["period_b"]["total_minutes"] == 100
        assert out["delta"]["total_minutes"] == -40
        assert out["delta"]["by_category"]["Product"] == -40
