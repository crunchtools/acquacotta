# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and this project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [2.20.0] - 2026-10-24

### Added
- **Social Share** plugin (spec 012). Install Acquacotta on Android and it shows up
  in the share sheet. Share a link and the new Social tab drafts one post per Postiz
  channel with Gemini, each within that channel's character limit. Edit the drafts,
  untick channels, and schedule for Postiz's next free slot, at a time you choose,
  or as Postiz drafts. The Postiz URL and API key, the Gemini key and model, and
  the default channels are stored only in your own Drive, encrypted. A link shared
  while signed out survives Google sign-in. Optional and per-user, enabled by
  default.
- The app is now an installable PWA: a web app manifest with icons and a share
  target, and a pass-through service worker that caches nothing.
- **Settings over MCP.** New tools `get_settings` and `update_settings` read
  and change your preferences: timer presets, breaks, sounds, display, clock,
  working hours, daily goal, Pomodoro types and colors, tab order, and turning
  optional plugins on or off. Every write is checked against an explicit
  schema, and unknown keys are rejected. RT's connection is configurable
  over MCP too, through `get_rt_config`, `set_rt_config` and
  `test_rt_connection`. Passwords and tokens are write-only and are never
  returned. Three settings are deliberately left out of MCP because they go
  through browser OAuth or session flows: enabling or rotating MCP access
  itself, switching the storage backend, and linking pCloud.
- **Tab order.** A new Tab Order card in Settings lets you drag the top-level
  tabs into any order, or move them with the arrow buttons. Reset to default
  restores the original order. The order is saved with your settings, and
  arrow-key navigation follows it.
- **Plugin settings live on the plugin.** Each plugin that has settings now
  shows a ⚙ Settings button on its row in the Plugins card, and the settings
  open inline beneath it. These replace the separate To-do, Discussions and
  RT Tickets cards. The Tickets tab has its own ⚙ button and, until RT is
  connected, a Connect RT button. Both open the RT settings directly.
- **RT Tickets** plugin: a first-class tab for your Request Tracker tickets,
  grouped by queue with a dynamic queue filter bar, and a detail view showing
  each ticket's native RT history thread. You can reply, comment, and change
  status from inside Acquacotta. RT is the source of truth: the server proxies
  RT's REST 2.0 API per request (reads are cached in IndexedDB for offline) and
  never stores ticket data. Point it at any RT 5+/6.x instance — the base URL,
  auth (HTTP Basic or an RT REST token), and the TicketSQL search are per-user
  config stored only in your own Google Drive, never on the server. Ships with
  its own `/api/rt/*` endpoints and MCP tools (`list_tickets`, `get_ticket`,
  `reply_ticket`, `comment_ticket`, `set_ticket_status`).
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
- `RT_ALLOWED_HOSTS` was never passed through to Gunicorn, so the RT allowlist
  set in the environment had no effect. It and `SOCIAL_ALLOWED_HOSTS` are now
  passed through. The README described an unset allowlist as "no restriction";
  it means public addresses only.
- RT ticket detail modal now widens to a readable 720px on desktop instead of
  staying a cramped 400px column (it shared the compact form-modal width). Mobile
  is unchanged — it was already full-width there.
- The "N items" badge on the Discussions and RT Tickets plugin rows now
  shows their real counts. Only To-do was being counted.
- RT settings now show how you sign in. The Authentication section is no
  longer collapsed. You choose "Username & password" or "REST token", a saved
  secret shows as •••••••• marked "saved", and a summary line names the method
  in use. The form reloads each time the panel opens. Choosing the token clears
  the username, since a saved username would otherwise take precedence.
- RT ticket history now shows message bodies, including each ticket's
  opening message. RT 6 links a transaction's attachments by URL only, with no
  id, so every body was being skipped.
- The Tickets tab no longer stays on "Loading tickets from RT…" when the
  request stalls. After 45 seconds it shows an error and falls back to the
  cached tickets.
- An RT URL saved without a scheme (`rt.example.com`) now gets `https://`
  added automatically. Before, every RT call failed with "base_url must be an
  http(s) URL".
- The buttons on plugin rows (Export CSV, Import CSV, Connect pCloud,
  Regenerate token) now look like buttons. A later style rule for the
  Pomodoro Types list was stripping them down to plain text.
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
- RT Tickets and Social Share share one implementation of secret encryption,
  Drive config storage and the SSRF destination check (`plugin_common.py`).
- Gunicorn's worker timeout is 90s (was the 30s default) and the container's
  Apache proxy timeout matches, so a draft that waits on Gemini isn't cut off.
- Relicensed from GPL-3.0 to AGPL-3.0-or-later, matching Constitution I and
  what this repo's constitution already declared.

### Changed

- Constitution is now a v1.18.0 manifest: fleet and profile rules apply by
  reference, and the file keeps only what is specific to this repo.
- Constitution validation is pinned to the inherited release via
  `.github/workflows/constitution.yml`.
- Dependabot auto-merges GitHub Actions minor and patch updates.
- CI runs browser tests against `index.html` (`tests/js/test_index.js`):
  tab order (apply, move, drag-and-drop, reset, save, arrow keys over hidden
  and reordered tabs) and plugin settings panels across `loadPlugins()`
  re-renders. The page is served with `Storage` and the CDN libraries stubbed.

### Security
- certifi 2026.10.23 (from 2026.7.22): drops the emSign root CAs whose
  intermediate keys were compromised (GHSA-6q48-6c7w-9gw2, critical).
- The SSRF check shared by RT Tickets and Social Share accepts only globally
  routable addresses (so carrier-grade NAT and IPv4-mapped loopback are refused
  too), and Social's fetches also check the address the socket actually
  connected to, which defeats DNS rebinding.
- Access logs (Gunicorn and the container's Apache) record the path without the
  query string or Referer, so shared links and OAuth location ids stay out of
  the logs.
- `escapeHtml` in the page now escapes quotes as well, so values it escapes are
  safe inside HTML attributes, not only in text.
- The Google sign-in hand-off page escapes `<` in its inline JSON, so a profile
  name can't close the script tag.

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
