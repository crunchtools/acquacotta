# Acquacotta Constitution

> **Version:** 2.1.0
> **Ratified:** 2025-12-27
> **Amended:** 2026-10-02
> **Status:** Active
> **Inherits:** [crunchtools/constitution](https://github.com/crunchtools/constitution) v1.21.0
> **Profile:** Web Application

This file holds what is specific to Acquacotta. The fleet rules and the Web
Application profile apply at the inherited version and are checked against
this repo's files by `constitution.yml`. They are not restated here.

## Product Principles

When these conflict, they win in this order.

1. **Privacy by design.** No analytics, telemetry or usage data. Google OAuth
   is used only for authentication and Sheets/Drive access, with the minimal
   scope `drive.file` (app-created files only). No user data is stored on the
   server.
2. **User data ownership.** Pomodoro records and settings live in the user's
   own Google Sheets, readable and editable outside the app, exportable to
   CSV. No proprietary format; removing the app leaves the data intact in the
   user's Drive.
3. **Simplicity and focus.** Acquacotta is a personal daily productivity
   cockpit: timer, time tracking, and plugins for todos, checklists, briefings
   and integrations. The core stays minimal and distraction-free; each plugin
   owns its own data and UI surface. Features outside daily personal
   productivity need explicit justification.
4. **Timer agnosticism.** The built-in timer and an external physical timer
   are equally supported. Manual entry of a completed pomodoro is a
   first-class feature; time tracking is the value, the timer is optional.
5. **Offline-first.** The app works without network. A browser-side
   IndexedDB cache serves all reads; background sync to Google Sheets never
   blocks the user, and failed syncs queue for retry.
6. **Container-ready.** One container, no dependency beyond Google APIs,
   configuration by environment variables, no persistent volume for
   application state.

## Stack and Credential Custody

- **Backend:** Python 3 with Flask (WSGI) behind Apache in the container. A
  plugin MAY run a second Python process with an ASGI framework
  (FastMCP/uvicorn) in the same container, such as the MCP server at `/mcp`,
  provided it stays stateless and single-container.
- **Frontend:** vanilla HTML/CSS/JavaScript, no framework and no build step.
- **Cloud storage:** Google Sheets API v4; **auth:** Google OAuth 2.0.
- **Stateless server:** it persists no OAuth credentials and no sessions.
  Credentials are held client-side (the browser in IndexedDB; agent/MCP
  access through an encrypted, server-sealed bearer token) and decrypted in
  memory per request. No refresh token is ever persisted server-side.
- Client-side custody is bounded by the `drive.file` scope, authenticated
  encryption of sealed tokens, and durable per-user revocation stored in the
  user's own storage, not on the server.
- HTTPS in production, CSRF protection on every state-changing endpoint,
  input validation on every API endpoint, and JSON responses with a
  consistent error format.

## Performance Targets

- Timer accuracy within 1 second.
- UI response under 100 ms for local operations.
- Sync completes within 5 seconds under normal network conditions.
- 10,000+ pomodoro records per user.

## Version Bump Meaning

MAJOR for breaking changes to the user data format, the API or the Google
Sheets schema; MINOR for new features; PATCH for fixes and minor tweaks.

## Image Chain and Release

- `Containerfile.base` builds `quay.io/crunchtools/acquacotta-base` (and
  `Containerfile.test` the `acquacotta-test` image) from
  `quay.io/crunchtools/ubi10-core`. **Parent image for cascade:**
  `quay.io/crunchtools/ubi10-core`; the base workflow listens for
  `parent-image-updated`.
- `Containerfile` builds `quay.io/crunchtools/acquacotta` from
  `acquacotta-base`.
- Every push to `main` rebuilds `:latest`, so production never lags `main`;
  a `v*` tag also publishes an immutable `:vX.Y.Z`.
- Image tags are unique to this repository. No other repo, including archived
  siblings and forks, may publish to the same tag: on 2026-05-19
  `acquacotta-old`'s weekly cron overwrote the OAuth fix six times in a row.
- Deployed units carry `--label io.containers.autoupdate=registry` and
  `--label PODMAN_SYSTEMD_UNIT=<unit>.service` so the nightly
  `podman-auto-update.timer` pulls the new `:latest`.

## Host Layout

Deployed at `/srv/<service>/` with the standard `code/`, `config/` and
`data/` directories bind-mounted into the container, published on
`127.0.0.1:8080:80` behind the crunchtools reverse proxy.

## Monitoring Coverage

Nagios: an HTTP check against `https://acquacotta.crunchtools.com`, a
container-port check on `:8080`, a Gunicorn process check and, when the MCP
plugin is enabled, an MCP (uvicorn) process check.

## Smoke Test

`smoke_test.sh`: the container starts, the Flask app answers a health check on
`:8080`, and the MCP endpoint completes an `initialize` handshake at `/mcp`.
Frontend changes are also tested by hand before merge.

## History

| Version | Date | Changes |
|---------|------|---------|
| 2.1.0 | 2026-10-02 | Manifest under constitution v1.18.0: fleet and profile restatement removed; offline cache corrected from SQLite to IndexedDB to match the code |

Earlier versions, from ratification on 2025-12-27 through 2.0.1, are in git
history.
