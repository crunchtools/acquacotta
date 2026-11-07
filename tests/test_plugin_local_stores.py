"""Plugins keep their data in the browser's IndexedDB, and the framework enforces it.

A plugin with a tab names its stores in PLUGIN_METADATA["local_stores"]; register()
refuses one that names none, and every name must be a store storage.js creates.
"""

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

import app

plugin_registry = app.plugin_registry  # imported via app, which registers every plugin

ROOT = Path(__file__).resolve().parent.parent
STORAGE_JS = (ROOT / "static" / "js" / "storage.js").read_text()
INDEX_HTML = (ROOT / "templates" / "index.html").read_text()


def _schema_stores():
    """Store names in storage.js's STORE_SCHEMA, resolved through the STORES map."""
    stores_block = re.search(r"const STORES = \{(.*?)\};", STORAGE_JS, re.S).group(1)
    names = dict(re.findall(r"(\w+):\s*'([^']+)'", stores_block))
    schema_block = re.search(r"const STORE_SCHEMA = \[(.*?)\n    \];", STORAGE_JS, re.S).group(1)
    return {names[const] for const in re.findall(r"name: STORES\.(\w+)", schema_block)}


TAB_PLUGINS = [p for p in plugin_registry.list_plugins() if p.get("has_tab")]


def test_tab_plugins_are_found():
    assert {"todos", "discussions", "rt", "social"} <= {p["id"] for p in TAB_PLUGINS}


@pytest.mark.parametrize("plugin", TAB_PLUGINS, ids=lambda p: p["id"])
def test_tab_plugin_stores_exist_in_indexeddb(plugin):
    declared = plugin.get("local_stores") or []
    assert declared, f"{plugin['id']} has a tab but no local_stores"
    missing = set(declared) - _schema_stores()
    assert not missing, f"{plugin['id']} names stores storage.js never creates: {sorted(missing)}"


def test_register_refuses_a_tab_without_local_stores():
    meta = {"id": "nocache", "type": "extension", "has_tab": True, "tab_id": "nocache"}
    with pytest.raises(ValueError, match="declares no local_stores"):
        plugin_registry.register("extension", "nocache", SimpleNamespace(), meta)
    assert plugin_registry.get_plugin("extension", "nocache") is None


def test_index_html_keeps_no_data_in_localstorage():
    """Plugin data goes through Storage into IndexedDB, not localStorage."""
    calls = re.findall(r"localStorage\.\w+", INDEX_HTML)
    assert not calls, f"index.html uses localStorage: {calls}"
