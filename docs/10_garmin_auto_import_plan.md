# Garmin Auto Import Plan

## Goal

Automatically import Garmin data into TrainingOS so workout analysis can use recovery, sleep, activity, and strength-session data without manual copy/paste.

## Recommended Path

Use a staged approach:

```text
Stage 1: local scheduled import
Stage 2: Supabase-backed import pipeline
Stage 3: official Garmin API or stable production provider
```

## Stage 1: Local Scheduled Import

This is the recommended first implementation.

```text
Mac local scheduler
-> Garmin export/import script
-> normalized JSON
-> Supabase
```

Why:

- easier to authenticate once;
- avoids storing Garmin credentials in cloud early;
- easier to debug;
- works before the full TrainingOS backend exists.

Recommended source order:

1. `garmin-data-export` for full and incremental exports.
2. `python-garminconnect` for targeted daily recovery metrics.
3. `garmin-connect-export` for activity CSV/GPX/TCX fallback.
4. `GarminDB` for local historical warehouse/reference.

## Stage 1 Setup Flow

### 1. Create ignored local folders

```text
TrainingOS/exports/
TrainingOS/tokens/
TrainingOS/imports/
```

These are ignored by Git.

### 2. First Garmin login

Run an interactive login once with the selected Garmin tool.

Expected result:

```text
Garmin token cached locally
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

### 5. Load into Supabase

Insert or upsert by stable keys:

```text
daily_recovery_metrics:
athlete_id + metric_date + provider

garmin_activities:
provider + external_activity_id
```

### 6. Schedule

Recommended MVP schedule:

```text
Daily import: 06:30
Post-workout import: manual Shortcut or button
Evening review: 21:00
```

## Stage 2: Supabase-Backed Pipeline

Once Stage 1 works, move the pipeline toward:

```text
Scheduled job
-> Garmin Provider
-> Supabase
-> AI review trigger
-> Google Calendar update
```

Options:

- local Mac scheduler continues to push into Supabase;
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
-> Supabase
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

## Security Rules

- Never commit `.env`.
- Never commit Garmin password.
- Never commit token cache.
- Never commit raw Garmin health export.
- Use `.gitignore` for exports and tokens.
- Keep only normalized test/sample data in GitHub.

## MVP Acceptance Criteria

The Garmin auto import MVP is successful when:

- one real Garmin account can authenticate;
- last 30 days can be imported;
- daily recovery metrics are normalized;
- at least one Strength activity can be imported;
- duplicate imports do not create duplicate records;
- AI review can use the imported recovery and activity data;
- no private data is committed to GitHub.

