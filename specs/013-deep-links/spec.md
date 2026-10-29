# Feature Specification: Deep Links

**Feature Branch**: `feature/deep-links-social-schedule`
**Created**: 2026-10-28
**Status**: Implemented (v2.27.0)
**Input**: Every tab, sub-tab and plugin item addressable by URL, so a todo can go
in a calendar invite or email and an RT ticket can be handed to an agent.

## Overview

Routes live in the URL hash, so they need no server change and work in the
installed PWA and offline. `AcquacottaUtils.parseRoute` / `formatRoute`
(static/js/utils.js) read and write them; segments are URI-encoded.

| Route | Opens |
|---|---|
| `#timer`, `#history`, `#settings` | the tab |
| `#reports/<day\|week\|month>` | Reports at that period |
| `#history/pomodoro/<id>` | History, scrolled to and highlighting the pomodoro |
| `#todos/list/<listId\|all>` | To-do, that list |
| `#todos/item/<todoId>` | To-do, the item's list, its edit dialog |
| `#discussions/person/<name>`, `#discussions/item/<id>` | Discussions, that person or item |
| `#rt/queue/<queue>`, `#rt/ticket/<id>` | Tickets, that queue or ticket (any ticket, fetched live if not cached) |
| `#social/compose`, `#social/posts`, `#social/post/<postizId>` | Social, that pane or post |
| `#settings/plugin/<pluginId>` | Settings, that plugin's panel open |

Each view registers `ROUTES[view] = { current(), <kind>(id) }` beside its own
code; a new plugin gets deep links by adding one entry. The URL follows state
with `history.replaceState` (no new history entries). Each item dialog has a
Copy link button. A route is kept in sessionStorage across a Google sign-in.

MCP tools add `link` to todo, discussion, ticket and pomodoro records, built
from `ACQUACOTTA_PUBLIC_URL` (fallback `OAUTH_REDIRECT_BASE`) by `deep_links.py`.

## User Scenarios

1. **Given** a todo link in a calendar invite, **When** opened, **Then** the To-do tab shows the item's list with its dialog open.
2. **Given** an item dialog, **When** Copy link is tapped, **Then** the clipboard holds the item's URL.
3. **Given** a link to a deleted item or turned-off tab, **When** opened, **Then** the app falls back to the list or first tab and says so.
4. **Given** a signed-out browser, **When** a link is opened and the user signs in, **Then** they land on the linked route.
5. **Given** an agent with MCP access, **When** it lists tickets, **Then** each has a `link` the user can click.
