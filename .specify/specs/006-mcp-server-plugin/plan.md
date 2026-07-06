# Implementation Plan: Hosted MCP Server Plugin

**Branch**: `feature/111-mcp-server-plugin` | **Date**: 2026-07-06 | **Spec**: [spec.md](./spec.md)
**Status**: Planning

## Summary

Add a hosted MCP endpoint to the existing Flask app as a new plugin. The endpoint speaks MCP over Streamable HTTP, authenticates agents with a stateless sealed bearer token (encrypted `{refresh_token, folder_id}`), and dispatches every tool call through the existing `storage_api` / `todos_plugin` functions. The server stays a pure gateway: no user data or credentials persisted. Tools are contributed by enabled plugins via a new `MCP_TOOLS` descriptor list, so todos and pomodoros ship now and future plugins extend the surface without touching the core.

## Technical Context

**Language/Version**: Python 3.x (matches existing Flask app)
**Primary Dependencies**: Flask (existing web app, WSGI), **FastMCP >= 2.0** (Streamable HTTP MCP server — same framework as `mcp-trentina`; ASGI/Starlette), `cryptography` (Fernet) for token sealing, `google-api-python-client` / `gspread` (existing), `google-auth` for refresh-token → access-token exchange
**Storage**: None new — reuses user's Google Drive via existing storage/plugin functions. No server-side persistence, no new volume.
**Testing**: pytest (existing `tests/`), following the project's manual-verification-before-merge gate
**Target Platform**: Linux container (existing Containerfile), served by Gunicorn behind Apache/reverse proxy on lotor
**Project Type**: Web application (single Flask service)
**Performance Goals**: Tool calls bounded by Drive latency (target < 5s, consistent with existing sync); auth decrypt is in-memory and negligible
**Constraints**: Store nothing server-side; minimal OAuth scopes unchanged; all config via env vars
**Scale/Scope**: Single-user-per-token; small tool surface (todos + pomodoros) at launch

## Constitution Check

*GATE: must pass before and after design.*

- **I. Privacy by Design** — PASS. No analytics/telemetry. Token sealed with server key; decrypted in memory only; nothing stored. Scopes unchanged (`drive.file`).
- **II. User Data Ownership** — PASS. Data stays in the user's Drive; all access via the same validated storage functions; no proprietary copy on the server.
- **III. Simplicity & Focus** — PASS with discipline. Directly supports daily productivity (agents managing tasks/time). Keep the core server thin; push tool logic into plugins.
- **IV. Timer Agnosticism** — N/A (no timer behavior changed); manual/agent entry is additive.
- **V. Offline-First** — N/A for the agent path (agents are inherently online); the browser/IndexedDB path is unchanged.
- **VI. Container-Ready** — PASS. New config is one env var (`MCP_TOKEN_SEAL_KEY`). No new persistent volume. Single container unchanged.

**New env var**: `MCP_TOKEN_SEAL_KEY` (Fernet key). Documented in `acquacotta.env.example`. Rotating it is the global panic-revoke.

## Key Design Decisions

### Auth: stateless sealed bearer token
- On enable, the app builds `token = fernet.encrypt(json{refresh_token, folder_id, service, issued_at, v})` → base64 → `aqc_v1.<blob>`.
- Agent sends `Authorization: Bearer aqc_v1.<blob>`.
- Per request: decrypt with `MCP_TOKEN_SEAL_KEY` → exchange refresh token for an access token (`google.oauth2.credentials.Credentials`) → build `drive_service` / `ctx` exactly as the web routes do → dispatch → discard.
- Revocation paths: disable plugin / regenerate (bump a per-user `issued_at` floor — see below), rotate `MCP_TOKEN_SEAL_KEY` (global), or revoke the Google grant.
- **Regenerate/disable without server state**: store only a tiny per-user `mcp_token_epoch` alongside the user's existing `location`/settings record (the app already persists per-user `location` via `save_location`). Tokens carry `issued_at`; the server rejects tokens with `issued_at < epoch`. This is metadata, not user content, and keeps revocation real without storing the token itself. (If we want truly zero per-user metadata, fall back to key-rotation-only revocation — flagged as an open question.)

### Transport — FastMCP behind the in-container Apache
- Use **FastMCP 2.0**, the same framework `mcp-trentina` runs (FastMCP + Starlette). It gives us Streamable HTTP, tool registration by decorator, and MCP protocol handling for free — no hand-rolled handler.
- **WSGI/ASGI reality**: Flask is WSGI; FastMCP is ASGI/Starlette. Rather than bridge them in one process, run FastMCP as a second process (uvicorn) inside the *same* container and let the container's **existing Apache reverse proxy** route `/mcp` → FastMCP and everything else → Gunicorn/Flask. Single container, no new volume — still Constitution VI compliant. (Apache already fronts Flask in the container per project CLAUDE.md.)
- FastMCP's auth hook validates the `Authorization: Bearer aqc_v1.<blob>` token (unseal → epoch check) before any tool runs; tools receive the built `ctx`.

### Tool contribution contract (#93 alignment)
- Extend plugin metadata with an optional `MCP_TOOLS` list; each entry: `{name, description, input_schema, handler}` where `handler(ctx, args)` returns a JSON-serializable result.
- A new `mcp_server.py` collects `MCP_TOOLS` from all *enabled/active* plugins via `plugin_registry`, builds the MCP `tools/list`, and routes `tools/call` to the right handler with a freshly built `ctx`.
- Todos and pomodoro tools are defined as descriptors on `todos_plugin` and a small `pomodoros` tool module wrapping `storage_api`.

## Project Structure

```text
.specify/specs/006-mcp-server-plugin/
├── spec.md      # done
├── plan.md      # this file
└── tasks.md     # via /speckit.tasks

# Source (repository root — matches existing flat layout)
mcp_server.py            # NEW: MCP transport, token seal/unseal, tools/list + tools/call dispatch
mcp_tokens.py            # NEW: Fernet seal/unseal + epoch revocation check
plugin_registry.py       # EDIT: expose enabled plugins' MCP_TOOLS; add helper get_mcp_tools()
todos_plugin.py          # EDIT: add MCP_TOOLS descriptors (list/create/complete/update, lists) reusing read_todos/write_todos
pomodoro_tools.py        # NEW: MCP_TOOLS for get_pomodoros/get_time_summary/tag_pomodoro_to_ticket over storage_api
app.py                   # EDIT: mount /mcp; add enable/disable + token mint/regenerate routes; UI settings hook
storage_api.py           # (reuse as-is; add get_time_summary aggregation if not present)
templates/               # EDIT: plugin settings UI — enable toggle, token display, agent config snippet
acquacotta.env.example   # EDIT: document MCP_TOKEN_SEAL_KEY
tests/
├── test_mcp_tokens.py       # NEW: seal/unseal, tamper, epoch revoke
├── test_mcp_server.py       # NEW: tools/list reflects enabled plugins; tools/call dispatch; auth failures
└── test_mcp_todos_e2e.py    # NEW: list/create/complete against a mocked storage backend
```

## Implementation Phases

1. **Token layer** — `mcp_tokens.py`: Fernet seal/unseal, `aqc_v1.` framing, tamper + epoch checks. Unit tests first.
2. **Tool contract** — `plugin_registry.get_mcp_tools()` gathers `MCP_TOOLS` from active plugins; define descriptor shape.
3. **Todos tools** — descriptors on `todos_plugin` wrapping existing `read_todos`/`write_todos` (add create/complete/update helpers that mutate the todos list safely).
4. **Pomodoro tools** — `pomodoro_tools.py` over `storage_api`; add `get_time_summary` aggregation if missing.
5. **MCP transport** — `mcp_server.py` mounted at `/mcp`; wire auth (decrypt → build ctx) → dispatch. Decide SDK vs. minimal handler in Phase 0.
6. **App + UI** — enable/disable + mint/regenerate routes; settings panel shows endpoint, one-time token, agent config snippet.
7. **Docs/env** — `acquacotta.env.example`, README note, plugin metadata.

## Testing Strategy

- **Unit**: token seal/unseal/tamper/epoch; tool descriptor aggregation; per-tool input validation.
- **Integration**: `tools/list` reflects enabled plugins; `tools/call` for each todo/pomodoro tool against a mocked storage backend; auth-failure paths never touch storage.
- **Manual (gate)**: connect Claude Code to the local `/mcp` endpoint with a real token; run list/create/complete todos and get_time_summary; confirm parity with the dashboard and that nothing is persisted server-side.

## Risks & Open Questions

- **FastMCP (ASGI) alongside Flask (WSGI)**: resolved by running FastMCP as a second uvicorn process behind the in-container Apache (route `/mcp`). Phase 0 spike confirms Apache routing + FastMCP bearer-auth hook.
- **Revocation vs. zero-state purity**: per-user `mcp_token_epoch` is tiny metadata but not literally zero state. Confirm this is acceptable vs. key-rotation-only revocation. **[Decision needed]**
- **Concurrent writes** to the full-replace todos file (agent + browser): last-write-wins, same as today. Document; revisit if it bites.
- **Refresh-token longevity**: if Google expires/revokes the grant, agents break until re-enable. Surface a clear error.
- **Token exposure**: bearer token grants full data access. One-time display, treat like a password; regenerate is the mitigation.
