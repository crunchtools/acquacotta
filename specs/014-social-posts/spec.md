# Feature Specification: Social Posts View

**Feature Branch**: `feature/deep-links-social-schedule`
**Created**: 2026-10-28
**Status**: Implemented (v2.27.0)
**Input**: See the schedule of future and past posts in the Social plugin.
Supersedes the 2026-10-24 split where Postiz was the only schedule viewer.

## Overview

The Social tab gets a Compose | Posts segment. Posts lists the user's Postiz
posts from the last 7 days through the next 28, grouped by local day, one row
per post group (posts created together across channels) with a chip per
channel tinted by state (Scheduled, Published, Failed, Draft). ‹ Earlier and
Later › move the window two weeks. A row opens a sheet with each channel's full
text, state, the published post's URL and a link to Postiz. Read-only: editing,
rescheduling and deleting stay in Postiz.

`GET /api/social/posts?start&end` (≤ 62 days) calls the Postiz public API
`GET /posts?startDate&endDate` and normalizes each post (`social_plugin.list_posts`):
HTML content to text, ids checked against `_ID_RE`, release URLs kept only if
http(s), unknown states shown as Scheduled.

## User Scenarios

1. **Given** Postiz is configured, **When** the user opens Social → Posts, **Then** posts from last week through the next four show, scrolled to what's next.
2. **Given** a published post, **When** its row is tapped, **Then** the sheet links to the live post.
3. **Given** Postiz is not configured, **When** Posts opens, **Then** it offers to connect Postiz.
