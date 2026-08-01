# Changelog

## [0.1.6] - 2026-08-01

### Added

- Added Garmin retry test result documenting Garmin SSO `429 Too Many Requests` state.
- Clarified that the next valid test is one token-initialization run after rate limit clears.
- Added successful Garmin import test result with token initialization and partial normalized metrics.

## [0.1.5] - 2026-07-31

### Added

- Added first local Garmin import MVP script.
- Added Python dependency file for Garmin import testing.
- Added Garmin Import MVP documentation and first-test checklist.
- Added value-free Garmin raw schema summary output for safer field mapping.
- Added `.env.local` support and a Garmin environment template for non-interactive local testing.
- Added local-only Garmin login web UI for credential entry when interactive terminal input is unavailable.
- Added visible submit feedback to the local Garmin login UI.
- Added Body Battery array normalization.
- Added Garmin token cache support to reduce repeated password logins and avoid rate limiting.

## [0.1.4] - 2026-07-31

### Added

- Added Garmin Auto Import Plan.
- Defined local scheduled import as the recommended first implementation.
- Added staged path from local import to Supabase-backed pipeline and official Garmin API.
- Added security and acceptance criteria for Garmin auto import MVP.

## [0.1.3] - 2026-07-31

### Added

- Added MVP usage flow test checklist.
- Added sample workout data for end-to-end flow testing.
- Linked usage flow test from MVP plan and artifacts index.
- Added first dry-run test result.

## [0.1.2] - 2026-07-31

### Added

- Added Garmin + Apple Shortcuts + ChatGPT usage flow.
- Clarified that Garmin built-in Strength activity should be tested as the primary recording surface.
- Added semi-automated ChatGPT App review path and fully automated backend AI path.
- Updated cloud architecture and roadmap with Shortcut-triggered review and backend automation.

## [0.1.1] - 2026-07-31

### Added

- Added Garmin Provider Strategy.
- Documented first-pass reuse of `python-garminconnect`, `GarminDB`, `garmin-data-export`, and `garmin-connect-export`.
- Added failure and same-source recheck protocol for Garmin integration breakage.
- Updated architecture, MVP plan, and backlog to use the Garmin Provider boundary.

## [0.1.0] - 2026-07-31

### Added

- Created TrainingOS project structure.
- Added vision and goals.
- Added V4 PR-centered training methodology.
- Added Google Calendar and ICS integration plan.
- Added Supabase + Garmin + AI cloud architecture proposal.
- Added database schema draft.
- Added roadmap from V4 to V6.
- Added MVP implementation plan.
- Added backlog.
- Added initial reusable artifacts.

### Project Version Mapping

- TrainingOS V4: calendar + PR methodology + manual/AI follow-up.
- TrainingOS V5: structured training database and dashboard.
- TrainingOS V6: Supabase cloud system with Garmin, Google Calendar, mobile logging, and AI.
