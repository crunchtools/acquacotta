# Acquacotta - Claude Code Instructions

## Project Overview

Acquacotta is a personal daily productivity cockpit with Pomodoro time tracking at its core. Before making changes, understand the project's governing principles and specifications.

## Required Reading

Before implementing any feature or making significant changes, read:

1. **Constitution** (`.specify/memory/constitution.md`) - Core principles that govern all decisions
2. **Baseline Spec** (`.specify/specs/000-baseline/spec.md`) - All user stories and requirements
3. **Technical Plan** (`.specify/specs/000-baseline/plan.md`) - Architecture and API documentation

## Core Principles (Summary)

All work must align with these principles (in priority order):

1. **Privacy by Design** - No analytics, no telemetry, minimal OAuth scopes
2. **User Data Ownership** - Data lives in user's Google Sheets, not our servers
3. **Simplicity & Focus** - Core stays minimal; plugins extend without bloating
4. **Timer Agnosticism** - Internal timer and external physical timers are equally supported
5. **Offline-First** - IndexedDB cache for all reads, background sync to Google Sheets
6. **Container-Ready** - Single container, env var config, no persistent volumes

## Technology Stack

- **Backend**: Python 3.x / Flask
- **Frontend**: Vanilla HTML/CSS/JavaScript (no build step)
- **Local Storage**: IndexedDB (browser-side)
- **Cloud Storage**: Google Sheets API v4
- **Auth**: Google OAuth 2.0 (credentials stored in IndexedDB, server is stateless)

## Local Development

### Container Names (Standardized)

Always use these exact names for local development:

- **Image**: `acquacotta:dev`
- **Container**: `acquacotta-dev`

### Build and Run Commands

```bash
# Build the dev image
podman build -t acquacotta:dev .

# Stop and remove existing container, then run new one
# Note: Map host port 5000 to container port 80 (Apache reverse proxy)
podman stop acquacotta-dev 2>/dev/null; podman rm acquacotta-dev 2>/dev/null
podman run -d --name acquacotta-dev -p 5000:80 --env-file .env acquacotta:dev

# View logs
podman logs acquacotta-dev

# One-liner for rebuild and restart
podman build -t acquacotta:dev . && podman stop acquacotta-dev 2>/dev/null; podman rm acquacotta-dev 2>/dev/null; podman run -d --name acquacotta-dev -p 5000:80 --env-file .env acquacotta:dev
```

### Environment Variables (.env)

Required for local development:
```
FLASK_ENV=development
FLASK_SECRET_KEY=dev-secret-key-not-for-production
SESSION_COOKIE_SECURE=false
OAUTH_REDIRECT_BASE=http://localhost:5000
GOOGLE_CLIENT_ID=<your-client-id>
GOOGLE_CLIENT_SECRET=<your-client-secret>
```

Optional — required only to link the "JSON on pCloud" storage backend:
```
PCLOUD_CLIENT_ID=<your-pcloud-client-id>
PCLOUD_CLIENT_SECRET=<your-pcloud-client-secret>
```

## Before Making Changes

1. Check if the change aligns with the constitution principles
2. Verify the change fits within existing user stories or propose a new spec
3. Manual entry must remain a first-class feature (Timer Agnosticism principle)
4. Never add analytics, tracking, or telemetry
5. Keep the UI minimal and distraction-free

## After Merging a PR

**ALWAYS** create a version tag after merging any PR:

1. Determine version bump type based on the constitution's semver rules:
   - **Patch** (x.y.Z): Bug fixes, minor tweaks, UI adjustments
   - **Minor** (x.Y.0): New features or significant enhancements
   - **Major** (X.0.0): Breaking changes to data format, API, or schema
2. Create and push the git tag (e.g., `git tag v1.18.1 && git push origin v1.18.1`)
3. This triggers the container build workflow automatically

Do NOT wait to be asked - tagging is part of the merge process.

## Spec-Kit Commands

Use these slash commands for structured development:

- `/speckit.constitution` - Update project principles
- `/speckit.specify` - Create a new feature specification
- `/speckit.plan` - Create implementation plan from spec
- `/speckit.tasks` - Generate task breakdown
- `/speckit.implement` - Execute implementation
- `/speckit.clarify` - Clarify ambiguous requirements
- `/speckit.analyze` - Cross-artifact consistency check

## File Structure

```
.specify/
├── memory/constitution.md    # Governing principles
├── specs/                    # Feature specifications
│   └── 000-baseline/         # Current app baseline
└── templates/                # Spec-kit templates

app.py                        # Flask application
sheets_storage.py             # Google Sheets operations
templates/                    # HTML templates
```

## Active Technologies
- JavaScript (ES6+), embedded in HTML + None (vanilla JS, no frameworks per constitution) (001-slidable-timer)
- N/A (timer state is in-memory only) (001-slidable-timer)

## Recent Changes
- 001-slidable-timer: Added JavaScript (ES6+), embedded in HTML + None (vanilla JS, no frameworks per constitution)
