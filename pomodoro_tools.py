"""Acquacotta pomodoro MCP tools — read time-tracking data and link it to tickets.

These wrap the same JSON-on-Drive storage functions the web app uses, so agents
see exactly what the dashboard sees. Pomodoros are core Acquacotta data, so these
tools are always registered when the MCP server is running.
"""

import json_google_drive_storage as drive_storage


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
        found = drive_storage.update_pomodoro(
            ctx["service"], ctx["folder_id"], pomodoro_id, {"ticket_id": ticket_id}
        )
        if not found:
            raise ToolError(f"No pomodoro found with id {pomodoro_id}")
        return {"status": "ok", "pomodoro_id": pomodoro_id, "ticket_id": ticket_id}
