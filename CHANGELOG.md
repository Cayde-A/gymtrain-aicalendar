# Changelog

## [0.1.9] - 2026-11-19

### Added

- Added Garmin's official Personal API Python client as the preferred single-user read transport.
- Added a Dashboard action for manually syncing today's Garmin recovery data into local SQLite with visible progress and result feedback.
- Added Dashboard cards for Personal API sleep duration and HRV status when Garmin does not provide sleep score or training readiness.
- Switched the local Dashboard to a threaded HTTP server so an incomplete browser connection or Garmin sync cannot block other page requests.
- Added the current Personal API sleep-score field mapping and a field-level legacy fallback for Training Readiness, with hybrid source provenance.
- Added current Personal API mappings for resting heart rate, stress, steps, total calories, and Body Battery daily summary fields.
- Added automatic `personal`/`legacy` read-provider selection with explicit override support.
- Added official activity pagination, activity details, associated workout metadata, and FIT download capability reporting.
- Added Personal API setup, credential handling, migration gates, and split read/write architecture documentation.
- Added categorized local daily health tables for sleep, HRV, energy, vitals, and readiness while preserving the compact recovery contract.
- Added extended Garmin field normalization and idempotent writes for sleep stages, HRV baseline, Body Battery flow, movement, calories, vital signs, and readiness factors.
- Added Dashboard visualization for 14-day recovery trends, sleep-stage composition, and categorized daily health indicators with an accessible data-table fallback.
- Added verified cleanup of temporary monthly sync packages after Supabase hash read-back, guarded by local retention policy, safe-path checks, and package SHA-256 matching.
- Added a bounded official FIT SDK fallback for Personal API strength activities whose summary/detail responses omit exercise sets.
- Live-verified two official Personal API Strength imports: 65 total sets, 31 active sets, and no missing reps, missing weights, abnormal weights, or unknown exercise mappings.
- Added a first-training anchor gate: recovery can keep syncing, while activity parsing, AI review, plan generation, and Garmin push wait for the first completed workout with an active set.
- Added explicit Dashboard and pipeline states for no training history and imported activities that contain no active sets.
- Added Dashboard locale negotiation from the browser/system `Accept-Language`, with complete Chinese and English labels, charts, empty states, onboarding notices, and Garmin sync feedback.
- Defined the native customer app as four primary pages: Today, Training, Nutrition, and Progress, including placement for food-photo correction, calories/macros, hydration, 16:8 reminders, trends, devices, and privacy settings.

### Changed

- Separated Garmin read capabilities from compatibility workout-write capabilities.
- Preserved current normalized recovery/activity shapes and source provenance across providers.
- Kept Training Readiness and Recovery Time nullable when neither the official response nor the scoped legacy fallback supplies them.
- Corrected Garmin Training Readiness `recoveryTime` conversion from minutes to hours.
- Kept `python-garminconnect` as the workout upload, scheduling, replacement, and device-push provider.

## [0.1.8] - 2026-10-04

### Added

- Added a shared Garmin provider module for authentication and token-store selection.
- Added Garmin provider capability discovery and installed-version reporting.
- Added structured provider errors for authentication, rate limits, schema failures, unavailable capabilities, outages, and unknown failures.
- Added machine-readable failed Garmin push results with retryability metadata.
- Added a deterministic data-quality gate for completed training days and next-day recovery records.
- Added blocking checks for missing reps, abnormal weights, unknown exercises, duplicate set order, and incomplete recovery.
- Added a documented JSON quality-report contract and automation-friendly exit codes.
- Added the observable daily pipeline with optional Garmin import, quality gates, review reuse, recovery finalization, overlap validation, trigger enforcement, and conditional push.
- Added persistent `pipeline_runs` state with one idempotent local record per source and target date pair.
- Added deterministic keep, reduced-volume, and deload set adjustments from normalized recovery metrics.
- Added a Garmin-catalog-verified Pull/back preset.
- Added persistent Garmin write operations with stable idempotency keys and resumable phase checkpoints.
- Added exponential backoff for retryable reads, no immediate retry for rate limits, and deferred retry timestamps.
- Added upload recovery through embedded idempotency markers and Garmin workout-list lookup.
- Added schedule read-back confirmation and explicit handling for ambiguous device-push outcomes.
- Added an optional read-only `gccli` adapter with structured errors and existing-normalizer envelopes.
- Added a value-free parity report for two activities, seven recovery days, and local workout dry-run validation.
- Added policy-driven raw Garmin cache cleanup with preview-by-default behavior, normalized-record verification, symlink protection, and verified deletion results.
- Added a deterministic RFC 5545 V4 calendar generator and regenerated the finite 48-day Chest/Core/Legs/Core/Pull/Recovery framework.
- Added a Gunyama candidate exercise catalog with 19 Garmin-verified mappings, venue evidence levels, idempotent seeding, and user availability confirmation commands.
- Added final-plan venue validation that blocks unavailable exercises, pauses on unconfirmed candidate equipment, and returns substitution suggestions before Garmin payload generation.
- Added an idempotent 56-day V4 program cycle using existing training-block storage, with eight weekly phase templates and automatic active-week selection.
- Added deterministic main-exercise progression guidance for baseline, small increase, keep, 5% reduction, and deload outcomes using PR state, RPE, recovery, and recent performance.
- Added scheduled volume ceilings and cycle context to final plans and Garmin workout descriptions.
- Added local-only body metric entry through CLI and the review Web UI, including range validation and same-day update behavior.
- Added latest body measurements and previous-record deltas to session and day AI review packets without exposing values in observability logs.
- Added a dedicated next-morning finalization command that reuses the observable daily pipeline and emits a compact recovery, cycle, progression, venue, payload, and push summary without an additional AI call.
- Added deterministic weekly JSON and Markdown review generation with training volume, exercise distribution, PR count, field completeness, recovery averages and coverage, and body-metric change.
- Added deterministic private monthly JSON and Markdown reports with session-type mix, best sets, e1RM trends, recovery coverage, and body-metric change.
- Added an exact-allowlist monthly Supabase package projection with recursive sensitive-key rejection, stable SHA-256 hashing, and idempotent local pending-batch persistence.
- Added an installable local PWA manifest, TrainingOS application icon, service worker registration, and privacy-safe offline shell without dynamic personal-data caching.
- Added a dependency-free Google Calendar API adapter sharing the V4 ICS event model, with deterministic recurring event IDs, create-or-patch idempotency, local sync persistence, and explicit write confirmation.
- Added privacy-minimized completed-session Calendar patches with best-set, PR-count, and review-decision summaries while excluding local notes and identifiers.
- Added a read-only local dashboard and made it the PWA home page, with 30-day training totals, data completeness, latest recovery and body state, current cycle, e1RM PRs, recent training days, and pipeline status.
- Added a trigger-gated OpenAI Responses API adapter with strict JSON Schema output, no-storage requests, local validation, review reuse, and sanitized failures.
- Added local voice-assisted workout entry and existing-session correction with Chinese/English set parsing, repeat and load-adjustment commands, editable previews, and no transcript persistence.
- Added an authenticated Supabase REST uploader for minimized monthly summaries with publishable-key user auth, RLS schema, idempotent upsert, SHA-256 read-back confirmation, and sanitized local failure states.
- Added a value-free Garmin provider recheck tool covering runtime versions, auth state, minimal dual-provider live probes, and deterministic failure recommendations.
- Added historical `garmin-data-export` cache/compact-text import with existing normalizers, source provenance, dry-run reporting, and idempotent SQLite writes.
- Added `source_tool` provenance to completed sessions and daily recovery metrics with legacy SQLite migration.
- Added a reuse matrix, integration sequence, license policy, and explicit TrainingOS-owned core definition.
- Added provider token-selection tests.

### Changed

- Routed recovery import, completed activity import, and workout push through the shared Garmin provider entry.
- Prevented workout upload transport failures from silently falling through to a second upload method.
- Replaced the moving GitHub Garmin dependency and stale `0.2.x` pin with `garminconnect` `0.3.17` to `<0.4`.
- Reprioritized the backlog around reliability, idempotency, quality gates, gccli parity, and fallback imports.

## [0.1.7] - 2026-08-27

### Changed

- Corrected TrainingOS planning logic so each session targets one primary large muscle group.
- Added adjacent-day muscle overlap constraints to the V4 methodology, preset rounds documentation, and AI review packet.
- Updated the Garmin workout payload preset from pull/lower recovery to leg-priority after chest/shoulder training.
- Added interstitial medium/high-intensity core rules and Garmin payload presets for core sessions between chest, legs, and pull days.
- Added TrainingOS-owned movement text cues and Garmin workout step description mapping.

## [0.1.6] - 2026-08-01

### Added

- Added local-first monthly sync strategy for privacy-aware TrainingOS data handling.
- Updated architecture and schema drafts so local SQLite is the complete private source of truth and Supabase is a minimized monthly sync layer.
- Added local SQLite storage helpers, completed Garmin activity import MVP, and local workout correction UI.
- Added local debug event timeline for observing Garmin import, SQLite writes, correction saves, and AI summary generation.
- Fixed Garmin completed-set parsing for `repetitionCount` and gram-based weight values.
- Documented completed activity and strength set field mappings, and centralized Garmin activity/set mapping rules in code.
- Updated manual post-workout AI analysis flow to generate an initial next-day plan draft, then defer final adjustment until next-day recovery sync.
- Added standardized low-compute AI review packet flow and manual AI JSON response saving into `ai_reviews`.
- Added same-day training grouping so multiple Garmin activities on one date are reviewed as one workout.
- Added Garmin retry test result documenting Garmin SSO `429 Too Many Requests` state.
- Clarified that the next valid test is one token-initialization run after rate limit clears.
- Added successful Garmin import test result with token initialization and partial normalized metrics.
- Added explicit Garmin-to-TrainingOS field mapping and mapping coverage output.
- Added Garmin Field Mapping documentation.
- Added preset training rounds design.
- Updated architecture, roadmap, usage flow, and backlog so TrainingOS generates workout rounds before Garmin execution.
- Added first planned workout for 2026-08-02.
- Successfully uploaded, scheduled, and pushed a Garmin Strength workout to Garmin Connect/device sync.
- Added Garmin workout push test record and separate Python 3.12 workout requirements.
- Confirmed Garmin Connect calendar and EPIX watch sync success for the first TrainingOS planned workout.
- Confirmed stable Garmin epix watch entry path through Strength -> Training -> Training Calendar.

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
