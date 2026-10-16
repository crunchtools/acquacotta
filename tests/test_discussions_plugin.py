"""Tests for discussions_plugin agent-facing CRUD helpers (used by the MCP tools).

read_discussions/write_discussions are patched to an in-memory document so we exercise
the mutation logic without touching Google Drive.
"""

import copy

import pytest

import discussions_plugin


@pytest.fixture
def store(monkeypatch):
    """In-memory discussions document standing in for Drive read/write.

    read returns a fresh copy each call (like parsing JSON off Drive) so writes
    replace, rather than alias, the stored document.
    """
    doc = {"discussions": []}

    def fake_read(_drive, _folder):
        return copy.deepcopy(doc)

    def fake_write(_drive, _folder, data):
        doc.clear()
        doc.update(copy.deepcopy(data))

    monkeypatch.setattr(discussions_plugin, "read_discussions", fake_read)
    monkeypatch.setattr(discussions_plugin, "write_discussions", fake_write)
    return doc


class TestAddDiscussion:
    def test_creates_with_defaults(self, store):
        d = discussions_plugin.add_discussion(None, "folder", "Discuss SLAs")
        assert d["topic"] == "Discuss SLAs"
        assert d["person"] == ""
        assert d["status"] == "open"
        assert d["priority"] == "none"
        assert d["outcome"] == ""
        assert d["talking_points"] == []
        assert d["discussed_at"] is None
        assert d["id"]
        assert store["discussions"] == [d]

    def test_captures_person_and_talking_points(self, store):
        d = discussions_plugin.add_discussion(
            None,
            "folder",
            "SLA commitments",
            person="Raj",
            context="background",
            talking_points=["explain guidance", "discuss sweet spot"],
            priority="high",
            source="https://slack/thread",
        )
        assert d["person"] == "Raj"
        assert d["context"] == "background"
        assert d["talking_points"] == ["explain guidance", "discuss sweet spot"]
        assert d["priority"] == "high"
        assert d["source"] == "https://slack/thread"

    def test_talking_points_accepts_newline_string(self, store):
        d = discussions_plugin.add_discussion(None, "folder", "X", talking_points="one\n\n  two  \nthree")
        assert d["talking_points"] == ["one", "two", "three"]

    def test_assigns_incrementing_sort_order(self, store):
        first = discussions_plugin.add_discussion(None, "folder", "One")
        second = discussions_plugin.add_discussion(None, "folder", "Two")
        assert second["sort_order"] > first["sort_order"]

    def test_rejects_blank_topic(self, store):
        with pytest.raises(ValueError):
            discussions_plugin.add_discussion(None, "folder", "   ")

    def test_rejects_bad_priority(self, store):
        with pytest.raises(ValueError):
            discussions_plugin.add_discussion(None, "folder", "X", priority="urgent")


class TestStatusAndOutcome:
    def test_mark_discussed_sets_status_timestamp_and_outcome(self, store):
        d = discussions_plugin.add_discussion(None, "folder", "Finish")
        done = discussions_plugin.set_discussion_status(None, "folder", d["id"], "discussed", outcome="agreed to ship")
        assert done["status"] == "discussed"
        assert done["discussed_at"] is not None
        assert done["outcome"] == "agreed to ship"

    def test_mark_discussed_without_outcome_leaves_it(self, store):
        d = discussions_plugin.add_discussion(None, "folder", "Finish")
        done = discussions_plugin.set_discussion_status(None, "folder", d["id"], "discussed")
        assert done["status"] == "discussed"
        assert done["outcome"] == ""

    def test_reopen_clears_timestamp_keeps_outcome(self, store):
        d = discussions_plugin.add_discussion(None, "folder", "Finish")
        discussions_plugin.set_discussion_status(None, "folder", d["id"], "discussed", outcome="done")
        reopened = discussions_plugin.set_discussion_status(None, "folder", d["id"], "open")
        assert reopened["status"] == "open"
        assert reopened["discussed_at"] is None
        assert reopened["outcome"] == "done"

    def test_status_unknown_returns_none(self, store):
        assert discussions_plugin.set_discussion_status(None, "folder", "nope", "discussed") is None

    def test_rejects_bad_status(self, store):
        d = discussions_plugin.add_discussion(None, "folder", "X")
        with pytest.raises(ValueError):
            discussions_plugin.set_discussion_status(None, "folder", d["id"], "closed")


class TestModify:
    def test_updates_only_provided_fields(self, store):
        d = discussions_plugin.add_discussion(None, "folder", "Topic", person="Raj")
        updated = discussions_plugin.modify_discussion(None, "folder", d["id"], {"person": "Stef"})
        assert updated["person"] == "Stef"
        assert updated["topic"] == "Topic"

    def test_normalizes_talking_points_on_update(self, store):
        d = discussions_plugin.add_discussion(None, "folder", "Topic")
        updated = discussions_plugin.modify_discussion(None, "folder", d["id"], {"talking_points": "a\nb"})
        assert updated["talking_points"] == ["a", "b"]

    def test_unknown_returns_none(self, store):
        assert discussions_plugin.modify_discussion(None, "folder", "nope", {"topic": "x"}) is None


class TestQueries:
    def test_filter_by_status(self, store):
        a = discussions_plugin.add_discussion(None, "folder", "A")
        discussions_plugin.add_discussion(None, "folder", "B")
        discussions_plugin.set_discussion_status(None, "folder", a["id"], "discussed")
        open_only = discussions_plugin.query_discussions(None, "folder", status="open")
        assert [d["topic"] for d in open_only] == ["B"]

    def test_filter_by_person_case_insensitive(self, store):
        discussions_plugin.add_discussion(None, "folder", "A", person="Raj")
        discussions_plugin.add_discussion(None, "folder", "B", person="Stef")
        results = discussions_plugin.query_discussions(None, "folder", person="raj")
        assert [d["topic"] for d in results] == ["A"]

    def test_filter_by_priority(self, store):
        discussions_plugin.add_discussion(None, "folder", "A", priority="high")
        discussions_plugin.add_discussion(None, "folder", "B", priority="low")
        results = discussions_plugin.query_discussions(None, "folder", priority="high")
        assert [d["topic"] for d in results] == ["A"]

    def test_filter_by_priority_rejects_bad_value(self, store):
        with pytest.raises(ValueError):
            discussions_plugin.query_discussions(None, "folder", priority="urgent")

    def test_text_search_tolerates_null_talking_points(self, store):
        # A record synced with talking_points=null must not crash the search.
        store["discussions"] = [{"id": "x", "topic": "ABI", "talking_points": None, "status": "open"}]
        results = discussions_plugin.query_discussions(None, "folder", q="abi")
        assert [d["id"] for d in results] == ["x"]

    def test_text_search_matches_topic_context_and_points(self, store):
        discussions_plugin.add_discussion(None, "folder", "ABI stability")
        discussions_plugin.add_discussion(None, "folder", "Other", context="mentions ABI here")
        discussions_plugin.add_discussion(None, "folder", "Third", talking_points=["raise ABI risk"])
        discussions_plugin.add_discussion(None, "folder", "Unrelated")
        results = discussions_plugin.query_discussions(None, "folder", q="abi")
        assert {d["topic"] for d in results} == {"ABI stability", "Other", "Third"}


class TestRemove:
    def test_removes_existing(self, store):
        d = discussions_plugin.add_discussion(None, "folder", "X")
        assert discussions_plugin.remove_discussion(None, "folder", d["id"]) is True
        assert store["discussions"] == []

    def test_missing_returns_false(self, store):
        assert discussions_plugin.remove_discussion(None, "folder", "nope") is False


class TestValidateSyncPayload:
    _UUID = "11111111-2222-3333-4444-555555555555"

    def test_accepts_valid_document(self):
        doc = {
            "discussions": [
                {"id": self._UUID, "topic": "X", "priority": "high", "status": "open", "talking_points": ["p"]}
            ]
        }
        assert discussions_plugin.validate_sync_payload(doc) == doc

    def test_defaults_missing_discussions_to_empty(self):
        assert discussions_plugin.validate_sync_payload({}) == {"discussions": []}

    def test_rejects_non_dict_payload(self):
        with pytest.raises(ValueError):
            discussions_plugin.validate_sync_payload([])

    def test_rejects_non_list_discussions(self):
        with pytest.raises(ValueError):
            discussions_plugin.validate_sync_payload({"discussions": {}})

    def test_rejects_record_without_id(self):
        with pytest.raises(ValueError):
            discussions_plugin.validate_sync_payload({"discussions": [{"topic": "X"}]})

    def test_rejects_non_uuid_id(self):
        with pytest.raises(ValueError):
            discussions_plugin.validate_sync_payload({"discussions": [{"id": "../../evil"}]})

    def test_rejects_bad_priority(self):
        with pytest.raises(ValueError):
            discussions_plugin.validate_sync_payload({"discussions": [{"id": self._UUID, "priority": "urgent"}]})

    def test_rejects_bad_status(self):
        with pytest.raises(ValueError):
            discussions_plugin.validate_sync_payload({"discussions": [{"id": self._UUID, "status": "closed"}]})

    def test_rejects_non_list_talking_points(self):
        with pytest.raises(ValueError):
            discussions_plugin.validate_sync_payload({"discussions": [{"id": self._UUID, "talking_points": "x"}]})

    def test_rejects_non_string_person(self):
        with pytest.raises(ValueError):
            discussions_plugin.validate_sync_payload({"discussions": [{"id": self._UUID, "person": 123}]})

    def test_rejects_non_string_topic(self):
        with pytest.raises(ValueError):
            discussions_plugin.validate_sync_payload({"discussions": [{"id": self._UUID, "topic": []}]})


class TestSafeRecords:
    _UUID = "11111111-2222-3333-4444-555555555555"

    def test_keeps_valid_records(self):
        recs = [{"id": self._UUID, "topic": "X"}]
        assert discussions_plugin._safe_records(recs) == recs

    def test_drops_non_uuid_id(self):
        recs = [{"id": "../evil", "topic": "X"}, {"id": self._UUID, "topic": "Y"}]
        kept = discussions_plugin._safe_records(recs)
        assert [r["id"] for r in kept] == [self._UUID]

    def test_drops_bad_enum_and_types(self):
        recs = [
            {"id": self._UUID, "priority": "urgent"},
            {"id": self._UUID, "status": "closed"},
            {"id": self._UUID, "talking_points": "x"},
        ]
        assert discussions_plugin._safe_records(recs) == []

    def test_non_list_returns_empty(self):
        assert discussions_plugin._safe_records({"not": "a list"}) == []


class TestReorder:
    def test_sets_sort_order(self, store):
        d = discussions_plugin.add_discussion(None, "folder", "X")
        moved = discussions_plugin.set_discussion_order(None, "folder", d["id"], 42)
        assert moved["sort_order"] == 42

    def test_missing_returns_none(self, store):
        assert discussions_plugin.set_discussion_order(None, "folder", "nope", 1) is None

    def test_rejects_non_integer(self, store):
        d = discussions_plugin.add_discussion(None, "folder", "X")
        with pytest.raises(ValueError):
            discussions_plugin.set_discussion_order(None, "folder", d["id"], "1")
