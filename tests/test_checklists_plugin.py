"""Tests for checklists_plugin: derived due status and payload validation."""

import json
from datetime import date

import pytest

import checklists_plugin


def _doc(schedule, run_date=None, completed=True, mode="fixed"):
    doc = {"templates": [{"id": "t", "name": "T", "schedule": schedule, "mode": mode, "items": []}], "runs": []}
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


class TestAfterCompletion:
    def test_weekly_waits_a_full_week(self):
        # Completed on a Sunday: fixed mode is due Monday, after_completion a week later.
        assert checklists_plugin.due_status(_doc("weekly", "2026-05-17"), date(2026, 5, 18))[0]["due"] is True
        assert checklists_plugin.due_status(_doc("weekly", "2026-05-17", mode="after_completion"), date(2026, 5, 18))[0]["due"] is False
        assert checklists_plugin.due_status(_doc("weekly", "2026-05-17", mode="after_completion"), date(2026, 5, 24))[0]["due"] is True

    def test_monthly_clamps_to_month_end(self):
        assert checklists_plugin.next_due("monthly", date(2026, 1, 31)) == date(2026, 2, 28)
        assert checklists_plugin.next_due("quarterly", date(2026, 11, 30)) == date(2027, 2, 28)
        assert checklists_plugin.next_due("daily", date(2026, 12, 31)) == date(2027, 1, 1)

    def test_unknown_mode_rejected(self):
        doc = {"templates": [{"id": "x", "name": "X", "schedule": "daily", "mode": "sometimes"}]}
        with pytest.raises(ValueError):
            checklists_plugin.validate_sync_payload(doc)


class TestStrictParsing:
    @pytest.mark.parametrize("value", ["2026-05-20", "2024-02-29"])
    def test_accepts_real_dates(self, value):
        assert checklists_plugin._parse_date(value) is not None

    @pytest.mark.parametrize("value", ["2026-05-20junk", "2026-02-30", "20260520", None, 20260520])
    def test_rejects_garbage(self, value):
        assert checklists_plugin._parse_date(value) is None

    @pytest.mark.parametrize("bad_id", ["Has Space", "UPPER", "../x", "a" * 65])
    def test_rejects_non_slug_ids(self, bad_id):
        with pytest.raises(ValueError):
            checklists_plugin.validate_sync_payload({"templates": [{"id": bad_id, "name": "X", "schedule": "daily"}]})

    def test_rejects_bad_timestamp(self):
        run = {"template_id": "x", "date": "2026-05-20", "completed_at": "yesterday"}
        with pytest.raises(ValueError):
            checklists_plugin.validate_sync_payload({"runs": [run]})


class _FakeTransport:
    def __init__(self, raw):
        self.raw = raw

    def download_file(self, _name):
        return self.raw


class TestReadChecklists:
    @pytest.mark.parametrize(
        ("raw", "template_ids"),
        [
            (None, []),
            ("", []),
            ("{not json", []),
            ("[]", []),
            (
                json.dumps(
                    {
                        "templates": [
                            {"id": "ok", "name": "OK", "schedule": "daily"},
                            {"id": "bad", "name": "Bad", "schedule": "hourly"},
                        ],
                        "runs": "nope",
                    }
                ),
                ["ok"],
            ),
        ],
    )
    def test_bad_input_degrades_per_record(self, monkeypatch, raw, template_ids):
        monkeypatch.setattr(checklists_plugin, "_transport", lambda *_: _FakeTransport(raw))
        doc = checklists_plugin.read_checklists(None, "folder")
        assert [t["id"] for t in doc["templates"]] == template_ids
        assert doc["runs"] == []
