"""Tests for per-user MCP plugin gating (spec 008).

An extension's MCP tools are gated on the CALLING user's own plugin_state_<id>
preference (read from their storage), never a shared global. A disabled plugin's
tools refuse with a clear error; enabled (or unset → default on) tools pass through.
"""

import pytest
from fastmcp.exceptions import ToolError

import mcp_server


@pytest.fixture
def caller_ctx(monkeypatch):
    """Stub require_ctx to a fixed caller and make get_settings return whatever the
    test puts in `state['settings']` — standing in for the caller's stored prefs."""
    state = {"settings": {}}
    ctx = {"service": object(), "folder_id": "folder-abc", "email": "user@example.com"}

    monkeypatch.setattr(mcp_server, "require_ctx", lambda: ctx)
    monkeypatch.setattr(
        mcp_server.json_google_drive_storage,
        "get_settings",
        lambda service, folder_id, defaults: dict(state["settings"]),
    )
    return state, ctx


def test_enabled_plugin_passes_through(caller_ctx):
    state, ctx = caller_ctx
    state["settings"] = {"plugin_state_todos": True}
    gated = mcp_server._make_plugin_ctx("todos")
    assert gated() is ctx


def test_unset_plugin_defaults_enabled(caller_ctx):
    state, ctx = caller_ctx
    state["settings"] = {}  # user never chose → default on
    gated = mcp_server._make_plugin_ctx("todos")
    assert gated() is ctx


def test_disabled_plugin_refuses(caller_ctx):
    state, _ctx = caller_ctx
    state["settings"] = {"plugin_state_todos": False}
    gated = mcp_server._make_plugin_ctx("todos")
    with pytest.raises(ToolError) as exc:
        gated()
    assert "todos" in str(exc.value)
    assert "disabled" in str(exc.value).lower()


def test_gating_is_per_plugin(caller_ctx):
    """Disabling one plugin does not gate another."""
    state, ctx = caller_ctx
    state["settings"] = {"plugin_state_todos": False, "plugin_state_other": True}
    assert mcp_server._make_plugin_ctx("other")() is ctx
    with pytest.raises(ToolError):
        mcp_server._make_plugin_ctx("todos")()


def test_registry_returns_id_registrar_pairs():
    """get_mcp_tool_registrars yields (plugin_id, callable) for every plugin with a
    registrar, so the MCP server can gate each per-user."""
    import plugin_registry

    pairs = plugin_registry.get_mcp_tool_registrars()
    assert pairs, "expected at least the todos registrar"
    for item in pairs:
        assert isinstance(item, tuple) and len(item) == 2
        pid, registrar = item
        assert isinstance(pid, str)
        assert callable(registrar)
    assert "todos" in {pid for pid, _ in pairs}
