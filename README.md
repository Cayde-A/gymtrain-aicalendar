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
5. After saving the workout, let Garmin Connect sync the completed activity.
6. TrainingOS imports or reconciles the Garmin activity, then AI reviews the result and prepares the next training recommendation.

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

Open the local correction page:

```bash
python3 scripts/local_review_ui.py
```

Then visit:

```text
http://127.0.0.1:8787
```

The correction page is for post-workout review. It lets the user correct exercise names, set order, weight, reps, RPE, pain notes, and readiness notes before AI analysis.

After correction, use `保存并进入 AI 复盘与初版计划` to open the manual post-workout analysis prompt. This analysis reviews the completed workout and creates an initial next-day training draft. The draft should be finalized only after next-day Garmin sleep and recovery metrics sync.

The AI review flow is standardized to reduce compute:

```text
TrainingOS builds a compact JSON packet
-> user sends packet to ChatGPT
-> ChatGPT returns JSON only
-> user pastes JSON back into TrainingOS
-> TrainingOS saves it to ai_reviews
```

During debugging, open:

```text
http://127.0.0.1:8787/debug
```

This shows local-only import and review events from `data/debug_events.jsonl`.

## Running tests

Unit tests are located in `tests/`.

From the repository root run:

```bash
python3 -m unittest discover -s tests
```
