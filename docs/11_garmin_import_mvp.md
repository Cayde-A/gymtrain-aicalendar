# Garmin Import MVP

## Purpose

This MVP tests whether TrainingOS can log in to Garmin Connect, fetch recent daily recovery data, and normalize it into a stable TrainingOS shape.

## Files

- `scripts/garmin_import.py`: interactive local Garmin import script.
- `requirements.txt`: Python dependency list.
- `exports/garmin/normalized/daily_recovery_metrics.json`: generated normalized output, ignored by Git.
- `exports/garmin/normalized/raw_schema_summary.json`: generated field-path/type summary, ignored by Git.
- `exports/garmin/raw/`: optional raw output, ignored by Git.

## Setup

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

If the Codex terminal does not allow interactive input, create a local `.env.local` file:

```text
GARMIN_EMAIL=your-email@example.com
GARMIN_PASSWORD=your-password
```

Use `env.garmin.example` as the template. `.env.local` is ignored by Git.

Run a 7-day import:

```bash
python3 scripts/garmin_import.py --days 7
```

Run a 30-day import and save raw Garmin responses:

```bash
python3 scripts/garmin_import.py --days 30 --include-raw
```

## Security

The script asks for Garmin credentials interactively.

Prefer interactive password input. Avoid passing passwords through command-line arguments because they can appear in shell history or process listings.

Do not commit:

- `.env`;
- Garmin credentials;
- Garmin token cache;
- `exports/`;
- raw health data.

These are already covered by `.gitignore`.

If you use `.env.local`, delete it after testing or keep it only on your private machine.

## Expected Output

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
  "raw_available": {
    "stats": false,
    "sleep": false,
    "hrv": false,
    "body_battery": false,
    "training_readiness": false
  }
}
```

Null values are acceptable in the first test. The purpose is to confirm login, available methods, and raw response shapes.

If `raw_available` is true but metric values are still null, rerun the importer and inspect:

```text
exports/garmin/normalized/raw_schema_summary.json
```

This file contains field names and types only. It intentionally omits health values so it is safer for field-mapping work.

## First Test Checklist

```text
Dependency install:
Garmin login:
MFA prompt:
7-day import:
Normalized JSON created:
Schema summary created:
Metrics populated:
Failures observed:
Next fix:
```
