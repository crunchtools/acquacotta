# Feature Specification: Sheets-to-JSON Migration Tool

**Feature Branch**: `feature/84-sheets-to-json-migration`
**Created**: 2026-06-29
**Status**: Draft
**Input**: GitHub Issue #84

## User Scenarios & Testing

### User Story 1 - Migrate Sheets Data to JSON (Priority: P1)

As an existing Acquacotta user with data in Google Sheets, I want to migrate my data to the JSON-on-Drive backend so I get faster sync and plugin support without losing any data.

**Why this priority**: This is the entire purpose of the feature. Without this, Sheets users are stuck on the old backend.

**Independent Test**: Sign in with a Google account that has an existing Sheets backend with pomodoros. Click "Migrate to JSON" in Settings. Verify all pomodoros appear in the JSON backend and the original Sheet is untouched.

**Acceptance Scenarios**:

1. **Given** a logged-in user on the Sheets backend with 50+ pomodoros, **When** they click "Migrate to JSON" and confirm, **Then** all pomodoros are copied to `Acquacotta/pomodoros.json` on Drive, settings are copied to `Acquacotta/settings.json`, the active backend switches to `json-google-drive`, and the original Sheet is not deleted.
2. **Given** a user on the Sheets backend, **When** migration fails partway (e.g., network error during Drive write), **Then** the user remains on the Sheets backend with no data loss and sees an error message.
3. **Given** a user who already has an `Acquacotta/` folder on Drive (e.g., from a previous migration attempt), **When** they migrate, **Then** they are warned and can choose to overwrite or cancel.

---

### User Story 2 - See Current Storage Backend (Priority: P2)

As an Acquacotta user, I want to see which storage backend I'm using so I know whether migration is available or already complete.

**Why this priority**: Users need to know their current state before they can make a migration decision. Simple UI addition.

**Independent Test**: Sign in with Google. The Settings page shows "Storage Backend: Google Sheets" or "Storage Backend: JSON on Drive" with the appropriate action available.

**Acceptance Scenarios**:

1. **Given** a user on the Sheets backend, **When** they open Settings, **Then** they see "Storage: Google Sheets" and a "Migrate to JSON" button.
2. **Given** a user already on the JSON backend, **When** they open Settings, **Then** they see "Storage: JSON on Drive" and no migration button.
3. **Given** a user not signed in to Google, **When** they open Settings, **Then** they see no storage backend info (local-only mode).

---

### User Story 3 - Migration Progress Feedback (Priority: P3)

As a user migrating from Sheets to JSON, I want to see progress during migration so I know it's working and how long to wait.

**Why this priority**: Large datasets (2000+ pomodoros) can take time. Without feedback, the user may think the app is frozen.

**Independent Test**: Initiate migration with 100+ pomodoros. Verify a progress indicator shows "Reading from Sheets...", "Writing to Drive...", "Switching backend..." stages.

**Acceptance Scenarios**:

1. **Given** a user initiating migration, **When** the process is running, **Then** a progress indicator shows the current step (reading, writing, switching).
2. **Given** migration completes successfully, **Then** the user sees a success message with the pomodoro count and a note that their Sheet was preserved.

---

### Edge Cases

- What happens if the user has duplicate pomodoro IDs in Sheets? Deduplicate during migration.
- What happens if the user has no pomodoros in Sheets? Migration succeeds with empty JSON files.
- What happens if the user's Drive quota is full? Migration fails gracefully, user stays on Sheets.
- What happens if the user migrates, then wants to go back to Sheets? Out of scope for this feature (they can manually switch via the plugin registry, and their Sheet is preserved).

## Requirements

### Functional Requirements

- **FR-001**: System MUST read all pomodoros from the active Sheets backend via `storage_api.get_pomodoros()`.
- **FR-002**: System MUST read all settings from the active Sheets backend via `storage_api.get_settings()`.
- **FR-003**: System MUST write pomodoros and settings to the JSON-on-Drive backend.
- **FR-004**: System MUST switch `plugin_registry.activate_storage()` to `json-google-drive` on success.
- **FR-005**: System MUST persist the user's storage location mapping so the switch survives page reload.
- **FR-006**: System MUST NOT delete the original Google Sheet.
- **FR-007**: System MUST leave the user on Sheets if migration fails at any step.
- **FR-008**: System MUST deduplicate pomodoros by ID during migration.
- **FR-009**: Settings page MUST display the current active storage backend.
- **FR-010**: "Migrate to JSON" button MUST only appear for users currently on the Sheets backend.

### Key Entities

- **Pomodoro**: Time tracking record (id, date, duration, type, notes, linked_todo_id)
- **Settings**: User preferences (timer presets, break durations, type definitions, timezone)
- **Storage Location Mapping**: `user_storage.json` — maps user+plugin to their storage location ID

## Success Criteria

### Measurable Outcomes

- **SC-001**: Migration preserves 100% of pomodoro records (count before = count after).
- **SC-002**: Migration completes in under 30 seconds for datasets up to 5,000 pomodoros.
- **SC-003**: Failed migration results in zero data loss — user remains on Sheets with all data intact.
- **SC-004**: After migration, all dashboard features (timer, history, reports, todos) work identically on the JSON backend.
