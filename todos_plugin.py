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


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def query_todos(drive_service, folder_id, status=None, list_id=None):
    """Return todos, optionally filtered by status ('pending'/'completed') and list_id."""
    data = read_todos(drive_service, folder_id)
    todos = data.get("todos", [])
    if status:
        todos = [t for t in todos if t.get("status") == status]
    if list_id is not None:
        todos = [t for t in todos if t.get("list_id") == list_id]
    todos = sorted(todos, key=lambda t: (t.get("status") != "pending", t.get("sort_order", 999999)))
    return todos


def query_lists(drive_service, folder_id):
    """Return the user's custom todo lists ordered by their `order` field."""
    data = read_todos(drive_service, folder_id)
    return sorted(data.get("lists", []), key=lambda listing: listing.get("order", 0))


def add_todo(drive_service, folder_id, title, notes="", priority="none", due_date=None, list_id=None):  # noqa: PLR0913
    """Create a todo and persist it. Returns the new todo record."""
    if not title or not title.strip():
        raise ValueError("title is required")
    if priority not in _VALID_PRIORITIES:
        raise ValueError(f"priority must be one of {_VALID_PRIORITIES}")
    data = read_todos(drive_service, folder_id)
    todos = data.setdefault("todos", [])
    if list_id is not None and list_id not in {listing.get("id") for listing in data.get("lists", [])}:
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
    write_todos(drive_service, folder_id, data)
    return todo


def set_todo_status(drive_service, folder_id, todo_id, status):
    """Mark a todo 'completed' or 'pending'. Returns the updated todo or None if not found."""
    if status not in ("pending", "completed"):
        raise ValueError("status must be 'pending' or 'completed'")
    data = read_todos(drive_service, folder_id)
    for todo in data.get("todos", []):
        if todo.get("id") == todo_id:
            todo["status"] = status
            todo["completed_at"] = _now_iso() if status == "completed" else None
            write_todos(drive_service, folder_id, data)
            return todo
    return None


def modify_todo(drive_service, folder_id, todo_id, fields):
    """Update allowed fields on a todo. Returns the updated todo or None if not found."""
    allowed = {"title", "notes", "priority", "due_date", "list_id"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if "priority" in updates and updates["priority"] not in _VALID_PRIORITIES:
        raise ValueError(f"priority must be one of {_VALID_PRIORITIES}")
    data = read_todos(drive_service, folder_id)
    known_lists = {listing.get("id") for listing in data.get("lists", [])}
    if "list_id" in updates and updates["list_id"] not in known_lists:
        raise ValueError(f"Unknown list_id: {updates['list_id']}")
    for todo in data.get("todos", []):
        if todo.get("id") == todo_id:
            todo.update(updates)
            write_todos(drive_service, folder_id, data)
            return todo
    return None


def register_mcp_tools(mcp, require_ctx):
    """Register todos MCP tools on a FastMCP instance.

    `require_ctx()` is supplied by the MCP server and returns the authenticated
    per-request context ``{"service", "folder_id", "email"}``.
    """
    from fastmcp.exceptions import ToolError

    @mcp.tool()
    def list_todos(status: str | None = None, list_id: str | None = None) -> list:
        """List the user's todos.

        Args:
            status: Optional filter — 'pending' or 'completed'.
            list_id: Optional filter — only todos in this custom list.
        """
        ctx = require_ctx()
        return query_todos(ctx["service"], ctx["folder_id"], status=status, list_id=list_id)

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
        result = set_todo_status(ctx["service"], ctx["folder_id"], todo_id, "completed")
        if result is None:
            raise ToolError(f"No todo found with id {todo_id}")
        return result

    @mcp.tool()
    def update_todo(  # noqa: PLR0913
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
            result = modify_todo(ctx["service"], ctx["folder_id"], todo_id, fields)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        if result is None:
            raise ToolError(f"No todo found with id {todo_id}")
        return result
