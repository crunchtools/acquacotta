# acquacotta Constitution

> **Version:** 1.0.0
> **Ratified:** 2026-03-10
> **Status:** Active
> **Inherits:** [crunchtools/constitution](https://github.com/crunchtools/constitution) v1.3.0
> **Profile:** Web Application

Acquacotta recipe tracker — Flask + Gunicorn behind Apache on ubi10-httpd. Pomodoro timer and time tracking app backed by Google Sheets API.

---

## License

AGPL-3.0-or-later

## Versioning

Follow Semantic Versioning 2.0.0. MAJOR/MINOR/PATCH.

## Base Image

`quay.io/crunchtools/ubi10-httpd:latest` — inherits Apache httpd with systemd from the crunchtools image tree. No RHSM needed; Python 3.12 is available in UBI repos.

**Parent image for cascade rebuild:** `quay.io/crunchtools/ubi10-httpd`

## Application Runtime

- **Language:** Python 3.12 with Flask and Gunicorn
- **Dependencies:** `requirements.txt`, installed with `pip3.12 install`
- **Services:**
  - `acquacotta.service` — Gunicorn serving the Flask app
  - `httpd.service` — Apache reverse proxy (inherited from ubi10-httpd)
- **Entry point:** `/sbin/init` (systemd)

## Host Directory Convention

Host data lives under `/srv/acquacotta/`:

- `code/` — application source (app.py, templates/, static/) bind-mounted `:ro,Z`
- `config/` — Apache vhost config, environment files bind-mounted `:ro,Z`
- `data/` — session data, local cache bind-mounted `:Z`

## Data Persistence

Acquacotta is primarily stateless — user data lives in Google Sheets, not locally. Local SQLite is used only as a read cache for offline-first operation. No database initialization service is needed. Session data does not persist across container restarts.

Volume mount for data directory provides cache persistence when desired.

## Containerfile Conventions

- Single-stage build on `ubi10-httpd`
- `rootfs/` directory provides systemd units and Apache config
- `dnf install` for Python, then `pip install` for dependencies, then `dnf clean all`
- Required LABELs: `maintainer`, `description`
- Default welcome page removed: `rm -f /etc/httpd/conf.d/welcome.conf`

## Runtime Configuration

- Environment file: `/etc/acquacotta.env` loaded via systemd `EnvironmentFile=`
- Google OAuth credentials via environment variables (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`)
- No hardcoded credentials in Containerfile or application code

## Registry

Published to `quay.io/crunchtools/acquacotta`.

## Cascade Rebuild

Workflow includes `repository_dispatch` listener for `parent-image-updated` events. When `ubi10-httpd` is updated, acquacotta rebuilds automatically.

## Monitoring

Zabbix monitoring:
- Web scenario (HTTP check) for Apache on port 80
- Application health check on Flask/Gunicorn

## Testing

- **Build test**: CI builds the Containerfile on every push to main
- **Health check**: Application starts and Apache responds with HTTP 200
- **Smoke test**: Core pages render correctly

## Quality Gates

1. Build — Containerfile builds successfully
2. Application health test — HTTP 200 from Apache
3. Push — Image pushed to Quay.io
