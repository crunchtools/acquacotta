"""Acquacotta Settings plugin — the user's app preferences, readable and writable over MCP.

Settings live in the user's own storage (settings.json in their Drive folder), the
same file the web UI reads on load, so a change made here shows up in the browser
on its next refresh. Every write is checked against an explicit schema: unknown keys
are rejected rather than silently stored, so an agent can't scribble junk into the
file the UI trusts.

Deliberately NOT settable here (browser OAuth/session flows): MCP access itself
(an agent must not mint or revoke its own credential), the storage backend, and the
pCloud link. Plugin-owned config with secrets (RT) has its own tools in that plugin.
"""

import re
from functools import cache
from zoneinfo import available_timezones

import json_google_drive_storage as drive_storage
import plugin_registry

# Mandatory feature plugin — always registered; its MCP tools are always available.
PLUGIN_METADATA = {
    "id": "settings",
    "name": "Settings",
    "description": "App preferences and timer configuration",
    "version": "1.1.0",
    "type": "extension",
    "author": "Crunchtools",
    "mandatory": True,
}

# Tabs every install has; extension tabs come from the plugin registry.
_CORE_TABS = ("timer", "reports", "history", "settings")

_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def _int_range(lo, hi):
    """Return a validator ``check(key, value) -> value`` accepting ints in [lo, hi] (not bools)."""

    def check(key, value):
        if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
            raise ValueError(f"{key} must be an integer from {lo} to {hi}")
        return value

    return check


def _bool(key, value):
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be true or false")
    return value


def _enum(*choices):
    """Return a validator ``check(key, value) -> value`` accepting only one of ``choices``."""

    def check(key, value):
        if value not in choices:
            raise ValueError(f"{key} must be one of: {', '.join(str(c) for c in choices)}")
        return value

    return check


def _hhmm(key, value):
    if not isinstance(value, str) or not _HHMM.match(value):
        raise ValueError(f"{key} must be a 24-hour time like 08:00")
    return value


@cache
def _timezones():
    return frozenset(available_timezones())


def _timezone(key, value):
    if value != "auto" and (not isinstance(value, str) or value not in _timezones()):
        raise ValueError(f"{key} must be 'auto' or an IANA timezone like America/New_York")
    return value


def _pomodoro_types(key, value):
    if not isinstance(value, list) or not all(isinstance(t, str) and t.strip() for t in value):
        raise ValueError(f"{key} must be a list of non-empty strings")
    cleaned = [t.strip() for t in value]
    if len(set(cleaned)) != len(cleaned):
        raise ValueError(f"{key} must not contain duplicates")
    return cleaned


def _type_colors(key, value):
    if not isinstance(value, dict) or not all(
        isinstance(k, str) and isinstance(v, str) and _HEX_COLOR.match(v) for k, v in value.items()
    ):
        raise ValueError(f"{key} must map type names to colors like #3b82f6")
    return value


def tab_ids():
    """Return every top-level tab id in default order.

    Returns:
        timer, reports, history, then each registered extension's tab, then settings.
    """
    ids = list(_CORE_TABS[:-1])
    for plugin in plugin_registry.list_plugins("extension"):
        if plugin.get("has_tab") and plugin.get("tab_id") and plugin["tab_id"] not in ids:
            ids.append(plugin["tab_id"])
    ids.append(_CORE_TABS[-1])
    return ids


def _tab_order(key, value):
    valid = set(tab_ids())
    if not isinstance(value, list) or not all(isinstance(t, str) for t in value):
        raise ValueError(f"{key} must be a list of tab ids")
    unknown = [t for t in value if t not in valid]
    if unknown:
        raise ValueError(f"{key} has unknown tab ids {unknown}; valid: {sorted(valid)}")
    if len(set(value)) != len(value):
        raise ValueError(f"{key} must not repeat a tab")
    return value


SCHEMA = {
    "timer_preset_1": _int_range(1, 60),
    "timer_preset_2": _int_range(1, 60),
    "timer_preset_3": _int_range(1, 60),
    "timer_preset_4": _int_range(1, 60),
    "short_break_minutes": _int_range(1, 30),
    "long_break_minutes": _int_range(1, 60),
    "pomodoros_until_long_break": _int_range(2, 10),
    "always_use_short_break": _bool,
    "auto_start_after_break": _bool,
    "tick_sound_enabled": _bool,
    "tick_sound_during_breaks": _bool,
    "tick_volume": _int_range(0, 100),
    "bell_at_pomodoro_end": _bool,
    "bell_at_break_end": _bool,
    "show_timer_ticks": _bool,
    "show_notes_field": _bool,
    "pip_timer_enabled": _bool,
    "timer_snap_interval": _enum(1, 30, 60),
    "timezone": _timezone,
    "date_format": _enum("auto", "us", "eu", "iso"),
    "clock_format": _enum("auto", "12", "24"),
    "period_labels": _enum("auto", "ampm", "morning"),
    "working_hours_start": _hhmm,
    "working_hours_end": _hhmm,
    "daily_minutes_goal": _int_range(0, 600),
    "pomodoro_types": _pomodoro_types,
    "type_colors": _type_colors,
    "tab_order": _tab_order,
}

_PLUGIN_STATE_PREFIX = "plugin_state_"


def _toggleable_plugin_ids():
    return {p["id"] for p in plugin_registry.list_plugins("extension") if not p.get("mandatory")}


def validate_changes(changes):
    """Check a settings update against SCHEMA and the optional-plugin toggles.

    Args:
        changes: setting name -> new value.

    Returns:
        A clean copy of ``changes`` (values normalized, e.g. stripped type names).

    Raises:
        ValueError: naming the first unknown key or invalid value.
    """
    if not isinstance(changes, dict) or not changes:
        raise ValueError("changes must be a non-empty object of setting: value")
    clean = {}
    for key, value in changes.items():
        if key.startswith(_PLUGIN_STATE_PREFIX):
            plugin_id = key[len(_PLUGIN_STATE_PREFIX) :]
            if plugin_id not in _toggleable_plugin_ids():
                raise ValueError(f"{key}: '{plugin_id}' is not an optional plugin that can be toggled")
            clean[key] = _bool(key, value)
        elif key in SCHEMA:
            clean[key] = SCHEMA[key](key, value)
        else:
            raise ValueError(f"Unknown setting '{key}'. Settable keys: {sorted(SCHEMA)} and plugin_state_<plugin>")
    return clean


def register_mcp_tools(mcp, require_ctx):
    """Register the settings tools on a FastMCP instance (always available).

    Args:
        mcp: the FastMCP instance to register the ``@mcp.tool()`` functions on.
        require_ctx: zero-arg callable returning the caller's
            ``{"service", "folder_id", "email"}`` context (raises on a bad token).

    Returns:
        None.
    """
    from fastmcp.exceptions import ToolError

    @mcp.tool()
    def get_settings() -> dict:
        """Get the caller's Acquacotta settings.

        Returns:
            ``{"settings": {...}, "settable": [...], "tabs": [...], "plugins": [...]}``:
            the stored settings, the keys update_settings accepts, the valid tab ids
            for tab_order, and the optional plugin ids for plugin_state_<id>.
        """
        ctx = require_ctx()
        return {
            "settings": drive_storage.get_settings(ctx["service"], ctx["folder_id"], {}),
            "settable": sorted(SCHEMA),
            "tabs": tab_ids(),
            "plugins": sorted(_toggleable_plugin_ids()),
        }

    @mcp.tool()
    def update_settings(changes: dict) -> dict:
        """Change one or more of the caller's settings. Other settings are left as-is.

        Args:
            changes: setting -> value, e.g. {"short_break_minutes": 5,
                "tab_order": ["timer", "rt", "todos", ...], "plugin_state_rt": true}.
                Call get_settings for the full list of keys and valid tab ids.

        Returns:
            ``{"updated": {...}}`` with the values written. The web UI picks them up
            on its next load.
        """
        ctx = require_ctx()
        try:
            clean = validate_changes(changes)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        drive_storage.save_settings(ctx["service"], ctx["folder_id"], clean)
        return {"updated": clean}
