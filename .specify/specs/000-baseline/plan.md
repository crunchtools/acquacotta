# Implementation Plan: Acquacotta Baseline

**Branch**: `000-baseline` | **Date**: 2025-12-27 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/000-baseline/spec.md`

## Summary

Acquacotta is a Pomodoro time tracking web application built with Python/Flask backend and vanilla HTML/CSS/JavaScript frontend. It uses a local SQLite cache for offline-first operation with background sync to Google Sheets for persistence. Users authenticate via Google OAuth 2.0 and their data is stored in a personal Google Sheet they own.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: Flask, Flask-Session, google-auth-oauthlib, google-api-python-client, Werkzeug
**Storage**: SQLite (local cache), Google Sheets API v4 (cloud persistence)
**Testing**: Manual testing, pytest (planned)
**Target Platform**: Linux/macOS/Windows browsers, containerized deployment
**Project Type**: Web application (monolithic - single Flask app serves API and static files)
**Performance Goals**: <100ms local operations, <5s sync operations
**Constraints**: Offline-capable, no persistent server storage, minimal OAuth scopes
**Scale/Scope**: Single user per session, 10,000+ pomodoros per user

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Privacy by Design | PASS | No analytics, minimal OAuth scopes, no server-side user data storage |
| II. User Data Ownership | PASS | Data stored in user's Google Sheets, CSV export available |
| III. Simplicity & Focus | PASS | Only Pomodoro timer, categorization, and reporting features |
| IV. Timer Agnosticism | PASS | Manual entry is P1 feature, UI supports both internal and external timer workflows |
| V. Offline-First | PASS | SQLite cache serves all reads, sync is background operation |
| VI. Container-Ready | PASS | Single container, env var config, no required volumes |

## Project Structure

### Documentation (this feature)

```text
.specify/
├── memory/
│   └── constitution.md      # Project principles and governance
├── specs/
│   └── 000-baseline/
│       ├── spec.md          # This baseline specification
│       └── plan.md          # This implementation plan
├── templates/               # Spec-kit templates
└── scripts/                 # Spec-kit automation scripts
```

### Source Code (repository root)

```text
# Web application structure
app.py                       # Flask application entry point
sheets_storage.py            # Google Sheets API operations

templates/
├── index.html               # Main application (timer, reports, settings)
├── privacy.html             # Privacy policy page
└── terms.html               # Terms of service page

.claude/
└── commands/                # Spec-kit slash commands
    ├── speckit.constitution.md
    ├── speckit.specify.md
    ├── speckit.plan.md
    ├── speckit.tasks.md
    ├── speckit.implement.md
    └── ...

# Supporting files
Dockerfile                   # Container build definition
requirements.txt             # Python dependencies
REQUIREMENTS.md              # Original requirements document
README.md                    # User documentation
```

**Structure Decision**: Monolithic web application - Flask serves both API endpoints and static HTML. Frontend is vanilla JavaScript embedded in index.html. This aligns with the Simplicity principle - no build step, no separate frontend deployment.

## Architecture Overview

### Data Flow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Browser UI    │────▶│   Flask API     │────▶│  SQLite Cache   │
│  (JavaScript)   │◀────│   (Python)      │◀────│  (Local)        │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │                        │
                               │ Background Sync        │
                               ▼                        │
                        ┌─────────────────┐            │
                        │  Google Sheets  │◀───────────┘
                        │     (Cloud)     │
                        └─────────────────┘
```

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Main application page |
| `/auth/google` | GET | Initiate Google OAuth |
| `/auth/callback` | GET | OAuth callback handler |
| `/auth/logout` | GET | Clear session and logout |
| `/api/auth/status` | GET | Get current auth state |
| `/api/pomodoros` | GET | List pomodoros (filtered by date) |
| `/api/pomodoros` | POST | Create new pomodoro |
| `/api/pomodoros/<id>` | PUT | Update pomodoro |
| `/api/pomodoros/<id>` | DELETE | Delete pomodoro |
| `/api/pomodoros/manual` | POST | Create manual entry |
| `/api/settings` | GET | Get user settings |
| `/api/settings` | POST | Save user settings |
| `/api/reports/<period>` | GET | Get report data (day/week/month) |
| `/api/export` | GET | Download CSV export |
| `/api/sync/status` | GET | Get sync status |
| `/api/sync/now` | POST | Trigger manual sync |
| `/api/migrate` | POST | Handle data migration |

#### Error Responses

Unexpected server-side failures on `/api/*` endpoints return HTTP 500 with a
fixed body; exception text and tracebacks are never sent to the client:

```json
{"error": "An internal error occurred", "correlation_id": "3f9c0a1b2d4e"}
```

The `correlation_id` (12 hex characters) is written to the server log next to
the full exception and traceback, so a user reporting a failure can quote it and
an operator can find the matching log entry. Non-API routes (OAuth start and
callback) return a plain-text `An internal error occurred. Reference: <id>` page
carrying the same id.

Expected errors keep a specific message: 400 for invalid input (validation
messages written for the user), 401 when not signed in, and 502 when an upstream
service (RT, Postiz, Gemini) fails — the 502 message names the service but does
not include the underlying network error.

### Database Schema

**pomodoros table**:
- `id` TEXT PRIMARY KEY
- `name` TEXT NOT NULL
- `type` TEXT NOT NULL
- `start_time` TEXT NOT NULL (ISO 8601)
- `end_time` TEXT NOT NULL (ISO 8601)
- `duration_minutes` INTEGER NOT NULL
- `notes` TEXT
- `synced` INTEGER DEFAULT 0

**settings table**:
- `key` TEXT PRIMARY KEY
- `value` TEXT NOT NULL (JSON encoded)
- `synced` INTEGER DEFAULT 0

**sync_queue table**:
- `id` INTEGER PRIMARY KEY AUTOINCREMENT
- `operation` TEXT NOT NULL
- `table_name` TEXT NOT NULL
- `record_id` TEXT NOT NULL
- `data` TEXT (JSON encoded)
- `created_at` TEXT NOT NULL

**sync_status table**:
- `key` TEXT PRIMARY KEY
- `value` TEXT NOT NULL

## Complexity Tracking

No constitution violations requiring justification.

## Key Implementation Decisions

1. **Per-user SQLite databases**: Each authenticated user gets a separate SQLite file (hashed email in filename) to isolate data and enable clean logout/login cycles.

2. **Background sync via threads**: Sync operations run in daemon threads to avoid blocking user interactions. Queue-based retry ensures eventual consistency.

3. **Google Drive API for file creation**: Using `drive.file` scope which only grants access to files created by the app, minimizing permission footprint.

4. **Session-based auth**: OAuth tokens stored in server-side Flask sessions, not in browser storage, for security.

5. **Single-file frontend**: All JavaScript/CSS embedded in index.html to eliminate build complexity and enable easy deployment.
