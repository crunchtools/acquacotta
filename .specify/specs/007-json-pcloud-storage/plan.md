# Implementation Plan: JSON on pCloud Storage Plugin

**Branch**: `feature/96-json-pcloud-storage` | **Date**: 2026-07-21 | **Spec**: [spec.md](spec.md)
**Spec ID**: 007-json-pcloud-storage | **Status**: Planning

## Summary

Add pCloud as a second JSON cloud storage backend by following the exact same 3-file pattern established in v2.7.0 for Google Drive: transport adapter → storage plugin module → app.py registration. The `json_storage_core` is unchanged; only a new transport and plugin wrapper are added.

## Technical Context

**Language/Version**: Python 3.12 (Flask backend), ES6 vanilla JS (frontend)
**Primary Dependencies**: `requests` (pCloud REST API; already in requirements or will be added), `json_storage_core` (existing)
**Storage**: pCloud cloud storage at `/Acquacotta/` path; IndexedDB (browser-side, credentials only)
**Testing**: pytest (existing test suite)
**Target Platform**: Linux container (Podman, UBI base image)
**Performance Goals**: 1 API call per batch write (same as Drive transport)
**Constraints**: Server stays stateless — no pCloud tokens stored server-side (constitution §5). HTTPS required for OAuth redirect.
**Scale/Scope**: Single-user per-session model, same as all other storage plugins.

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| Privacy by Design | ✅ | No analytics; tokens in IndexedDB only |
| User Data Ownership | ✅ | Data lives in user's own pCloud account |
| Simplicity & Focus | ✅ | Follows existing pattern; no new abstractions |
| Timer Agnosticism | ✅ | Storage layer only; timer unaffected |
| Offline-First | ✅ | IndexedDB is source of truth; pCloud is remote sync |
| Container-Ready | ✅ | No new persistent volumes; env vars for config |

## Project Structure

### Documentation (this feature)

```text
.specify/specs/007-json-pcloud-storage/
├── spec.md       # Feature spec
└── plan.md       # This file
```

### Source Code Changes

```text
transports/
└── pcloud_transport.py        # NEW: 4-function transport interface

json_pcloud_storage.py         # NEW: 11-function storage plugin contract

app.py                         # MODIFY: import + register json-pcloud plugin

requirements.txt               # MODIFY: add `requests` if not present

templates/index.html           # MODIFY: pCloud OAuth UI (login button, status card)
```

## Implementation Steps

### Phase 1: Transport Layer

**File**: `transports/pcloud_transport.py`

pCloud REST API base: `https://api.pcloud.com/` (or `eapi.pcloud.com` for EU accounts).

Key endpoints:
- `getfolder` — list folder contents (used in `ensure_directory` / `file_exists`)
- `createfolder` — create folder if missing (`ensure_directory`)
- `getfilelink` → download (`download_file`)
- `uploadfile` — multipart upload (`upload_file`)
- `listfolder` — check file existence (`file_exists`)

The transport receives a `pcloud_token` (OAuth access token) and `folder_path` string (`/Acquacotta`). It wraps the pCloud REST API with `requests`.

```python
class PCloudTransport:
    BASE = "https://api.pcloud.com"

    def __init__(self, token, folder_path="/Acquacotta"):
        self._token = token
        self._folder_path = folder_path
        self._folder_id_cache = None

    def ensure_directory(self): ...   # createfolderifnotexists
    def download_file(self, filename): ...  # getfilelink → GET content
    def upload_file(self, filename, content): ...  # uploadfile multipart
    def file_exists(self, filename): ...  # listfolder + check
```

### Phase 2: Storage Plugin Module

**File**: `json_pcloud_storage.py`

Exact structural mirror of `json_google_drive_storage.py` with Google Drive replaced by `PCloudTransport`. The module parameter is `pcloud_token` + `folder_path` instead of `drive_service` + `folder_id`.

Functions (same 11 as Drive plugin):
1. `build_context(credentials, request_creds)` → `{"token": ..., "location": ...}`
2. `get_pomodoros(token, folder_path, start_date, end_date)`
3. `save_pomodoro(token, folder_path, pomodoro)`
4. `save_pomodoros_batch(token, folder_path, new_pomodoros)`
5. `update_pomodoro(token, folder_path, pomodoro_id, update_fields)`
6. `delete_pomodoro(token, folder_path, pomodoro_id)`
7. `get_settings(token, folder_path, defaults)`
8. `save_settings(token, folder_path, settings_data, replace_all=False)`
9. `get_mcp_state(token, folder_path)` — stores `mcp_access.json` same as Drive
10. `set_mcp_state(token, folder_path, enabled, epoch)`
11. `deduplicate_pomodoros(token, folder_path)`
12. `count_pomodoros(token, folder_path)`
13. `clear_pomodoros(token, folder_path)`

PLUGIN_METADATA:
```python
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
```

### Phase 3: app.py Registration

Three additions to `app.py`:

1. `import json_pcloud_storage`
2. `plugin_registry.register("storage", "json-pcloud", json_pcloud_storage, json_pcloud_storage.PLUGIN_METADATA)`
3. `_provision_json_pcloud(credentials, user_email, requested_path)` function + add `"json-pcloud": _provision_json_pcloud` to dispatch table in `_provision_storage()`

The `credentials` for pCloud will be `{"pcloud_token": "<access_token>"}` extracted from the session/IndexedDB payload (server remains stateless).

### Phase 4: pCloud OAuth Flow

pCloud OAuth 2.0 endpoints:
- Auth: `https://my.pcloud.com/oauth2/authorize`
- Token: `https://api.pcloud.com/oauth2_token`

New Flask routes:
- `GET /auth/pcloud` — redirect to pCloud authorize URL
- `GET /auth/pcloud/callback` — exchange code for token, store in IndexedDB-bound response

The token is returned to the frontend the same way the Google OAuth token is — the server hands it off to the JS layer which stores it in IndexedDB. No server-side session persistence.

Frontend: new `loginPCloud()` function in `index.html`, analogous to the Google login button handler.

### Phase 5: Frontend Plugin Card

The plugin card for `json-pcloud` in `loadPlugins()`:
- Shows folder path (`/Acquacotta` default)
- "Open pCloud" link to `https://my.pcloud.com`
- Login button triggers `loginPCloud()`
- Active status badge

Minimal change: add `json-pcloud` to the existing plugin card conditional logic, similar to `json-google-drive`.

## Complexity Tracking

No constitution violations — this follows the established pattern exactly.

## Open Questions

1. **EU vs US API endpoint**: pCloud has `api.pcloud.com` (US) and `eapi.pcloud.com` (EU). The token response indicates which location to use (`locationid` field). The transport should respect this.
2. **`requests` dependency**: Check if already in `requirements.txt`; add if missing.
3. **Mandatory plugin designation**: `json-pcloud` should be optional (same as `json-google-drive`). Only `sheets` is mandatory? Actually check: `json-google-drive` is the default but not mandatory in the strict sense — confirm before implementing.
