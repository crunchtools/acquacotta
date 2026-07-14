"""Acquacotta Plugin Registry — type system, contracts, and discovery."""

PLUGIN_TYPES = {
    "storage": {
        "description": "Data storage backends",
        "contract": [
            "get_pomodoros",
            "save_pomodoro",
            "save_pomodoros_batch",
            "update_pomodoro",
            "delete_pomodoro",
            "get_settings",
            "save_settings",
            "deduplicate_pomodoros",
            "count_pomodoros",
            "clear_pomodoros",
            "build_context",
        ],
        "singleton": True,
    },
    "extension": {
        "description": "Dashboard extensions (tabs, data)",
        "contract": [],
        "singleton": False,
    },
    "integration": {
        "description": "External system integrations",
        "contract": [],
        "singleton": False,
    },
    "import": {
        "description": "One-time data migration tools",
        "contract": [],
        "singleton": False,
    },
}

_plugins = {}  # plugin_type -> {plugin_id -> {module, metadata, active}}
_active_storage = None


def register(plugin_type, plugin_id, module, metadata):
    """Register a plugin. Validates it implements the required contract."""
    if plugin_type not in PLUGIN_TYPES:
        raise ValueError(f"Unknown plugin type: {plugin_type}")

    contract = PLUGIN_TYPES[plugin_type]["contract"]
    missing = [fn for fn in contract if not callable(getattr(module, fn, None))]
    if missing:
        raise ValueError(f"Plugin '{plugin_id}' missing required functions: {', '.join(missing)}")

    if plugin_type not in _plugins:
        _plugins[plugin_type] = {}

    # Mandatory plugins register active and can never be disabled; others default off.
    mandatory = bool(metadata.get("mandatory", False))
    _plugins[plugin_type][plugin_id] = {
        "module": module,
        "metadata": metadata,
        "active": mandatory,
        "mandatory": mandatory,
    }


def is_mandatory(plugin_type, plugin_id):
    """True if the plugin is registered and marked mandatory (always-on)."""
    return bool(_plugins.get(plugin_type, {}).get(plugin_id, {}).get("mandatory", False))


def activate_storage(plugin_id):
    """Set the active storage backend."""
    global _active_storage
    if "storage" not in _plugins or plugin_id not in _plugins["storage"]:
        raise ValueError(f"Storage plugin not registered: {plugin_id}")

    for pid in _plugins["storage"]:
        _plugins["storage"][pid]["active"] = pid == plugin_id

    _active_storage = plugin_id


def deactivate_storage():
    """Disable cloud storage sync. App falls back to local IndexedDB only."""
    global _active_storage
    if "storage" in _plugins:
        for pid in _plugins["storage"]:
            _plugins["storage"][pid]["active"] = False
    _active_storage = None


def get_active_storage():
    """Get the currently active storage backend module, or None if disabled."""
    if _active_storage is None:
        return None
    return _plugins["storage"][_active_storage]["module"]


def get_active_storage_id():
    """Get the id of the currently active storage backend."""
    return _active_storage


def activate_extension(plugin_id):
    """Enable an extension plugin."""
    if "extension" not in _plugins or plugin_id not in _plugins["extension"]:
        raise ValueError(f"Extension plugin not registered: {plugin_id}")
    _plugins["extension"][plugin_id]["active"] = True


def deactivate_extension(plugin_id):
    """Disable an extension plugin."""
    if "extension" not in _plugins or plugin_id not in _plugins["extension"]:
        raise ValueError(f"Extension plugin not registered: {plugin_id}")
    _plugins["extension"][plugin_id]["active"] = False


def get_plugin(plugin_type, plugin_id):
    """Get a specific plugin's module by type and id."""
    if plugin_type in _plugins and plugin_id in _plugins[plugin_type]:
        return _plugins[plugin_type][plugin_id]["module"]
    return None


def list_plugins(plugin_type=None):
    """List all registered plugins, optionally filtered by type."""
    plugin_summaries = []
    types_to_list = [plugin_type] if plugin_type else PLUGIN_TYPES.keys()

    for ptype in types_to_list:
        if ptype not in _plugins:
            continue
        for _pid, info in _plugins[ptype].items():
            entry = dict(info["metadata"])
            # Mandatory plugins are always active; otherwise report the registry flag.
            entry["active"] = True if info["mandatory"] else info["active"]
            entry["mandatory"] = info["mandatory"]
            entry["plugin_type"] = ptype
            plugin_summaries.append(entry)

    return plugin_summaries


def get_mcp_tool_registrars():
    """Return ``(plugin_id, register_mcp_tools, mandatory)`` triples for every plugin
    exposing ``register_mcp_tools``. The MCP server uses ``mandatory`` to decide gating:
    mandatory plugins are always available; optional ones are gated per-user (spec 008).
    """
    registrars = []
    for _ptype, plugins in _plugins.items():
        for pid, info in plugins.items():
            registrar = getattr(info["module"], "register_mcp_tools", None)
            if callable(registrar):
                registrars.append((pid, registrar, info["mandatory"]))
    return registrars


def list_plugin_types():
    """List all available plugin types with descriptions."""
    return {
        ptype: {
            "description": info["description"],
            "singleton": info["singleton"],
            "registered_count": len(_plugins.get(ptype, {})),
        }
        for ptype, info in PLUGIN_TYPES.items()
    }
