# Feature Specification: Social Posts View

**Feature Branch**: `feature/deep-links-social-schedule`
**Created**: 2026-10-28
**Status**: Implemented (v2.27.0)
**Input**: See the schedule of future and past posts in the Social plugin.
Supersedes the 2026-10-24 split where Postiz was the only schedule viewer.

## Overview

The Social tab gets a Compose | Posts segment. Posts follows Compose's look
and feel (v2.28.0, Fable UX spec): the slot sheet's day blocks (`.social-day`)
from Today, a week at a time; "Next week ›" appends seven days. Last week is
loaded with the first request ([today−7, today+7)) but collapsed behind
"‹ Last week · N failed"; revealing it keeps Today in place, and later taps
("‹ Earlier") prepend a week. One row per post group (posts created together
across channels), styled like the link card: time, an exception word (Failed,
Draft, Not sent yet), a chip per channel (filled = published, red = failed,
dashed = draft), two lines of text; failed rows get an accent bar. A row opens
the bottom sheet with each channel's state word, full text, "View post ›" and
Open in Postiz. One status line carries signed out, not connected, offline and
unreachable. Read-only: editing, rescheduling and deleting stay in Postiz.

`GET /api/social/posts?start&end` (≤ 62 days) calls the Postiz public API
`GET /posts?startDate&endDate` and normalizes each post (`social_plugin.list_posts`):
HTML content to text, ids checked against `_ID_RE`, release URLs kept only if
http(s), unknown states shown as Scheduled.

## User Scenarios

1. **Given** Postiz is configured, **When** the user opens Social → Posts, **Then** posts from last week through the next four show, scrolled to what's next.
2. **Given** a published post, **When** its row is tapped, **Then** the sheet links to the live post.
3. **Given** Postiz is not configured, **When** Posts opens, **Then** it offers to connect Postiz.
