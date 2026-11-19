# Garmin Auto Import Plan

## Goal

Automatically import Garmin data into TrainingOS so workout analysis can use recovery, sleep, activity, and strength-session data without manual copy/paste.

## Recommended Path

Use a staged approach:

```text
Stage 1: official Personal API local scheduled import
Stage 2: monthly minimized Supabase sync
Stage 3: official Training API write adapter if business access is needed
```

## Stage 1: Local Scheduled Import

This is the recommended first implementation.

```text
Mac local scheduler
-> Garmin export/import script
-> normalized JSON
-> Local SQLite
-> temporary raw cache
```

Why:

- easier to authenticate once;
- avoids storing Garmin credentials in cloud early;
- easier to debug;
- works before the full TrainingOS backend exists.

Recommended source order:

1. Garmin Connect Personal API for official health and activity reads.
2. `python-garminconnect` for temporary read fallback and workout writes.
3. `garmin-data-export` for historical and incremental export fallback.
4. `garmin-connect-export` for activity CSV/GPX/TCX fallback.
5. GarminDB for local historical warehouse/reference.

## Stage 1 Setup Flow

### 1. Create ignored local folders

```text
TrainingOS/exports/
TrainingOS/tokens/
TrainingOS/imports/
```

These are ignored by Git.

### 2. First Garmin authentication

Create a Garmin Personal API key and store it in the local protected key file. Run the compatibility login only when workout write testing is required.

Expected result:

```text
Personal API bearer token cached locally
No password committed
No token committed
```

### 3. Initial backfill

Import recent history first.

Recommended initial range:

```text
last 30-90 days
```

Import categories:

- daily health;
- sleep;
- HRV;
- Body Battery;
- stress;
- training readiness;
- activities;
- body composition if available.

### 4. Normalize

Convert Garmin raw output into TrainingOS fields.

Minimum daily record:

```json
{
  "provider": "garmin",
  "metric_date": "2026-07-31",
  "sleep_score": null,
  "sleep_duration_minutes": null,
  "hrv_status": null,
  "resting_heart_rate": null,
  "body_battery": null,
  "stress_score": null,
  "training_readiness": null,
  "recovery_time_hours": null,
  "steps": null,
  "calories": null
}
```

Minimum activity record:

```json
{
  "provider": "garmin",
  "external_activity_id": null,
  "activity_date": "2026-07-31",
  "activity_type": "strength_training",
  "duration_seconds": null,
  "average_heart_rate": null,
  "max_heart_rate": null,
  "calories": null,
  "exercise_sets": []
}
```

### 5. Load into Local SQLite

Insert or upsert by stable keys:

```text
daily_recovery_metrics:
athlete_id + metric_date + provider

garmin_activities:
provider + external_activity_id
```

### 6. Monthly minimized sync

Once per month, generate a minimized summary from local SQLite and upload only the approved summary fields to Supabase.

Default upload:

- training days;
- session count by type;
- exercise-level volume summary;
- best sets and PR count;
- estimated 1RM trends;
- recovery averages;
- approved AI monthly summary;
- next-month focus.

Default exclusions:

- raw Garmin JSON;
- Garmin tokens;
- Garmin user ID;
- device identifiers;
- GPS routes;
- minute-level heart-rate series;
- private notes.

After successful upload:

```text
Delete temporary sync package
Delete raw Garmin cache older than retention window
Keep local SQLite history
```

### 7. Schedule

Recommended current schedule:

```text
Daily import and plan workflow: 00:00 local time
Post-workout import: manual Shortcut or button
Evening review: 21:00
Monthly minimized sync: first day of month
```

## Stage 2: Monthly Minimized Supabase Sync

Once Stage 1 works, move the pipeline toward:

```text
Scheduled job
-> Garmin Provider
-> Local SQLite
-> AI review trigger
-> Monthly minimized summary
-> Supabase
-> Google Calendar update if approved
```

Options:

- local Mac scheduler continues to write into SQLite and push only monthly summaries into Supabase;
- GitHub Actions scheduled job, if Garmin authentication is stable;
- small private server or cloud worker;
- Supabase Edge Function only if the Garmin provider can run reliably there.

## Stage 3: Official Garmin API

For production-grade reliability, evaluate Garmin Connect Developer Program.

Official path:

```text
Garmin user consent
-> Garmin API push/pull
-> TrainingOS webhook/API
-> Local SQLite
-> minimized Supabase summaries
```

Use official API when:

- unofficial login breaks too often;
- the system needs production reliability;
- multiple users are supported;
- commercial use becomes relevant.

## Shortcut Integration

Apple Shortcuts should not be the main database importer.

Best Shortcut roles:

- trigger post-workout import;
- open TrainingOS review page;
- send today's summary to ChatGPT App during MVP;
- show tomorrow's planned session;
- prompt for corrections if Garmin set data is wrong.

Recommended flow:

```text
Save Garmin workout
-> Wait for Garmin Connect sync
-> Run "TrainingOS Review" Shortcut
-> Shortcut calls local/cloud endpoint
-> Endpoint imports latest Garmin data
-> AI review is generated or opened in ChatGPT
```

## Data Quality Risks

Garmin may miss or mislabel:

- exact exercise name;
- machine variation;
- RPE;
- pain;
- technique quality;
- subjective fatigue;
- reason for performance change.

TrainingOS still needs a correction layer:

```text
Garmin raw activity
-> imported workout
-> user correction form
-> clean TrainingOS workout record
```

## Completed Activity Import MVP

The local completed activity importer is:

```text
scripts/garmin_activity_import.py
```

It uses Garmin activity APIs in this order:

```text
get_activities_by_date
-> get_activity / get_activity_details
-> get_activity_exercise_sets
-> normalize completed session
-> write completed_sessions and set_logs to local SQLite
```

Recommended command:

```bash
python3 scripts/garmin_activity_import.py --days 7 --limit 5
```

Use `--strength-only` when the recent activity list includes multiple sport types and only strength sessions should be imported.

By default, raw Garmin payloads are not saved. Use `--include-raw` only for local debugging, and never commit those files.

## Correction UI MVP

The local correction interface is:

```text
scripts/local_review_ui.py
```

Recommended command:

```bash
python3 scripts/local_review_ui.py
```

Open:

```text
http://127.0.0.1:8787
```

The correction page supports:

- exercise name correction;
- set order correction;
- set type correction;
- weight correction;
- rep correction;
- RPE entry;
- pain and technique notes;
- readiness notes;
- AI review summary generation.

## Manual Post-Workout AI Analysis

After correction, the user can choose:

```text
Save correction
or
Save and enter AI analysis + initial next-day draft
```

The AI analysis step should review the completed workout and generate an initial next-day training draft.

It should not finalize the next-day training plan yet. The initial draft should be adjusted the next morning after Garmin sleep, HRV, Body Battery, readiness, and recovery metrics have synced into TrainingOS.

To reduce compute, TrainingOS should not send full history or long chat context.

MVP flow:

```text
build_ai_review_packet()
-> compact JSON packet
-> ChatGPT JSON response
-> paste response into TrainingOS
-> save_ai_review_response()
-> ai_reviews
```

For AI review, same-day Garmin activities should be grouped as one training day:

```text
completed_sessions where date(completed_at) = training_date
-> day-level compact packet
-> one AI review for the training day
```

The AI response should be JSON only and include:

- `analysis_summary`;
- `performance_direction`;
- `risk_flags`;
- `data_quality_issues`;
- `initial_next_day_plan`;
- `next_morning_adjustment_rules`.

## Security Rules

- Never commit `.env`.
- Never commit Garmin password.
- Never commit token cache.
- Never commit raw Garmin health export.
- Use `.gitignore` for exports and tokens.
- Keep only normalized test/sample data in GitHub.
- Keep local SQLite out of Git.
- Upload monthly minimized summaries to Supabase by default, not raw provider payloads.

## MVP Acceptance Criteria

The Garmin auto import MVP is successful when:

- one real Garmin account can authenticate;
- last 30 days can be imported;
- daily recovery metrics are normalized;
- at least one Strength activity can be imported;
- duplicate imports do not create duplicate records;
- AI review can use the imported recovery and activity data;
- no private data is committed to GitHub.
