# Feature Specification: Accessibility Audit & Fixes

**Feature Branch**: `feature/73-accessibility-audit`  
**Created**: 2026-05-10  
**Status**: Draft  
**Input**: GitHub Issue #73 — Run accessibility audit and fix identified issues

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Keyboard-Only Timer Operation (Priority: P1)

A user who cannot use a mouse navigates the entire timer workflow using only the keyboard: selecting a preset duration, entering a task name, choosing a type, starting/pausing/stopping the timer, and logging a completed pomodoro.

**Why this priority**: Timer operation is the core function. If keyboard users can't operate it, the app is fundamentally inaccessible.

**Independent Test**: Tab through the timer view from nav to log completion. Every interactive element must be reachable and operable with Enter/Space.

**Acceptance Scenarios**:

1. **Given** the timer view is active, **When** a user presses Tab repeatedly, **Then** focus moves through all preset buttons, name input, type select, and action buttons in logical order
2. **Given** a timer preset button has focus, **When** the user presses Enter or Space, **Then** the preset is selected and visually indicated
3. **Given** the timer is running, **When** the user tabs to the Stop button and presses Enter, **Then** the timer stops and the log prompt appears

---

### User Story 2 - Screen Reader Navigation (Priority: P1)

A screen reader user can understand the page structure, identify all controls, and receive feedback when actions occur (timer starts, pomodoro logged, sync status changes).

**Why this priority**: Without proper ARIA labels and semantic HTML, screen reader users cannot use the app at all.

**Independent Test**: Navigate with a screen reader (NVDA/VoiceOver). All controls announce their purpose; status changes are announced via live regions.

**Acceptance Scenarios**:

1. **Given** a screen reader is active, **When** the user navigates the page, **Then** all buttons, inputs, and sections have descriptive accessible names
2. **Given** the timer starts, **When** the countdown updates, **Then** the timer state change is announced (start/pause/complete) without spamming every second
3. **Given** a pomodoro is logged, **When** the action completes, **Then** a live region announces success or failure

---

### User Story 3 - Sufficient Color Contrast (Priority: P2)

All text and interactive elements meet WCAG 2.1 AA contrast ratios (4.5:1 for normal text, 3:1 for large text and UI components).

**Why this priority**: The dark theme with muted secondary text colors likely has contrast issues that affect readability for low-vision users.

**Independent Test**: Run axe-core or Lighthouse on every view. All contrast violations are resolved.

**Acceptance Scenarios**:

1. **Given** the app uses `--text-secondary: #a0a0a0` on `--bg-secondary: #16213e`, **When** contrast is checked, **Then** the ratio meets 4.5:1 (currently ~3.8:1 — needs fix)
2. **Given** any UI element, **When** its contrast ratio is measured, **Then** it meets AA minimums

---

### User Story 4 - Manual Entry Form Accessibility (Priority: P2)

The manual entry modal is fully accessible: all fields have associated labels, the modal traps focus, and Escape closes it.

**Why this priority**: Manual entry is a first-class feature (Timer Agnosticism principle). It must be equally accessible.

**Independent Test**: Open the manual entry modal with keyboard, fill all fields, submit, and close — all without a mouse.

**Acceptance Scenarios**:

1. **Given** the History view is active, **When** the user activates "+ Add Manual", **Then** the modal opens and focus moves to the first field
2. **Given** the modal is open, **When** the user presses Tab at the last field, **Then** focus wraps to the first field (focus trap)
3. **Given** the modal is open, **When** the user presses Escape, **Then** the modal closes and focus returns to the trigger button

---

### Edge Cases

- What happens when the timer completes while focus is elsewhere on the page? (Live region should announce it)
- How does the slidable timer dial work with keyboard? (Must support arrow keys)
- Are chart.js visualizations in Reports accessible? (Need text alternatives or data tables)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: All interactive elements MUST be keyboard accessible (Tab, Enter, Space, Escape, Arrow keys)
- **FR-002**: All form inputs MUST have associated `<label>` elements or `aria-label` attributes
- **FR-003**: All buttons MUST have accessible names (visible text or `aria-label`)
- **FR-004**: Navigation MUST use `role="tablist"` / `role="tab"` pattern or equivalent semantic markup
- **FR-005**: Modals MUST implement focus trap and restore focus on close
- **FR-006**: Status changes (timer start/stop/complete, sync status) MUST use `aria-live` regions
- **FR-007**: Color contrast MUST meet WCAG 2.1 AA (4.5:1 normal text, 3:1 large text/UI components)
- **FR-008**: Focus indicators MUST be visible on all interactive elements
- **FR-009**: Page MUST include a skip navigation link
- **FR-010**: Touch targets MUST be at least 44x44 CSS pixels on mobile
- **FR-011**: Charts MUST have text alternatives (summary or data table)

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Lighthouse accessibility score >= 90 on all pages (index, privacy, terms)
- **SC-002**: Zero critical or serious axe-core violations
- **SC-003**: All timer and manual entry controls are operable with keyboard only
- **SC-004**: All text meets WCAG 2.1 AA contrast ratios
