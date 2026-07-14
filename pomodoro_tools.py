"""Acquacotta pomodoro MCP tools — read time-tracking data and link it to tickets.

These wrap the same JSON-on-Drive storage functions the web app uses, so agents
see exactly what the dashboard sees. Pomodoros are core Acquacotta data, so these
tools are always registered when the MCP server is running.
"""

import uuid
from datetime import datetime, timedelta, timezone

import json_google_drive_storage as drive_storage

# Pomodoro is a mandatory feature plugin: time tracking is core to Acquacotta, so it
# is always registered and enabled and cannot be disabled. Its MCP tools (below) are
# therefore always available to every authenticated caller.
PLUGIN_METADATA = {
    "id": "pomodoro",
    "name": "Pomodoro",
    "description": "Pomodoro time tracking — the core of Acquacotta",
    "version": "1.0.0",
    "type": "extension",
    "author": "Crunchtools",
    "mandatory": True,
}


def _iso_z(dt):
    """ISO 8601 with a trailing 'Z', matching the timestamps the web UI writes."""
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _pomodoro_type(pomodoro):
    """A pomodoro's category, tolerating either 'type' or 'category' field names."""
    return pomodoro.get("type") or pomodoro.get("category")


def query_pomodoros(drive_service, folder_id, start_date=None, end_date=None, type=None):
    """Return pomodoros in a date range, optionally filtered by type/category."""
    pomodoros = drive_storage.get_pomodoros(drive_service, folder_id, start_date, end_date)
    if type:
        pomodoros = [p for p in pomodoros if _pomodoro_type(p) == type]
    return pomodoros


def time_summary(drive_service, folder_id, start_date=None, end_date=None, category=None):
    """Aggregate minutes by category over a date range.

    Returns ``{"total_minutes", "total_count", "by_category": {cat: {minutes, count}}}``.
    If ``category`` is given, only that category is included.
    """
    pomodoros = drive_storage.get_pomodoros(drive_service, folder_id, start_date, end_date)
    by_category = {}
    total_minutes = 0
    total_count = 0
    for pomodoro in pomodoros:
        cat = _pomodoro_type(pomodoro) or "Uncategorized"
        if category and cat != category:
            continue
        minutes = pomodoro.get("duration_minutes")
        if minutes is None:
            minutes = pomodoro.get("duration", 0)
        try:
            minutes = int(minutes)
        except (TypeError, ValueError):
            minutes = 0
        bucket = by_category.setdefault(cat, {"minutes": 0, "count": 0})
        bucket["minutes"] += minutes
        bucket["count"] += 1
        total_minutes += minutes
        total_count += 1
    return {"total_minutes": total_minutes, "total_count": total_count, "by_category": by_category}


def record_pomodoro(
    drive_service, folder_id, name, type, duration_minutes, notes=None, end_time=None, linked_todo_id=None
):
    """Record a completed pomodoro after the fact (manual entry). Returns the new record.

    ``end_time`` defaults to now; ``start_time`` is derived as end_time minus the
    duration, mirroring the web UI's manual-entry form.
    """
    if not name or not name.strip():
        raise ValueError("name is required")
    try:
        duration_minutes = int(duration_minutes)
    except (TypeError, ValueError) as exc:
        raise ValueError("duration_minutes must be an integer") from exc
    if duration_minutes <= 0:
        raise ValueError("duration_minutes must be positive")
    if end_time:
        try:
            end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("end_time must be an ISO timestamp") from exc
    else:
        end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(minutes=duration_minutes)
    pomodoro = {
        "id": str(uuid.uuid4()),
        "name": name.strip(),
        "type": type,
        "start_time": _iso_z(start_dt),
        "end_time": _iso_z(end_dt),
        "duration_minutes": duration_minutes,
        "notes": notes,
        "linked_todo_id": linked_todo_id,
        "synced": False,
    }
    drive_storage.save_pomodoro(drive_service, folder_id, pomodoro)
    return pomodoro


def compare_time_summary(drive_service, folder_id, start_a, end_a, start_b, end_b, category=None):
    """Compare tracked time across two date ranges (e.g. this week vs last).

    Returns ``{"period_a", "period_b", "delta"}`` where each period is a
    ``time_summary`` result and ``delta`` holds the A-minus-B differences.
    """
    period_a = time_summary(drive_service, folder_id, start_a, end_a, category)
    period_b = time_summary(drive_service, folder_id, start_b, end_b, category)
    categories = set(period_a["by_category"]) | set(period_b["by_category"])
    by_category = {
        cat: period_a["by_category"].get(cat, {"minutes": 0})["minutes"]
        - period_b["by_category"].get(cat, {"minutes": 0})["minutes"]
        for cat in categories
    }
    delta = {
        "total_minutes": period_a["total_minutes"] - period_b["total_minutes"],
        "total_count": period_a["total_count"] - period_b["total_count"],
        "by_category": by_category,
    }
    return {"period_a": period_a, "period_b": period_b, "delta": delta}


def register_mcp_tools(mcp, require_ctx):
    """Register pomodoro MCP tools on a FastMCP instance."""
    from fastmcp.exceptions import ToolError

    @mcp.tool()
    def get_pomodoros(
        start_date: str | None = None,
        end_date: str | None = None,
        type: str | None = None,
    ) -> list:
        """Retrieve pomodoro time-tracking records.

        Args:
            start_date: Inclusive ISO start (YYYY-MM-DD or full timestamp).
            end_date: Inclusive ISO end.
            type: Optional category filter (e.g. 'Product', 'Content').
        """
        ctx = require_ctx()
        return query_pomodoros(ctx["service"], ctx["folder_id"], start_date, end_date, type)

    @mcp.tool()
    def get_time_summary(
        start_date: str | None = None,
        end_date: str | None = None,
        category: str | None = None,
    ) -> dict:
        """Summarize tracked time by category over a period.

        Args:
            start_date: Inclusive ISO start.
            end_date: Inclusive ISO end.
            category: Optional — restrict the summary to a single category.
        """
        ctx = require_ctx()
        return time_summary(ctx["service"], ctx["folder_id"], start_date, end_date, category)

    @mcp.tool()
    def tag_pomodoro_to_ticket(pomodoro_id: str, ticket_id: str) -> dict:
        """Link a pomodoro to an external ticket by writing a ticket_id on the record.

        Args:
            pomodoro_id: The id of the pomodoro to tag.
            ticket_id: The external ticket identifier (e.g. RHEL-1234).
        """
        ctx = require_ctx()
        found = drive_storage.update_pomodoro(ctx["service"], ctx["folder_id"], pomodoro_id, {"ticket_id": ticket_id})
        if not found:
            raise ToolError(f"No pomodoro found with id {pomodoro_id}")
        return {"status": "ok", "pomodoro_id": pomodoro_id, "ticket_id": ticket_id}

    @mcp.tool()
    def log_pomodoro(
        name: str,
        type: str,
        duration_minutes: int,
        notes: str | None = None,
        end_time: str | None = None,
        linked_todo_id: str | None = None,
    ) -> dict:
        """Log a completed time block manually (for work done away from the timer).

        Args:
            name: What the block was for.
            type: Category (e.g. 'Product', 'Content').
            duration_minutes: Length of the block in minutes.
            notes: Optional notes.
            end_time: Optional ISO timestamp the block ended (defaults to now); the
                start is derived from the duration.
            linked_todo_id: Optional todo id to associate the block with.
        """
        ctx = require_ctx()
        try:
            return record_pomodoro(
                ctx["service"], ctx["folder_id"], name, type, duration_minutes, notes, end_time, linked_todo_id
            )
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool()
    def get_time_comparison(
        start_a: str,
        end_a: str,
        start_b: str,
        end_b: str,
        category: str | None = None,
    ) -> dict:
        """Compare tracked time between two periods (e.g. this week vs last week).

        Args:
            start_a: Inclusive ISO start of period A (the primary period).
            end_a: Inclusive ISO end of period A.
            start_b: Inclusive ISO start of period B (the baseline).
            end_b: Inclusive ISO end of period B.
            category: Optional — restrict the comparison to a single category.

        Returns each period's summary plus an A-minus-B delta.
        """
        ctx = require_ctx()
        return compare_time_summary(ctx["service"], ctx["folder_id"], start_a, end_a, start_b, end_b, category)
