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
