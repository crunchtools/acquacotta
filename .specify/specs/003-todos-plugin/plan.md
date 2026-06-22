# Implementation Plan: Todos Plugin

**Branch**: `feature/86-todos-plugin` | **Date**: 2026-06-21 | **Spec**: `specs/003-todos-plugin/spec.md`
**Input**: Feature specification from `/specs/003-todos-plugin/spec.md`

## Summary

Add a Todos plugin as the first `extension`-type plugin in Acquacotta. Introduces a "To-do" tab in the dashboard with full CRUD, custom lists, priority/due-date sorting, and the ability to link pomodoro sessions to todos. Data is stored in IndexedDB (offline-first) and synced to `plugins/todos/data.json` on Google Drive.

## Technical Context

**Language/Version**: Python 3.x (Flask backend), vanilla JavaScript ES6+ (frontend)
**Primary Dependencies**: Flask, Google Drive API (existing), IndexedDB (existing)
**Storage**: IndexedDB (local, offline-first) + Google Drive JSON file (`plugins/todos/data.json`)
**Testing**: Manual verification + existing test patterns
**Target Platform**: Web browser (desktop + mobile responsive)
**Project Type**: Web application (monolith — single `index.html`, single `app.py`)
**Performance Goals**: <100ms for local operations, <5s for Drive sync
**Constraints**: No frameworks (vanilla JS per constitution), offline-first, no persistent server state

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Privacy by Design | PASS | No new OAuth scopes needed — `drive.file` already covers app-created files |
| II. User Data Ownership | PASS | Data lives in user's Drive as JSON, portable, deletable |
| III. Simplicity & Focus | PASS | Todos directly support daily personal productivity |
| IV. Timer Agnosticism | PASS | Linking is optional — manual entry and external timers unaffected |
| V. Offline-First | PASS | IndexedDB is primary store, Drive sync is background |
| VI. Container-Ready | PASS | No new server state, no new volumes |

## Architecture

### Data Flow

```
Browser (IndexedDB)          Flask Backend              Google Drive
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│ todos_store      │────▶│ /api/todos/*     │────▶│ plugins/todos/   │
│ (offline-first)  │◀────│ (proxy to Drive) │◀────│   data.json      │
└─────────────────┘     └──────────────────┘     └──────────────────┘
```

### Plugin Registration

Register as `extension` type (non-singleton) in `plugin_registry.py`. The Todos plugin uses the existing JSON-on-Drive transport for its data file — same pattern as pomodoros.json but in the `plugins/todos/` subfolder.

### Data Model

```json
{
  "lists": [
    { "id": "uuid", "name": "Professional", "order": 0 },
    { "id": "uuid", "name": "Personal", "order": 1 }
  ],
  "todos": [
    {
      "id": "uuid",
      "title": "Review RHEL 10 roadmap",
      "notes": "Focus on container improvements",
      "status": "pending",
      "priority": "high",
      "due_date": "2026-06-25",
      "list_id": "uuid",
      "created_at": "2026-06-21T10:00:00Z",
      "completed_at": null,
      "linked_pomodoros": []
    }
  ]
}
```

### Pomodoro Data Model Extension

Add `linked_todo_id` (nullable string) to pomodoro records. This field is ignored by existing code, backward-compatible. The same pattern will be reused for `linked_ticket_id` when the ticket system plugin (#88) lands.

```javascript
// Extended pomodoro object
{
  id: "uuid",
  name: "RHEL 10 review",
  type: "Product",
  duration_minutes: 25,
  notes: "...",
  linked_todo_id: "todo-uuid-here"  // NEW — nullable
}
```

## Project Structure

### Source Code Changes

```
app.py                          # Add /api/todos/* routes
todos_plugin.py                 # NEW — plugin module with Drive read/write
plugin_registry.py              # Register todos as extension plugin
templates/index.html            # Add To-do tab, todo UI, timer linking dropdown
```

### No New Files for Storage

Todos reuses the existing `json_storage_core.py` + `google_drive_transport.py` for reading/writing `plugins/todos/data.json`. No new transport or storage module needed.

## Implementation Phases

### Phase 1: Frontend — To-do Tab + IndexedDB (P1 stories)

1. Add "To-do" tab button to nav bar (between History and Settings)
2. Add `todos-view` tabpanel with:
   - List selector/grouping
   - Todo list with checkbox, title, priority badge, due date
   - Add/edit todo form (inline or modal)
   - Completed section (collapsible)
3. IndexedDB `todos` object store for offline-first CRUD
4. List management UI (create, rename, reorder, delete)
5. Sorting: overdue first → priority desc → created_at asc

### Phase 2: Backend — Drive Sync + API Routes (P2 stories)

1. `todos_plugin.py` — read/write `plugins/todos/data.json` via Drive transport
2. Flask routes:
   - `GET /api/todos` — fetch all todos and lists
   - `POST /api/todos` — create todo
   - `PUT /api/todos/<id>` — update todo
   - `DELETE /api/todos/<id>` — delete todo
   - `GET /api/todos/lists` — fetch lists
   - `POST /api/todos/lists` — create list
   - `PUT /api/todos/lists/<id>` — update list
   - `DELETE /api/todos/lists/<id>` — delete list
   - `POST /api/todos/sync` — full sync (push local to Drive)
   - `GET /api/todos/sync` — pull from Drive
3. Register as `extension` plugin in plugin_registry
4. Sync logic: same pattern as pomodoro sync (IndexedDB → batch push to Drive)

### Phase 3: Pomodoro Linking (P2 story)

1. Add `linked_todo_id` field to pomodoro creation/edit forms
2. "Linked to" dropdown on timer view — populated from active (non-completed) todos
3. Display linked todo title in History tab entries
4. Calculate and display total time on each todo in the To-do tab
5. Handle orphaned links gracefully (deleted todos)

### Phase 4: Google Tasks Import (P3 story — stretch)

1. Settings section: "Import from Google Tasks" button
2. Requires `tasks.readonly` OAuth scope (additional consent prompt)
3. Maps Google Tasks lists → Acquacotta lists, tasks → todos
4. Deduplication by title + list name
5. Subtask flattening with parent reference in notes

## Complexity Tracking

No constitution violations. The feature fits cleanly within the existing architecture — it's the designed use case for the `extension` plugin type.
