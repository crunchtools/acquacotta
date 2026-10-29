# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and this project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [2.32.0] - 2026-10-29

### Changed
- Modals: every record modal ends Copy link · · · Cancel, Save. The primary
  button is last, as on GNOME, Android and macOS, and the label names the
  action (NN/g, PatternFly). Add Pomodoro's "Add" is now "Save".
- Tickets: the ticket modal is an edit form like the others. One Save applies
  the comment or reply and the status change, then closes; Cancel discards.
  "Set status" and "Send" are gone, and status is a dropdown of RT's
  lifecycle instead of free text.
- Escape presses the open modal's Cancel on every modal that has one (it used
  to work only on the pomodoro add and edit modals).
- tests/test_modals.py enforces the labels, the order and the Escape wiring.

## [2.31.3] - 2026-10-29

### Fixed
- Tickets: on a phone (or with larger text) the ticket modal clipped its
  Close and Send buttons off the bottom, so it could not be dismissed. The
  modal now scrolls as a whole when it doesn't fit, with the actions pinned
  to the bottom. Modal titles are smaller on narrow screens.

## [2.31.2] - 2026-10-29

### Fixed
- Modals: every view and plugin uses one modal component. Record modals
  (pomodoros, to-dos, discussions, tickets) are all the same width; only
  confirmations and system prompts use the compact size. Any modal can mark a
  long region `.modal-scroll` to get the ticket modal's scrolling. A test
  fails the build if a modal is sized by id or inline style.

## [2.31.1] - 2026-10-29

### Fixed
- Tickets: the ticket modal no longer scrolls as a whole. The header, comment
  form and actions stay in place and only the history thread scrolls, filling
  the height that is left. Modal scrollbars are thin and theme-coloured, and
  the page behind an open modal no longer scrolls.

## [2.31.0] - 2026-10-29

### Changed
- Social: Bluesky posts carry a link card instead of the article image as a
  photo. Our Postiz (0.8.0, fork patch 9) builds the card, so Bluesky joins
  X, Mastodon and Threads in getting the bare link. The composer counts a
  Bluesky link as bsky.app shows it (`www.xda-developers.com/linus-torval...`,
  38 characters, not 132), and counts graphemes.

## [2.30.1] - 2026-10-29

### Fixed
- Social → Posts "Open in Postiz" opens Postiz's calendar on the post's day
  instead of the Postiz home page. Postiz has no URL that opens a single post
  in its editor; its calendar takes `startDate`, `endDate` and `display`.

## [2.30.0] - 2026-10-29

### Changed
- Social → Posts uses Compose's parts and layout (Fable UX spec,
  `specs/015-social-consistency`). A Past | Upcoming segment sits where
  Post now | Schedule sits in Compose; below it are ten entries and Show more.
  Every channel glyph is Compose's 44px chip: filled when it goes or went,
  outline when it doesn't, ringed when it needs a look. There is no green.
  Each row has the same layout: date and time, channels, text.
- Day blocks, "No posts" lines and Earlier/Next week paging are gone.
  Show more fetches further out (56-day windows, up to a year).
- `#social/posts/past` links to Past.
- Arrow keys move between the options of every Social segment. The Compose
  over-limit chip class `over` is now `flag`.

## [2.29.0] - 2026-10-28

### Changed
- Social → Posts shows one entry per post, not one per channel (Fable UX
  revision). Postiz records at the same minute join when they share a group or
  say the same thing (whitespace and links ignored), so a post made separately
  in Postiz for each channel is one entry too. Channels with the same text are
  one version; when they differ the entry says "· 2 versions" and lists each
  version once, captioned "On X" / "On LinkedIn, Mastodon".
- Entries expand in place (one at a time) instead of opening a bottom sheet:
  the text once, then a line per channel with its state and "View post ›",
  then Copy link and Open in Postiz. `#social/post/<id>` opens the entry for
  any of its channels' ids.
- A partly failed post reads "1 of 3 failed".
- Runs of empty days fold into one line ("Fri, Oct 30 – Sat, Oct 31  No posts").

## [2.28.0] - 2026-10-28

### Changed
- Social → Posts redesigned to match Compose (Fable UX spec): the slot sheet's
  day blocks starting at Today, a week at a time ("Next week ›" appends);
  last week is loaded but collapsed behind "‹ Last week", which shows how many
  of its posts failed. Rows are link-card style with the time, an exception
  word (Failed, Draft, Not sent yet), state chips and two lines of text; a
  failed post gets an accent bar. One status line for signed out, Postiz not
  connected, offline and unreachable, with the matching action button.
- The post sheet always shows each channel's state as a word.
- A deep link to a post outside the first two weeks is looked up nine weeks
  either side.
- Sending from Compose drops the cached Posts copy so Posts paints fresh.

## [2.27.0] - 2026-10-28

### Added
- Deep links: every tab, sub-view and item has a URL (`/#todos/item/<id>`,
  `/#rt/ticket/<id>`, `/#discussions/person/<name>`, `/#social/posts`, …; see
  `specs/013-deep-links`), for calendar invites, emails and handing items to
  agents. Each item dialog has a Copy link button (the installed app has no
  address bar). A link survives a Google sign-in. A link to a missing item or a
  turned-off tab falls back with a notice. New plugins get links by registering a
  route handler.
- A ticket link opens any ticket, not only those in the Tickets query
  (`GET /api/rt/ticket/<id>`).
- MCP tools return a `link` on each todo, discussion, ticket and pomodoro when
  `ACQUACOTTA_PUBLIC_URL` is set.
- Social → Posts: the Postiz schedule, past and future (last week plus the next
  four), one row per post group with per-channel status; tap for each channel's
  full text, the published post and Postiz (`GET /api/social/posts`). Read-only.

### Security
- Authlib 1.8.0 → 1.9.1 (CVE-2026-96760 critical, CVE-2026-114615, CVE-2026-114616),
  oauthlib 3.3.1 → 4.0.0 (CVE-2026-49272), dnspython 2.8.0 → 2.9.0 (CVE-2026-114605).

### Fixed
- Reports could draw the daily chart twice when two loads overlapped (fast
  period clicks), throwing "Canvas is already in use".
- The Reports period label and ‹ › stepping parsed the date as UTC, so west of
  UTC the Day view showed yesterday and stepping stalled or skipped a day.

## [2.26.2] - 2026-10-28

### Fixed
- Shared-link images now post reliably on LinkedIn and Bluesky. The image is no
  longer uploaded to Postiz first; acquacotta validates it (same SSRF guard) and
  hands Postiz the source image URL as the media path. A Postiz-hosted upload URL
  is not fetchable from inside the Postiz container (its public hostname serves a
  self-signed cert there, and Postiz's own guard blocks the internal address), so
  LinkedIn and Bluesky — which download the image themselves — failed on it, while
  Facebook (which has its servers fetch the URL) succeeded. The source URL is
  publicly reachable, so every provider can fetch it.

## [2.26.1] - 2026-10-27

### Changed
- Shared-link images are now attached per platform instead of to every channel.
  X, Mastodon, and Threads get the bare URL so they keep auto-unfurling their own
  native card, which a photo attachment would otherwise suppress. Every other
  channel (LinkedIn, Bluesky, Facebook, and media-first platforms like Instagram)
  gets the article photo, since it can't make a good card from a bare URL. This
  fixes the v2.26.0 regression where attaching the photo everywhere replaced
  those native cards with a lone image. When every selected channel unfurls its
  own link, the image is not fetched or uploaded at all.

## [2.26.0] - 2026-10-26

### Changed
- Shared links now post with the article image. The composer sends the page's
  og:image URL (already fetched for the preview card) back on post, and the
  server attaches it to every selected channel as a photo. LinkedIn and Bluesky,
  which don't unfurl a link posted through their API, now show the image instead
  of a bare link. Removing the card with ✕ still posts without it.

## [2.25.0] - 2026-10-25

### Changed
- Social composer redesign (UX spec by Fable). **Post now | Schedule** segment
  above the button; Post now shows nothing else. Schedule shows the next open
  slot, and tapping it opens a bottom sheet of Postiz's open slots grouped by
  day, a week at a time (**Next week ›** for more), with **Set an exact
  time…** as the escape hatch. Replaces the ‹ › arrows.
- One tap sends (the two-tap confirm is gone). The button says what will
  happen: "Post to 6 channels" or "Schedule · Sun 10:20 AM".
- One status line under the composer; errors in the accent colour. Draft from
  link sits beside the counter. Channel marks are plain letters, no emoji.

### Added
- `GET /api/social/slots?channel&start&days`: every open slot for a run of
  local days in one request (days walked in parallel).

### Fixed
- Slot controls showed in Post-now mode (`display:flex` overrode `hidden`).
- Stale JavaScript after a deploy: static scripts are now versioned by a hash
  of their content instead of a hand-bumped number, which v2.24.0 missed, so
  phones kept the old slot code for hours behind Cloudflare's cache.

## [2.24.0] - 2026-10-24

### Added
- ‹ › beside the scheduled slot step through Postiz's open slots: › asks for
  the first free slot after the one shown (needs crunchtools/postiz >= 0.7.0,
  `find-slot?after=`), ‹ steps back. The slot shown is the one scheduled.

## [2.23.0] - 2026-10-24

### Added
- "Schedule for later" now offers **Next open slot** (the default, labelled
  with the slot, e.g. "Mon, Oct 26, 10:20 AM") or **Pick a time**. Next open
  slot sends no time; the server asks Postiz for the free window at send time,
  so it can't go stale. With crunchtools/postiz v0.6.0 and
  `POSTIZ_SLOT_WEEKDAYS=1-5`, that slot skips weekends.

## [2.22.1] - 2026-10-24

### Fixed
- "Schedule for later" prefilled every post with the next weekday at 9 AM, so
  scheduled posts piled onto one time. The picker now fills with Postiz's next
  free posting window for the channel (new `GET /api/social/slot`), so each
  post takes the next open window. A time you pick by hand still wins.

## [2.22.0] - 2026-10-24

### Changed
- Social composer redesign (UX review by Fable): text first, then a link card
  (thumbnail, title, site; ✕ removes it) for a shared link, one row of platform
  chips that remember your selection, a "N left · X" counter that names any
  channel you're over, and one button ("Post to N channels"). "Schedule for
  later" switches that button to scheduling instead of adding a second one.
  The confirming tap waits until you tap again or tap elsewhere, with no timer.
- Channels render instantly from a per-device cache and refresh in the
  background (the Postiz round trip took 1.2–2.1 s on every open).

### Added
- `POST /api/social/preview`: a link card for the composer. The og:image travels
  as a data: URI under 750 KB (the CSP blocks other image hosts), and it's
  display-only: posts carry just the URL and each platform builds its own card.

## [2.21.0] - 2026-10-24

### Changed
- Social is now a single composer: one text box, channel toggle chips, a count
  against the tightest selected limit, and Post now / Schedule buttons. It
  replaces one card per channel. A shared link drops into the text box instead
  of drafting automatically, and "Draft from link" (Gemini, optional) writes one
  post sized for every selected channel. Post now takes a confirming second tap.
- Channel avatars are gone: Acquacotta's CSP blocks Postiz-hosted images, so
  they rendered broken; channels show as platform-name chips instead.

## [2.20.1] - 2026-10-24

### Fixed
- Social Share: a bare Postiz address (`https://postiz.example.com`) now resolves
  to `/api/public/v1`. It used to resolve to `/public/v1`, which the Postiz
  frontend answers with a redirect, so channels failed to load with a 502.
  Configs saved that way are repaired on use, and a redirect now reports the
  URL problem instead of a generic error.
- The Social settings form marks the Gemini key optional.

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
