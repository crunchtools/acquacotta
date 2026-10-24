# Feature Specification: Social Share Plugin

**Feature Branch**: `feat/social-share`
**Created**: 2026-10-24
**Status**: Draft
**Input**: Share a URL from an Android phone (Samsung, Chrome) to Acquacotta, have it
AI-draft a post per social channel, edit them, pick channels and a time, and schedule
them through the user's self-hosted Postiz, used headless through its public API.

## Overview

Acquacotta gains an optional **Social Share** extension plugin (id `social`, tab
"Social"), per-user and enabled by default (spec 008). It has two halves:

- **PWA share target.** A web app manifest (`/manifest.webmanifest`) makes the app
  installable and registers it in Android's share sheet (`share_target`, GET to
  `/share`). A pass-through service worker (`/sw.js`) exists only to satisfy Chrome's
  install criteria; it caches nothing, so a deploy is always live on the next load.
- **Compose and schedule.** The Social tab takes the shared link, the server fetches
  the page and makes one Gemini call that drafts a post per selected channel, the user
  edits, and the server creates the posts in Postiz.

Custody follows RT Tickets (spec 011): the connection config (Postiz URL and API key,
Gemini key and model, default channels) lives in the user's own Drive at
`plugins/social/config.json`, secrets encrypted with the server seal key, read per
request, never stored server-side. Drafts live only in the page until scheduled.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Share from the phone, schedule in a few taps (Priority: P1)

The user reads an article on the phone, taps Share, picks Acquacotta. The Social tab
opens with the link, drafts appear for the default channels, the user tweaks one and
taps Schedule; Postiz queues the posts in its next free slot.

**Independent Test**: With Postiz and Gemini configured, open
`/share?text=Look+https://example.com/a` signed in; drafts appear for the default
channels and Schedule creates one Postiz post group.

**Acceptance Scenarios**:

1. **Given** the installed app, **When** the user shares a link from another Android app, **Then** Acquacotta opens on the Social tab with that link.
2. **Given** the link arrived in `text` with surrounding words, **When** `/share` handles it, **Then** the first http(s) URL is extracted.
3. **Given** a signed-in user with Postiz and Gemini configured, **When** the Social tab opens from a share, **Then** drafts are requested at once for the default channels.
4. **Given** drafts, **When** the user taps Schedule with "next free slot", **Then** the posts are created in Postiz for the first channel's next free slot and the time is shown with a link to Postiz.

### User Story 2 - Share while signed out (Priority: P1)

**Acceptance Scenarios**:

1. **Given** a signed-out browser, **When** a link is shared, **Then** the Social tab keeps it and offers Google sign-in.
2. **Given** sign-in starts from there, **When** the OAuth round trip completes, **Then** the user lands on the Social tab with the link (carried in the signed OAuth state, not server storage).

### User Story 3 - Edit, choose channels and time (Priority: P1)

**Acceptance Scenarios**:

1. **Given** drafts, **When** the user edits one, **Then** its live count against the channel's limit updates and turns red when over.
2. **Given** a channel toggled off, **When** scheduling, **Then** it is not posted.
3. **Given** a post over its limit, **When** the user schedules (not draft), **Then** the request is refused with the channel named.
4. **Given** "pick a time" or "save as draft", **When** scheduling, **Then** Postiz gets that date or a draft.

### User Story 4 - Configure (Priority: P2)

The user sets the Postiz API URL and key, the Gemini key and model, tests the
connection, and ticks the channels selected by default.

**Acceptance Scenarios**:

1. **Given** saved keys, **When** the config is read, **Then** only `has_*` flags come back, and saving other fields keeps the keys.
2. **Given** a typed URL like `postiz.example.com/api`, **When** saved, **Then** it is stored as `https://postiz.example.com/api/public/v1`.

### Edge Cases

- The shared page is not HTML (a PDF): drafts are written from the URL alone.
- The page image is not PNG, JPEG, GIF or WebP, is over 5 MB, or is on a non-public address: posts go out without it, with a warning.
- A page names a canonical URL on another host: the fetched URL is used.
- Gemini skips a channel: that card is empty for the user to write.
- Postiz rejects the key: a 502 with "Postiz rejected the API key".

## Requirements *(mandatory)*

- **FR-001**: The app MUST serve a manifest with `start_url "/"`, `display "standalone"`, 192 and 512 px icons, theme colors matching the app, and `share_target {action "/share", method "GET", params {title, text, url}}`, as `application/manifest+json`.
- **FR-002**: The app MUST serve a service worker at `/sw.js`, root scope, `no-store`, that caches nothing.
- **FR-003**: `/share` MUST redirect to `/?view=social&share=<url>` with the first http(s) URL from `url`, else `text`; without one it opens the Social tab empty.
- **FR-004**: `/auth/google?share=<url>` MUST carry the link in the signed OAuth state, encrypted so Google cannot read it, and the callback MUST land on the Social tab with it.
- **FR-005**: Every server-side fetch of a user-supplied URL MUST pass the SSRF guard: http(s) only, no loopback, private, link-local, reserved, multicast or unspecified address, re-checked on every redirect; page fetches are size- and time-capped. A Postiz host may be allowed by the operator with `SOCIAL_ALLOWED_HOSTS`.
- **FR-006**: Drafting MUST be one Gemini REST call in JSON mode, returning a post per requested channel; page content is passed as untrusted data, and voice rules (no hype, at most two hashtags, at most one emoji, URL once) are fixed in the system instruction.
- **FR-007**: Scheduling MUST use the Postiz public API (`POST /posts`, types schedule, draft, now) with the raw API key in `Authorization`; the page image is downloaded by the server through the SSRF guard and uploaded to Postiz (`POST /upload`), never passed to Postiz as a URL to fetch.
- **FR-008**: Secrets MUST be stored encrypted in the user's Drive and never returned to a client.
- **FR-009**: All page-, Postiz- and Gemini-sourced text MUST be rendered as text or escaped (quotes included) in attributes.

## Out of Scope

- MCP tools for social posting.
- Per-channel provider settings beyond X's reply policy (Reddit subreddits, YouTube titles, and so on): Postiz reports what is missing.
- Threads (multi-part posts), per-channel times, video, and uploading a photo from the phone.
- Offline drafting or a queue of shares made while offline.
