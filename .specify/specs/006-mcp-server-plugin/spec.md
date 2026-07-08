# Feature Specification: Hosted MCP Server Plugin

**Feature Branch**: `feature/111-mcp-server-plugin`
**Created**: 2026-07-06
**Status**: Draft
**Version**: 0.1.0
**Author**: Scott McCarty
**Input**: GitHub Issue #111 (supersedes #90) + user requirement: "Kagetora and Takeda need to see my todo items, add to them, mark them resolved"

## Overview

Acquacotta stores everything as JSON in the user's own cloud storage, and the web app is already **stateless** — the browser holds the user's Google OAuth credentials plus a `folder_id` and passes them per request (`X-Credentials` header); the server persists nothing. This feature extends that exact model to agents.

We ship a **hosted MCP (Model Context Protocol) server as an Acquacotta plugin** that users toggle on/off. When enabled, it exposes the data of the user's *other* enabled plugins (todos, pomodoros, and future plugins) as MCP tools over a network endpoint, so agents like **Kagetora** and **Takeda** can read and write that data through a validated API instead of hand-editing JSON files on Drive.

The hosted server remains a **pure API gateway**: it stores no user data or credentials. Access is granted by a **stateless signed bearer token** minted from the UI — an encrypted blob carrying the user's refresh token and `folder_id`, sealed with a server-held key. The server decrypts it in memory per request, uses it to reach the user's storage through the same storage/plugin functions the web app uses, and discards it.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Agents manage todos over MCP (Priority: P1)

As Scott, I want Kagetora and Takeda to see my todo items, add new ones, and mark them resolved through an MCP endpoint, so my agents can act on my task list without me hand-editing JSON on Drive or exposing the raw files to corruption.

**Why this priority**: This is the concrete driver for #111. Todos are the highest-value read/write surface for agents, and getting the full round trip working (auth → list → create → complete) proves the whole gateway pattern end to end. Delivered alone, it is a viable MVP.

**Independent Test**: Enable the MCP plugin in the UI, copy the token into a Claude Code / agent MCP config, then have the agent call `list_todos`, `create_todo`, and `complete_todo`. Verify the changes appear in the Acquacotta web UI and in the Drive `plugins/todos/data.json`, and that the server stored nothing locally.

**Acceptance Scenarios**:

1. **Given** the MCP plugin is enabled and a token is configured in the agent, **When** the agent calls `list_todos`, **Then** it receives the user's todos (optionally filtered by list and status) sourced live from the user's storage.
2. **Given** a valid token, **When** the agent calls `create_todo(title, list, priority, due_date)`, **Then** a new todo is written through the same path as the web UI and is visible in the dashboard on next sync.
3. **Given** an existing todo, **When** the agent calls `complete_todo(id)`, **Then** the todo is marked complete with a timestamp, identical to clicking the checkbox in the UI.
4. **Given** an existing todo, **When** the agent calls `update_todo(id, fields)`, **Then** the specified fields (title, notes, list, priority, due date) are updated and others are preserved.
5. **Given** the agent calls `list_todo_lists`, **Then** it receives the user's custom lists so it can target the right one.

---

### User Story 2 - Agents read time-tracking data over MCP (Priority: P1)

As Scott, I want agents to query my pomodoro records and time summaries through MCP, so briefings and reports ("how much Product time this week?") come from the API rather than parsing raw records.

**Why this priority**: Pomodoros are Acquacotta's core data. Read access to time data is what makes agent-generated briefings (Kagetora) and weekly reporting useful. Ships in the same feature per the full-multi-plugin scope decision.

**Independent Test**: With a valid token, have the agent call `get_pomodoros(start_date, end_date)` and `get_time_summary(period, category)` and compare the results against the dashboard's own totals for the same range.

**Acceptance Scenarios**:

1. **Given** a valid token, **When** the agent calls `get_pomodoros(start_date, end_date, type?)`, **Then** it receives the matching pomodoro records for that range from the user's storage.
2. **Given** a valid token, **When** the agent calls `get_time_summary(period, category?)`, **Then** it receives aggregated totals matching what the dashboard reports for the same period.
3. **Given** an existing pomodoro, **When** the agent calls `tag_pomodoro_to_ticket(pomodoro_id, ticket_id)`, **Then** the record is updated with the ticket linkage via the storage API.

---

### User Story 3 - Enable/disable the plugin and manage the token (Priority: P1)

As Scott, I want to turn MCP access on and off and mint/revoke my token from the Acquacotta UI, so I control whether agents can reach my data and can cut them off instantly.

**Why this priority**: Without enable/disable and revocation, the endpoint is neither controllable nor safe. This is inseparable from P1 — the token is the auth mechanism for stories 1 and 2.

**Independent Test**: Enable the plugin, confirm a token is issued and displayed once; disable it (or rotate) and confirm previously issued tokens no longer authenticate.

**Acceptance Scenarios**:

1. **Given** the user opens plugin settings, **When** they enable "MCP Access", **Then** a bearer token is generated and shown once with the endpoint URL and copy-paste agent config.
2. **Given** MCP Access is enabled, **When** the user disables it, **Then** the endpoint rejects that user's existing tokens.
3. **Given** a token exists, **When** the user chooses "regenerate", **Then** a new token is issued and the previous one stops working.
4. **Given** a request arrives with an invalid, tampered, or expired token, **When** the server processes it, **Then** it returns an MCP auth error and performs no storage access.

---

### User Story 4 - Plugin-contributed tool surface (Priority: P2)

As a plugin author, I want a plugin to declare the MCP tools it contributes, so the MCP server's tool surface reflects exactly the plugins the user has enabled and grows with the ecosystem without changing the core server.

**Why this priority**: This is the extensibility contract that lets tickets (#88/#89), checklists (#87), and briefings (#91) plug in later. It generalizes stories 1–2 but isn't required for the first agents to work, so P2.

**Independent Test**: Add a tool descriptor to the todos plugin and a stub second plugin; verify the MCP `tools/list` reflects only enabled plugins' tools, and disabling a plugin removes its tools.

**Acceptance Scenarios**:

1. **Given** a plugin declares MCP tool descriptors, **When** the plugin is enabled, **Then** its tools appear in the endpoint's `tools/list`.
2. **Given** a plugin is disabled, **When** an agent lists tools, **Then** that plugin's tools are absent and calling them errors cleanly.
3. **Given** two enabled plugins declare tools, **When** an agent lists tools, **Then** both sets are present with no core-server code change.

### Edge Cases

- **Expired/revoked Google grant**: the sealed refresh token no longer works → server returns an auth error advising the user to re-enable MCP from the UI; no partial writes.
- **Tampered token**: signature/decryption fails → rejected before any storage access.
- **Server key rotation**: all outstanding tokens invalidate at once (documented as the global "panic revoke").
- **Concurrent writes** (agent + browser writing todos): last-write-wins on the full-replace todos file, consistent with today's `/api/todos/sync` behavior; document the limitation.
- **Plugin disabled mid-session**: in-flight tool calls for that plugin error cleanly.
- **Storage backend not provisioned** (`folder_id` missing): tools return a clear "storage not configured" error.
- **Large result sets**: `get_pomodoros` over a wide range must bound response size (date-range required or capped).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST expose a hosted MCP endpoint over Streamable HTTP that any standard MCP client (Claude Code, Claude apps, Kagetora, Takeda) can connect to.
- **FR-002**: The MCP server MUST be implemented as an Acquacotta plugin that the user can enable and disable.
- **FR-003**: Enabling the plugin MUST mint a per-user stateless bearer token; disabling or regenerating MUST invalidate previously issued tokens for that user.
- **FR-003a**: Per-user revocation MUST be implemented via a per-user token epoch (a revocation watermark timestamp) stored in the user's own Drive (`mcp_access.json`), NOT on the server. Each token carries its `issued_at`; the server MUST reject any token whose `issued_at` predates the user's current epoch. Disable and Regenerate advance the epoch. Because the watermark lives in the user's storage, revocation is durable across server restarts and the server keeps zero per-user state (constitution I, II & VI).
- **FR-004**: The bearer token MUST be a sealed (encrypted + authenticated) blob containing the user's refresh token and `folder_id`, decryptable only with a server-held key supplied via environment variable.
- **FR-005**: The server MUST NOT persist user data or credentials — it decrypts the token in memory per request, performs the operation, and retains nothing (Privacy by Design; Container-Ready with no new persistent volume).
- **FR-006**: All data access MUST go through the same storage API and plugin functions the web app uses (`storage_api`, `todos_plugin`, etc.) — no direct raw-JSON manipulation and no bypass of validation.
- **FR-007**: The server MUST enforce strict per-user isolation — a token only ever reaches its own owner's storage.
- **FR-008**: Todos tools MUST include: `list_todos` (filterable by status, list, priority, and text), `list_todo_lists`, `create_todo`, `complete_todo`, `complete_todos` (bulk), `update_todo`, `delete_todo`, `reorder_todo`, and list management (`create_todo_list`, `rename_todo_list`, `delete_todo_list`).
- **FR-009**: Pomodoro tools MUST include: `get_pomodoros`, `get_time_summary`, `get_time_comparison` (period-over-period), `log_pomodoro` (manual entry), and `tag_pomodoro_to_ticket`. Per Timer Agnosticism, `log_pomodoro` records a completed block only; live/running timers remain browser-side and are out of scope for the stateless server.
- **FR-010**: The tool surface MUST be assembled from the user's enabled plugins; a plugin MUST be able to declare its MCP tool descriptors so new plugins contribute tools without core-server changes (contract aligns with #93).
- **FR-011**: The UI MUST present the endpoint URL, the one-time token, and ready-to-paste agent MCP config when the plugin is enabled.
- **FR-012**: Invalid, tampered, expired, or revoked tokens MUST be rejected with a clear MCP auth error and MUST NOT trigger any storage access.
- **FR-013**: Tool inputs MUST be validated; errors MUST return consistent, structured MCP error responses.

### Key Entities

- **MCP Access Token**: An opaque, per-user bearer credential held only by the agent. Internally a sealed blob of `{refresh_token, folder_id, issued_at, version}`. Not stored server-side. Invalidated by disable, regenerate, server-key rotation, or Google grant revocation.
- **MCP Tool Descriptor**: A plugin-declared description of a tool (name, input schema, handler) that the MCP server aggregates from enabled plugins.
- **Request Context (`ctx`)**: Derived per request from the decrypted token (`service`/`location`/`folder_id` + a built `drive_service`), identical in shape to what the web routes build today.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Kagetora and Takeda can complete a full round trip — list todos, create a todo, mark it resolved — against a live account using only the minted token.
- **SC-002**: Zero user data or credentials are written to server-side storage; the deployed unit adds no persistent volume (verifiable by inspection of the container/systemd unit).
- **SC-003**: Disabling the plugin or regenerating the token causes previously issued tokens to be rejected within one request.
- **SC-004**: `get_time_summary` results match the dashboard's own totals for the same period (parity check).
- **SC-005**: The endpoint's `tools/list` reflects exactly the user's enabled plugins; disabling a plugin removes its tools with no core-server change.
- **SC-006**: A tampered or expired token never reaches storage (auth failure precedes any Drive call).

## Out of Scope

- Ticket, checklist, and briefing tools beyond the generic contribution contract (land with #87/#88/#89/#91).
- A public multi-tenant SaaS signup flow — this serves existing authenticated Acquacotta users.
- Real-time push/streaming of state changes to agents (see #105).
- Per-tool granular scopes/permissions within a single token (future enhancement).

## Dependencies & Relationships

- Supersedes #90 (local stdio server).
- Aligns with #93 (plugin registry / tool-contribution contract).
- `tag_pomodoro_to_ticket` becomes fully meaningful once #88/#89 land; until then it writes the linkage field only.
