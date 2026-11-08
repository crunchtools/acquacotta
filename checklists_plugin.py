"""Acquacotta Checklists Plugin — recurring daily/weekly/monthly/quarterly checklists.

Templates and run history live in ``plugins/checklists/data.json`` in the user's own
storage, as ``{"templates": [...], "runs": [...]}``.

Whether a checklist is *due* is never stored. There is no server-side scheduler to
flip a flag, so ``due_status`` derives it at read time from the template's schedule,
its mode and its last completed run. The four schedules (day, ISO week starting
Monday, calendar month, calendar quarter) are explicit cases, not a general
recurrence-rule engine.

A template's ``mode`` picks the rule. ``fixed`` (the default): due when no run was
completed within the current period. ``after_completion``: due once a whole period
has passed since the last completed run (``next_due``), so a late run pushes the next
one back instead of piling up.
"""

import calendar
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone

import plugin_common

PLUGIN_ID = "checklists"

PLUGIN_METADATA = {
    "id": PLUGIN_ID,
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
MODES = ("fixed", "after_completion")
_DAYS_PER_WEEK = 7
_MONTHS_PER_YEAR = 12
_MONTHS_PER_PERIOD = {"monthly": 1, "quarterly": 3}
_ID_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_MAX_STR = 200
_MAX_ITEMS = 200
_MAX_RECORDS = 10000

logger = logging.getLogger(__name__)


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


def _add_months(day, months):
    """``day`` moved forward ``months`` calendar months, clamped to the month's last day."""
    year, month_index = divmod(day.month - 1 + months, _MONTHS_PER_YEAR)
    year, month = day.year + year, month_index + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def next_due(schedule, completed):
    """For ``after_completion``: the first day a run completed on ``completed`` is stale."""
    if schedule == "daily":
        return completed + timedelta(days=1)
    if schedule == "weekly":
        return completed + timedelta(days=_DAYS_PER_WEEK)
    if schedule in _MONTHS_PER_PERIOD:
        return _add_months(completed, _MONTHS_PER_PERIOD[schedule])
    raise ValueError(f"schedule must be one of {SCHEDULES}")


def _parse_date(value):
    """An exact ``YYYY-MM-DD`` string naming a real date, else None."""
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_timestamp(value):
    """An ISO 8601 timestamp; a trailing "Z" is mapped to +00:00 for Python before 3.11."""
    if not isinstance(value, str) or len(value) > _MAX_STR:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def due_status(doc, today=None):
    """Return one entry per template: ``{template, due, last_completed}``.

    In ``fixed`` mode ``due`` is True when no completed run of the template falls on
    or after the start of the current period. In ``after_completion`` mode it is True
    once ``next_due`` of the last completed run has arrived. Computed on every call.
    """
    today = today or datetime.now(timezone.utc).date()
    last_by_template = {}
    for run in doc.get("runs", []):
        day = _parse_date(run.get("date")) if run.get("completed_at") else None
        template_id = run.get("template_id")
        if day is not None and (template_id not in last_by_template or day > last_by_template[template_id]):
            last_by_template[template_id] = day
    statuses = []
    for template in doc.get("templates", []):
        start = period_start(template["schedule"], today)
        last = last_by_template.get(template["id"])
        if last is None:
            due = True
        elif template.get("mode") == "after_completion":
            due = today >= next_due(template["schedule"], last)
        else:
            due = last < start
        statuses.append(
            {
                "template": template,
                "due": due,
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
    mode = template.get("mode", "fixed")
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    template_id = template.get("id")
    if not isinstance(template_id, str) or not _ID_RE.fullmatch(template_id):
        raise ValueError("id must be a short lowercase slug")
    items = template.get("items", [])
    if not isinstance(items, list) or len(items) > _MAX_ITEMS:
        raise ValueError("items must be a list")
    return {
        "id": template_id,
        "name": _clean_str(template.get("name"), "name"),
        "schedule": template["schedule"],
        "mode": mode,
        "items": [_clean_template_item(item, n) for n, item in enumerate(items, start=1)],
    }


def _clean_timestamp(run, name):
    value = run.get(name)
    if value is None:
        return None
    if _parse_timestamp(value) is None:
        raise ValueError(f"{name} must be an ISO 8601 timestamp or null")
    return value


def _clean_run(run):
    if not isinstance(run, dict) or _parse_date(run.get("date")) is None:
        raise ValueError("each run needs a YYYY-MM-DD date")
    items = run.get("items", [])
    if not isinstance(items, list) or len(items) > _MAX_ITEMS:
        raise ValueError("run items must be a list")
    return {
        "template_id": _clean_str(run.get("template_id"), "template_id"),
        "date": run["date"],
        "started_at": _clean_timestamp(run, "started_at"),
        "completed_at": _clean_timestamp(run, "completed_at"),
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


def _keep_valid(records, clean, kind):
    kept, dropped = [], 0
    for record in records if isinstance(records, list) else []:
        try:
            kept.append(clean(record))
        except ValueError:
            dropped += 1
    if dropped:
        logger.warning("Dropped %d invalid stored checklist %s record(s)", dropped, kind)
    return kept


def read_checklists(drive_service, folder_id):
    """Read the document. A missing or unparseable file reads as empty; an invalid
    record is dropped on its own, so one bad entry cannot blank the rest."""
    stored = plugin_common.read_json_object(
        plugin_common.config_transport(drive_service, folder_id, PLUGIN_ID), CHECKLISTS_FILE
    )
    if stored is None:
        return _empty_doc()
    return {
        "templates": _keep_valid(stored.get("templates"), _clean_template, "template"),
        "runs": _keep_valid(stored.get("runs"), _clean_run, "run"),
    }


def write_checklists(drive_service, folder_id, doc):
    """Persist the document (full replace)."""
    content = json.dumps(doc, indent=2, ensure_ascii=False)
    plugin_common.config_transport(drive_service, folder_id, PLUGIN_ID).upload_file(CHECKLISTS_FILE, content)
