"""Acquacotta Todos Plugin — task management with custom lists and pomodoro linking."""

import json
import uuid
from datetime import datetime, timezone

from transports.google_drive_transport import GoogleDriveTransport

PLUGIN_METADATA = {
    "id": "todos",
    "name": "Todos",
    "description": "Task management with custom lists and pomodoro linking",
    "version": "1.0.0",
    "type": "extension",
    "author": "Crunchtools",
    "has_tab": True,
    "tab_label": "To-do",
    "tab_id": "todos",
    "has_timer_types": True,
    "has_counts": True,
    "has_sync": True,
    "has_import_export": True,
    "has_history_decorators": True,
}

TODOS_FILE = "data.json"
PLUGIN_FOLDER = "plugins/todos"

_EMPTY_DATA = {"todos": [], "lists": []}


def _transport(drive_service, folder_id):
    return GoogleDriveTransport(drive_service, folder_id)


def _ensure_plugin_folder(t, folder_id):
    """Ensure plugins/todos/ subfolder exists, return its folder ID."""
    service = t._service
    plugins_id = _find_or_create_folder(service, folder_id, "plugins")
    return _find_or_create_folder(service, plugins_id, "todos")


def _find_or_create_folder(service, parent_id, name):
    query = (
        f"name='{name}' and '{parent_id}' in parents "
        f"and mimeType='application/vnd.google-apps.folder' and trashed=false"
    )
    results = service.files().list(q=query, spaces="drive", fields="files(id)").execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]
    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = service.files().create(body=metadata, fields="id").execute()
    return folder["id"]


def read_todos(drive_service, folder_id):
    t = _transport(drive_service, folder_id)
    todos_folder_id = _ensure_plugin_folder(t, folder_id)
    todos_transport = GoogleDriveTransport(drive_service, todos_folder_id)
    content = todos_transport.download_file(TODOS_FILE)
    if content is None:
        return dict(_EMPTY_DATA)
    try:
        todos_data = json.loads(content)
        if not isinstance(todos_data, dict):
            return dict(_EMPTY_DATA)
        todos_data.setdefault("todos", [])
        todos_data.setdefault("lists", [])
        return todos_data
    except (json.JSONDecodeError, TypeError):
        return dict(_EMPTY_DATA)


def write_todos(drive_service, folder_id, todos_data):
    t = _transport(drive_service, folder_id)
    todos_folder_id = _ensure_plugin_folder(t, folder_id)
    todos_transport = GoogleDriveTransport(drive_service, todos_folder_id)
    content = json.dumps(todos_data, indent=2, ensure_ascii=False)
    todos_transport.upload_file(TODOS_FILE, content)


# =============================================================================
# Agent-facing CRUD helpers (used by the MCP tools below and reusable directly)
#
# These read the whole todos document, mutate it, and write it back — the same
# full-replace contract the web UI's /api/todos/sync uses. Todo and list record
# shapes mirror static/js/storage.js exactly so agent-created records are
# indistinguishable from UI-created ones.
# =============================================================================

_VALID_PRIORITIES = ("none", "low", "medium", "high")
_UNSORTED_LAST = 999999  # todos lacking a sort_order sort after those that have one


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def query_todos(drive_service, folder_id, status=None, list_id=None, priority=None, q=None):
    """Return todos, optionally filtered by status, list_id, priority, and a text query.

    `q` matches case-insensitively against title and notes.
    """
    if priority is not None and priority not in _VALID_PRIORITIES:
        raise ValueError(f"priority must be one of {_VALID_PRIORITIES}")
    todos_doc = read_todos(drive_service, folder_id)
    todos = todos_doc.get("todos", [])
    if status:
        todos = [t for t in todos if t.get("status") == status]
    if list_id is not None:
        todos = [t for t in todos if t.get("list_id") == list_id]
    if priority is not None:
        todos = [t for t in todos if t.get("priority") == priority]
    if q:
        needle = q.lower()
        todos = [
            t for t in todos if needle in (t.get("title") or "").lower() or needle in (t.get("notes") or "").lower()
        ]
    todos = sorted(todos, key=lambda t: (t.get("status") != "pending", t.get("sort_order", _UNSORTED_LAST)))
    return todos


def query_lists(drive_service, folder_id):
    """Return the user's custom todo lists ordered by their `order` field."""
    todos_doc = read_todos(drive_service, folder_id)
    return sorted(todos_doc.get("lists", []), key=lambda listing: listing.get("order", 0))


def add_todo(drive_service, folder_id, title, notes="", priority="none", due_date=None, list_id=None):
    """Create a todo and persist it. Returns the new todo record."""
    if not title or not title.strip():
        raise ValueError("title is required")
    if priority not in _VALID_PRIORITIES:
        raise ValueError(f"priority must be one of {_VALID_PRIORITIES}")
    todos_doc = read_todos(drive_service, folder_id)
    todos = todos_doc.setdefault("todos", [])
    if list_id is not None and list_id not in {listing.get("id") for listing in todos_doc.get("lists", [])}:
        raise ValueError(f"Unknown list_id: {list_id}")
    max_order = max((t.get("sort_order", 0) for t in todos), default=0)
    todo = {
        "id": str(uuid.uuid4()),
        "title": title.strip(),
        "notes": notes or "",
        "status": "pending",
        "priority": priority,
        "due_date": due_date,
        "list_id": list_id,
        "sort_order": max_order + 1,
        "created_at": _now_iso(),
        "completed_at": None,
    }
    todos.append(todo)
    write_todos(drive_service, folder_id, todos_doc)
    return todo


def set_todo_status(drive_service, folder_id, todo_id, status):
    """Mark a todo 'completed' or 'pending'. Returns the updated todo or None if not found."""
    if status not in ("pending", "completed"):
        raise ValueError("status must be 'pending' or 'completed'")
    todos_doc = read_todos(drive_service, folder_id)
    for todo in todos_doc.get("todos", []):
        if todo.get("id") == todo_id:
            todo["status"] = status
            todo["completed_at"] = _now_iso() if status == "completed" else None
            write_todos(drive_service, folder_id, todos_doc)
            return todo
    return None


def modify_todo(drive_service, folder_id, todo_id, fields):
    """Update allowed fields on a todo. Returns the updated todo or None if not found."""
    allowed = {"title", "notes", "priority", "due_date", "list_id"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if "priority" in updates and updates["priority"] not in _VALID_PRIORITIES:
        raise ValueError(f"priority must be one of {_VALID_PRIORITIES}")
    todos_doc = read_todos(drive_service, folder_id)
    known_lists = {listing.get("id") for listing in todos_doc.get("lists", [])}
    if "list_id" in updates and updates["list_id"] not in known_lists:
        raise ValueError(f"Unknown list_id: {updates['list_id']}")
    for todo in todos_doc.get("todos", []):
        if todo.get("id") == todo_id:
            todo.update(updates)
            write_todos(drive_service, folder_id, todos_doc)
            return todo
    return None


def remove_todo(drive_service, folder_id, todo_id):
    """Permanently remove a todo. Returns True if it existed, False otherwise."""
    todos_doc = read_todos(drive_service, folder_id)
    todos = todos_doc.get("todos", [])
    remaining = [t for t in todos if t.get("id") != todo_id]
    if len(remaining) == len(todos):
        return False
    todos_doc["todos"] = remaining
    write_todos(drive_service, folder_id, todos_doc)
    return True


def complete_todos_bulk(drive_service, folder_id, todo_ids, status="completed"):
    """Set status on many todos in one read-modify-write.

    Returns ``{"updated": [ids], "not_found": [ids]}``.
    """
    if status not in ("pending", "completed"):
        raise ValueError("status must be 'pending' or 'completed'")
    todos_doc = read_todos(drive_service, folder_id)
    by_id = {t.get("id"): t for t in todos_doc.get("todos", [])}
    updated, not_found = [], []
    stamp = _now_iso() if status == "completed" else None
    for todo_id in todo_ids:
        todo = by_id.get(todo_id)
        if todo is None:
            not_found.append(todo_id)
            continue
        todo["status"] = status
        todo["completed_at"] = stamp
        updated.append(todo_id)
    if updated:
        write_todos(drive_service, folder_id, todos_doc)
    return {"updated": updated, "not_found": not_found}


def set_todo_order(drive_service, folder_id, todo_id, sort_order):
    """Set a todo's sort_order (its position within its list). Returns the todo or None."""
    if not isinstance(sort_order, int):
        raise ValueError("sort_order must be an integer")
    todos_doc = read_todos(drive_service, folder_id)
    for todo in todos_doc.get("todos", []):
        if todo.get("id") == todo_id:
            todo["sort_order"] = sort_order
            write_todos(drive_service, folder_id, todos_doc)
            return todo
    return None


def add_list(drive_service, folder_id, name):
    """Create a custom todo list. Returns the new list record."""
    if not name or not name.strip():
        raise ValueError("name is required")
    todos_doc = read_todos(drive_service, folder_id)
    lists = todos_doc.setdefault("lists", [])
    listing = {"id": str(uuid.uuid4()), "name": name.strip(), "order": len(lists)}
    lists.append(listing)
    write_todos(drive_service, folder_id, todos_doc)
    return listing


def rename_list(drive_service, folder_id, list_id, name):
    """Rename a custom todo list. Returns the updated list or None if not found."""
    if not name or not name.strip():
        raise ValueError("name is required")
    todos_doc = read_todos(drive_service, folder_id)
    for listing in todos_doc.get("lists", []):
        if listing.get("id") == list_id:
            listing["name"] = name.strip()
            write_todos(drive_service, folder_id, todos_doc)
            return listing
    return None


def delete_list(drive_service, folder_id, list_id):
    """Delete a custom list, orphaning its todos (list_id → None). Returns True if it existed."""
    todos_doc = read_todos(drive_service, folder_id)
    lists = todos_doc.get("lists", [])
    remaining = [listing for listing in lists if listing.get("id") != list_id]
    if len(remaining) == len(lists):
        return False
    todos_doc["lists"] = remaining
    for todo in todos_doc.get("todos", []):
        if todo.get("list_id") == list_id:
            todo["list_id"] = None
    write_todos(drive_service, folder_id, todos_doc)
    return True


def register_mcp_tools(mcp, require_ctx):
    """Register todos MCP tools on a FastMCP instance.

    `require_ctx()` is supplied by the MCP server and returns the authenticated
    per-request context ``{"service", "folder_id", "email"}``.
    """
    from fastmcp.exceptions import ToolError

    @mcp.tool()
    def list_todos(
        status: str | None = None,
        list_id: str | None = None,
        priority: str | None = None,
        q: str | None = None,
    ) -> list:
        """List the user's todos.

        Args:
            status: Optional filter — 'pending' or 'completed'.
            list_id: Optional filter — only todos in this custom list.
            priority: Optional filter — 'none', 'low', 'medium', or 'high'.
            q: Optional text search — matches title and notes, case-insensitively.
        """
        ctx = require_ctx()
        try:
            return query_todos(ctx["service"], ctx["folder_id"], status=status, list_id=list_id, priority=priority, q=q)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool()
    def list_todo_lists() -> list:
        """List the user's custom todo lists (id + name), so you can target one when creating todos."""
        ctx = require_ctx()
        return query_lists(ctx["service"], ctx["folder_id"])

    @mcp.tool()
    def create_todo(
        title: str,
        notes: str = "",
        priority: str = "none",
        due_date: str | None = None,
        list_id: str | None = None,
    ) -> dict:
        """Create a new todo.

        Args:
            title: The todo text (required).
            notes: Optional longer description.
            priority: 'none', 'low', 'medium', or 'high'.
            due_date: Optional ISO date (YYYY-MM-DD) or datetime.
            list_id: Optional id of a custom list (see list_todo_lists).
        """
        ctx = require_ctx()
        try:
            return add_todo(ctx["service"], ctx["folder_id"], title, notes, priority, due_date, list_id)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool()
    def complete_todo(todo_id: str) -> dict:
        """Mark a todo as completed (resolved).

        Args:
            todo_id: The id of the todo to complete.
        """
        ctx = require_ctx()
        completed = set_todo_status(ctx["service"], ctx["folder_id"], todo_id, "completed")
        if completed is None:
            raise ToolError(f"No todo found with id {todo_id}")
        return completed

    @mcp.tool()
    def update_todo(
        todo_id: str,
        title: str | None = None,
        notes: str | None = None,
        priority: str | None = None,
        due_date: str | None = None,
        list_id: str | None = None,
    ) -> dict:
        """Update fields on an existing todo. Only provided fields change.

        Args:
            todo_id: The id of the todo to update.
            title: New title.
            notes: New notes.
            priority: 'none', 'low', 'medium', or 'high'.
            due_date: New ISO due date, or empty string to leave unchanged.
            list_id: Move the todo to this custom list.
        """
        ctx = require_ctx()
        fields = {"title": title, "notes": notes, "priority": priority, "due_date": due_date, "list_id": list_id}
        try:
            updated = modify_todo(ctx["service"], ctx["folder_id"], todo_id, fields)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        if updated is None:
            raise ToolError(f"No todo found with id {todo_id}")
        return updated

    @mcp.tool()
    def delete_todo(todo_id: str) -> dict:
        """Permanently delete a todo (distinct from complete_todo, which only resolves it).

        Args:
            todo_id: The id of the todo to delete.
        """
        ctx = require_ctx()
        if not remove_todo(ctx["service"], ctx["folder_id"], todo_id):
            raise ToolError(f"No todo found with id {todo_id}")
        return {"status": "ok", "deleted": todo_id}

    @mcp.tool()
    def complete_todos(todo_ids: list[str]) -> dict:
        """Mark several todos completed in a single operation.

        Args:
            todo_ids: The ids of the todos to complete.

        Returns which ids were updated and which weren't found.
        """
        ctx = require_ctx()
        return complete_todos_bulk(ctx["service"], ctx["folder_id"], todo_ids, "completed")

    @mcp.tool()
    def reorder_todo(todo_id: str, sort_order: int) -> dict:
        """Change a todo's sort position without touching its other fields.

        Args:
            todo_id: The id of the todo to move.
            sort_order: The new sort_order (lower sorts earlier).
        """
        ctx = require_ctx()
        try:
            moved = set_todo_order(ctx["service"], ctx["folder_id"], todo_id, sort_order)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        if moved is None:
            raise ToolError(f"No todo found with id {todo_id}")
        return moved

    @mcp.tool()
    def create_todo_list(name: str) -> dict:
        """Create a custom todo list.

        Args:
            name: The list name.
        """
        ctx = require_ctx()
        try:
            return add_list(ctx["service"], ctx["folder_id"], name)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool()
    def rename_todo_list(list_id: str, name: str) -> dict:
        """Rename a custom todo list.

        Args:
            list_id: The id of the list to rename.
            name: The new name.
        """
        ctx = require_ctx()
        try:
            renamed = rename_list(ctx["service"], ctx["folder_id"], list_id, name)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        if renamed is None:
            raise ToolError(f"No list found with id {list_id}")
        return renamed

    @mcp.tool()
    def delete_todo_list(list_id: str) -> dict:
        """Delete a custom todo list. Todos in it are kept but moved to no list.

        Args:
            list_id: The id of the list to delete.
        """
        ctx = require_ctx()
        if not delete_list(ctx["service"], ctx["folder_id"], list_id):
            raise ToolError(f"No list found with id {list_id}")
        return {"status": "ok", "deleted": list_id}
