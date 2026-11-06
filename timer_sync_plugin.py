"""Acquacotta Timer Sync Plugin — share the active timer across a user's clients.

The running timer is advertised in ``plugins/timer-sync/synchronization.json`` in
the user's own Drive. Each client keeps its own local ``setInterval`` timer, which
stays the source of truth for its UI; the file is advisory.

Guarantees (deliberately weak):

* Last writer wins. The storage layer has no compare-and-swap (no ETag/If-Match),
  so two clients that both read ``idle`` and both start a timer will both write,
  and the last write survives. The stale-owner rule below is the safety net:
  simultaneous starts converge on one timer within one poll cycle, and no client
  is left showing a timer the file says is idle.
* Remaining time is never stored. It is computed at read time from
  ``start_time`` + ``duration_minutes``. (There is no pause concept in the
  pomodoro model; if one is added it arrives as accumulated-pause seconds.)
* A running timer whose ``last_checkin`` is older than ``STALE_AFTER_SECONDS``
  is treated as idle, so any client may take over.
"""

import json
from datetime import datetime, timezone

import plugin_common
from transports.google_drive_transport import GoogleDriveTransport

PLUGIN_METADATA = {
    "id": "timer-sync",
    "name": "Timer Sync",
    "description": "Show the running timer on all your logged-in devices",
    "version": "1.0.0",
    "type": "extension",
    "author": "Crunchtools",
    "has_tab": False,
}

SYNC_FILE = "synchronization.json"
PLUGIN_FOLDER = "plugins/timer-sync"

SCHEMA_VERSION = 1
CHECKIN_INTERVAL_SECONDS = 60
# Three missed check-ins before takeover: one missed poll must not hand the timer over.
MISSED_CHECKINS_BEFORE_STALE = 3
STALE_AFTER_SECONDS = CHECKIN_INTERVAL_SECONDS * MISSED_CHECKINS_BEFORE_STALE

_STATES = ("running", "idle")
_TIMER_TYPES = ("focus", "short_break", "long_break")
_MAX_DURATION_MINUTES = 24 * 60
_MAX_STR = 200


def _idle_doc():
    return {"version": SCHEMA_VERSION, "timer": {"state": "idle"}}


def _parse_time(value):
    """Parse an ISO-8601 timestamp to an aware UTC datetime, or None."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(moment):
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _age_seconds(value, now):
    """Seconds elapsed from the ISO timestamp ``value`` to ``now``; infinite if unparseable."""
    moment = _parse_time(value)
    now = now or datetime.now(timezone.utc)
    return float("inf") if moment is None else (now - moment).total_seconds()


def remaining_seconds(timer, now=None):
    """Seconds left on a timer, derived from start_time and duration_minutes (never below 0)."""
    elapsed = _age_seconds(timer.get("start_time"), now)
    return int(max(0, timer["duration_minutes"] * 60 - elapsed))


def is_stale(timer, now=None):
    """True if a running timer's owner has not checked in within STALE_AFTER_SECONDS."""
    return _age_seconds(timer.get("last_checkin"), now) > STALE_AFTER_SECONDS


def validate_timer(payload):
    """Validate a client's timer state and return a clean copy; raises ValueError.

    ``state`` "idle" carries nothing else. A "running" timer needs a type, a
    duration, a start_time and the owning client id.
    """
    if not isinstance(payload, dict):
        raise ValueError("timer must be an object")
    state = payload.get("state")
    if state not in _STATES:
        raise ValueError(f"state must be one of {_STATES}")
    if state == "idle":
        return {"state": "idle"}
    timer_type = payload.get("type")
    if timer_type not in _TIMER_TYPES:
        raise ValueError(f"type must be one of {_TIMER_TYPES}")
    duration = payload.get("duration_minutes")
    valid_duration = isinstance(duration, (int, float)) and not isinstance(duration, bool)
    if not valid_duration or not 0 < duration <= _MAX_DURATION_MINUTES:
        raise ValueError("duration_minutes must be a positive number of minutes")
    start = _parse_time(payload.get("start_time"))
    if start is None:
        raise ValueError("start_time must be an ISO-8601 timestamp")
    owner = payload.get("owner_client_id")
    if not isinstance(owner, str) or not owner or len(owner) > _MAX_STR:
        raise ValueError("owner_client_id is required")
    clean = {
        "state": "running",
        "type": timer_type,
        "duration_minutes": duration,
        "start_time": _iso(start),
        "owner_client_id": owner,
        "linked_todo_id": None,
    }
    for key in ("name", "linked_todo_id"):
        value = payload.get(key)
        if value is not None and (not isinstance(value, str) or len(value) > _MAX_STR):
            raise ValueError(f"{key} must be a string")
        clean[key] = value
    return clean


def _transport(drive_service, folder_id):
    plugin_folder_id = plugin_common.ensure_plugin_folder(drive_service, folder_id, "timer-sync")
    return GoogleDriveTransport(drive_service, plugin_folder_id)


def read_sync(drive_service, folder_id, now=None):
    """Read the sync document, as seen by a client at ``now``.

    A running timer gains a computed ``remaining_seconds``. A stale owner, a
    finished timer or an unreadable file all read as idle.
    """
    now = now or datetime.now(timezone.utc)
    content = _transport(drive_service, folder_id).download_file(SYNC_FILE)
    if content is None:
        return _idle_doc()
    try:
        doc = json.loads(content)
        timer = validate_timer(doc["timer"])
        last_checkin = _parse_time(doc["timer"].get("last_checkin"))
    except (json.JSONDecodeError, TypeError, KeyError, ValueError):
        return _idle_doc()
    if timer["state"] != "running":
        return _idle_doc()
    timer["last_checkin"] = _iso(last_checkin) if last_checkin else None
    if is_stale(timer, now) or remaining_seconds(timer, now) <= 0:
        return _idle_doc()
    timer["remaining_seconds"] = remaining_seconds(timer, now)
    return {"version": SCHEMA_VERSION, "timer": timer}


def write_sync(drive_service, folder_id, timer_payload, now=None):
    """Record a client's check-in (last writer wins — see module docstring).

    Returns the clean document that was written.
    """
    now = now or datetime.now(timezone.utc)
    timer = validate_timer(timer_payload)
    if timer["state"] == "running":
        timer["last_checkin"] = _iso(now)
    doc = {"version": SCHEMA_VERSION, "timer": timer}
    _transport(drive_service, folder_id).upload_file(SYNC_FILE, json.dumps(doc, indent=2, ensure_ascii=False))
    return doc
