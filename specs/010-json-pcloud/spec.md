# Feature Specification: JSON on pCloud Storage Plugin

**Feature Branch**: `feature/096-json-pcloud`
**Created**: 2026-07-21
**Status**: Implemented
**Version**: 0.2.0
**Author**: Scott McCarty
**Spec ID**: 010-json-pcloud
**GitHub Issue**: #96

## Overview

Add pCloud as a second JSON storage backend. Implements the shared 4-function transport interface (`download_file`, `upload_file`, `ensure_directory`, `file_exists`) against the pCloud API, then wires it into `json_storage_core` exactly as the Google Drive transport does. Registered as plugin ID `json-pcloud`.

Scott already has pCloud infrastructure and an MCP server (`mcp__pcloud`) for file operations, so the API patterns are well understood.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Provision pCloud Storage and Log In (Priority: P1)

A user who prefers pCloud over Google Drive opens Settings > Plugins, sees the "JSON on pCloud" storage plugin, and switches to it. The app creates `/Acquacotta/` on pCloud, stores credentials in IndexedDB, and begins syncing.

**Why this priority**: The entire feature is worthless without the ability to authenticate and provision. Must ship first.

**Independent Test**: Can be tested by selecting the pCloud plugin in Settings > Plugins, completing the OAuth flow, and verifying `/Acquacotta/pomodoros.json` appears in the user's pCloud.

**Acceptance Scenarios**:

1. **Given** the user is not logged in to pCloud, **When** they select "JSON on pCloud" in Settings > Plugins and click the login button, **Then** the pCloud OAuth flow opens and returns a token.
2. **Given** the user has completed OAuth, **When** the app provisions storage, **Then** `/Acquacotta/` exists (or is created) in pCloud and `pomodoros.json` and `settings.json` are present.
3. **Given** provisioning succeeds, **When** the app loads, **Then** `activeStorage` is `json-pcloud` and the plugin card shows "On".

---

### User Story 2 — Sync Pomodoros to pCloud (Priority: P2)

A user records a Pomodoro session. The timer completes, the session is saved to IndexedDB, and the background sync writes it to `/Acquacotta/pomodoros.json` on pCloud.

**Why this priority**: Core data durability — the whole point of a storage plugin.

**Independent Test**: Manually log a Pomodoro, then check pCloud via the MCP tool or web UI to confirm the JSON was written with the correct record.

**Acceptance Scenarios**:

1. **Given** the active backend is `json-pcloud`, **When** a Pomodoro is saved, **Then** `pomodoros.json` on pCloud is updated with the new record.
2. **Given** multiple Pomodoros are queued offline, **When** the batch sync runs, **Then** all are written in a single `upload_file` call (no duplicates).
3. **Given** `pomodoros.json` does not yet exist, **When** the first Pomodoro is saved, **Then** the file is created in `/Acquacotta/`.

---

### User Story 3 — Plugin Card Shows pCloud Status (Priority: P3)

The Settings > Plugins page shows the pCloud plugin card with its active/inactive state, an "Open Folder" link to `/Acquacotta/` on pCloud, and a sync status indicator.

**Why this priority**: Quality-of-life. The core plugin works without this, but users need visibility.

**Independent Test**: With the plugin active, inspect the plugin card for a link and sync count.

**Acceptance Scenarios**:

1. **Given** the plugin is active and provisioned, **When** the Plugins tab loads, **Then** the card shows the pCloud folder path and an "Open Folder" button.
2. **Given** the plugin is inactive, **When** the Plugins tab loads, **Then** the card shows toggle "Off" with no location link.

---

### Edge Cases

- What happens when pCloud returns a 401 (token expired)? → Surface auth error, prompt re-login.
- What happens when `/Acquacotta/` does not exist on first provision? → `ensure_directory` creates it.
- What happens when `pomodoros.json` is corrupt? → `json_storage_core.parse_pomodoros` returns `[]`; existing behaviour unchanged.
- What happens if the user switches back to Google Drive? → `active_storage` changes; pCloud credentials remain in IndexedDB for future use.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST implement `PCloudTransport` with `download_file`, `upload_file`, `ensure_directory`, `file_exists` matching the same 4-function contract as `GoogleDriveTransport`.
- **FR-002**: System MUST create `json_pcloud_storage.py` with the same 11-function plugin contract as `json_google_drive_storage.py`.
- **FR-003**: System MUST register the plugin as `json-pcloud` in `app.py` alongside existing storage plugins.
- **FR-004**: System MUST implement a `pcloud_oauth` auth flow so users can authenticate without sharing credentials with the server.
- **FR-005**: System MUST store pCloud tokens in IndexedDB only (server remains stateless — constitution §5).
- **FR-006**: System MUST add `_provision_json_pcloud` to `_provision_storage()` dispatch table.
- **FR-007**: Plugin MUST set `PLUGIN_METADATA.frontend_fields = ["pcloud_folder_path"]`.
- **FR-008**: Default storage path on pCloud MUST be `/Acquacotta/` (matches issue spec).
- **FR-009**: System MUST NOT store pCloud refresh tokens server-side (constitution §5 — no server-side credential persistence).

### Key Entities

- **PCloudTransport**: Adapter that calls pCloud REST API; holds folder path + file-id cache.
- **json_pcloud_storage**: Plugin module; wires `PCloudTransport` to `json_storage_core`.
- **pcloud_oauth auth flow**: Separate from `google_oauth`; uses pCloud's `/oauth2_token` endpoint.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can complete the pCloud OAuth flow and have `/Acquacotta/pomodoros.json` written within 30 seconds of first login.
- **SC-002**: All existing storage plugin tests continue to pass (no regression to `json-google-drive` or `sheets`).
- **SC-003**: `save_pomodoros_batch` writes all queued items in exactly 1 pCloud API call.
- **SC-004**: Switching between `json-pcloud` and `json-google-drive` backends produces no data loss.

## Assumptions

- **Google remains the identity provider; pCloud is storage only.** The user signs in with Google (which is how the app learns their email and resolves their per-user backend, spec 007) and then *links* a pCloud account for storage. Making pCloud a second identity provider is a much larger change to per-user backend resolution and is out of scope here.
- The pCloud access token rides in the browser's IndexedDB `auth` store alongside the Google credentials and is sent on each request, exactly like the Google token. A Google re-login merges into — rather than replaces — that record, so a linked pCloud account survives signing back in.
- pCloud OAuth access tokens are long-lived (valid until revoked), so there is no refresh-token flow to implement. An expired or revoked token surfaces as an auth error and the user re-links.
- The storage location for this backend is a **path** (`/Acquacotta`), not an opaque id — pCloud's API accepts paths directly, so no folder-id cache is needed.

## Out of Scope

- pCloud as an identity provider (signing in *with* pCloud instead of Google).
- Migrating existing data between `json-google-drive` and `json-pcloud` (the Sheets → JSON migration tool is not generalized here).
- Nested custom folder paths whose parent directories do not already exist.
- **MCP access over pCloud.** The MCP server's sealed tokens carry a Google Drive folder id and Google credentials, and every tool resolves storage through `json_google_drive_storage`. Serving pCloud-backed users over MCP means changing the sealed-token payload and the MCP auth path — a separate spec. Until then, MCP access remains Drive-backed only.
