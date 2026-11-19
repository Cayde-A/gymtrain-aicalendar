# TrainingOS

TrainingOS is a personal training platform project for turning a static fitness plan into a long-term, data-driven training system.

The project starts from TrainingOS V4: a PR-centered training methodology with Google Calendar/ICS scheduling and manual training follow-up. It then evolves toward V5/V6: a local-first system using SQLite, optional monthly Supabase sync, Garmin data, mobile training capture, dashboards, and AI coaching.

## Project Goals

- Keep the training plan usable in real life, especially during fat loss.
- Use PR and estimated 1RM trends as the main performance signal.
- Keep training weights dynamic instead of hardcoded into the calendar.
- Use Google Calendar/ICS for reminders and training structure.
- Use a local-first database as the long-term source of truth.
- Integrate Garmin as a physiology data provider, not as the core database.
- Build toward an AI-assisted training loop that can adjust future sessions.

## Project Map

- [Vision and Goals](docs/01_vision_goals.md)
- [V4 PR Training Methodology](docs/02_v4_training_methodology.md)
- [Google Calendar and ICS Integration](docs/03_calendar_ics_integration.md)
- [Cloud Architecture Proposal](docs/04_cloud_architecture.md)
- [Database Schema Draft](docs/05_database_schema_draft.md)
- [Roadmap V4 to V6](docs/06_roadmap_v4_to_v6.md)
- [MVP Implementation Plan](docs/07_mvp_implementation_plan.md)
- [Garmin Provider Strategy](docs/08_garmin_provider_strategy.md)
- [Garmin, Shortcuts, and ChatGPT Usage Flow](docs/09_usage_flow_garmin_shortcuts_chatgpt.md)
- [Garmin Auto Import Plan](docs/10_garmin_auto_import_plan.md)
- [Garmin Import MVP](docs/11_garmin_import_mvp.md)
- [Garmin Field Mapping](docs/12_garmin_field_mapping.md)
- [Preset Training Rounds](docs/13_preset_training_rounds.md)
- [Local-First Monthly Sync Strategy](docs/14_local_first_monthly_sync.md)
- [AI Trigger Policy](docs/15_ai_trigger_policy.md)
- [PR Tracking Design](docs/16_pr_tracking_design.md)
- [Reuse Integration and TrainingOS-Owned Core](docs/17_reuse_integration_and_self_built_core.md)
- [Data Quality Gate](docs/18_data_quality_gate.md)
- [Daily Pipeline](docs/19_daily_pipeline.md)
- [Garmin Write Reliability](docs/20_garmin_write_reliability.md)
- [gccli Parity and Adoption Gate](docs/21_gccli_parity.md)
- [Garmin Raw Cache Retention and Cleanup](docs/22_garmin_raw_cache_cleanup.md)
- [Gunyama Exercise Catalog](docs/23_gunyama_exercise_catalog.md)
- [Gunyama Final Plan Validation](docs/26_gunyama_plan_validation.md)
- [Eight-Week PR Program Cycle](docs/27_eight_week_program_cycle.md)
- [Local Body Metrics](docs/28_local_body_metrics.md)
- [Morning Plan Finalization](docs/29_morning_plan_finalization.md)
- [Weekly Review](docs/30_weekly_review.md)
- [Monthly Report](docs/31_monthly_report.md)
- [Minimized Monthly Sync Package](docs/32_minimized_monthly_sync_package.md)
- [Local PWA Shell](docs/33_local_pwa.md)
- [Google Calendar API Adapter](docs/34_google_calendar_api.md)
- [Local Dashboard](docs/35_local_dashboard.md)
- [Structured AI Review Adapter](docs/36_structured_ai_adapter.md)
- [Local Voice Input](docs/37_local_voice_input.md)
- [Supabase Monthly Upload](docs/38_supabase_monthly_upload.md)
- [Garmin Personal API Migration](docs/39_garmin_personal_api_migration.md)
- [Garmin Provider Failure Recheck](docs/24_garmin_provider_recheck.md)
- [Historical garmin-data-export Import](docs/25_historical_garmin_data_export_import.md)
- [Local SQLite Schema](schema/local_sqlite.sql)
- [Backlog](BACKLOG.md)
- [Artifacts](artifacts/README.md)
- [Changelog](CHANGELOG.md)

## Current Baseline

Current version: `V4.0 Project Baseline`

V4 should be treated as the first testable operating model:

1. Google Calendar provides the weekly training structure.
2. Each workout follows PR-centered dynamic progression.
3. Workout results are captured after each session.
4. AI reviews session data and recommends the next adjustment.
5. Garmin data is considered recovery context, initially manual or exported.

Implementation status has advanced beyond the original V4 documentation baseline: local SQLite, Garmin recovery/activity import, correction UI, PR tracking, AI trigger policy, Garmin workout payload generation, and Garmin push are available as MVP components. The remaining work is reliability, adapter hardening, end-to-end automation, and broader user testing.

The project reuses Garmin transports and general infrastructure, while TrainingOS owns normalization, data-quality checks, PR rules, training planning, trigger policy, and privacy lifecycle. See [Reuse Integration and TrainingOS-Owned Core](docs/17_reuse_integration_and_self_built_core.md).

## MVP Garmin Usage Flow

The current MVP uses Garmin as the workout execution surface and TrainingOS as the planning and analysis layer.

Recommended flow:

1. TrainingOS generates a planned strength workout from recent training history and recovery context.
2. The workout is sent or recreated in Garmin Connect and synced to the watch.
3. On the watch, open the planned workout from the training calendar:

```text
Watch face
-> START
-> Strength
-> Hold MENU
-> Training
-> Training Calendar
-> Select planned workout
-> Do Workout
```

4. During training, use Garmin's built-in Strength activity to record sets, reps, weight, and rest.
5. Each generated plan should target one primary large muscle group and reduce overlap with the previous day.
6. After chest/shoulder training, the default next-day target is legs rather than back or arms.
7. Medium/high-intensity core work can be inserted between chest, legs, and pull days when it does not impair the next primary session.
8. TrainingOS attaches short movement cues to planned exercises instead of copying Garmin animation resources.
9. After saving the workout, let Garmin Connect sync the completed activity.
10. TrainingOS imports or reconciles the Garmin activity, then AI reviews the result and prepares the next training recommendation.

For a new user or after an account has no usable training history, recovery
metrics may continue syncing but TrainingOS stays in
`waiting_for_first_training`. It does not parse training, call AI, generate a
plan, or push to Garmin until the first completed workout contains at least one
active set. An imported activity without active sets is shown as
`first_training_needs_data` and must be resynced or corrected first.

To distinguish a new user from a training interruption, a synchronized daily
pipeline with no local anchor performs one bounded 180-day Garmin Strength
history lookup (maximum five activities) before entering the waiting state.

Do not store personal Garmin credentials, OAuth tokens, raw health exports, device identifiers, or private workout results in Git.

## Privacy Model

TrainingOS is local-first by default:

```text
Local SQLite
-> complete private training and recovery history

Supabase
-> optional monthly minimized summaries

GitHub
-> reusable code, docs, schema, and fake test data only
```

The default sync strategy is monthly upload of minimized summaries, followed by cleanup of raw Garmin cache and temporary sync packages.

## Garmin Read and Write Providers

TrainingOS now separates Garmin reads from Garmin writes:

```text
Garmin Connect Personal API (official, preferred reads)
-> recovery metrics + activities + activity details + official FIT set decoding

python-garminconnect (compatibility writes)
-> upload + schedule + replace + device push
```

Install both adapters:

```bash
.venv-garmin/bin/python -m pip install -r requirements.txt
```

Create a Personal API key in Garmin Connect Web, then save the key as a single
line in `~/.config/garmin/connect-personal-api-key`. On macOS/Linux:

```bash
chmod 600 ~/.config/garmin/connect-personal-api-key
```

For local input without placing the key in chat or terminal history, start:

```bash
.venv/bin/python scripts/garmin_local_login_ui.py
```

Then open `http://127.0.0.1:8765` and use the Personal API Key form. The same
page keeps legacy email/password input separate for compatibility workout
write and watch-push operations.

The default `GARMIN_READ_PROVIDER=auto` behavior prefers the official Personal
API when the key is available and otherwise preserves the legacy read path.
Use `GARMIN_READ_PROVIDER=personal` to require official reads or `legacy` for a
temporary compatibility test. Personal API access is pull-only, so configuring
it does not change Garmin workout upload or watch-push behavior.

Personal API does not currently expose dedicated Training Readiness or Recovery
Time endpoints. When a valid local legacy token cache exists, TrainingOS uses
it only to fill missing Training Readiness fields and marks the record source
as `garmin-connect-personal-api-python+python-garminconnect`. Without that
fallback, these fields remain nullable; TrainingOS never fabricates Garmin
values. See [Garmin Personal API Migration](docs/39_garmin_personal_api_migration.md).

## Local Review MVP

Initialize the local private database:

```bash
python3 scripts/trainingos_db.py --init
```

Import recent completed Garmin Strength activities into local SQLite:

```bash
python3 scripts/garmin_activity_import.py --days 7 --limit 5
```

Add `--strength-only` when the activity list contains multiple sport types and only strength sessions should be imported.

If Personal API activity details omit Strength sets, the importer automatically
uses the official Garmin FIT SDK against the downloaded activity file. The
normalized session keeps source provenance, and all existing correction,
quality, same-day grouping, and PR rules still apply.

Open the local correction page:

```bash
python3 scripts/local_review_ui.py
```

Then visit:

```text
http://127.0.0.1:8787
```

The Dashboard stores Garmin health data in five local categories: sleep, HRV,
energy/activity, vitals, and readiness. It shows a 14-day recovery trend,
sleep-stage composition, and detailed daily indicators. The compact
Dashboard also shows the first-training waiting state when no usable completed
session exists, so an interruption or empty history is not reported as a
generic analysis failure.
`daily_recovery_metrics` summary remains the planning-engine contract; detailed
category rows stay local and are not included in the default monthly cloud
upload.

The correction page is for post-workout review. It lets the user correct exercise names, set order, weight, reps, RPE, pain notes, and readiness notes before AI analysis.

After correction, use `保存并进入 AI 复盘与初版计划` to open the manual post-workout analysis prompt. This analysis reviews the completed workout and creates an initial next-day training draft. The draft should be finalized only after next-day Garmin sleep and recovery metrics sync.

The AI review flow is standardized to reduce compute:

```text
TrainingOS groups same-day Garmin activities into one training day
-> TrainingOS builds a compact JSON packet
-> user sends packet to ChatGPT
-> ChatGPT returns JSON only
-> user pastes JSON back into TrainingOS
-> TrainingOS saves it to ai_reviews
```

PR tracking is automatic after import or correction:

```text
Session sets
-> build PR candidates per exercise
-> compare with exercise_pr_state
-> update only when the candidate is greater
-> append pr_records only for real improvements
```

API calls are controlled by a local trigger policy. Open:

```text
http://127.0.0.1:8787/settings
```

Default behavior is conservative:

- post-workout AI review uses manual copy/paste;
- next-morning recovery adjustment requires user confirmation before API use;
- Garmin workout push requires user confirmation;
- automatic API calls are disabled unless explicitly enabled;
- daily AI calls are capped by a local setting.

During debugging, open:

```text
http://127.0.0.1:8787/debug
```

This shows local-only import and review events from `data/debug_events.jsonl`.

Before AI analysis or final plan generation, run the deterministic quality gate:

```bash
.venv-garmin/bin/python scripts/trainingos_quality.py --date YYYY-MM-DD
.venv-garmin/bin/python scripts/trainingos_quality.py --date YYYY-MM-DD --recovery-date YYYY-MM-DD
```

Exit code `2` means correction or recovery synchronization is required. See [Data Quality Gate](docs/18_data_quality_gate.md).

Run the observable daily workflow against local data:

```bash
.venv-garmin/bin/python scripts/trainingos_pipeline.py \
  --date YYYY-MM-DD \
  --target-date YYYY-MM-DD
```

The command stops at the next required state instead of bypassing correction, review, recovery, trigger, or overlap checks. Live Garmin writes require the policy gate and explicit flags under the default settings. See [Daily Pipeline](docs/19_daily_pipeline.md).

Run the optional `gccli` transport parity check after one-time browser SSO:

```bash
gccli auth login YOUR_GARMIN_EMAIL
.venv-garmin/bin/python scripts/gccli_parity.py \
  --activities 2 \
  --days 7 \
  --end-date YYYY-MM-DD \
  --live-python-baseline \
  --workout /tmp/trainingos-gccli-dry-run.json
```

This check is read-only and writes a value-free coverage report. `gccli` workout writes remain disabled until the documented adoption gate passes. See [gccli Parity and Adoption Gate](docs/21_gccli_parity.md).

Preview the 30-day raw Garmin cache retention policy:

```bash
.venv-garmin/bin/python scripts/garmin_cache_cleanup.py
```

Add `--apply` only after normalized import has succeeded. The command deletes only verified old raw files and confirms each removal; unverified files and symlinks are retained. See [Garmin Raw Cache Retention and Cleanup](docs/22_garmin_raw_cache_cleanup.md).

Seed the local Gunyama candidate catalog and validate its Garmin mappings:

```bash
.venv-garmin/bin/python scripts/gunyama_exercise_catalog.py
```

Specific equipment starts as `candidate` because the venue does not publish a machine-level inventory. Use `--confirm "Exercise Name"` or `--unavailable "Exercise Name"` after observing the gym floor. See [Gunyama Exercise Catalog](docs/23_gunyama_exercise_catalog.md).

Final plans now validate every preset movement against that catalog before a Garmin payload is created. A candidate plan stops with `needs_venue_confirmation`; after checking the equipment, either persist observations with the catalog command or confirm candidates for one run:

```bash
.venv-garmin/bin/python scripts/trainingos_pipeline.py \
  --date YYYY-MM-DD \
  --target-date YYYY-MM-DD \
  --confirm-candidate-equipment
```

An exercise marked `unavailable` always blocks finalization until the plan is changed. See [Gunyama Final Plan Validation](docs/26_gunyama_plan_validation.md).

Create or inspect the deterministic eight-week V4 program cycle:

```bash
.venv-garmin/bin/python scripts/trainingos_program_cycle.py \
  --date YYYY-MM-DD \
  --create \
  --goal "PR progression with controlled fatigue"
```

The daily pipeline creates a cycle on first finalization when none is active,
then applies the current week's phase, volume ceiling, top-set rep focus, and
primary-exercise progression decision. See [Eight-Week PR Program Cycle](docs/27_eight_week_program_cycle.md).

Record private body metrics through the local UI at `http://127.0.0.1:8787/body`
or through the CLI:

```bash
.venv-garmin/bin/python scripts/trainingos_body_metrics.py \
  --date YYYY-MM-DD \
  --weight-kg 80.2 \
  --waist-cm 84
```

The data remains in local SQLite. AI review packets receive only the latest
available measurements and changes from the previous record. See [Local Body Metrics](docs/28_local_body_metrics.md).

After target-date Garmin recovery has synced, finalize the saved initial draft
without another AI call:

```bash
.venv-garmin/bin/python scripts/trainingos_morning_finalize.py \
  --training-date YYYY-MM-DD \
  --date YYYY-MM-DD \
  --sync-garmin
```

The compact result reports recovery adjustment, cycle phase, progression,
venue status, payload path, and Garmin push state. See [Morning Plan Finalization](docs/29_morning_plan_finalization.md).

Generate a deterministic local weekly review without an AI call:

```bash
.venv-garmin/bin/python scripts/trainingos_weekly_review.py \
  --week-ending YYYY-MM-DD
```

The command writes JSON and Markdown under `exports/reviews/`. See [Weekly Review](docs/30_weekly_review.md).

Generate the local monthly report:

```bash
.venv-garmin/bin/python scripts/trainingos_monthly_report.py \
  --month YYYY-MM
```

It writes JSON and Markdown under `exports/reports/`, with no AI or cloud call. See [Monthly Report](docs/31_monthly_report.md).

Build the allowlisted, privacy-scanned monthly Supabase package without uploading it:

```bash
.venv-garmin/bin/python scripts/trainingos_monthly_sync_package.py \
  --month YYYY-MM
```

The package is saved under `exports/sync/` and recorded locally as `pending`. See [Minimized Monthly Sync Package](docs/32_minimized_monthly_sync_package.md).

The local review UI now exposes an installable PWA manifest and service worker:

```text
http://127.0.0.1:8787/
```

The Dashboard's `立即读取 Garmin` action performs an explicit one-day Personal
API recovery sync into local SQLite, refreshes the status cards, and records a
redacted debug event. It does not call AI or upload a workout to Garmin.

Only the static offline shell, manifest, and icon are cached; private dynamic pages are always network-first. See [Local PWA Shell](docs/33_local_pwa.md).

Generate Google Calendar API payloads from the same V4 model used by ICS:

```bash
.venv-garmin/bin/python scripts/trainingos_google_calendar.py \
  --start-date YYYY-MM-DD
```

Dry-run is the default. Live writes require `--push --confirm` and a separately
authorized `GOOGLE_CALENDAR_ACCESS_TOKEN`. See [Google Calendar API Adapter](docs/34_google_calendar_api.md).

The PWA home page is now the local dashboard:

```text
http://127.0.0.1:8787/
```

It reads normalized SQLite state only and does not trigger sync, AI, planning, or writes. See [Local Dashboard](docs/35_local_dashboard.md).

Generate a strict Responses API request without sending it:

```bash
.venv-garmin/bin/python scripts/trainingos_openai_review.py \
  --date YYYY-MM-DD
```

A live call additionally requires `--call --confirm`, an allowed local trigger policy, and `OPENAI_API_KEY`. The returned initial draft is saved only after strict local validation and still passes through deterministic next-morning finalization. See [Structured AI Review Adapter](docs/36_structured_ai_adapter.md).

Open the local voice-assisted workout entry page at:

```text
http://127.0.0.1:8787/entry
```

Voice transcripts are parsed into editable fields and are not persisted. The same control is available on imported-session correction pages. Browser speech recognition availability and audio processing depend on the browser; typed phrases remain the local fallback. See [Local Voice Input](docs/37_local_voice_input.md).

Dry-run the authenticated Supabase upload boundary without a network call:

```bash
.venv-garmin/bin/python scripts/trainingos_supabase_sync.py \
  --month YYYY-MM
```

Live upload requires the reviewed RLS schema, a publishable key, a signed-in user access token, and `--push --confirm`. TrainingOS verifies the remote SHA-256 before marking the local batch uploaded. See [Supabase Monthly Upload](docs/38_supabase_monthly_upload.md).

Run a value-free Garmin provider health check after an authentication, schema, rate-limit, or outage failure:

```bash
.venv-garmin/bin/python scripts/garmin_provider_recheck.py --live
```

The report compares the smallest read path through `python-garminconnect` and `gccli`, then recommends continuing, waiting, logging in, or using a read-only fallback. See [Garmin Provider Failure Recheck](docs/24_garmin_provider_recheck.md).

Preview a historical `garmin-data-export` directory without writing to SQLite:

```bash
.venv-garmin/bin/python scripts/garmin_data_export_import.py \
  /private/path/to/export \
  --dry-run
```

The adapter supports upstream JSON cache and compact/split/update text formats, imports Strength by default, and reuses current field mapping and idempotent storage. See [Historical garmin-data-export Import](docs/25_historical_garmin_data_export_import.md).

## Running tests

Garmin integration currently requires Python 3.12 or newer. Install the pinned runtime dependencies with:

```bash
python3 -m pip install -r requirements.txt
```

Unit tests are located in `tests/`.

From the repository root run:

```bash
python3 -m unittest discover -s tests
```
