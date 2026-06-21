# Feature Specification: JSON Storage Core + Google Drive Transport

**Feature Branch**: `feature/83-json-google-drive`  
**Created**: 2026-06-19  
**Status**: Draft  
**Input**: GitHub Issue #83 — JSON storage core + Google Drive transport (json-google-drive plugin)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - New User Gets JSON Backend by Default (Priority: P1)

A new user signs up via Google OAuth and their pomodoro data is stored as JSON files on their Google Drive instead of a Google Spreadsheet. The `Acquacotta/` folder and `pomodoros.json` / `settings.json` files are created automatically on first login.

**Why this priority**: This is the core value proposition — faster, simpler storage that eliminates the Sheets API bottleneck (syncing 2402 pomodoros took minutes; a single JSON file write is sub-second).

**Independent Test**: Log in with a fresh Google account. Verify `Acquacotta/` folder is created on Drive with `pomodoros.json` and `settings.json`. Save a pomodoro, reload, confirm it persists.

**Acceptance Scenarios**:

1. **Given** a new user with no Acquacotta data, **When** they complete OAuth login, **Then** an `Acquacotta/` folder is created on their Google Drive containing empty `pomodoros.json` and `settings.json` files, and `folder_id` is stored in IndexedDB.
2. **Given** a logged-in new user, **When** they save their first pomodoro, **Then** it appears in `pomodoros.json` on Drive and is retrievable on page reload.

---

### User Story 2 - Existing User CRUD Operations (Priority: P1)

A logged-in user can create, read, update, and delete pomodoros through the existing UI. All operations go through the JSON storage backend transparently — the user experience is identical to the Sheets backend but faster.

**Why this priority**: Without full CRUD, the backend is unusable. This shares P1 with Story 1 because login without CRUD is meaningless.

**Independent Test**: Log in, create 5 pomodoros, edit one, delete one, verify the remaining 4 are correct. Filter by date range. Run deduplication. Export CSV.

**Acceptance Scenarios**:

1. **Given** a user with existing pomodoros, **When** they view the history, **Then** all pomodoros are loaded from `pomodoros.json` sorted by start_time descending.
2. **Given** a user editing a pomodoro, **When** they save changes, **Then** the update is reflected in `pomodoros.json` on Drive.
3. **Given** a user deleting a pomodoro, **When** they confirm deletion, **Then** it is removed from `pomodoros.json` on Drive.
4. **Given** a user with duplicate pomodoros, **When** they run deduplication, **Then** duplicates are removed and the count is reported.

---

### User Story 3 - Plugin-Aware Storage Context (Priority: P2)

The `_storage_context()` function and OAuth callback dynamically adapt to whichever storage plugin is active. The Sheets plugin continues to work unchanged. The JSON plugin gets a Drive service and `folder_id` instead of a Sheets service and `spreadsheet_id`.

**Why this priority**: Without this, the JSON plugin can't integrate into the existing app.py dispatch layer. But it's P2 because it's infrastructure, not user-visible.

**Independent Test**: Activate the `json-google-drive` plugin, verify API calls use Drive. Switch back to `sheets`, verify API calls use Sheets.

**Acceptance Scenarios**:

1. **Given** `json-google-drive` is the active storage plugin, **When** any API endpoint calls `_storage_context()`, **Then** it returns a context with a Drive service and `folder_id` (not a Sheets service and `spreadsheet_id`).
2. **Given** `sheets` is the active storage plugin, **When** any API endpoint calls `_storage_context()`, **Then** behavior is unchanged from current implementation.
3. **Given** the OAuth callback completes, **When** `json-google-drive` is active, **Then** `folder_id` is written to IndexedDB settings store (not `spreadsheet_id`).

---

### User Story 4 - Settings Persistence (Priority: P2)

User settings (timer presets, pomodoro types, sound preferences) are stored in `settings.json` on Drive and survive across sessions.

**Why this priority**: Settings must work for the app to be usable, but a user can still track pomodoros with default settings.

**Independent Test**: Change timer presets and pomodoro types, log out, log back in, verify settings are restored.

**Acceptance Scenarios**:

1. **Given** a user saves custom settings, **When** they reload the page, **Then** settings are loaded from `settings.json` on Drive.
2. **Given** a user uses "Overwrite Google" for settings, **When** the operation completes, **Then** `settings.json` on Drive matches the local settings exactly.

---

### Edge Cases

- What happens when the `Acquacotta/` folder is deleted from Drive? → Re-create on next API call.
- What happens when `pomodoros.json` is manually edited and contains invalid JSON? → Return empty list, don't crash.
- What happens when the user has no network? → Offline-first IndexedDB handles it; sync fails gracefully.
- What happens during concurrent writes from multiple tabs? → Last write wins (same as Sheets behavior).
- What happens when `pomodoros.json` grows to 5 MB (a decade of data)? → Still sub-second read/write; Drive API handles it fine.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST implement `json_storage_core.py` with transport-agnostic serialization, CRUD, filtering, dedup, count, and clear operations.
- **FR-002**: System MUST define a transport interface with `download_file`, `upload_file`, `ensure_directory`, and `file_exists` methods.
- **FR-003**: System MUST implement `transports/google_drive_transport.py` implementing the transport interface using the Google Drive API v3.
- **FR-004**: System MUST implement `json_google_drive_storage.py` wiring core + transport to fulfill the full storage plugin contract (11 functions).
- **FR-005**: System MUST create `Acquacotta/` folder on Drive on first use via `ensure_directory`.
- **FR-006**: System MUST read/write `pomodoros.json` and `settings.json` within the `Acquacotta/` folder.
- **FR-007**: System MUST register as `json-google-drive` storage plugin with proper `PLUGIN_METADATA`.
- **FR-008**: New users MUST default to `json-google-drive` backend.
- **FR-009**: System MUST work with existing `drive.file` OAuth scope (no new permissions).
- **FR-010**: System MUST implement plugin-aware `_storage_context()` using each plugin's `build_context()`.
- **FR-011**: System MUST implement plugin-aware IndexedDB hydration in the OAuth callback, writing `folder_id` for JSON plugins and `spreadsheet_id` for Sheets.

### Key Entities

- **JsonStorageCore**: Transport-agnostic module handling serialization, CRUD, filtering, dedup on plain Python dicts/lists.
- **GoogleDriveTransport**: Thin adapter implementing the 4-function transport interface against Google Drive API v3.
- **JsonGoogleDriveStorage**: Storage plugin module wiring core + transport, implementing the 11-function storage contract.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Full read of all pomodoros completes in under 2 seconds (vs. minutes with Sheets for 2400+ records).
- **SC-002**: All 11 storage contract functions pass integration tests against a real Google Drive folder.
- **SC-003**: Existing Sheets backend continues to work unchanged when activated.
- **SC-004**: Adding a future transport (e.g., pCloud) requires only ~50 lines of transport code + a thin plugin file.
- **SC-005**: No new OAuth permissions required — `drive.file` scope covers both Sheets and Drive file operations.
