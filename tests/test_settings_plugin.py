"""Tests for the Settings plugin's MCP surface: schema validation and the tools.

Importing mcp_server populates the plugin registry exactly as production does, so
tab ids and toggleable plugin ids come from the real registrations.
"""

import pytest
from fastmcp.exceptions import ToolError

import mcp_server
import settings_plugin


class FakeMCP:
    """Captures @mcp.tool() functions by name so tests can call them directly."""

    def __init__(self):
        self.tools = {}

    def tool(self):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


@pytest.fixture
def tools(monkeypatch):
    stored = {"short_break_minutes": 5, "todo_sort_orders": {"x": "y"}}
    saved = []

    def fake_get(_service, _folder, defaults):
        merged = dict(defaults)
        merged.update(stored)
        return merged

    def fake_save(_service, _folder, data, replace_all=False):
        assert replace_all is False
        saved.append(dict(data))
        stored.update(data)

    monkeypatch.setattr(settings_plugin.drive_storage, "get_settings", fake_get)
    monkeypatch.setattr(settings_plugin.drive_storage, "save_settings", fake_save)
    mcp = FakeMCP()
    ctx = {"service": None, "folder_id": "folder", "email": "u@example.com"}
    settings_plugin.register_mcp_tools(mcp, lambda: ctx)
    return mcp.tools, stored, saved


def test_mcp_server_registers_settings_tools_ungated():
    registrars = {pid: (fn, mandatory) for pid, fn, mandatory in mcp_server.plugin_registry.get_mcp_tool_registrars()}
    assert registrars["settings"] == (settings_plugin.register_mcp_tools, True)


class TestValidateChanges:
    def test_accepts_known_keys(self):
        clean = settings_plugin.validate_changes(
            {"timer_preset_4": 25, "clock_format": "24", "working_hours_start": "07:30", "timezone": "America/New_York"}
        )
        assert clean["timer_preset_4"] == 25

    @pytest.mark.parametrize(
        "changes",
        [
            {"timer_preset_1": 0},
            {"timer_preset_1": 61},
            {"timer_preset_1": True},
            {"short_break_minutes": "5"},
            {"tick_sound_enabled": "yes"},
            {"clock_format": 24},
            {"working_hours_end": "25:00"},
            {"timezone": "Mars/Olympus"},
            {"type_colors": {"Work": "red"}},
            {"pomodoro_types": ["Work", "Work"]},
        ],
    )
    def test_rejects_bad_values(self, changes):
        with pytest.raises(ValueError):
            settings_plugin.validate_changes(changes)

    def test_rejects_unknown_key(self):
        with pytest.raises(ValueError, match="Unknown setting"):
            settings_plugin.validate_changes({"evil": 1})

    def test_rejects_empty(self):
        with pytest.raises(ValueError):
            settings_plugin.validate_changes({})

    def test_optional_plugin_toggle(self):
        assert settings_plugin.validate_changes({"plugin_state_rt": False}) == {"plugin_state_rt": False}

    def test_mandatory_plugin_toggle_refused(self):
        with pytest.raises(ValueError, match="not an optional plugin"):
            settings_plugin.validate_changes({"plugin_state_pomodoro": False})

    def test_tab_order(self):
        ids = settings_plugin.tab_ids()
        assert ids[0] == "timer" and ids[-1] == "settings"
        assert {"todos", "discussions", "rt"} <= set(ids)
        order = list(reversed(ids))
        assert settings_plugin.validate_changes({"tab_order": order}) == {"tab_order": order}

    @pytest.mark.parametrize("order", [["timer", "nope"], ["timer", "timer"], "timer"])
    def test_tab_order_rejects(self, order):
        with pytest.raises(ValueError):
            settings_plugin.validate_changes({"tab_order": order})


class TestTools:
    def test_get_settings(self, tools):
        t, _stored, _saved = tools
        result = t["get_settings"]()
        assert result["settings"]["short_break_minutes"] == 5
        assert "tab_order" in result["settable"]
        assert "rt" in result["plugins"] and "pomodoro" not in result["plugins"]

    def test_update_merges(self, tools):
        t, stored, saved = tools
        assert t["update_settings"]({"long_break_minutes": 20}) == {"updated": {"long_break_minutes": 20}}
        assert saved == [{"long_break_minutes": 20}]
        assert stored["short_break_minutes"] == 5  # untouched
        assert stored["todo_sort_orders"] == {"x": "y"}

    def test_update_rejects_without_writing(self, tools):
        t, _stored, saved = tools
        with pytest.raises(ToolError):
            t["update_settings"]({"long_break_minutes": 20, "bogus": 1})
        assert saved == []
