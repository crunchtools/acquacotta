# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and this project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **Discussions** plugin: a first-class tab for conversations to have with
  people, broken out of the Todos "Discussions" list. Each discussion records
  the person, topic, context, talking points, priority, and — once it happens —
  the outcome, and the list is organized and filtered by person. Ships with its
  own `/api/discussions/sync` endpoint, IndexedDB store, and MCP tools
  (`list_discussions`, `create_discussion`, `mark_discussed`,
  `update_discussion`, `delete_discussion`, `reorder_discussion`). Optional and
  per-user, enabled by default (spec 008).

### Fixed
- The Discussions person filter now lists only people who still have an open
  discussion. People whose discussions are all done drop off the bar, so it
  reflects conversations that still need to happen; the edit-modal autocomplete
  still offers every known person.
- Edit modals no longer clip off the top of the screen on mobile. The modal now
  scrolls internally with a sticky Save/Cancel footer, instead of overflowing a
  fixed, centered overlay with no way to reach the top field. The Discussions form
  also leads with Person and Topic, tucks the enrichment fields behind a "More
  details" expander, and only shows Outcome when editing an existing discussion.
- The production image now includes `discussions_plugin.py`. The Containerfile
  copies an explicit file list and the new module was missing, so v2.17.0 booted
  into `ModuleNotFoundError` and gunicorn failed to start. A build-time import
  check now fails the build if any app module is missing from the image.
- Pull requests now build the base and app images and fail on fixable
  HIGH/CRITICAL vulnerabilities. Before, Trivy ran only after an image had
  been pushed, with exit code 0, so it could never stop anything. Accepted
  findings go in `.trivyignore` with a reason.
- Two Gourmand exceptions had their `classification` stranded below a stale
  section header; the headers are gone.
- Todo edits that fail to reach the cloud backend are no longer deleted by
  the next auto-refresh: the push checks the response, stays pending and
  retries.

### Changed
- Relicensed from GPL-3.0 to AGPL-3.0-or-later, matching Constitution I and
  what this repo's constitution already declared.

### Changed

- Constitution is now a v1.18.0 manifest: fleet and profile rules apply by
  reference, and the file keeps only what is specific to this repo.
- Constitution validation is pinned to the inherited release via
  `.github/workflows/constitution.yml`.
- Dependabot auto-merges GitHub Actions minor and patch updates.

## [2.16.2] - 2026-09-20

### Fixed

- `acquacotta-base` and `acquacotta-test` never carried a semver tag matching
  the app's release version. `container-base.yml` only had a path-triggered
  push to `main` (Containerfile.base/.test changes) plus `:latest`/`:sha`
  tags -- no `tags: v*` trigger at all, so a release of the main app never
  produced a matching base/test image. Nagios's registry-drift check
  (crunchtools/nagios-agent) expects every image in a repo to carry its
  newest git tag; these silently never did. Added the tag trigger and a
  `docker/metadata-action` semver tag to all four jobs (base + test, Quay +
  GHCR).

## [2.16.1] - 2026-08-01

This changelog starts here (RT #1484). acquacotta has 76 version tags and no
GitHub Releases, so there are no authored release notes to back-fill from.
Reconstructing that history from commit subjects would satisfy the letter of
Constitution II while defeating its purpose, so it has deliberately not been
done. Everything from this version forward is recorded properly.

For history prior to 2.16.1, see `git log` and the tag list.
