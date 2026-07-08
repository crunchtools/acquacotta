"""JSON on Google Drive storage plugin for Acquacotta.

Wires json_storage_core (shared logic) with google_drive_transport (Drive API).
"""

import json

from googleapiclient.discovery import build

import json_storage_core as core
from transports.google_drive_transport import GoogleDriveTransport

PLUGIN_METADATA = {
    "id": "json-google-drive",
    "name": "JSON on Google Drive",
    "description": "Store data as JSON files on your Google Drive",
    "version": "1.0.0",
    "type": "storage",
    "author": "crunchtools",
    "frontend_fields": ["folder_id"],
    "auth_flow": "google_oauth",
}

POMODOROS_FILE = "pomodoros.json"
SETTINGS_FILE = "settings.json"
MCP_STATE_FILE = "mcp_access.json"


def build_context(credentials, request_creds):
    """Build Drive-specific storage context from credentials."""
    service = build("drive", "v3", credentials=credentials)
    return {
        "service": service,
        "location": request_creds.get("folder_id"),
    }


def _transport(drive_service, folder_id):
    return GoogleDriveTransport(drive_service, folder_id)


def get_pomodoros(drive_service, folder_id, start_date=None, end_date=None):
    t = _transport(drive_service, folder_id)
    content = t.download_file(POMODOROS_FILE)
    pomodoros = core.parse_pomodoros(content)
    return core.filter_by_date(pomodoros, start_date, end_date)


def save_pomodoro(drive_service, folder_id, pomodoro):
    t = _transport(drive_service, folder_id)
    content = t.download_file(POMODOROS_FILE)
    pomodoros = core.parse_pomodoros(content)
    pomodoros, was_new = core.add_pomodoro(pomodoros, pomodoro)
    if was_new:
        t.upload_file(POMODOROS_FILE, core.serialize_pomodoros(pomodoros))
    return was_new


def save_pomodoros_batch(drive_service, folder_id, new_pomodoros):
    if not new_pomodoros:
        return 0
    t = _transport(drive_service, folder_id)
    content = t.download_file(POMODOROS_FILE)
    pomodoros = core.parse_pomodoros(content)
    pomodoros, added = core.add_pomodoros_batch(pomodoros, new_pomodoros)
    if added:
        t.upload_file(POMODOROS_FILE, core.serialize_pomodoros(pomodoros))
    return added


def update_pomodoro(drive_service, folder_id, pomodoro_id, update_fields):
    t = _transport(drive_service, folder_id)
    content = t.download_file(POMODOROS_FILE)
    pomodoros = core.parse_pomodoros(content)
    pomodoros, found = core.update_pomodoro(pomodoros, pomodoro_id, update_fields)
    if found:
        t.upload_file(POMODOROS_FILE, core.serialize_pomodoros(pomodoros))
    return found


def delete_pomodoro(drive_service, folder_id, pomodoro_id):
    t = _transport(drive_service, folder_id)
    content = t.download_file(POMODOROS_FILE)
    pomodoros = core.parse_pomodoros(content)
    pomodoros, found = core.delete_pomodoro(pomodoros, pomodoro_id)
    if found:
        t.upload_file(POMODOROS_FILE, core.serialize_pomodoros(pomodoros))
    return found


def get_settings(drive_service, folder_id, defaults):
    t = _transport(drive_service, folder_id)
    content = t.download_file(SETTINGS_FILE)
    stored = core.parse_settings(content)
    merged = dict(defaults)
    merged.update(stored)
    return merged


def save_settings(drive_service, folder_id, settings_data, replace_all=False):
    t = _transport(drive_service, folder_id)
    if replace_all:
        t.upload_file(SETTINGS_FILE, core.serialize_settings(settings_data))
        return

    content = t.download_file(SETTINGS_FILE)
    existing = core.parse_settings(content)
    merged = core.merge_settings(existing, settings_data, replace_all=False)
    t.upload_file(SETTINGS_FILE, core.serialize_settings(merged))


def get_mcp_state(drive_service, folder_id):
    """Return the user's MCP access state {'enabled': bool, 'epoch': int} from their Drive.

    Kept in the user's own Drive (not on the server) so revocation survives restarts
    while the server stays stateless. The epoch is a watermark: any token minted
    before it is rejected (constitution I, II & VI).
    """
    t = _transport(drive_service, folder_id)
    content = t.download_file(MCP_STATE_FILE)
    if not content:
        return {"enabled": False, "epoch": 0}
    try:
        state = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return {"enabled": False, "epoch": 0}
    return {"enabled": bool(state.get("enabled", False)), "epoch": int(state.get("epoch", 0))}


def set_mcp_state(drive_service, folder_id, enabled, epoch):
    """Persist the user's MCP access state to their Drive."""
    t = _transport(drive_service, folder_id)
    t.upload_file(MCP_STATE_FILE, json.dumps({"enabled": bool(enabled), "epoch": int(epoch)}))


def deduplicate_pomodoros(drive_service, folder_id):
    t = _transport(drive_service, folder_id)
    content = t.download_file(POMODOROS_FILE)
    pomodoros = core.parse_pomodoros(content)
    deduped, removed = core.deduplicate(pomodoros)
    if removed:
        t.upload_file(POMODOROS_FILE, core.serialize_pomodoros(deduped))
    return {"removed": removed, "total": len(deduped)}


def count_pomodoros(drive_service, folder_id):
    t = _transport(drive_service, folder_id)
    content = t.download_file(POMODOROS_FILE)
    pomodoros = core.parse_pomodoros(content)
    return len(pomodoros)


def clear_pomodoros(drive_service, folder_id):
    t = _transport(drive_service, folder_id)
    content = t.download_file(POMODOROS_FILE)
    pomodoros = core.parse_pomodoros(content)
    count = len(pomodoros)
    t.upload_file(POMODOROS_FILE, core.serialize_pomodoros([]))
    return {"status": "ok", "cleared": count}
