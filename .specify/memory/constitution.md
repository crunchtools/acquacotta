# Acquacotta Constitution

> **Version:** 1.3.0
> **Ratified:** 2025-12-27
> **Status:** Active
> **Inherits:** [crunchtools/constitution](https://github.com/crunchtools/constitution) v1.6.0
> **Profile:** Web Application

## License

AGPL-3.0-or-later. See the universal [crunchtools/constitution](https://github.com/crunchtools/constitution).

## Core Principles

### I. Privacy by Design
The application collects no analytics, telemetry, or usage data. Google OAuth is used solely for authentication and Sheets API access. No user data is stored on application servers - all data flows directly between user browser and Google APIs. Session data expires and is not persisted beyond the browser session. The application requests minimal OAuth scopes (`drive.file` for app-created files only).

### II. User Data Ownership
Users own and control their data. All pomodoro records and settings are stored in the user's personal Google Sheets, accessible and editable outside the application. The application creates no proprietary data formats or vendor lock-in. Users can export their data to CSV at any time. Deleting the application leaves user data intact in their Google Drive.

### III. Simplicity & Focus
Acquacotta is a Pomodoro timer and time tracker - nothing more. Features MUST directly support: starting/stopping timers, categorizing completed work, and viewing time reports. Feature requests that deviate from core Pomodoro methodology require explicit justification. The UI MUST remain minimal and distraction-free. Avoid feature creep - say no to features that add complexity without proportional value.

### IV. Timer Agnosticism
Users MUST be able to use the built-in timer OR an external physical timer (e.g., a desk timer) with equal effectiveness. The application MUST NOT assume the internal timer is always used. Manual entry of pomodoros MUST be a first-class feature, not an afterthought. The UI MUST make it equally easy to: (a) start the internal timer and log on completion, or (b) log a completed pomodoro after using an external timer. Time tracking is the core value - the timer is optional tooling.

### V. Offline-First Architecture
The application MUST function without network connectivity. Local SQLite serves as the primary data store for all read operations. Background sync propagates changes to Google Sheets without blocking user interactions. Sync failures MUST NOT disrupt the user experience - operations queue for retry. Local cache provides instant responsiveness regardless of network conditions.

### VI. Container-Ready Deployment
The application MUST be deployable as a single container with no external dependencies beyond Google APIs. All configuration via environment variables. No required persistent volumes for application state (user data lives in Google Sheets). Stateless design enables horizontal scaling. Support both rootless Podman and Docker deployments.

## Technology Constraints

### Stack Requirements
- **Backend**: Python 3.x with Flask
- **Frontend**: Vanilla HTML/CSS/JavaScript (no build step required)
- **Local Storage**: SQLite for offline cache
- **Cloud Storage**: Google Sheets API v4
- **Authentication**: Google OAuth 2.0
- **Containerization**: OCI-compliant container images

### Security Requirements
- HTTPS required for production deployments
- OAuth tokens stored only in server-side sessions
- No client-side storage of credentials
- CSRF protection on all state-changing endpoints
- Input validation on all API endpoints

### Performance Targets
- Timer accuracy within 1 second
- UI response time under 100ms for local operations
- Sync operations complete within 5 seconds under normal network conditions
- Support for 10,000+ pomodoro records per user

## Development Workflow

### Code Quality Gates
- All Python code MUST pass linting (flake8/ruff)
- Frontend code MUST work without JavaScript frameworks
- API endpoints MUST return JSON with consistent error formats
- Changes MUST be tested manually before merge

### Branching Strategy
- `main` branch is always deployable
- Feature branches follow `feature/description` naming
- Bug fixes follow `fix/description` naming
- All changes via pull request with review

### Release & Versioning
The application follows [Semantic Versioning](https://semver.org/) (semver):
- **Major** (X.0.0): Breaking changes to user data format, API, or Google Sheets schema
- **Minor** (x.Y.0): New features or significant enhancements (e.g., new UI capabilities)
- **Patch** (x.y.Z): Bug fixes, performance improvements, or minor tweaks

Container builds via GitHub Actions MUST trigger on BOTH:
- `push: branches: [main]` — every merge to `main` rebuilds `:latest` automatically, so production never lags behind `main`.
- `push: tags: [v*]` — version tags additionally publish an immutable `:vX.Y.Z` tag.

Container image tags MUST be unique to this repository. No other repository — including archived siblings or forks — may publish to the same `quay.io/crunchtools/<image>` tag. A zombie repo sharing a tag will silently overwrite production. (See 2026-05-19 incident: `acquacotta-old`'s weekly cron clobbered the OAuth fix six times in a row.)

Deployed systemd units on lotor MUST include `--label io.containers.autoupdate=registry` and `--label PODMAN_SYSTEMD_UNIT=<unit>.service` so the nightly `podman-auto-update.timer` pulls new `:latest` images automatically.

After merging a PR:
1. Confirm the merge-to-`main` build pushed `:latest` to quay.
2. Determine version bump type based on changes; tag (e.g., `v1.14.0`) and push to also publish a `:vX.Y.Z` tag.
3. Lotor auto-update reconciles overnight; force-pull with `podman auto-update` on lotor if urgent.

## Deployment & Operations

### Host Layout
Deployed on lotor at `/srv/acquacotta.crunchtools.com/` following the standard
`code/` / `config/` / `data/` convention; the container bind-mounts these
directories and publishes `127.0.0.1:8080:80` behind the crunchtools reverse proxy.

### Monitoring
Monitored by Zabbix: a web scenario against `https://acquacotta.crunchtools.com`,
a container-port check on `:8080`, and a Gunicorn process check.

### Testing
| Test | What it verifies |
|------|------------------|
| **Build test** | CI builds the image from the Containerfile on every push and PR |
| **Smoke test** | Container starts and the Flask app answers a health check on `:8080` |

### Cascade Rebuild
Rebuilds weekly and on `repository_dispatch` when the parent image updates
(parent-image-updated cascade), picking up base-image security fixes.

## Governance

This constitution supersedes informal practices and ad-hoc decisions. Amendments require:
1. Written proposal with rationale
2. Review period for feedback
3. Documentation of the change
4. Version increment

All development decisions MUST align with these principles. When principles conflict, prioritize in order: Privacy, User Data Ownership, Simplicity, Timer Agnosticism, Offline-First, Container-Ready.

**Version**: 1.3.0 | **Ratified**: 2025-12-27 | **Last Amended**: 2026-05-19
