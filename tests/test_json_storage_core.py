"""Tests for json_storage_core.py — transport-agnostic CRUD, serialization, filtering.

This is core infrastructure. Tests cover every function, edge case, and
data corruption scenario.
"""

import json

import json_storage_core as core


class TestParsePomodoros:
    def test_none_returns_empty(self):
        assert core.parse_pomodoros(None) == []

    def test_empty_string_returns_empty(self):
        assert core.parse_pomodoros("") == []

    def test_invalid_json_returns_empty(self):
        assert core.parse_pomodoros("{broken json}") == []

    def test_non_string_non_dict_returns_empty(self):
        assert core.parse_pomodoros(42) == []

    def test_list_json_string(self):
        data = json.dumps([{"id": "1"}, {"id": "2"}])
        result = core.parse_pomodoros(data)
        assert len(result) == 2
        assert result[0]["id"] == "1"

    def test_dict_with_pomodoros_key(self):
        data = json.dumps({"pomodoros": [{"id": "1"}]})
        result = core.parse_pomodoros(data)
        assert len(result) == 1

    def test_dict_without_pomodoros_key(self):
        data = json.dumps({"other": "stuff"})
        result = core.parse_pomodoros(data)
        assert result == []

    def test_accepts_dict_directly(self):
        result = core.parse_pomodoros({"pomodoros": [{"id": "1"}]})
        assert len(result) == 1

    def test_accepts_list_directly(self):
        result = core.parse_pomodoros([{"id": "1"}, {"id": "2"}])
        assert len(result) == 2

    def test_empty_list(self):
        assert core.parse_pomodoros("[]") == []

    def test_empty_pomodoros_key(self):
        assert core.parse_pomodoros('{"pomodoros": []}') == []


class TestSerializePomodoros:
    def test_empty_list(self):
        result = core.serialize_pomodoros([])
        parsed = json.loads(result)
        assert parsed == {"pomodoros": []}

    def test_roundtrip(self):
        original = [{"id": "1", "name": "Test"}]
        serialized = core.serialize_pomodoros(original)
        parsed = core.parse_pomodoros(serialized)
        assert parsed == original

    def test_preserves_all_fields(self):
        pomo = {
            "id": "abc",
            "name": "Work",
            "type": "Content",
            "start_time": "2026-01-15T10:00:00Z",
            "end_time": "2026-01-15T10:25:00Z",
            "duration_minutes": 25,
            "notes": "Some notes",
        }
        serialized = core.serialize_pomodoros([pomo])
        parsed = core.parse_pomodoros(serialized)
        assert parsed[0] == pomo


class TestSettingsSerialization:
    def test_parse_none(self):
        assert core.parse_settings(None) == {}

    def test_parse_empty(self):
        assert core.parse_settings("") == {}

    def test_parse_invalid_json(self):
        assert core.parse_settings("{bad}") == {}

    def test_parse_non_dict(self):
        assert core.parse_settings("[1, 2]") == {}

    def test_parse_valid(self):
        data = json.dumps({"key": "value", "num": 42})
        result = core.parse_settings(data)
        assert result == {"key": "value", "num": 42}

    def test_accepts_dict_directly(self):
        result = core.parse_settings({"key": "value"})
        assert result == {"key": "value"}

    def test_roundtrip(self):
        original = {"timer_preset_1": 5, "sound_enabled": True, "types": ["A", "B"]}
        serialized = core.serialize_settings(original)
        parsed = core.parse_settings(serialized)
        assert parsed == original


class TestAddPomodoro:
    def test_add_to_empty_list(self):
        result, was_new = core.add_pomodoro([], {"id": "1", "name": "Test"})
        assert was_new is True
        assert len(result) == 1
        assert result[0]["id"] == "1"

    def test_add_duplicate_is_skipped(self):
        existing = [{"id": "1", "name": "Original"}]
        result, was_new = core.add_pomodoro(existing, {"id": "1", "name": "Duplicate"})
        assert was_new is False
        assert len(result) == 1
        assert result[0]["name"] == "Original"

    def test_add_different_id(self):
        existing = [{"id": "1"}]
        result, was_new = core.add_pomodoro(existing, {"id": "2"})
        assert was_new is True
        assert len(result) == 2

    def test_mutates_input_list(self):
        original = [{"id": "1"}]
        result, _ = core.add_pomodoro(original, {"id": "2"})
        assert result is original


class TestAddPomodorosBatch:
    def test_add_batch_to_empty(self):
        new = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
        result, added = core.add_pomodoros_batch([], new)
        assert added == 3
        assert len(result) == 3

    def test_batch_skips_duplicates(self):
        existing = [{"id": "1"}, {"id": "2"}]
        new = [{"id": "2"}, {"id": "3"}, {"id": "1"}]
        result, added = core.add_pomodoros_batch(existing, new)
        assert added == 1
        assert len(result) == 3

    def test_batch_all_duplicates(self):
        existing = [{"id": "1"}, {"id": "2"}]
        new = [{"id": "1"}, {"id": "2"}]
        result, added = core.add_pomodoros_batch(existing, new)
        assert added == 0
        assert len(result) == 2

    def test_batch_empty_new(self):
        existing = [{"id": "1"}]
        result, added = core.add_pomodoros_batch(existing, [])
        assert added == 0
        assert len(result) == 1

    def test_batch_deduplicates_within_new(self):
        result, added = core.add_pomodoros_batch([], [{"id": "1"}, {"id": "1"}, {"id": "1"}])
        assert added == 1
        assert len(result) == 1


class TestUpdatePomodoro:
    def test_update_existing(self):
        pomodoros = [{"id": "1", "name": "Old", "type": "Content"}]
        result, found = core.update_pomodoro(pomodoros, "1", {"name": "New"})
        assert found is True
        assert result[0]["name"] == "New"
        assert result[0]["type"] == "Content"

    def test_update_nonexistent(self):
        pomodoros = [{"id": "1", "name": "Test"}]
        result, found = core.update_pomodoro(pomodoros, "999", {"name": "New"})
        assert found is False
        assert result[0]["name"] == "Test"

    def test_update_multiple_fields(self):
        pomodoros = [{"id": "1", "name": "Old", "type": "A", "notes": "old note"}]
        result, found = core.update_pomodoro(pomodoros, "1", {"name": "New", "type": "B", "notes": "new note"})
        assert found is True
        assert result[0]["name"] == "New"
        assert result[0]["type"] == "B"
        assert result[0]["notes"] == "new note"

    def test_update_empty_list(self):
        result, found = core.update_pomodoro([], "1", {"name": "New"})
        assert found is False
        assert result == []


class TestDeletePomodoro:
    def test_delete_existing(self):
        pomodoros = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
        result, found = core.delete_pomodoro(pomodoros, "2")
        assert found is True
        assert len(result) == 2
        assert all(p["id"] != "2" for p in result)

    def test_delete_nonexistent(self):
        pomodoros = [{"id": "1"}]
        result, found = core.delete_pomodoro(pomodoros, "999")
        assert found is False
        assert len(result) == 1

    def test_delete_from_empty(self):
        result, found = core.delete_pomodoro([], "1")
        assert found is False
        assert result == []

    def test_delete_only_item(self):
        result, found = core.delete_pomodoro([{"id": "1"}], "1")
        assert found is True
        assert result == []

    def test_delete_returns_new_list(self):
        original = [{"id": "1"}, {"id": "2"}]
        result, _ = core.delete_pomodoro(original, "1")
        assert result is not original


class TestFilterByDate:
    def _make_pomodoros(self):
        return [
            {"id": "1", "start_time": "2026-01-10T10:00:00Z"},
            {"id": "2", "start_time": "2026-01-15T10:00:00Z"},
            {"id": "3", "start_time": "2026-01-20T10:00:00Z"},
            {"id": "4", "start_time": "2026-01-25T10:00:00Z"},
        ]

    def test_no_filter(self):
        result = core.filter_by_date(self._make_pomodoros())
        assert len(result) == 4

    def test_start_date_only(self):
        result = core.filter_by_date(self._make_pomodoros(), start_date="2026-01-15")
        assert len(result) == 3
        assert all(p["start_time"] >= "2026-01-15" for p in result)

    def test_end_date_only(self):
        result = core.filter_by_date(self._make_pomodoros(), end_date="2026-01-20T23:59:59Z")
        assert len(result) == 3

    def test_both_dates(self):
        result = core.filter_by_date(self._make_pomodoros(), start_date="2026-01-14", end_date="2026-01-21")
        assert len(result) == 2

    def test_sorted_descending(self):
        result = core.filter_by_date(self._make_pomodoros())
        times = [p["start_time"] for p in result]
        assert times == sorted(times, reverse=True)

    def test_empty_list(self):
        assert core.filter_by_date([], start_date="2026-01-01") == []

    def test_no_matches(self):
        result = core.filter_by_date(self._make_pomodoros(), start_date="2027-01-01")
        assert result == []

    def test_missing_start_time_field(self):
        pomodoros = [{"id": "1"}, {"id": "2", "start_time": "2026-01-15T10:00:00Z"}]
        result = core.filter_by_date(pomodoros, start_date="2026-01-10")
        assert len(result) == 1


class TestDeduplicate:
    def test_no_duplicates(self):
        pomodoros = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
        result, removed = core.deduplicate(pomodoros)
        assert removed == 0
        assert len(result) == 3

    def test_removes_duplicates(self):
        pomodoros = [{"id": "1"}, {"id": "2"}, {"id": "1"}, {"id": "3"}, {"id": "2"}]
        result, removed = core.deduplicate(pomodoros)
        assert removed == 2
        assert len(result) == 3

    def test_keeps_first_occurrence(self):
        pomodoros = [
            {"id": "1", "name": "First"},
            {"id": "1", "name": "Second"},
        ]
        result, removed = core.deduplicate(pomodoros)
        assert removed == 1
        assert result[0]["name"] == "First"

    def test_empty_list(self):
        result, removed = core.deduplicate([])
        assert removed == 0
        assert result == []

    def test_single_item(self):
        result, removed = core.deduplicate([{"id": "1"}])
        assert removed == 0
        assert len(result) == 1

    def test_all_duplicates(self):
        pomodoros = [{"id": "1"}, {"id": "1"}, {"id": "1"}]
        result, removed = core.deduplicate(pomodoros)
        assert removed == 2
        assert len(result) == 1


class TestMergeSettings:
    def test_replace_all(self):
        existing = {"a": 1, "b": 2, "c": 3}
        updates = {"x": 10, "y": 20}
        result = core.merge_settings(existing, updates, replace_all=True)
        assert result == {"x": 10, "y": 20}

    def test_incremental_update(self):
        existing = {"a": 1, "b": 2}
        updates = {"b": 99, "c": 3}
        result = core.merge_settings(existing, updates, replace_all=False)
        assert result == {"a": 1, "b": 99, "c": 3}

    def test_incremental_preserves_existing(self):
        existing = {"a": 1, "b": 2}
        result = core.merge_settings(existing, {}, replace_all=False)
        assert result == {"a": 1, "b": 2}

    def test_returns_new_dict(self):
        existing = {"a": 1}
        result = core.merge_settings(existing, {"b": 2})
        assert result is not existing


class TestFullRoundtrip:
    def test_lifecycle(self):
        pomodoros = []

        pomodoros, _ = core.add_pomodoro(
            pomodoros,
            {
                "id": "p1",
                "name": "Task 1",
                "type": "Content",
                "start_time": "2026-01-15T10:00:00Z",
                "end_time": "2026-01-15T10:25:00Z",
                "duration_minutes": 25,
                "notes": None,
            },
        )
        pomodoros, _ = core.add_pomodoro(
            pomodoros,
            {
                "id": "p2",
                "name": "Task 2",
                "type": "Product",
                "start_time": "2026-01-15T11:00:00Z",
                "end_time": "2026-01-15T11:25:00Z",
                "duration_minutes": 25,
                "notes": "Important",
            },
        )

        serialized = core.serialize_pomodoros(pomodoros)
        restored = core.parse_pomodoros(serialized)
        assert len(restored) == 2

        restored, found = core.update_pomodoro(restored, "p1", {"name": "Updated Task"})
        assert found is True
        assert restored[0]["name"] == "Updated Task"

        restored, found = core.delete_pomodoro(restored, "p2")
        assert found is True
        assert len(restored) == 1

        final = core.serialize_pomodoros(restored)
        final_parsed = core.parse_pomodoros(final)
        assert len(final_parsed) == 1
        assert final_parsed[0]["name"] == "Updated Task"

    def test_large_batch(self):
        pomodoros = [
            {"id": str(i), "name": f"Task {i}", "start_time": f"2026-01-{15 + (i % 15):02d}T10:00:00Z"}
            for i in range(1000)
        ]
        serialized = core.serialize_pomodoros(pomodoros)
        restored = core.parse_pomodoros(serialized)
        assert len(restored) == 1000

        filtered = core.filter_by_date(restored, start_date="2026-01-20", end_date="2026-01-25")
        assert all("2026-01-20" <= p["start_time"] <= "2026-01-25" for p in filtered)

        deduped, removed = core.deduplicate(restored)
        assert removed == 0
        assert len(deduped) == 1000
