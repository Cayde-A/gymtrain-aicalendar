# Backlog

## Now

- Create a Garmin Personal API key and live-verify seven recovery days plus two recent Strength activities against the legacy provider.
- Add official FIT parsing only if Personal API activity details do not contain complete strength sets.
- Add post-upload retention cleanup for temporary monthly sync packages.

## Recently Completed

- Added the official Garmin Personal API read adapter with automatic selection, read/write capability separation, and legacy read fallback.
- Added shared Garmin authentication and token-store selection.
- Added Garmin provider capability discovery and version reporting.
- Added structured authentication, rate-limit, schema, unavailable-capability, outage, and unknown errors.
- Added machine-readable failed push results for scheduled-task decisions.
- Added deterministic training and recovery quality gates with blocking exit codes.
- Added coverage for missing reps, abnormal weight, unknown exercises, rest sets, bodyweight warnings, and incomplete recovery.
- Added an observable import -> quality -> review -> recovery -> final plan -> conditional Garmin push state machine.
- Added persistent pipeline state, review reuse, deterministic recovery volume adjustment, and muscle-overlap blocking.
- Added a Garmin-catalog-verified Pull/back preset so the primary split is executable.
- Added persistent Garmin write idempotency, phase checkpoints, deferred retry metadata, and remote schedule confirmation.
- Added lost-response recovery for upload/schedule and explicit handling for ambiguous device pushes.
- Added the read-only gccli adapter and value-free parity report.
- Verified gccli against two live strength activities, seven live recovery days, and one workout dry-run.
- Verified exact cross-provider field parity and idempotent local reimport; gccli remote writes remain disabled.
- Added 30-day raw Garmin cache preview/apply cleanup with normalized-record proof, symlink protection, aggregate reporting, and post-delete verification.
- Added a deterministic V4 ICS generator and regenerated the 48-day calendar from the current Chest/Core/Legs/Core/Pull/Recovery rules.
- Added a 19-movement Gunyama candidate catalog with Garmin mapping validation, evidence levels, legacy schema migration, and user confirmation commands.
- Enforced Gunyama candidate confirmation and unavailable-equipment blocking before final plan payload generation, with substitution suggestions.
- Added a persisted 56-day V4 cycle with eight weekly phases, scheduled deloads, volume ceilings, top-set rep focus, and deterministic PR progression decisions.
- Added local-only body metric recording through CLI and Web, same-day updates, range validation, trend context, and compact AI packet integration.
- Added a dedicated next-morning finalization command that reuses saved review state, optionally syncs Garmin, performs deterministic adjustment, and returns compact action status without an AI call.
- Added deterministic local weekly JSON and Markdown reviews covering training volume, exercise load, PRs, data completeness, recovery coverage, and body-metric changes.
- Added deterministic private monthly JSON and Markdown reports with session mix, exercise volume, best sets, PR records, e1RM trends, recovery coverage, and body-metric changes.
- Added an allowlisted, privacy-scanned, hash-stable, idempotent monthly Supabase sync package generator with local pending-batch persistence and no upload side effect.
- Added an installable local PWA shell with manifest, app icon, responsive pages, service worker, and a privacy-safe offline fallback that never caches dynamic personal data.
- Added a dependency-free Google Calendar API adapter behind the ICS model, with deterministic event IDs, create/update idempotency, completed-summary patching, local sync state, and explicit OAuth/write confirmation gates.
- Added a read-only local dashboard as the PWA home page, combining recent training load, data completeness, recovery, body metrics, cycle state, e1RM PRs, training days, and pipeline outcomes.
- Added a trigger-gated OpenAI Responses API adapter with strict structured output, local validation, review reuse, and no-storage requests.
- Added voice-assisted local workout entry and imported-set correction with editable previews, repeat commands, local parsing, and no transcript persistence.
- Added an authenticated Supabase monthly uploader using publishable-key user sessions, RLS, idempotent upsert, SHA-256 read-back, and sanitized failure state.
- Added a value-free dual-provider failure recheck with deterministic fallback recommendations and a same-source update checklist.
- Added an Apache-2.0-compatible historical `garmin-data-export` adapter for JSON cache and compact text, with provenance, quality counts, and idempotent import.

## Next

- Evaluate gccli remote writes only in an isolated upload/schedule/cleanup test account flow.
- Live-verify Google Calendar create, repeat-update, and completed-summary patch after user OAuth authorization.
- Live-verify one structured AI review after user API-key authorization.
- Provision the Supabase RLS schema and live-verify initial upload, repeat upsert, read-back, and cross-user isolation.

## Later

- Explore music-pause or rest-detection prompt.

## Research

- Track approved Garmin integration sources for breakage, updates, and replacements.
- Compare local SQLite MVP vs direct Supabase MVP.
- Test fastest mobile logging interaction.
- Validate whether automatic prompts are practical on iOS.
- Recheck adopted Garmin projects for releases, security notices, and license changes before upgrades.
