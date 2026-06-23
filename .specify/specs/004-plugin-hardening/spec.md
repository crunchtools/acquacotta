# Feature Specification: Plugin Framework Hardening

**Feature Branch**: `101-plugin-hardening`  
**Created**: 2026-06-23  
**Status**: Draft  
**Input**: GitHub issue #101

## User Scenarios & Testing

### User Story 1 - Plugin-Aware Type Dropdown (Priority: P1)

When starting a pomodoro, the Type dropdown shows both standard types (Content, Product, etc.) and items injected by active extension plugins. Selecting a todo from the Todos plugin sets the type to the todo's parent list name and links the pomodoro to that todo. This replaces the need for a separate "Linked to" picker.

**Why this priority**: This is the user-facing integration point that makes plugins feel native. Without it, every future plugin (checklists, tickets) would need its own bespoke linking UI.

**Independent Test**: Start a pomodoro, verify the dropdown shows standard types above a separator and todo items grouped by list below. Select a todo item — verify the completed pomodoro records the correct type and `linked_todo_id`.

**Acceptance Scenarios**:

1. **Given** the Todos plugin is active with pending todos, **When** the user opens the Type dropdown, **Then** todo lists with pending items appear below a separator, expandable into individual todos
2. **Given** the Todos plugin is not active, **When** the user opens the Type dropdown, **Then** only standard types appear (no separator, no todo items)
3. **Given** a future plugin declares `has_timer_types: true`, **When** the user opens the Type dropdown, **Then** that plugin's items also appear below the separator

---

### User Story 2 - Persistent Plugin State (Priority: P1)

When the user enables or disables a plugin in Settings, that choice persists across container restarts. On app boot, the saved plugin states are restored from IndexedDB (synced to cloud via settings).

**Why this priority**: Without persistence, users lose their plugin configuration on every restart. This is table-stakes for a reliable plugin system.

**Independent Test**: Enable the Todos plugin, restart the container, reload the app — verify the plugin is still active.

**Acceptance Scenarios**:

1. **Given** the user disables the Todos plugin in Settings, **When** the container restarts, **Then** the Todos tab is not shown and todo items don't appear in the Type dropdown
2. **Given** the user re-enables the Todos plugin, **When** the page loads, **Then** the Todos tab reappears and the Type dropdown includes todo items

---

### User Story 3 - Enriched Plugin Metadata & Capability Flags (Priority: P2)

Each plugin's `PLUGIN_METADATA` declares its capabilities via boolean flags (`has_tab`, `has_timer_types`, `has_counts`, `has_sync`, `has_import_export`, `has_history_decorators`). Core code queries these flags instead of hardcoding plugin IDs.

**Why this priority**: This is the contract that all future plugins implement against. Without it, every new plugin requires hardcoded integration points in core.

**Independent Test**: Add a `has_timer_types: True` flag to the Todos plugin metadata — verify the Type dropdown dynamically discovers it. Remove the flag — verify todos disappear from the dropdown without any other code change.

**Acceptance Scenarios**:

1. **Given** a plugin declares `has_tab: True` and `tab_label: "To-do"`, **When** the plugin is active, **Then** a tab with that label appears in the navigation
2. **Given** a plugin declares `has_counts: True`, **When** the Settings page renders, **Then** the plugin's card shows a dynamic item count queried from the plugin
3. **Given** a plugin does NOT declare `has_timer_types`, **When** the Type dropdown renders, **Then** that plugin contributes nothing to the dropdown

---

### User Story 4 - Dynamic Settings Cards with Plugin Actions (Priority: P2)

The Settings > Plugins section dynamically renders a card for each registered plugin. Cards show name, description, version, active/inactive toggle, and capability-specific actions (import/export buttons for plugins that declare `has_import_export`). No hardcoded plugin UI in Settings.

**Why this priority**: Removes the pattern of adding hardcoded spans/buttons to Settings for each new plugin. Import/export buttons move from the To-do tab to the plugin's Settings card.

**Independent Test**: Check that the Todos plugin card in Settings shows import/export buttons, item count, and active toggle — all driven by metadata, not hardcoded HTML.

**Acceptance Scenarios**:

1. **Given** three plugins are registered, **When** the user opens Settings > Plugins, **Then** three cards appear with name, description, version, and toggle
2. **Given** the Todos plugin declares `has_import_export: True`, **When** its Settings card renders, **Then** import/export buttons appear on the card
3. **Given** a plugin declares `has_counts: True`, **When** its card renders, **Then** a count badge shows the current item count

---

### User Story 5 - Frontend PluginUI Registry (Priority: P3)

A `PluginUI` registry on the frontend allows plugins to register their UI contributions: timer type providers, history decorators, count providers, and sync handlers. Core code iterates over registered providers instead of checking for specific plugin IDs.

**Why this priority**: The architectural foundation for all frontend plugin integrations. P3 because the immediate impact is refactoring existing hardcoded integrations to use the registry — the user experience doesn't change, but it's required before additional plugins can be added.

**Independent Test**: Verify that the `populateTypeDropdowns` function loops over `PluginUI.getTimerTypeProviders()` instead of hardcoding a check for `todos`.

**Acceptance Scenarios**:

1. **Given** the PluginUI registry has two timer type providers registered, **When** the Type dropdown renders, **Then** both providers' items appear
2. **Given** a plugin registers a history decorator, **When** the History tab renders pomodoros linked to that plugin, **Then** the decorator annotates those items

---

### User Story 6 - Plugin Sync Contracts (Priority: P3)

Plugins that declare `has_sync: True` implement `syncToCloud()` and `loadFromCloud()`. The core sync orchestrator invokes these during init and periodic sync events, instead of hardcoding calls to specific plugin sync functions.

**Why this priority**: P3 because the Todos plugin already has sync working via hardcoded calls. This refactors it to a contract so future plugins get sync for free.

**Independent Test**: Verify that `Storage.loadTodosFromCloud()` is invoked through the plugin sync contract, not by name.

**Acceptance Scenarios**:

1. **Given** two plugins declare `has_sync: True`, **When** the app boots and the user is logged in, **Then** both plugins' `loadFromCloud()` methods are called
2. **Given** a plugin does NOT declare `has_sync`, **When** sync runs, **Then** that plugin is skipped

---

### Edge Cases

- What happens when a plugin is disabled while a pomodoro is linked to one of its items? The pomodoro keeps its `linked_todo_id` — it's historical data, not broken.
- What happens when plugin metadata is missing capability flags? Default to `false` — the plugin contributes nothing until flags are declared.
- What happens when IndexedDB has saved state for a plugin that no longer exists? Ignore it gracefully — don't error on orphaned settings.

## Requirements

### Functional Requirements

- **FR-001**: PLUGIN_METADATA MUST include capability flags: `has_tab`, `tab_label`, `has_timer_types`, `has_counts`, `has_sync`, `has_import_export`, `has_history_decorators`
- **FR-002**: Plugin active/inactive state MUST persist in IndexedDB settings store, keyed as `plugin_state_<plugin_id>`
- **FR-003**: The Type dropdown MUST dynamically query active plugins with `has_timer_types: True` for injectable items
- **FR-004**: `parseTypeValue()` MUST be extensible — handle `todo:<id>`, `ticket:<id>`, `checklist:<id>` prefixes
- **FR-005**: Settings > Plugins MUST render cards dynamically from plugin registry metadata
- **FR-006**: Import/export buttons MUST appear on plugin Settings cards (not on plugin tabs)
- **FR-007**: Plugins declaring `has_sync: True` MUST be invoked during core sync orchestration
- **FR-008**: History decorators MUST be provided by plugins via the PluginUI registry

### Key Entities

- **PluginMetadata**: Backend declaration of plugin identity and capabilities
- **PluginUI**: Frontend registry mapping plugin IDs to UI contribution functions
- **TimerTypeProvider**: Function that returns `{label, items[]}` for the Type dropdown
- **HistoryDecorator**: Function that annotates pomodoro history items with plugin context

## Success Criteria

### Measurable Outcomes

- **SC-001**: Adding a new extension plugin requires zero changes to core HTML/JS — only plugin files and registration
- **SC-002**: Plugin state survives container restarts (verified by toggle → restart → check)
- **SC-003**: Type dropdown renders plugin items within 100ms of dropdown open (constitution performance target)
- **SC-004**: All hardcoded references to "todos" in core code (outside the plugin itself) are replaced with registry queries
