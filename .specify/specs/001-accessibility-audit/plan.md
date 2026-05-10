# Implementation Plan: Accessibility Audit & Fixes

**Branch**: `feature/73-accessibility-audit` | **Date**: 2026-05-10 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-accessibility-audit/spec.md`

## Summary

Run a comprehensive WCAG 2.1 AA accessibility audit on Acquacotta, then fix all critical and serious issues. The app is a single-page Flask app with a dark theme, tab-based navigation, timer controls, manual entry modal, charts, and settings. All UI is in `templates/index.html` with vanilla JS — no build step, no framework.

## Technical Context

**Language/Version**: Python 3.x (Flask backend), Vanilla JS/HTML/CSS (frontend)  
**Primary Dependencies**: Flask, Chart.js, Flatpickr  
**Storage**: IndexedDB (browser), Google Sheets API  
**Testing**: Lighthouse CLI, axe-core (browser), manual keyboard testing  
**Target Platform**: Desktop + mobile browsers  
**Constraints**: No JS frameworks, no build step, single HTML template  

## Constitution Check

| Principle | Impact | Status |
|-----------|--------|--------|
| Privacy by Design | No analytics added | PASS |
| User Data Ownership | No data changes | PASS |
| Simplicity & Focus | Accessibility is usability, not feature creep | PASS |
| Timer Agnosticism | Manual entry gets equal a11y treatment | PASS |
| Offline-First | No network changes | PASS |
| Container-Ready | No deployment changes | PASS |

## Implementation Approach

### Phase 1: Automated Audit (Baseline)

1. Build and run the container locally
2. Run Lighthouse accessibility audit via Chrome DevTools or CLI
3. Run axe-core via browser extension or bookmarklet
4. Document all findings with severity levels

### Phase 2: Semantic HTML & ARIA (FR-001 through FR-006)

Files to modify: `templates/index.html`

- Add `<main>` landmark around content
- Add skip navigation link
- Convert nav buttons to proper `role="tablist"` / `role="tab"` / `role="tabpanel"` pattern
- Add `aria-label` to all icon-only buttons (PiP, navigation arrows)
- Add `<label>` elements or `aria-label` to all form inputs
- Add `aria-live="polite"` region for timer status and sync announcements
- Add focus trap to manual entry modal and any confirmation dialogs
- Add `aria-hidden="true"` to decorative elements

### Phase 3: Visual Accessibility (FR-007 through FR-010)

Files to modify: `templates/index.html` (CSS section)

- Fix color contrast: adjust `--text-secondary` and any other failing colors
- Add visible focus indicators (`:focus-visible` styles)
- Ensure touch targets are 44x44px minimum on mobile
- Test all changes against AA contrast requirements

### Phase 4: Chart Accessibility (FR-011)

Files to modify: `templates/index.html` (JS section)

- Add `role="img"` and `aria-label` to chart canvases with summary descriptions
- Consider adding a visually-hidden data summary for screen readers

### Phase 5: Verification

- Re-run Lighthouse — target score >= 90
- Re-run axe-core — zero critical/serious violations
- Manual keyboard walkthrough of all views
- Screen reader spot-check (VoiceOver or NVDA)

## Project Structure

### Documentation (this feature)

```text
specs/001-accessibility-audit/
├── spec.md              # Feature specification
└── plan.md              # This file
```

### Source Code Changes

```text
templates/
└── index.html           # All HTML, CSS, and JS changes (semantic markup, ARIA, contrast, focus)
templates/
├── privacy.html         # Minor: add skip link, landmark roles if missing
└── terms.html           # Minor: add skip link, landmark roles if missing
```

## Complexity Tracking

No constitution violations. This is a pure enhancement to existing UI with no new dependencies, no data changes, and no architecture impact.
