# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and this project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **RT Tickets** plugin: a first-class tab for your Request Tracker tickets,
  grouped by queue with a dynamic queue filter bar, and a detail view showing
  each ticket's native RT history thread. You can reply, comment, and change
  status from inside Acquacotta. RT is the source of truth: the server proxies
  RT's REST 2.0 API per request (reads are cached in IndexedDB for offline) and
  never stores ticket data. Point it at any RT 5+/6.x instance — the base URL,
  auth (HTTP Basic or an RT REST token), and the TicketSQL search are per-user
  config stored only in your own Google Drive, never on the server. Ships with
  its own `/api/rt/*` endpoints and MCP tools (`list_tickets`, `get_ticket`,
  `reply_ticket_tool`, `comment_ticket_tool`, `set_ticket_status_tool`).
  Optional and per-user, enabled by default (spec 011).
- **Discussions** plugin: a first-class tab for conversations to have with
  people, broken out of the Todos "Discussions" list. Each discussion records
  the person, topic, context, talking points, priority, and — once it happens —
  the outcome, and the list is organized and filtered by person. Ships with its
  own `/api/discussions/sync` endpoint, IndexedDB store, and MCP tools
  (`list_discussions`, `create_discussion`, `mark_discussed`,
  `update_discussion`, `delete_discussion`, `reorder_discussion`). Optional and
  per-user, enabled by default (spec 008).
- Mobile week view: on screens 768px wide or narrower, the weekly overview
  becomes a tappable 7-day strip (today in the accent color, the selected day
  filled, with each day's pomodoro count) and the selected day's pomodoros
  appear full-width below. Swipe left or right to change days; swiping past
  either end moves to the adjacent week. The +/− controls are always visible
  on mobile instead of only on hover, which touch screens can't do.

### Fixed
- The weekly pie chart's labels no longer clip off-screen on phones; at
  768px and below it shows a legend with counts under the chart instead.
- Completing a discussion now works on desktop. The checkbox called a native
  `prompt()` to capture the outcome; browsers suppress that dialog in several
  desktop cases, so it returned null and the click did nothing. One click now
  marks it discussed (preserving any existing outcome); the outcome is recorded
  by editing the discussion.
- The Discussions person filter now lists only people who still have an open
  discussion. People whose discussions are all done drop off the bar, so it
  reflects conversations that still need to happen; the edit-modal autocomplete
  still offers every known person.
- Edit modals no longer clip off the top of the screen on mobile. The modal now
  scrolls internally with a sticky Save/Cancel footer, instead of overflowing a
  fixed, centered overlay with no way to reach the top field. The Discussions form
  also leads with Person and Topic, tucks the enrichment fields behind a "More
  details" expander, and only shows Outcome when editing an existing discussion.
- The production image now includes `discussions_plugin.py`. The Containerfile
  copies an explicit file list and the new module was missing, so v2.17.0 booted
  into `ModuleNotFoundError` and gunicorn failed to start. A build-time import
  check now fails the build if any app module is missing from the image.
- Pull requests now build the base and app images and fail on fixable
  HIGH/CRITICAL vulnerabilities. Before, Trivy ran only after an image had
  been pushed, with exit code 0, so it could never stop anything. Accepted
  findings go in `.trivyignore` with a reason.
- Two Gourmand exceptions had their `classification` stranded below a stale
  section header; the headers are gone.
- Todo edits that fail to reach the cloud backend are no longer deleted by
  the next auto-refresh: the push checks the response, stays pending and
  retries.

### Changed
- Relicensed from GPL-3.0 to AGPL-3.0-or-later, matching Constitution I and
  what this repo's constitution already declared.

### Changed

- Constitution is now a v1.18.0 manifest: fleet and profile rules apply by
  reference, and the file keeps only what is specific to this repo.
- Constitution validation is pinned to the inherited release via
  `.github/workflows/constitution.yml`.
- Dependabot auto-merges GitHub Actions minor and patch updates.

## [2.16.2] - 2026-09-20

### Fixed

- `acquacotta-base` and `acquacotta-test` never carried a semver tag matching
  the app's release version. `container-base.yml` only had a path-triggered
  push to `main` (Containerfile.base/.test changes) plus `:latest`/`:sha`
  tags -- no `tags: v*` trigger at all, so a release of the main app never
  produced a matching base/test image. Nagios's registry-drift check
  (crunchtools/nagios-agent) expects every image in a repo to carry its
  newest git tag; these silently never did. Added the tag trigger and a
  `docker/metadata-action` semver tag to all four jobs (base + test, Quay +
  GHCR).

## [2.16.1] - 2026-08-01

This changelog starts here (RT #1484). acquacotta has 76 version tags and no
GitHub Releases, so there are no authored release notes to back-fill from.
Reconstructing that history from commit subjects would satisfy the letter of
Constitution II while defeating its purpose, so it has deliberately not been
done. Everything from this version forward is recorded properly.

For history prior to 2.16.1, see `git log` and the tag list.
