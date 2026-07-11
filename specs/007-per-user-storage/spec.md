# Feature Specification: Per-User Storage Backend Selection

**Feature Branch**: `007-per-user-storage`
**Created**: 2026-07-11
**Status**: Draft
**Input**: User description: "Per-user storage backend selection: authoritative per-user backend choice, no global race, correct folder-vs-spreadsheet id handling"

## Overview

Each Acquacotta user syncs their data to one of two storage backends in their own Google account: **Google Sheets** (a spreadsheet) or **JSON-on-Google-Drive** (a folder). Today the app tracks which backend is "active" as a single **process-wide** value rather than a per-user choice. As a result a user's backend selection is not reliably remembered, is contaminated by other activity, and their two location identifiers (a Drive **folder id** and a Sheets **spreadsheet id**) get crossed. The observable effect is that a user signs in and the app silently uses the *wrong* backend, so their data never loads.

This feature makes each user's storage-backend choice **authoritative, per-user, and durable across sign-out**, and makes the two location identifiers unambiguous end-to-end, so login and sync are deterministic for every user.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Returning user's backend and data load reliably (Priority: P1)

A user who has previously chosen a storage backend signs out and signs back in (possibly on a new device, after clearing their browser, or after the service restarts). The app resolves *their* backend and *their* data location, and their data loads — every time, without the user having to re-select anything or paste an id.

**Why this priority**: This is the core failure today — a JSON user is silently resolved to Sheets on re-login and their data never appears. Without this, the app is unusable across sign-out for anyone who isn't on the process-wide default backend.

**Independent Test**: With a user whose recorded backend is JSON-on-Drive, sign out completely and sign back in; confirm the app resolves to JSON, opens their existing folder, and loads their pomodoros and todos — with no dependence on prior browser state or which user last used the service.

**Acceptance Scenarios**:

1. **Given** a user whose recorded choice is JSON-on-Drive, **When** they sign out and sign back in, **Then** the app resolves to JSON, uses their existing folder, and their data loads.
2. **Given** a user whose recorded choice is Sheets, **When** they sign out and sign back in, **Then** the app resolves to Sheets, uses their existing spreadsheet, and their data loads.
3. **Given** the service has just restarted (no in-memory state), **When** any returning user signs in, **Then** their backend is resolved from their durable choice, not from a default.

---

### User Story 2 - Concurrent users never affect each other's backend (Priority: P1)

Two users are active at the same time on different backends (one on Sheets, one on JSON). Each user's requests always use *their own* backend; neither user's activity changes the backend the other user gets.

**Why this priority**: The app is a hosted multi-user service. A shared process-wide "active backend" means one user's session can flip another user onto the wrong backend (last-writer-wins), corrupting where data is read/written. Per-user isolation is a correctness and data-safety requirement.

**Independent Test**: Drive requests for two users with different recorded backends interleaved; confirm each user's operations consistently target their own backend and location regardless of the other's activity or ordering.

**Acceptance Scenarios**:

1. **Given** User A on Sheets and User B on JSON acting concurrently, **When** their requests interleave, **Then** A's operations always target Sheets and B's always target JSON.
2. **Given** User A changes their backend, **When** User B makes a request, **Then** User B's resolved backend is unchanged.

---

### User Story 3 - The login form uses the correct location field per backend (Priority: P2)

At sign-in, the user is offered the location field appropriate to their backend — a **Drive Folder ID** for JSON, a **Spreadsheet ID** for Sheets — and the value they enter (or that is remembered) is always transmitted and interpreted as that kind of id, never crossed.

**Why this priority**: Folder ids and spreadsheet ids are both opaque Google ids and are currently conflated (the app stored a single "spreadsheet id" and sent it for both backends). A folder id sent as a spreadsheet id makes provisioning fail. This must be correct for JSON users to sign in at all with an explicit id.

**Independent Test**: On a JSON account, confirm the sign-in form shows a "Drive Folder ID" field, an entered folder id is accepted and used as a folder, and it is never treated as a spreadsheet id; repeat symmetrically for Sheets.

**Acceptance Scenarios**:

1. **Given** a user whose backend is JSON, **When** the sign-in form is shown, **Then** it offers a Drive Folder ID field and an entered id is used as a folder id.
2. **Given** a user whose backend is Sheets, **When** the sign-in form is shown, **Then** it offers a Spreadsheet ID field and an entered id is used as a spreadsheet id.
3. **Given** either backend, **When** the location field is left blank, **Then** the user's existing location is found automatically (by their recorded choice or by discovery) without creating a duplicate.

---

### User Story 4 - Switching backend is an explicit, durable per-user choice (Priority: P3)

A user deliberately switches their storage backend. That choice is recorded as theirs and is honored on every subsequent request and future sign-in, until they change it again.

**Why this priority**: Backend selection should be a conscious, remembered decision — not something inferred from stale client state or flipped implicitly on page load. This removes the implicit client-driven "toggle" behavior that caused drift.

**Independent Test**: As a user, switch backend, sign out and back in, and confirm the newly chosen backend is the one used; confirm no page-load side effect silently changes it.

**Acceptance Scenarios**:

1. **Given** a user switches to a different backend, **When** they sign out and back in, **Then** the newly chosen backend is used.
2. **Given** a signed-in session, **When** the page loads, **Then** the user's recorded backend is used as-is and is not implicitly changed by the client.

---

### Edge Cases

- **Data in both backends**: A user who has an old spreadsheet *and* a JSON folder is resolved to their **recorded choice**, deterministically — never guessed from which ids happen to be cached.
- **No recorded choice (new or first-time user)**: Resolves to a single, well-defined default backend, and the user can switch; provisioning finds-or-creates their location without duplicating it.
- **Missing/corrupt preference record**: The system fails safe — it does not silently read or write to the wrong backend; the user is guided to (re)select rather than losing or splitting data.
- **Wrong-kind id entered**: A value entered in the folder field is only ever used as a folder id (and vice versa); it is never reinterpreted as the other kind.
- **Stale client state after sign-out**: Leftover ids or flags in the browser do not override the user's recorded backend choice.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST record each user's chosen storage backend as a per-user value that is durable across sign-out, sign-in, and service restarts.
- **FR-002**: The system MUST resolve the active storage backend for any operation from the *requesting user's* recorded choice, never from a value shared across users.
- **FR-003**: One user's backend choice or activity MUST NOT change the backend resolved for any other user.
- **FR-004**: At sign-in, the system MUST provision and open the user's recorded backend and location deterministically, without requiring the user to re-select or re-enter their location.
- **FR-005**: The system MUST store and transmit the JSON location (**folder id**) and the Sheets location (**spreadsheet id**) as distinct, correctly-named values, and MUST NOT use one where the other is expected.
- **FR-006**: The sign-in experience MUST present the location field appropriate to the user's backend and, when a value is provided, use it as that kind of id.
- **FR-007**: When the user provides no location, the system MUST locate the user's existing storage (by recorded choice or by discovery) without creating a duplicate spreadsheet or folder.
- **FR-008**: When a user switches backend, the system MUST persist that as the user's authoritative choice and honor it on all subsequent operations and future sign-ins.
- **FR-009**: The system MUST NOT implicitly change a user's backend as a side effect of page load or restored client state.
- **FR-010**: On a missing, ambiguous, or unreadable preference, the system MUST fail safe (not read/write the wrong backend) and prompt the user to confirm their backend rather than silently defaulting in a way that splits their data.
- **FR-011**: The per-user preference record MUST contain only backend selection and location pointers — no pomodoro, todo, settings content, or other user data/PII beyond the account identifier already required to key it.
- **FR-012**: User content (pomodoros, todos, settings) MUST continue to live only in the user's own Google storage and browser cache; this feature adds no user content to the server.

### Key Entities

- **User Storage Preference**: The per-user record of where and how a user syncs. Attributes: the user's account identifier (key), the chosen backend (Sheets or JSON-on-Drive), and the location pointer for that backend (spreadsheet id or folder id). It is a *pointer*, not user content.
- **Storage Backend**: A supported sync target — "Google Sheets" (identified by a spreadsheet id) or "JSON on Google Drive" (identified by a folder id). Exactly one is active per user at a time.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of returning users (on either backend) are resolved to their own backend and location on sign-in, including after a service restart and with no reliance on prior browser state.
- **SC-002**: 0 instances of a user's backend being determined by another user's activity under concurrent use.
- **SC-003**: 0 instances of a folder id being used as a spreadsheet id (or vice versa) across sign-in and sync.
- **SC-004**: A user who switches backend and signs out/in gets the newly chosen backend 100% of the time.
- **SC-005**: A user with no location entered has their existing storage found without any duplicate spreadsheet or folder being created.
- **SC-006**: The server stores no user content — only the per-user backend/location pointer — verifiable by inspecting what the server persists.

## Assumptions

- A small per-user server-side record mapping account identifier → {backend, location pointer} is acceptable; the constitution's constraint is against storing user **PII/content** on the server, not against a minimal routing pointer. User data itself remains solely in the user's Google storage and browser cache.
- Both backends remain supported; some users are still on Sheets, so this is not a Sheets-removal.
- The default backend for brand-new users is JSON-on-Google-Drive (the current standard post-migration), and new users may switch to Sheets.
- The account identifier used to key the preference is the user's Google account email, already obtained during OAuth.

## Out of Scope

- Removing or deprecating the Google Sheets backend.
- Migrating existing users' data between backends (this feature preserves each user's current backend and data in place).
- Changes to how MCP token access resolves storage (MCP tokens already carry their own folder pointer).
