"""Acquacotta user→storage-location mapping (shared by Flask app and MCP server).

This is the ONLY per-user metadata the server keeps: a pointer to where each
user's data lives (their Drive folder id / spreadsheet id) plus the MCP access
state (enabled flag + revocation epoch). No user content — pomodoros, todos, and
settings all live in the user's own storage. See constitution I & II.

Both the Flask process and the MCP server process import this module so they
read/write the same mapping file under XDG_DATA_HOME.
"""

import json
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "acquacotta"


def _mapping_path():
    """Path to the user-to-storage-location mapping file (migrates legacy name)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    new_path = DATA_DIR / "user_storage.json"
    if not new_path.exists():
        legacy_path = DATA_DIR / "user_spreadsheets.json"
        if legacy_path.exists():
            legacy_path.rename(new_path)
    return new_path


def _read_mapping():
    path = _mapping_path()
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _write_mapping(mapping):
    with open(_mapping_path(), "w") as f:
        json.dump(mapping, f)


def get_stored_location(email, plugin_id):
    """Get stored storage location for a user+plugin combination."""
    mapping = _read_mapping()
    user_entry = mapping.get(email, {})
    if isinstance(user_entry, str):
        # Legacy flat value was always a Sheets spreadsheet id.
        return user_entry if plugin_id == "sheets" else None
    return user_entry.get(plugin_id)


def save_location(email, plugin_id, location_id):
    """Save storage location (or arbitrary JSON-serializable state) for a user+plugin."""
    mapping = _read_mapping()
    user_entry = mapping.get(email, {})
    if isinstance(user_entry, str):
        user_entry = {"sheets": user_entry}
    user_entry[plugin_id] = location_id
    mapping[email] = user_entry
    _write_mapping(mapping)


# --- MCP access state (enabled flag + revocation epoch) -----------------------
#
# Stored under the reserved plugin key "mcp" as {"enabled": bool, "epoch": int}.
# The epoch is a revocation watermark: any token minted before it is rejected.

_MCP_KEY = "mcp"


def get_mcp_state(email):
    """Return the user's MCP access state: {'enabled': bool, 'epoch': int}."""
    state = get_stored_location(email, _MCP_KEY)
    if not isinstance(state, dict):
        return {"enabled": False, "epoch": 0}
    return {"enabled": bool(state.get("enabled", False)), "epoch": int(state.get("epoch", 0))}


def set_mcp_state(email, enabled, epoch):
    """Persist the user's MCP access state."""
    save_location(email, _MCP_KEY, {"enabled": bool(enabled), "epoch": int(epoch)})
