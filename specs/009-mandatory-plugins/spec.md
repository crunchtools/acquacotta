# Feature Specification: Everything-is-a-Plugin (Mandatory + Optional Plugins)

**Feature Branch**: `feature/009-mandatory-plugins`
**Created**: 2026-07-13
**Status**: Draft
**Input**: "Pomodoro, Settings, and Todos should all be plugins. Pomodoro and Settings should be mandatory plugins." (queued after specs 007/008)

## Overview

Acquacotta's features are currently modeled inconsistently. **Todos** is a first-class plugin (registered, has a tab, contributes MCP tools, per-user enable/disable from spec 008). **Pomodoros** are "core" — their MCP tools are hardcoded into the MCP server and their data operations live inside the storage-backend contract, but there is no "pomodoro plugin." **Settings** is neither a plugin nor a tab — just a view plus two functions on the storage contract. So "what features exist" is expressed three different ways.

This feature unifies the model: **every user-facing feature is a plugin.** Pomodoro, Settings, and Todos are all registered plugins listed uniformly. Two of them — **Pomodoro and Settings** — are **mandatory**: always registered, always enabled, and not user-toggleable (the app is meaningless without them). Todos remains an **optional** plugin the user can enable/disable per-user (spec 008 behavior, unchanged).

The result: one consistent plugin model across the registry, the web Plugins UI, and the MCP server — with a clear, enforced distinction between mandatory features and optional ones.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Every feature appears uniformly as a plugin (Priority: P1)

A user opens Settings → Plugins and sees Pomodoro, Settings, and Todos listed the same way as any plugin, each showing whether it is mandatory or optional.

**Why this priority**: Today the plugin list only shows Todos (and storage/MCP). Pomodoro and Settings are invisible as plugins, so the "everything is a plugin" model isn't real or inspectable.

**Independent Test**: Load the Plugins list; confirm Pomodoro, Settings, and Todos are all present, with Pomodoro and Settings clearly marked mandatory.

**Acceptance Scenarios**:

1. **Given** the Plugins list, **When** it renders, **Then** Pomodoro, Settings, and Todos are all shown as plugins.
2. **Given** a mandatory plugin (Pomodoro or Settings), **When** it is shown, **Then** it is marked mandatory and presents no working "disable" control.

---

### User Story 2 - Mandatory plugins cannot be disabled (Priority: P1)

A user (or an API/MCP caller) cannot turn off Pomodoro or Settings; they are always on for everyone.

**Why this priority**: These features are foundational — disabling them would break the app. "Mandatory" must be enforced, not merely labeled.

**Independent Test**: Attempt to disable Pomodoro (or Settings) via the UI toggle and via the toggle API; confirm it stays enabled and the attempt is rejected/ignored. Confirm their MCP tools always work.

**Acceptance Scenarios**:

1. **Given** a mandatory plugin, **When** a disable is attempted through any interface, **Then** it remains enabled and the attempt is refused (no state change).
2. **Given** a mandatory plugin, **When** any user calls its MCP tools, **Then** they always work, regardless of that user's other plugin choices.

---

### User Story 3 - Optional plugins keep their per-user enable/disable (Priority: P1)

Todos remains an optional plugin each user can enable or disable for themselves, exactly as in spec 008, on both web and MCP.

**Why this priority**: This feature must not regress the per-user optional-plugin behavior just shipped in 008.

**Independent Test**: Disable Todos for one user; confirm its tab hides and its MCP tools refuse for that user, while another user is unaffected — unchanged from 008.

**Acceptance Scenarios**:

1. **Given** Todos (optional), **When** a user disables it, **Then** its tab hides and its MCP tools refuse for that user only.
2. **Given** Todos disabled for user A, **When** user B uses the app, **Then** Todos is unaffected for user B.

---

### User Story 4 - Consistent behavior after restart and across interfaces (Priority: P2)

Mandatory plugins are always present after a service restart with no per-user state; optional-plugin choices persist per-user. The web UI and MCP agree on which plugins are mandatory vs optional and on each user's enablement.

**Acceptance Scenarios**:

1. **Given** a service restart, **When** any user connects, **Then** Pomodoro and Settings are registered and enabled without any stored per-user state.
2. **Given** the same user on web and MCP, **When** they inspect plugins, **Then** both interfaces report the same mandatory/optional classification and the same enablement for optional plugins.

---

### Edge Cases

- **Attempt to disable a mandatory plugin via a crafted API/MCP call**: refused; no state change; feature stays enabled.
- **A user's stored preference says a mandatory plugin is off** (stale/imported data): ignored — mandatory always wins.
- **A newly added optional plugin with no recorded choice**: defaults enabled (unchanged from 008).
- **Registry lists a mandatory plugin**: it is always `active`, independent of any per-user setting.

## Requirements *(mandatory)*

- **FR-001**: Pomodoro, Settings, and Todos MUST each be modeled and listed as plugins through the same registry and Plugins UI.
- **FR-002**: The system MUST distinguish **mandatory** plugins (Pomodoro, Settings) from **optional** plugins (Todos), and expose that classification to the web UI and MCP.
- **FR-003**: Mandatory plugins MUST always be registered and enabled, independent of any per-user preference or process state, including after a service restart.
- **FR-004**: The system MUST refuse any attempt (UI, API, or MCP) to disable a mandatory plugin, making no state change.
- **FR-005**: Mandatory plugins' MCP tools MUST always be available to every authenticated caller (never gated off).
- **FR-006**: Optional plugins MUST retain per-user enable/disable on web and MCP exactly as defined in spec 008 (no regression).
- **FR-007**: The web Plugins UI MUST list every plugin (Pomodoro, Settings, Todos). Mandatory plugins MUST render with a **checked, disabled (locked)** toggle and a **"Required"** badge — visibly on and clearly non-changeable. Optional plugins MUST render with their normal per-user toggle (checked by default, user-changeable).
- **FR-008**: The web UI and MCP MUST agree on the mandatory/optional classification and on each user's optional-plugin enablement.
- **FR-009**: This change MUST NOT alter how any feature's data is stored or its on-the-wire/on-disk data format (no user-data migration).

### Key Entities

- **Plugin**: a registered feature with an id, display metadata, a classification (**mandatory** or **optional**), and optional contributions (a UI tab, MCP tools). Pomodoro, Settings, Todos are plugins; storage backends and MCP-access remain their own plugin categories.
- **Mandatory Plugin**: a Plugin that is always registered and enabled and cannot be disabled by any user or interface.
- **Optional Plugin**: a Plugin whose enablement is a per-user choice (spec 008), defaulting to enabled.

## Success Criteria *(mandatory)*

- **SC-001**: 100% of the three features (Pomodoro, Settings, Todos) appear as plugins in the registry and Plugins UI.
- **SC-002**: 0 successful attempts to disable a mandatory plugin via any interface.
- **SC-003**: Mandatory plugins' MCP tools succeed for 100% of authenticated callers regardless of their other plugin choices.
- **SC-004**: Optional-plugin per-user behavior (spec 008) passes 100% of its existing checks (no regression).
- **SC-005**: No change to stored data or data formats — verifiable by diffing what is persisted before/after.

## Assumptions

- "Mandatory" is expressed as plugin classification/metadata plus registry enforcement — not by writing per-user state (mandatory plugins need no per-user record).
- Pomodoro's existing MCP tools are re-homed from hardcoded "core" registration onto the Pomodoro plugin, keeping the same tool names and behavior.
- Settings may have no MCP tools today; as a mandatory plugin it still appears in the registry/UI and is always-on. Adding Settings MCP tools is not required by this spec.
- Per-user optional-plugin state continues to use the existing `plugin_state_<id>` preference from spec 008.

## Out of Scope

- **Decoupling the storage-backend contract** (moving pomodoro/settings persistence out of the storage plugin's fat contract into the feature plugins). This spec makes features first-class plugins at the registry/UI/MCP layer; the persistence layer keeps its current shape. A future spec may separate "what feature" from "where stored."
- Adding new MCP tools for Settings.
- Any change to storage-backend selection (spec 007) or to the per-user optional-plugin mechanism itself (spec 008).
- Data migration of any kind.
