# Garmin Provider Strategy

## Decision

TrainingOS will first combine four reusable Garmin open-source paths before building a custom Garmin integration from scratch.

The Garmin integration must be wrapped behind a `Garmin Provider` boundary so the rest of TrainingOS depends only on normalized data, not on any single GitHub library or unofficial endpoint.

## Recommended Stack

### 1. python-garminconnect

Role: primary programmatic access layer.

Use for:

- daily health metrics;
- sleep;
- HRV;
- stress;
- Body Battery;
- training readiness;
- activities;
- body composition;
- raw endpoint exploration.

TrainingOS usage:

```text
python-garminconnect
-> raw Garmin JSON
-> TrainingOS normalization
-> Supabase tables
```

### 2. GarminDB

Role: local data warehouse reference and fallback.

Use for:

- studying mature Garmin data modeling;
- local SQLite backup;
- incremental import patterns;
- Jupyter/data-analysis workflow inspiration.

TrainingOS usage:

```text
GarminDB
-> inspect SQLite/table patterns
-> adapt useful ideas into TrainingOS schema
```

### 3. garmin-data-export

Role: LLM-friendly export and incremental update bridge.

Use for:

- initial full Garmin export;
- incremental updates;
- compact JSON/text output for AI review;
- quick backup before building direct Supabase ingestion.

TrainingOS usage:

```text
garmin-data-export
-> compact update files
-> parser/normalizer
-> daily_recovery_metrics + activity tables
```

### 4. garmin-connect-export

Role: activity export fallback.

Use for:

- activity CSV export;
- GPX/TCX export;
- backup of activity history;
- cross-checking activity summaries.

TrainingOS usage:

```text
garmin-connect-export
-> activities.csv / GPX / TCX
-> TrainingOS activity import
```

## Normalization Boundary

The provider should output a stable internal shape:

```json
{
  "provider": "garmin",
  "source_tool": "python-garminconnect",
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
  "calories": null,
  "raw_payload": {}
}
```

No downstream TrainingOS logic should depend directly on Garmin raw field names.

## Failure and Same-Source Recheck Protocol

If a Garmin integration fails, do not immediately redesign the system.

Follow this sequence:

1. Identify failure scope:
   - login/authentication;
   - endpoint schema change;
   - missing metric;
   - rate limit;
   - package version conflict;
   - Garmin-side outage.
2. Recheck the same source first:
   - latest release;
   - recent commits;
   - open and closed issues;
   - pull requests;
   - README/authentication notes;
   - dependency updates such as `garth`, `curl_cffi`, or OAuth token handling.
3. Test the smallest working path:
   - login only;
   - one daily metric;
   - one activity fetch;
   - one incremental export.
4. Patch TrainingOS adapter only:
   - preserve normalized output shape;
   - keep schema stable unless the metric model truly changed.
5. If the original source has no fix, check the other three approved sources.
6. If all four fail, reassess official Garmin Developer Program or alternative bridge paths.

## Source Priority During Failure

Use this priority order:

1. `python-garminconnect` for API-level repair.
2. `garmin-data-export` for immediate export continuity.
3. `GarminDB` for local warehouse continuity.
4. `garmin-connect-export` for activity-level backup continuity.
5. Official Garmin Developer Program if the project needs production-grade stability.

## Security Rules

- Do not commit Garmin credentials.
- Do not commit Garmin tokens.
- Do not commit raw health exports.
- Store tokens and exports outside version control.
- Treat Garmin OAuth tokens like passwords.
- Prefer interactive credential entry during setup.

## MVP Implementation Path

1. Start with `garmin-data-export` to confirm account access and data availability.
2. Use `python-garminconnect` directly for daily recovery metrics.
3. Compare exported activity data with `garmin-connect-export`.
4. Use GarminDB as a reference if schema or historical import becomes complex.
5. Normalize into TrainingOS tables.
6. Add failure recheck notes to changelog whenever the provider is updated.

