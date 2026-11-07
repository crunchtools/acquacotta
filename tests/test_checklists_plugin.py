"""Tests for checklists_plugin: derived due status and payload validation."""

from datetime import date

import pytest

import checklists_plugin


def _doc(schedule, run_date=None, completed=True):
    doc = {"templates": [{"id": "t", "name": "T", "schedule": schedule, "items": []}], "runs": []}
    if run_date:
        doc["runs"].append(
            {"template_id": "t", "date": run_date, "completed_at": "2026-01-01T00:00:00Z" if completed else None}
        )
    return doc


class TestPeriodStart:
    def test_four_schedules(self):
        today = date(2026, 5, 20)  # a Wednesday
        assert checklists_plugin.period_start("daily", today) == date(2026, 5, 20)
        assert checklists_plugin.period_start("weekly", today) == date(2026, 5, 18)
        assert checklists_plugin.period_start("monthly", today) == date(2026, 5, 1)
        assert checklists_plugin.period_start("quarterly", today) == date(2026, 4, 1)

    def test_unknown_schedule(self):
        with pytest.raises(ValueError):
            checklists_plugin.period_start("hourly", date(2026, 5, 20))


class TestDueStatus:
    def test_due_when_never_run(self):
        status = checklists_plugin.due_status(_doc("daily"), date(2026, 5, 20))[0]
        assert status["due"] is True
        assert status["last_completed"] is None

    def test_not_due_after_completion_in_period(self):
        today = date(2026, 5, 20)
        assert checklists_plugin.due_status(_doc("weekly", "2026-05-18"), today)[0]["due"] is False
        assert checklists_plugin.due_status(_doc("quarterly", "2026-04-02"), today)[0]["due"] is False

    def test_due_again_in_next_period(self):
        today = date(2026, 5, 20)
        assert checklists_plugin.due_status(_doc("daily", "2026-05-19"), today)[0]["due"] is True
        assert checklists_plugin.due_status(_doc("weekly", "2026-05-17"), today)[0]["due"] is True
        assert checklists_plugin.due_status(_doc("monthly", "2026-04-30"), today)[0]["due"] is True

    def test_incomplete_run_does_not_count(self):
        today = date(2026, 5, 20)
        assert checklists_plugin.due_status(_doc("daily", "2026-05-20", completed=False), today)[0]["due"] is True


class TestValidate:
    def test_accepts_valid_document(self):
        doc = {
            "templates": [{"id": "m", "name": "Morning", "schedule": "daily", "items": [{"label": "Calendar"}]}],
            "runs": [{"template_id": "m", "date": "2026-05-20", "items": [{"label": "Calendar", "checked": 1}]}],
        }
        clean = checklists_plugin.validate_sync_payload(doc)
        assert clean["templates"][0]["items"] == [{"label": "Calendar", "order": 1}]
        assert clean["runs"][0]["items"] == [{"label": "Calendar", "checked": True}]

    @pytest.mark.parametrize(
        "bad",
        [
            [],
            {"templates": [{"id": "x", "name": "X", "schedule": "custom", "items": []}]},
            {"templates": [{"id": "", "name": "X", "schedule": "daily"}]},
            {"runs": [{"template_id": "x", "date": "nope"}]},
        ],
    )
    def test_rejects_invalid(self, bad):
        with pytest.raises(ValueError):
            checklists_plugin.validate_sync_payload(bad)
