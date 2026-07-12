# Feature Specification: Per-User Extension (Plugin) Enablement

**Feature Branch**: `008-per-user-extensions`
**Created**: 2026-07-12
**Status**: Draft
**Input**: Complete the per-user plugin work started in spec 007. 007 made the *storage* backend a per-user choice; extension plugins (e.g. Todos) are still enabled/disabled process-globally, so one user's toggle changes the app for everyone — on both the web UI and the MCP server.

## Overview

Acquacotta has extension plugins (today: **Todos**) that add UI and MCP tools. Enabling or disabling an extension is currently a **process-global** action: `activate_extension`/`deactivate_extension` mutate shared server state, and the MCP server hardcodes `activate_extension("todos")`. On a hosted multi-user service this means one user turning Todos off removes it for everyone, and every MCP caller sees the same globally-active tool set regardless of their own choice.

This feature makes each user's extension enablement an **authoritative, per-user preference**, consistent with how spec 007 handles the storage backend. A user's choice affects only that user, on both the web UI and MCP.

The source of truth is the user's own `plugin_state_<id>` preference, which already lives in the user's storage (Google Sheets/JSON-on-Drive) and browser cache — consistent with the constitution's **User Data Ownership** principle. Extensions default to **enabled** unless the user has explicitly disabled one.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - One user's extension toggle never affects another (Priority: P1)

Two users use the hosted app concurrently. One disables the Todos extension; the other still sees and uses Todos normally.

**Why this priority**: This is the core defect — extension enablement is shared, so the app silently reconfigures for unrelated users. Per-user isolation is a correctness requirement for a multi-user service.

**Independent Test**: With User A disabling Todos, confirm User B's web UI still shows the Todos tab and User B's MCP session still exposes the Todos tools.

**Acceptance Scenarios**:

1. **Given** User A disables Todos, **When** User B loads the app, **Then** User B still sees Todos (their own choice is unchanged).
2. **Given** User A disables Todos, **When** User B calls a Todos MCP tool, **Then** it works for User B.

---

### User Story 2 - MCP tools are gated on the calling user's own choice (Priority: P1)

An MCP caller only reaches an extension's tools while that extension is enabled in *their* account.

**Why this priority**: MCP currently exposes a globally-active tool set. A caller who disabled Todos should not have Todos tools act on their data, and a caller who has it enabled must.

**Independent Test**: With Todos disabled for a caller, a Todos tool call returns a clear "plugin disabled" error; with it enabled, the same call succeeds.

**Acceptance Scenarios**:

1. **Given** a caller with Todos disabled, **When** they call a Todos tool, **Then** they get a clear error telling them to enable the plugin — no data change.
2. **Given** a caller with Todos enabled (or no explicit choice), **When** they call a Todos tool, **Then** it works.

---

### User Story 3 - Choice persists and defaults to enabled (Priority: P2)

A user's extension choice persists across reloads, sign-out/in, and service restarts. A user who has never chosen sees extensions **enabled** by default.

**Acceptance Scenarios**:

1. **Given** a new user who has made no choice, **When** they load the app or call MCP, **Then** extensions are enabled by default.
2. **Given** a user who disabled Todos, **When** they reload or the service restarts, **Then** Todos stays disabled for them.

---

### Edge Cases

- **No preference recorded**: extension defaults to enabled (newly added plugins are on by default).
- **Service restart**: enablement is derived from the user's own preference, not in-memory global state, so it survives restarts.
- **Stale global state**: a leftover process-global active flag must not override a user's own recorded choice.

## Requirements *(mandatory)*

- **FR-001**: Extension enablement MUST be resolved per-user from the requesting user's own preference, never from process-global state.
- **FR-002**: One user's extension enable/disable MUST NOT change enablement for any other user, on either the web UI or MCP.
- **FR-003**: The MCP server MUST gate each extension's tools on the calling user's own enablement; a disabled extension's tools MUST refuse with a clear, actionable error and make no data change.
- **FR-004**: An extension with no recorded user choice MUST default to enabled.
- **FR-005**: A user's extension choice MUST persist across reload, sign-out/in, and service restart.
- **FR-006**: The web UI (tabs, settings cards, toggles) MUST reflect the current user's own enablement.
- **FR-007**: This feature MUST NOT store additional user content/PII on the server beyond what already exists; extension preferences live in the user's own storage/cache.

## Success Criteria *(mandatory)*

- **SC-001**: 0 instances of one user's extension toggle changing enablement for another user (web or MCP).
- **SC-002**: 100% of MCP tool calls for a disabled extension are refused with a clear error and no data change; 100% for an enabled (or default) extension succeed.
- **SC-003**: A user with no recorded choice gets extensions enabled by default, 100% of the time.
- **SC-004**: A disabled-Todos choice survives a service restart 100% of the time.

## Assumptions

- The per-user extension preference is the existing `plugin_state_<id>` setting already written by the client and synced to the user's storage; no new server-side per-user record is required.
- MCP callers are identified by their token (which carries the user's storage location), so the MCP server can read the caller's own preference.
- Only the Todos extension exists today; the design applies uniformly to any future extension.

## Out of Scope

- Changes to storage-backend selection (shipped in 007).
- The sync-performance batching of IndexedDB writes (tracked separately, issue #117).
