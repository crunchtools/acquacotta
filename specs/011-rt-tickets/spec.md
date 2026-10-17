# Feature Specification: RT Tickets Plugin

**Feature Branch**: `feature/rt-tickets-plugin`
**Created**: 2026-10-17
**Status**: Draft
**Input**: See the user's RT (Request Tracker) tickets inside Acquacotta — like Todos/Discussions, but a ticket is an entire string of tasks (its history thread). A standalone plugin with its own tab and settings, usable against anyone's RT instance.

## Overview

Acquacotta gains an optional **RT Tickets** extension plugin (id `rt`, tab "Tickets"),
cloning the Todos/Discussions vertical: its own tab, settings card, IndexedDB store,
sync endpoint, and MCP tools, enabled by default and per-user (spec 008).

It differs from the Drive-owned plugins in one essential way: **RT is the source of
truth**, so this is a *read-through proxy + write-through actions* mirror rather than a
document the browser owns. Reads fetch live from RT's REST 2.0 API (through the Flask
server) and cache in IndexedDB for offline; writes (reply/comment/status) post straight
to RT. The only thing persisted to the user's Drive is the connection config.

The plugin is instance-agnostic: the RT base URL, authentication, and the TicketSQL
search are all per-user configuration (`plugins/rt/config.json` in the user's own
Drive), consistent with the constitution's **User Data Ownership** and stateless-server
principles. No RT credential or ticket content is ever stored on the server.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See my tickets, grouped by queue (Priority: P1)

A logged-in user who has configured RT opens the Tickets tab and sees the tickets
matching their search (default: `Owner = '__CurrentUser__'` and still open), with a
dynamic filter bar of the queues present (e.g. Personal, Professional). Clicking a
queue chip filters to that queue; "All" clears it.

**Independent Test**: With RT configured and tickets owned by the user, the tab lists
them and the queue chips filter the list.

**Acceptance Scenarios**:

1. **Given** RT is configured, **When** the user opens Tickets, **Then** their owned-open tickets appear newest-updated first.
2. **Given** tickets span two queues, **When** the user clicks a queue chip, **Then** only that queue's tickets show.
3. **Given** RT is not configured, **When** the user opens Tickets, **Then** a prompt directs them to Settings → RT Tickets.

### User Story 2 - A ticket is its history thread (Priority: P1)

Opening a ticket shows its native RT history — correspondence, comments, and status
changes in chronological order, with message bodies for correspondence/comments — as
the "string of tasks" that makes up the ticket.

**Independent Test**: Opening a ticket with correspondence shows the thread with
author, timestamp, type, and content.

**Acceptance Scenarios**:

1. **Given** a ticket with correspondence, **When** the user opens it, **Then** the thread renders newest-first with bodies.
2. **Given** RT-sourced content, **When** it renders, **Then** it is shown as text (never interpreted as HTML).

### User Story 3 - Act on a ticket from Acquacotta (Priority: P1)

From the ticket detail the user can add a public reply, an internal comment, or change
the status; the change lands in RT and the thread/list reflects it.

**Acceptance Scenarios**:

1. **Given** a ticket, **When** the user posts a reply or comment, **Then** it is added in RT and appears in the thread.
2. **Given** a ticket, **When** the user sets a new status, **Then** RT is updated (and a now-closed ticket drops from the open view).

### User Story 4 - Bring your own RT instance (Priority: P2)

Any user can configure their own RT: base URL, auth (HTTP Basic or an RT REST token),
an optional public URL for clickable ticket links, and the TicketSQL search — then
test the connection. Secrets are stored only in the user's Drive and masked on read.

**Acceptance Scenarios**:

1. **Given** valid RT settings, **When** the user clicks Test connection, **Then** RT's version is reported.
2. **Given** saved secrets, **When** the config is re-read, **Then** the token/password are masked (presence only) and editing other fields preserves them.

### Edge Cases

- RT unreachable or auth rejected → the UI shows the error and falls back to the cached tickets.
- `base_url` pointed at an auth-gated front end that returns HTML → a clear "not JSON / wrong address" error.
- A deployment where RT is behind an external auth proxy (e.g. Cloudflare Access): the server is configured with RT's private address so it reaches RT directly; the browser-facing `public_url` is used only for ticket links.

## Requirements *(mandatory)*

- **FR-001**: The plugin MUST be an optional, per-user extension enabled by default (spec 008), owning the `rt` tab and `rt-settings-card`.
- **FR-002**: The server MUST proxy RT REST 2.0 for reads and writes, using per-request config from the user's Drive, and MUST persist no RT credentials or ticket data server-side.
- **FR-003**: Ticket reads MUST cache in IndexedDB (DB v5, `tickets` store) and serve offline; the cache is a full replace of each live fetch.
- **FR-004**: The ticket list MUST offer a dynamic queue filter bar derived from the fetched tickets, plus an open/all status filter.
- **FR-005**: The detail view MUST render the RT history thread (type, creator, created, description, and message content for correspondence/comments) as escaped text.
- **FR-006**: The UI MUST support adding correspondence, adding a comment, and changing status, each written through to RT.
- **FR-007**: Auth MUST support HTTP Basic (preferred when a Basic user is set) or an RT REST 2.0 token; the config form MUST mask secrets and preserve unentered secrets on save.
- **FR-008**: MCP tools MUST expose the same capabilities (`list_tickets`, `get_ticket`, reply/comment/status), gated per-user like other optional plugins.
- **FR-009**: All RT-sourced ids used in the UI MUST be validated as integers at the trust boundary; all RT-sourced text MUST be rendered as text, never HTML.

## Out of Scope

- Creating new tickets, attachments/file upload, custom fields, and ticket links/dependencies (v1 is read + reply/comment/status).
- Mirroring RT ticket content into the user's Drive (RT remains the source of truth).
- Encrypting the stored RT config at rest (possible follow-up; the config lives in the user's own `drive.file`-scoped storage).
