"""Acquacotta Checklists Plugin — recurring daily/weekly/monthly/quarterly checklists.

Templates and run history live in ``plugins/checklists/data.json`` in the user's own
storage, as ``{"templates": [...], "runs": [...]}``.

Whether a checklist is *due* is never stored. There is no server-side scheduler to
flip a flag, so ``due_status`` derives it at read time from the template's schedule
and the completed runs: a template is due when no run of it was completed within the
current period (day, ISO week starting Monday, calendar month or calendar quarter).
The four schedules are explicit cases, not a general recurrence-rule engine.
"""

import json
from datetime import date, datetime, timezone

import plugin_common
from transports.google_drive_transport import GoogleDriveTransport

PLUGIN_METADATA = {
    "id": "checklists",
    "name": "Checklists",
    "description": "Recurring daily, weekly, monthly and quarterly checklists with run history",
    "version": "1.0.0",
    "type": "extension",
    "author": "Crunchtools",
    "has_tab": False,
}

CHECKLISTS_FILE = "data.json"
PLUGIN_FOLDER = "plugins/checklists"

SCHEDULES = ("daily", "weekly", "monthly", "quarterly")
_MAX_STR = 200
_MAX_ITEMS = 200
_MAX_RECORDS = 10000


def _empty_doc():
    return {"templates": [], "runs": []}


def period_start(schedule, today):
    """First day of the period containing ``today`` for one of the four schedules."""
    if schedule == "daily":
        return today
    if schedule == "weekly":
        return date.fromordinal(today.toordinal() - today.weekday())
    if schedule == "monthly":
        return today.replace(day=1)
    if schedule == "quarterly":
        return today.replace(month=3 * ((today.month - 1) // 3) + 1, day=1)
    raise ValueError(f"schedule must be one of {SCHEDULES}")


def _parse_date(value):
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def due_status(doc, today=None):
    """Return one entry per template: ``{template, due, last_completed}``.

    ``due`` is True when no run of the template with a ``completed_at`` falls on or
    after the start of the current period. Computed from the data on every call.
    """
    today = today or datetime.now(timezone.utc).date()
    statuses = []
    for template in doc.get("templates", []):
        start = period_start(template["schedule"], today)
        completed = [
            _parse_date(run.get("date"))
            for run in doc.get("runs", [])
            if run.get("template_id") == template["id"] and run.get("completed_at")
        ]
        completed = [d for d in completed if d is not None]
        last = max(completed, default=None)
        statuses.append(
            {
                "template": template,
                "due": last is None or last < start,
                "last_completed": last.isoformat() if last else None,
            }
        )
    return statuses


def _clean_str(value, name, required=True):
    if not isinstance(value, str) or len(value) > _MAX_STR or (required and not value.strip()):
        raise ValueError(f"{name} must be a non-empty string up to {_MAX_STR} characters")
    return value


def _clean_run_item(item):
    if not isinstance(item, dict):
        raise ValueError("each run item must be an object")
    return {"label": _clean_str(item.get("label"), "label"), "checked": bool(item.get("checked"))}


def _clean_template_item(item, position):
    if not isinstance(item, dict):
        raise ValueError("each item must be an object")
    order = item.get("order", position)
    if isinstance(order, bool) or not isinstance(order, int):
        raise ValueError("item order must be an integer")
    return {"label": _clean_str(item.get("label"), "label"), "order": order}


def _clean_template(template):
    if not isinstance(template, dict):
        raise ValueError("each template must be an object")
    if template.get("schedule") not in SCHEDULES:
        raise ValueError(f"schedule must be one of {SCHEDULES}")
    items = template.get("items", [])
    if not isinstance(items, list) or len(items) > _MAX_ITEMS:
        raise ValueError("items must be a list")
    return {
        "id": _clean_str(template.get("id"), "id"),
        "name": _clean_str(template.get("name"), "name"),
        "schedule": template["schedule"],
        "items": [_clean_template_item(item, n) for n, item in enumerate(items, start=1)],
    }


def _clean_run(run):
    if not isinstance(run, dict) or _parse_date(run.get("date")) is None:
        raise ValueError("each run needs an ISO date")
    items = run.get("items", [])
    if not isinstance(items, list) or len(items) > _MAX_ITEMS:
        raise ValueError("run items must be a list")
    return {
        "template_id": _clean_str(run.get("template_id"), "template_id"),
        "date": run["date"][:10],
        "started_at": run.get("started_at"),
        "completed_at": run.get("completed_at"),
        "items": [_clean_run_item(i) for i in items],
    }


def validate_sync_payload(payload):
    """Validate a full-replace document and return a clean copy; raises ValueError."""
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    templates, runs = payload.get("templates", []), payload.get("runs", [])
    if not isinstance(templates, list) or not isinstance(runs, list):
        raise ValueError("templates and runs must be lists")
    if len(templates) > _MAX_RECORDS or len(runs) > _MAX_RECORDS:
        raise ValueError("too many records")
    return {
        "templates": [_clean_template(t) for t in templates],
        "runs": [_clean_run(r) for r in runs],
    }


def _transport(drive_service, folder_id):
    plugin_folder_id = plugin_common.ensure_plugin_folder(drive_service, folder_id, "checklists")
    return GoogleDriveTransport(drive_service, plugin_folder_id)


def read_checklists(drive_service, folder_id):
    """Read the document; a missing, malformed or invalid file reads as empty."""
    try:
        stored = json.loads(_transport(drive_service, folder_id).download_file(CHECKLISTS_FILE) or "")
        return validate_sync_payload(stored)
    except (json.JSONDecodeError, TypeError, ValueError):
        return _empty_doc()


def write_checklists(drive_service, folder_id, doc):
    """Persist the document (full replace)."""
    content = json.dumps(doc, indent=2, ensure_ascii=False)
    _transport(drive_service, folder_id).upload_file(CHECKLISTS_FILE, content)
