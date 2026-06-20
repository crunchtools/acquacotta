# Implementation Plan: JSON Storage Core + Google Drive Transport

**Branch**: `feature/83-json-google-drive` | **Date**: 2026-06-19 | **Spec**: `002-json-google-drive/spec.md`
**Input**: Feature specification from `/specs/002-json-google-drive/spec.md`

## Summary

Replace the Google Sheets storage backend with a JSON-on-Google-Drive backend as the default for new users. Build a two-layer architecture: a shared `json_storage_core.py` (transport-agnostic CRUD/serialization) and a `transports/google_drive_transport.py` (4-function interface). Wire them together in `json_google_drive_storage.py` implementing the full 11-function storage contract. Refactor `app.py` to make `_storage_context()` and the OAuth callback plugin-aware.

## Technical Context

**Language/Version**: Python 3.x (Flask)
**Primary Dependencies**: Flask, google-api-python-client, google-auth-oauthlib
**Storage**: Google Drive API v3 (JSON files), IndexedDB (browser cache)
**Testing**: Manual verification + existing test patterns
**Target Platform**: Linux container (OCI), all modern browsers
**Project Type**: Web application (monolith)
**Performance Goals**: Sub-2-second full read for 2400+ pomodoros (vs. minutes with Sheets)
**Constraints**: No new OAuth scopes, drive.file only, stateless server
**Scale/Scope**: Single user per session, ~5 MB max data over a decade

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Privacy by Design | PASS | Same OAuth, same drive.file scope, no new data collection |
| II. User Data Ownership | PASS | JSON on user's Drive is even more portable than Sheets |
| III. Simplicity & Focus | PASS | Plugin architecture already approved (#80/#85), this adds a cleaner backend |
| IV. Timer Agnosticism | N/A | Storage layer, not timer |
| V. Offline-First | PASS | IndexedDB remains the primary read path; Drive is the sync target |
| VI. Container-Ready | PASS | No new persistent volumes, same stateless design |

## Project Structure

### Documentation (this feature)

```text
specs/002-json-google-drive/
├── spec.md              # Feature specification
└── plan.md              # This file
```

### Source Code (new and modified files)

```text
# New files
json_storage_core.py                 # Shared JSON serialization, CRUD, filtering, dedup
transports/                          # Transport implementations directory
├── __init__.py
└── google_drive_transport.py        # Google Drive API v3 transport (4 functions)
json_google_drive_storage.py         # Storage plugin: core + transport, PLUGIN_METADATA

# Modified files
app.py                               # Plugin-aware _storage_context(), OAuth callback, default backend
storage_api.py                       # Use plugin's build_context() instead of hardcoded Sheets logic
```

## Implementation Phases

### Phase 1: JSON Storage Core (`json_storage_core.py`)

The core module operates on plain Python dicts/lists. It doesn't know or care where JSON files live.

**Functions to implement:**

```python
def parse_pomodoros(json_content: str | None) -> list[dict]
def serialize_pomodoros(pomodoros: list[dict]) -> str
def parse_settings(json_content: str | None) -> dict
def serialize_settings(settings: dict) -> str
def add_pomodoro(pomodoros: list[dict], pomodoro: dict) -> tuple[list[dict], bool]
def add_pomodoros_batch(pomodoros: list[dict], new_pomodoros: list[dict]) -> tuple[list[dict], int]
def update_pomodoro(pomodoros: list[dict], pomodoro_id: str, update_fields: dict) -> tuple[list[dict], bool]
def delete_pomodoro(pomodoros: list[dict], pomodoro_id: str) -> tuple[list[dict], bool]
def filter_by_date(pomodoros: list[dict], start_date: str | None, end_date: str | None) -> list[dict]
def deduplicate(pomodoros: list[dict]) -> tuple[list[dict], int]
def merge_settings(existing: dict, updates: dict, replace_all: bool) -> dict
```

Key design decisions:
- All functions are pure — take data in, return data out
- `add_pomodoro` returns `(updated_list, was_new)` for duplicate detection
- Sort by `start_time` descending on read (matches Sheets behavior)
- Invalid JSON returns empty list/dict, never crashes

### Phase 2: Google Drive Transport (`transports/google_drive_transport.py`)

Thin adapter around Google Drive API v3. ~80 lines.

```python
class GoogleDriveTransport:
    def __init__(self, drive_service, folder_id):
        ...
    
    def download_file(self, filename: str) -> str | None:
        """Download a file from the Acquacotta folder. Returns content or None."""
    
    def upload_file(self, filename: str, content: str) -> None:
        """Upload/overwrite a file in the Acquacotta folder."""
    
    def ensure_directory(self) -> str:
        """Ensure Acquacotta/ folder exists, return folder_id."""
    
    def file_exists(self, filename: str) -> bool:
        """Check if a file exists in the folder."""
```

Drive API operations:
- `files().list()` with `q="name='X' and 'folder_id' in parents"` to find files
- `files().get_media()` to download content
- `files().create()` to create new files
- `files().update()` with `media_body` to overwrite existing files
- `files().create()` with `mimeType='application/vnd.google-apps.folder'` for directory

### Phase 3: JSON Google Drive Storage Plugin (`json_google_drive_storage.py`)

Wires core + transport. Implements all 11 storage contract functions. ~120 lines.

```python
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

def build_context(credentials, request_creds):
    """Build Drive-specific storage context."""
    service = build("drive", "v3", credentials=credentials)
    return {"service": service, "location": request_creds.get("folder_id")}
```

Each function follows the pattern:
1. Create transport from service + folder_id
2. Download the relevant JSON file
3. Parse with core
4. Apply operation with core
5. Serialize with core
6. Upload back via transport

### Phase 4: Plugin-Aware App Integration (`app.py` + `storage_api.py`)

**4a. Refactor `_storage_context()`** — use the active plugin's `build_context()`:

```python
def _storage_context():
    backend = plugin_registry.get_active_storage()
    if backend is None:
        return None
    credentials = get_credentials()
    if not credentials:
        return None
    request_creds = get_credentials_from_request()
    if not request_creds:
        return None
    return backend.build_context(credentials, request_creds)
```

**4b. Refactor `is_logged_in()`** — check for plugin-appropriate location field:

```python
def is_logged_in():
    creds = get_credentials_from_request()
    if not creds or not creds.get("token"):
        return False
    backend = plugin_registry.get_active_storage()
    if backend is None:
        return True  # logged in but no backend (offline-only mode)
    metadata = getattr(backend, 'PLUGIN_METADATA', {})
    required_fields = metadata.get('frontend_fields', [])
    return all(creds.get(f) for f in required_fields)
```

**4c. Refactor OAuth callback** — plugin-aware IndexedDB hydration:

Instead of hardcoding `spreadsheet_id`, read from the active plugin's metadata:
- `json-google-drive` → find/create `Acquacotta/` folder → write `folder_id` to IndexedDB
- `sheets` → find/create spreadsheet → write `spreadsheet_id` to IndexedDB

**4d. Change default backend** — register both plugins, activate `json-google-drive`:

```python
plugin_registry.register("storage", "sheets", sheets_storage, sheets_storage.PLUGIN_METADATA)
plugin_registry.register("storage", "json-google-drive", json_google_drive_storage, json_google_drive_storage.PLUGIN_METADATA)
plugin_registry.activate_storage("json-google-drive")  # New default
```

**4e. Remove `storage_api.py` hardcoded imports** — the dispatch layer already uses `plugin_registry.get_active_storage()`, but `StorageUnavailable` inherits from `HttpError` which is Sheets-specific. Make it a plain exception.

### Phase 5: Frontend Credential Handling

The frontend already sends credentials generically via `X-Credentials` header. The only change needed is that the OAuth callback JS writes `folder_id` instead of `spreadsheet_id` into IndexedDB when the JSON plugin is active. The `storage.js` module's `_getCredentials()` already reads from the `settings` store generically — it sends whatever is there.

Verify that `storage.js` sends `folder_id` in the credentials payload when it's present in IndexedDB. If it only sends `spreadsheet_id`, add `folder_id` to the fields it includes.

## Complexity Tracking

No constitution violations. The plugin architecture was explicitly approved in constitution v2.0.0 (Principle III amendment, PR #85).

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Drive API rate limiting | Low | Single file read/write per operation, well within quotas |
| Breaking existing Sheets users | Medium | Sheets plugin remains registered; existing users keep their `spreadsheet_id` in IndexedDB |
| OAuth callback complexity | Medium | Careful refactor with fallback to current behavior if no `build_context` exists |
