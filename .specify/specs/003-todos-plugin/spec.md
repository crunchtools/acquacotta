# Feature Specification: Todos Plugin

**Feature Branch**: `feature/86-todos-plugin`
**Created**: 2026-06-21
**Status**: Draft
**Input**: GitHub Issue #86 + Google Tasks feature analysis + user requirements

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View and manage todos in a dashboard tab (Priority: P1)

As a user, I want a "To-do" tab in the Acquacotta dashboard where I can see all my todos organized by custom lists, so I can manage tasks alongside my time tracking without switching to Google Tasks.

**Why this priority**: The tab is the foundation — without it, no other todo functionality has a home. This delivers immediate value by consolidating the scatter of Google Tasks into the daily cockpit.

**Independent Test**: Navigate to the To-do tab, create a todo, edit it, mark it complete, delete it. All CRUD operations work with data persisted in IndexedDB (offline) and synced to Drive (online).

**Acceptance Scenarios**:

1. **Given** the user is on the dashboard, **When** they click the "To-do" tab, **Then** the todo view shows with their todos grouped by list
2. **Given** the user is on the To-do tab, **When** they click "Add Todo", **Then** a form appears with fields: title, notes, list (dropdown), priority, due date
3. **Given** a todo exists, **When** the user clicks the checkbox, **Then** the todo is marked complete with a timestamp and moves to a "Completed" section
4. **Given** a todo exists, **When** the user clicks edit, **Then** they can modify title, notes, list, priority, and due date
5. **Given** a completed todo, **When** the user clicks delete, **Then** the todo is permanently removed
6. **Given** todos exist with different priorities, **When** viewing a list, **Then** todos sort by: overdue first, then by priority (high > medium > low), then by creation date

---

### User Story 2 - Custom lists (Priority: P1)

As a user, I want to create, rename, and delete custom lists to organize my todos by context (Professional, Personal, Shopping, Travel, etc.), mirroring the organizational structure I already use in Google Tasks.

**Why this priority**: Custom lists are core to the organizing model. Without them, the todo plugin is a flat list — unusable for someone with 6+ lists like Scott.

**Independent Test**: Create a new list, rename it, move a todo to it, delete an empty list.

**Acceptance Scenarios**:

1. **Given** the user is on the To-do tab, **When** they click "Manage Lists", **Then** they can create a new list with a custom name
2. **Given** multiple lists exist, **When** viewing the To-do tab, **Then** todos are grouped under list headings with collapsible sections
3. **Given** a list exists with no todos, **When** the user deletes it, **Then** the list is removed
4. **Given** a list has todos, **When** the user tries to delete it, **Then** a confirmation asks whether to move todos to another list or delete them
5. **Given** lists exist, **When** the user drags a list heading, **Then** they can reorder lists

---

### User Story 3 - Link pomodoro to a todo (Priority: P2)

As a user, when I start or log a pomodoro, I want to optionally select a todo I'm working on, so my time tracking connects to my task list and I can later see how much time I spent on each todo.

**Why this priority**: This is the key differentiator over Google Tasks — linking time to tasks. Deferred to P2 because CRUD (P1) must work first. This also lays infrastructure for ticket linking (#88 RT integration) later.

**Independent Test**: Start a pomodoro, select a todo from the dropdown, complete it. The pomodoro record shows the linked todo. The todo shows total time spent.

**Acceptance Scenarios**:

1. **Given** the user is on the Timer tab starting/logging a pomodoro, **When** the timer form loads, **Then** an optional "Linked to" dropdown shows active todos from all lists
2. **Given** a pomodoro is linked to a todo, **When** viewing the todo detail, **Then** the total time spent (sum of linked pomodoro durations) is displayed
3. **Given** a pomodoro is linked to a todo, **When** viewing the History tab, **Then** the linked todo title appears on the pomodoro entry
4. **Given** a todo has linked pomodoros, **When** the todo is deleted, **Then** the pomodoros remain but their link is cleared (orphan-safe)

---

### User Story 4 - Todo persistence on Drive (Priority: P2)

As a user, I want my todos stored in `plugins/todos/data.json` on Google Drive alongside my pomodoro data, so my todos sync across devices and I own my data.

**Why this priority**: Without cloud persistence, todos only live in IndexedDB and are lost on browser clear. But local-first (P1 CRUD in IndexedDB) must work before sync is layered on.

**Independent Test**: Create a todo while logged in, verify it appears in `Acquacotta/plugins/todos/data.json` on Drive. Clear IndexedDB, reload — todos rehydrate from Drive.

**Acceptance Scenarios**:

1. **Given** the user is logged in with Google, **When** they create/edit/complete/delete a todo, **Then** the change syncs to `plugins/todos/data.json` on Drive
2. **Given** the user clears their browser data, **When** they log back in, **Then** todos rehydrate from Drive
3. **Given** the user is offline, **When** they modify todos, **Then** changes queue in IndexedDB and sync when connectivity returns

---

### User Story 5 - Google Tasks import (Priority: P3)

As a user, I want to import my existing Google Tasks into Acquacotta's Todos plugin as a one-time migration, so I can consolidate without re-entering hundreds of tasks.

**Why this priority**: Nice-to-have for migration. Users can start fresh or manually recreate their active todos. The import is a convenience, not a blocker.

**Independent Test**: Click "Import from Google Tasks" in settings, authorize the Tasks API scope, verify all lists and tasks appear in the Todos tab.

**Acceptance Scenarios**:

1. **Given** the user clicks "Import from Google Tasks", **When** authorization succeeds, **Then** all Google Tasks lists and their tasks are imported with titles, notes, due dates, and completion status preserved
2. **Given** an import has already been run, **When** the user runs it again, **Then** duplicates are detected by title+list and skipped
3. **Given** Google Tasks has subtasks, **When** imported, **Then** subtasks become top-level todos with a note indicating the parent (flatten, don't support hierarchy)

---

### Edge Cases

- What happens when a linked todo is deleted? Pomodoros keep their `linked_todo_id` but display "(deleted todo)" instead of the title.
- What happens when the user has no lists? A default "General" list is auto-created on first use.
- What happens with very long todo titles? Truncate with ellipsis in the list view, show full title in detail/edit view.
- What happens when Drive sync fails mid-write? Local IndexedDB is source of truth; retry on next sync cycle.
- Maximum todos per list? No enforced limit — JSON file stays small even at thousands of entries.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST add a "To-do" tab to the main navigation between History and Settings
- **FR-002**: System MUST support CRUD operations on todos: create, read, update, delete
- **FR-003**: System MUST support custom lists: create, rename, reorder, delete
- **FR-004**: Each todo MUST have: id, title, notes, status (pending/completed), priority (high/medium/low/none), due_date, list, created_at, completed_at, linked_pomodoros[]
- **FR-005**: System MUST persist todos in IndexedDB for offline-first operation
- **FR-006**: System MUST sync todos to `plugins/todos/data.json` on Google Drive when logged in
- **FR-007**: System MUST add an optional "Linked to" dropdown on the timer/manual-entry forms showing active todos
- **FR-008**: Pomodoro data model MUST support a `linked_todo_id` field (nullable, string)
- **FR-009**: System MUST display total time spent (from linked pomodoros) on each todo
- **FR-010**: System MUST register as an `extension` plugin type in the plugin registry
- **FR-011**: System MUST sort todos: overdue first, then by priority descending, then by creation date
- **FR-012**: Completed todos MUST show in a collapsible "Completed" section at the bottom of each list

### Key Entities

- **Todo**: The core entity — a task with title, notes, priority, due date, list membership, completion status, and linked pomodoros
- **TodoList**: A named grouping of todos (e.g., "Professional", "Personal", "Shopping"). User-customizable.
- **Pomodoro (existing, extended)**: Extended with nullable `linked_todo_id` field to connect time to tasks

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can create, edit, complete, and delete todos entirely offline (IndexedDB only)
- **SC-002**: Todo CRUD operations respond in under 100ms (constitution performance target)
- **SC-003**: Syncing up to 500 todos to Drive completes within 5 seconds
- **SC-004**: Linking a pomodoro to a todo adds no perceptible latency to the timer save flow
- **SC-005**: The Todos tab renders correctly on mobile viewports (min 320px width)
