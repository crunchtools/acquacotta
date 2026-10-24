# Implementation Plan: Social Share Plugin

**Branch**: `feat/social-share` | **Date**: 2026-10-24 | **Spec**: [spec.md](./spec.md)

## Summary

A new extension plugin, `social_plugin.py`, built like `rt_plugin.py`: per-user config
in the user's Drive, a server-side client for an outside service, and its own tab and
settings panel. Shared plumbing with RT (secret encryption, the Drive config folder,
the SSRF destination check) moves into `plugin_common.py`, which both plugins use.

## Technical Context

**Language/Version**: Python 3.11+ (Flask), vanilla JS, no build step
**New dependencies**: none (`requests`, `cryptography` and the stdlib `html.parser` already present)
**External APIs**: Postiz public API v1 (self-hosted), Gemini `generateContent` REST
**Storage**: `plugins/social/config.json` in the user's Drive; nothing server-side
**Testing**: pytest (`tests/test_social_plugin.py`), Puppeteer (`tests/js/test_index.js`)

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| Privacy by design | PASS | No telemetry; the page and drafts go only to the user's own Gemini key and Postiz |
| User data ownership | PASS | Config in the user's Drive; posts live in their Postiz |
| Simplicity | PASS | Optional plugin, own tab; one Gemini call per draft |
| Offline-first | N/A | Drafting and scheduling are online by nature; the rest of the app is unchanged, and the service worker caches nothing |
| Container-ready | PASS | No new process or volume; one optional env var |
| Stateless server | PASS | Share link survives sign-in in the signed OAuth state (encrypted with the seal key so Google cannot read it), not a server session |

## Design

### Request flow

```
Android share sheet
  -> GET /share?text=...            (manifest share_target)
  -> 302 /?view=social&share=<url>
  -> page: signed in?  no  -> keep link (sessionStorage), sign-in button sends
                              /auth/google?share=<url> -> state["shr"] -> callback
                              -> /?view=social&share=<url>
                       yes -> GET  /api/social/integrations (channels + limits)
                              POST /api/social/draft        (fetch page + Gemini)
                              POST /api/social/schedule     (image -> Postiz /upload, then /posts)
```

### Modules

| File | Role |
|------|------|
| `plugin_common.py` | `encrypt_secret`/`decrypt_secret`, `config_transport`/`save_config` (plugins/<id>/config.json), `is_public_host`, `check_destination(url, allowlist_env, strict)` |
| `social_plugin.py` | config (validate, read, write, public, update), `extract_shared_url`, `fetch_page` + `parse_page`, Postiz client (`test_connection`, `list_integrations`, `find_slot`, `schedule`, `build_post_payload`), Gemini (`build_draft_prompt`, `draft_posts`, `parse_draft_response`) |
| `rt_plugin.py` | now uses `plugin_common`; RT keeps strict allowlist mode |
| `app.py` | `/manifest.webmanifest`, `/sw.js`, `/share`, OAuth `share` state, `/api/social/*` |
| `static/manifest.webmanifest`, `static/js/sw.js`, `static/icon-*.png` | PWA |
| `templates/index.html`, `static/js/storage.js` | Social tab, settings panel, API wrappers |

### API

| Route | Body / result |
|-------|---------------|
| `GET /api/social/config` | public config + `postiz_url` |
| `POST /api/social/config` | partial config; empty secret keeps the stored one |
| `POST /api/social/test` | `{ok, channels}` |
| `GET /api/social/integrations` | `{configured, integrations[{id,name,identifier,picture,disabled,max_length}], default_channels, has_gemini_api_key}` |
| `POST /api/social/draft` | `{url, channels[]}` -> `{page, drafts[{integration_id,text,max_length,over_limit}]}` |
| `POST /api/social/schedule` | `{mode, date?, image_url?, posts[{integration_id,identifier,text}]}` -> `{date, posts, warnings, postiz_url}` |

Errors follow RT: 401 not signed in, 400 bad input (`ValueError`), 502 upstream
(`SocialError`), 500 Drive.

### Timeouts

A draft is a page fetch (10 s budget) plus Gemini (45 s). That fits inside
Apache's 60 s default on the host's outer reverse proxy, which this repo does not
configure. Inside the container, the vhost sets `ProxyTimeout 90` and Gunicorn's
worker timeout goes from the default 30 s to 90 s, so neither cuts a draft short.

### Security

- SSRF: `check_destination` on the page, every redirect hop, the page image and the
  Postiz base; `allow_redirects=False` on Postiz calls. DNS rebinding between the
  check and the connect is closed by `session_for`, which refuses a socket whose
  peer is not public (an allowlisted Postiz host is exempt by design).
- Prompt injection: page fields go into the prompt as quoted JSON labelled untrusted;
  output is only draft text the user reviews before anything posts.
- XSS: `escapeHtml` now also escapes quotes, so it is safe in attributes across the page.
- Canonical URLs are only trusted on the fetched host.

## Testing

- `tests/test_social_plugin.py`: config masking and encryption round trip, SSRF
  guard (loopback, private, link-local, schemes, redirect to metadata), URL
  extraction from `text`, page parsing, Gemini prompt and response parsing with HTTP
  mocked, Postiz auth header and `POST /posts` payload shape, `/share` redirect,
  OAuth state carrying the link, post-login landing, manifest and service worker.
- `tests/js/test_index.js`: signed-out share landing, signed-in auto-draft, XSS in
  page and channel fields, over-limit refusal and schedule request shape.
