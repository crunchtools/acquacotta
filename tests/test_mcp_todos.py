"""Tests for todos_plugin agent-facing CRUD helpers (used by the MCP todos tools).

read_todos/write_todos are patched to an in-memory document so we exercise the
mutation logic without touching Google Drive.
"""

import copy

import pytest

import todos_plugin


@pytest.fixture
def store(monkeypatch):
    """In-memory todos document standing in for Drive read/write.

    read returns a fresh copy each call (like parsing JSON off Drive) so writes
    replace, rather than alias, the stored document.
    """
    doc = {"todos": [], "lists": [{"id": "list-work", "name": "Work", "order": 0}]}

    def fake_read(_drive, _folder):
        return copy.deepcopy(doc)

    def fake_write(_drive, _folder, data):
        doc.clear()
        doc.update(copy.deepcopy(data))

    monkeypatch.setattr(todos_plugin, "read_todos", fake_read)
    monkeypatch.setattr(todos_plugin, "write_todos", fake_write)
    return doc


class TestAddTodo:
    def test_creates_with_defaults(self, store):
        todo = todos_plugin.add_todo(None, "folder", "Write spec")
        assert todo["title"] == "Write spec"
        assert todo["status"] == "pending"
        assert todo["priority"] == "none"
        assert todo["completed_at"] is None
        assert todo["id"]
        assert store["todos"] == [todo]

    def test_assigns_incrementing_sort_order(self, store):
        first = todos_plugin.add_todo(None, "folder", "One")
        second = todos_plugin.add_todo(None, "folder", "Two")
        assert second["sort_order"] > first["sort_order"]

    def test_rejects_blank_title(self, store):
        with pytest.raises(ValueError):
            todos_plugin.add_todo(None, "folder", "   ")

    def test_rejects_bad_priority(self, store):
        with pytest.raises(ValueError):
            todos_plugin.add_todo(None, "folder", "X", priority="urgent")

    def test_rejects_unknown_list(self, store):
        with pytest.raises(ValueError):
            todos_plugin.add_todo(None, "folder", "X", list_id="nope")

    def test_accepts_known_list(self, store):
        todo = todos_plugin.add_todo(None, "folder", "X", list_id="list-work")
        assert todo["list_id"] == "list-work"


class TestStatusAndUpdate:
    def test_complete_sets_status_and_timestamp(self, store):
        todo = todos_plugin.add_todo(None, "folder", "Finish")
        done = todos_plugin.set_todo_status(None, "folder", todo["id"], "completed")
        assert done["status"] == "completed"
        assert done["completed_at"] is not None

    def test_complete_unknown_returns_none(self, store):
        assert todos_plugin.set_todo_status(None, "folder", "missing", "completed") is None

    def test_reopen_clears_timestamp(self, store):
        todo = todos_plugin.add_todo(None, "folder", "Finish")
        todos_plugin.set_todo_status(None, "folder", todo["id"], "completed")
        reopened = todos_plugin.set_todo_status(None, "folder", todo["id"], "pending")
        assert reopened["status"] == "pending"
        assert reopened["completed_at"] is None

    def test_modify_updates_only_provided_fields(self, store):
        todo = todos_plugin.add_todo(None, "folder", "Original", notes="keep")
        updated = todos_plugin.modify_todo(None, "folder", todo["id"], {"title": "Changed", "notes": None})
        assert updated["title"] == "Changed"
        assert updated["notes"] == "keep"

    def test_modify_unknown_returns_none(self, store):
        assert todos_plugin.modify_todo(None, "folder", "missing", {"title": "x"}) is None


class TestQueries:
    def test_filter_by_status(self, store):
        a = todos_plugin.add_todo(None, "folder", "A")
        todos_plugin.add_todo(None, "folder", "B")
        todos_plugin.set_todo_status(None, "folder", a["id"], "completed")
        pending = todos_plugin.query_todos(None, "folder", status="pending")
        assert [t["title"] for t in pending] == ["B"]

    def test_filter_by_list(self, store):
        todos_plugin.add_todo(None, "folder", "InList", list_id="list-work")
        todos_plugin.add_todo(None, "folder", "NoList")
        in_list = todos_plugin.query_todos(None, "folder", list_id="list-work")
        assert [t["title"] for t in in_list] == ["InList"]

    def test_query_lists_sorted(self, store):
        store["lists"].append({"id": "list-home", "name": "Home", "order": 1})
        names = [listing["name"] for listing in todos_plugin.query_lists(None, "folder")]
        assert names == ["Work", "Home"]

    def test_filter_by_priority(self, store):
        todos_plugin.add_todo(None, "folder", "Hot", priority="high")
        todos_plugin.add_todo(None, "folder", "Cold", priority="low")
        high = todos_plugin.query_todos(None, "folder", priority="high")
        assert [t["title"] for t in high] == ["Hot"]

    def test_filter_by_priority_rejects_bad_value(self, store):
        with pytest.raises(ValueError):
            todos_plugin.query_todos(None, "folder", priority="urgent")

    def test_text_search_matches_title_and_notes(self, store):
        todos_plugin.add_todo(None, "folder", "Buy milk")
        todos_plugin.add_todo(None, "folder", "Call bank", notes="about the MILK refund")
        todos_plugin.add_todo(None, "folder", "Unrelated")
        hits = {t["title"] for t in todos_plugin.query_todos(None, "folder", q="milk")}
        assert hits == {"Buy milk", "Call bank"}


class TestRemoveTodo:
    def test_removes_existing(self, store):
        todo = todos_plugin.add_todo(None, "folder", "Delete me")
        assert todos_plugin.remove_todo(None, "folder", todo["id"]) is True
        assert store["todos"] == []

    def test_missing_returns_false(self, store):
        assert todos_plugin.remove_todo(None, "folder", "nope") is False


class TestBulkComplete:
    def test_completes_known_reports_unknown(self, store):
        a = todos_plugin.add_todo(None, "folder", "A")
        b = todos_plugin.add_todo(None, "folder", "B")
        outcome = todos_plugin.complete_todos_bulk(None, "folder", [a["id"], b["id"], "ghost"])
        assert outcome["updated"] == [a["id"], b["id"]]
        assert outcome["not_found"] == ["ghost"]
        assert all(t["status"] == "completed" for t in store["todos"])

    def test_no_write_when_none_match(self, store, monkeypatch):
        writes = []
        monkeypatch.setattr(todos_plugin, "write_todos", lambda _d, _f, doc: writes.append(doc))
        outcome = todos_plugin.complete_todos_bulk(None, "folder", ["ghost"])
        assert outcome == {"updated": [], "not_found": ["ghost"]}
        assert writes == []


class TestReorderTodo:
    def test_sets_sort_order(self, store):
        todo = todos_plugin.add_todo(None, "folder", "Move me")
        moved = todos_plugin.set_todo_order(None, "folder", todo["id"], 99)
        assert moved["sort_order"] == 99
        assert store["todos"][0]["sort_order"] == 99

    def test_missing_returns_none(self, store):
        assert todos_plugin.set_todo_order(None, "folder", "nope", 1) is None

    def test_rejects_non_integer(self, store):
        todo = todos_plugin.add_todo(None, "folder", "X")
        with pytest.raises(ValueError):
            todos_plugin.set_todo_order(None, "folder", todo["id"], "first")


class TestListManagement:
    def test_add_list_appends_with_order(self, store):
        listing = todos_plugin.add_list(None, "folder", "Errands")
        assert listing["name"] == "Errands"
        assert listing["order"] == 1  # after the seeded "Work" list at order 0
        assert listing["id"]

    def test_add_list_rejects_blank(self, store):
        with pytest.raises(ValueError):
            todos_plugin.add_list(None, "folder", "  ")

    def test_rename_list(self, store):
        renamed = todos_plugin.rename_list(None, "folder", "list-work", "Job")
        assert renamed["name"] == "Job"

    def test_rename_missing_returns_none(self, store):
        assert todos_plugin.rename_list(None, "folder", "nope", "X") is None

    def test_delete_list_orphans_its_todos(self, store):
        todo = todos_plugin.add_todo(None, "folder", "In work list", list_id="list-work")
        assert todos_plugin.delete_list(None, "folder", "list-work") is True
        assert store["lists"] == []
        assert store["todos"][0]["id"] == todo["id"]
        assert store["todos"][0]["list_id"] is None

    def test_delete_missing_list_returns_false(self, store):
        assert todos_plugin.delete_list(None, "folder", "nope") is False
