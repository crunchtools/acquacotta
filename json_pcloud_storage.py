"""JSON on pCloud storage plugin for Acquacotta.

Wires json_storage_core (shared logic) with pcloud_transport (pCloud REST API).
"""

import json

import json_storage_core as core
from transports.pcloud_transport import PCloudClient, PCloudTransport

PLUGIN_METADATA = {
    "id": "json-pcloud",
    "name": "JSON on pCloud",
    "description": "Store data as JSON files on your pCloud Drive",
    "version": "1.0.0",
    "type": "storage",
    "author": "crunchtools",
    "frontend_fields": ["pcloud_folder_path"],
    "auth_flow": "pcloud_oauth",
}

POMODOROS_FILE = "pomodoros.json"
SETTINGS_FILE = "settings.json"
MCP_STATE_FILE = "mcp_access.json"


def build_context(credentials, request_creds):
    """Build pCloud-specific storage context from the request's credentials.

    `credentials` is the Google identity — pCloud is a storage backend, not an
    identity provider, so it is unused here. The pCloud token lives in the
    browser next to the Google credentials and rides in on every request; the
    server never stores it (constitution I & II).
    """
    client = PCloudClient(
        request_creds.get("pcloud_token"),
        request_creds.get("pcloud_api_host"),
    )
    return {
        "service": client,
        "location": request_creds.get("pcloud_folder_path"),
    }


def _transport(pcloud_client, folder_path):
    return PCloudTransport(pcloud_client, folder_path)


def get_pomodoros(pcloud_client, folder_path, start_date=None, end_date=None):
    t = _transport(pcloud_client, folder_path)
    content = t.download_file(POMODOROS_FILE)
    pomodoros = core.parse_pomodoros(content)
    return core.filter_by_date(pomodoros, start_date, end_date)


def save_pomodoro(pcloud_client, folder_path, pomodoro):
    t = _transport(pcloud_client, folder_path)
    content = t.download_file(POMODOROS_FILE)
    pomodoros = core.parse_pomodoros(content)
    pomodoros, was_new = core.add_pomodoro(pomodoros, pomodoro)
    if was_new:
        t.upload_file(POMODOROS_FILE, core.serialize_pomodoros(pomodoros))
    return was_new


def save_pomodoros_batch(pcloud_client, folder_path, new_pomodoros):
    if not new_pomodoros:
        return 0
    t = _transport(pcloud_client, folder_path)
    content = t.download_file(POMODOROS_FILE)
    pomodoros = core.parse_pomodoros(content)
    pomodoros, added = core.add_pomodoros_batch(pomodoros, new_pomodoros)
    if added:
        t.upload_file(POMODOROS_FILE, core.serialize_pomodoros(pomodoros))
    return added


def update_pomodoro(pcloud_client, folder_path, pomodoro_id, update_fields):
    t = _transport(pcloud_client, folder_path)
    content = t.download_file(POMODOROS_FILE)
    pomodoros = core.parse_pomodoros(content)
    pomodoros, found = core.update_pomodoro(pomodoros, pomodoro_id, update_fields)
    if found:
        t.upload_file(POMODOROS_FILE, core.serialize_pomodoros(pomodoros))
    return found


def delete_pomodoro(pcloud_client, folder_path, pomodoro_id):
    t = _transport(pcloud_client, folder_path)
    content = t.download_file(POMODOROS_FILE)
    pomodoros = core.parse_pomodoros(content)
    pomodoros, found = core.delete_pomodoro(pomodoros, pomodoro_id)
    if found:
        t.upload_file(POMODOROS_FILE, core.serialize_pomodoros(pomodoros))
    return found


def get_settings(pcloud_client, folder_path, defaults):
    t = _transport(pcloud_client, folder_path)
    content = t.download_file(SETTINGS_FILE)
    stored = core.parse_settings(content)
    merged = dict(defaults)
    merged.update(stored)
    return merged


def save_settings(pcloud_client, folder_path, settings_data, replace_all=False):
    t = _transport(pcloud_client, folder_path)
    if replace_all:
        t.upload_file(SETTINGS_FILE, core.serialize_settings(settings_data))
        return

    content = t.download_file(SETTINGS_FILE)
    existing = core.parse_settings(content)
    merged = core.merge_settings(existing, settings_data, replace_all=False)
    t.upload_file(SETTINGS_FILE, core.serialize_settings(merged))


def get_mcp_state(pcloud_client, folder_path):
    """Return the user's MCP access state {'enabled': bool, 'epoch': int} from pCloud.

    Kept in the user's own pCloud (not on the server) so revocation survives
    restarts while the server stays stateless. The epoch is a watermark: any
    token minted before it is rejected (constitution I, II & VI).
    """
    t = _transport(pcloud_client, folder_path)
    content = t.download_file(MCP_STATE_FILE)
    if not content:
        return {"enabled": False, "epoch": 0}
    try:
        state = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return {"enabled": False, "epoch": 0}
    return {"enabled": bool(state.get("enabled", False)), "epoch": int(state.get("epoch", 0))}


def set_mcp_state(pcloud_client, folder_path, enabled, epoch):
    """Persist the user's MCP access state to their pCloud."""
    t = _transport(pcloud_client, folder_path)
    t.upload_file(MCP_STATE_FILE, json.dumps({"enabled": bool(enabled), "epoch": int(epoch)}))


def deduplicate_pomodoros(pcloud_client, folder_path):
    t = _transport(pcloud_client, folder_path)
    content = t.download_file(POMODOROS_FILE)
    pomodoros = core.parse_pomodoros(content)
    deduped, removed = core.deduplicate(pomodoros)
    if removed:
        t.upload_file(POMODOROS_FILE, core.serialize_pomodoros(deduped))
    return {"removed": removed, "total": len(deduped)}


def count_pomodoros(pcloud_client, folder_path):
    t = _transport(pcloud_client, folder_path)
    content = t.download_file(POMODOROS_FILE)
    pomodoros = core.parse_pomodoros(content)
    return len(pomodoros)


def clear_pomodoros(pcloud_client, folder_path):
    t = _transport(pcloud_client, folder_path)
    content = t.download_file(POMODOROS_FILE)
    pomodoros = core.parse_pomodoros(content)
    count = len(pomodoros)
    t.upload_file(POMODOROS_FILE, core.serialize_pomodoros([]))
    return {"status": "ok", "cleared": count}
