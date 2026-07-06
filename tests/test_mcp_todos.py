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
