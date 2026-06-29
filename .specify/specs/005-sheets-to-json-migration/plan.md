# Implementation Plan: Sheets-to-JSON Migration Tool

**Branch**: `feature/84-sheets-to-json-migration` | **Date**: 2026-06-29 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/005-sheets-to-json-migration/spec.md`

## Summary

Add a backend API endpoint and Settings UI that reads all data from the Sheets storage plugin, writes it to JSON-on-Drive, switches the active backend, and persists the mapping. The existing `storage_api` and `plugin_registry` infrastructure handles both reading (Sheets) and writing (JSON) — migration is essentially a cross-backend copy.

## Technical Context

**Language/Version**: Python 3.x / Flask + Vanilla JS
**Primary Dependencies**: Flask, google-api-python-client (Sheets), json_google_drive_storage, plugin_registry
**Storage**: Google Sheets (source) → JSON on Google Drive (target)
**Testing**: Manual verification in browser
**Target Platform**: Linux container (OCI)
**Constraints**: Offline-first, stateless server, no persistent volumes

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| Privacy by Design | ✅ Pass | No new data collection. Migration uses existing OAuth credentials. |
| User Data Ownership | ✅ Pass | User's Sheet is preserved. JSON files live in user's Drive. |
| Simplicity & Focus | ✅ Pass | Single button, clear confirmation, no new concepts. |
| Timer Agnosticism | ✅ N/A | No timer changes. |
| Offline-First | ✅ Pass | Migration requires network (reading Sheets, writing Drive), but failure is non-destructive. IndexedDB cache still works. |
| Container-Ready | ✅ Pass | No new env vars or volumes. |

## Architecture

### Migration Flow

```
User clicks "Migrate to JSON" → Confirmation modal
    ↓
POST /api/migrate-to-json
    ↓
1. Read all pomodoros from Sheets (sheets_storage.get_pomodoros)
2. Read settings from Sheets (sheets_storage.get_settings)
3. Provision JSON-on-Drive folder (json_google_drive_storage)
4. Write pomodoros to JSON (json_google_drive_storage.save_pomodoros_batch)
5. Write settings to JSON (json_google_drive_storage.save_settings)
6. Update user_storage.json to point to json-google-drive + folder_id
7. Activate json-google-drive in plugin_registry
    ↓
Return success + counts → Frontend updates UI
```

### Key Design Decision: Server-Side Migration

Migration runs entirely on the server via a single API call. The server has access to both storage backends and can read/write atomically. The frontend just triggers it and shows progress.

## Project Structure

### Files to Modify

```text
app.py                          # Add /api/migrate-to-json endpoint
templates/index.html            # Add storage backend indicator + migrate button + modal
static/js/storage.js            # Add migration trigger + progress UI logic
```

### No New Files

The migration logic lives in `app.py` as a single endpoint. No new Python modules needed — it uses existing `sheets_storage`, `json_google_drive_storage`, and `plugin_registry` directly.

## Implementation Steps

### Step 1: Backend API — `/api/migrate-to-json` (app.py)

Add a new Flask endpoint that:
1. Verifies user is logged in and on Sheets backend
2. Builds a Sheets context and reads all pomodoros + settings
3. Provisions the JSON-on-Drive folder (reuses `_provision_json_google_drive`)
4. Builds a JSON context and writes all data
5. Updates `user_storage.json` mapping
6. Switches `plugin_registry.activate_storage("json-google-drive")`
7. Returns JSON with success status, pomodoro count, and folder ID

Error handling: if any step fails, do NOT switch the backend. Return error with the failed step.

### Step 2: Frontend — Storage Backend Indicator (index.html)

In the Settings `google-logged-in` section, add:
- A line showing "Storage: Google Sheets" or "Storage: JSON on Drive"
- A "Migrate to JSON" button (only visible when on Sheets)

### Step 3: Frontend — Migration Modal (index.html)

Add a confirmation modal:
- Title: "Migrate to JSON on Drive"
- Body: Explains what will happen (data copied, Sheet preserved, backend switches)
- Buttons: Cancel / Migrate

### Step 4: Frontend — Migration Logic (storage.js)

Add JavaScript:
- `showMigrateToJsonModal()` — shows the confirmation modal
- `runMigrateToJson()` — calls POST `/api/migrate-to-json`, shows progress, handles success/error
- Update `updateCloudUI()` to show storage backend indicator and conditionally show the migrate button

## Complexity Tracking

No constitution violations. This is a straightforward data-copy operation using existing APIs.
