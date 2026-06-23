"""Acquacotta Todos Plugin — task management with custom lists and pomodoro linking."""

import json

from transports.google_drive_transport import GoogleDriveTransport

PLUGIN_METADATA = {
    "id": "todos",
    "name": "Todos",
    "description": "Task management with custom lists and pomodoro linking",
    "version": "1.0.0",
    "type": "extension",
    "author": "Crunchtools",
}

TODOS_FILE = "data.json"
PLUGIN_FOLDER = "plugins/todos"

_EMPTY_DATA = {"todos": [], "lists": []}


def _transport(drive_service, folder_id):
    return GoogleDriveTransport(drive_service, folder_id)


def _ensure_plugin_folder(t, folder_id):
    """Ensure plugins/todos/ subfolder exists, return its folder ID."""
    service = t._service
    # Find or create "plugins" folder
    plugins_id = _find_or_create_folder(service, folder_id, "plugins")
    # Find or create "todos" inside plugins
    return _find_or_create_folder(service, plugins_id, "todos")


def _find_or_create_folder(service, parent_id, name):
    query = (
        f"name='{name}' and '{parent_id}' in parents "
        f"and mimeType='application/vnd.google-apps.folder' and trashed=false"
    )
    results = service.files().list(q=query, spaces="drive", fields="files(id)").execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]
    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = service.files().create(body=metadata, fields="id").execute()
    return folder["id"]


def read_todos(drive_service, folder_id):
    t = _transport(drive_service, folder_id)
    todos_folder_id = _ensure_plugin_folder(t, folder_id)
    todos_transport = GoogleDriveTransport(drive_service, todos_folder_id)
    content = todos_transport.download_file(TODOS_FILE)
    if content is None:
        return dict(_EMPTY_DATA)
    try:
        data = json.loads(content)
        if not isinstance(data, dict):
            return dict(_EMPTY_DATA)
        data.setdefault("todos", [])
        data.setdefault("lists", [])
        return data
    except (json.JSONDecodeError, TypeError):
        return dict(_EMPTY_DATA)


def write_todos(drive_service, folder_id, data):
    t = _transport(drive_service, folder_id)
    todos_folder_id = _ensure_plugin_folder(t, folder_id)
    todos_transport = GoogleDriveTransport(drive_service, todos_folder_id)
    content = json.dumps(data, indent=2, ensure_ascii=False)
    todos_transport.upload_file(TODOS_FILE, content)
