# Garmin Import MVP

## Purpose

This MVP tests whether TrainingOS can authenticate through Garmin's official Personal API, fetch recent daily recovery data, and normalize it into a stable TrainingOS shape. The legacy Garmin Connect login remains a temporary fallback and the workout-write path.

## Files

- `scripts/garmin_import.py`: interactive local Garmin import script.
- `scripts/garmin_activity_import.py`: completed-activity importer with official FIT fallback.
- `scripts/garmin_fit_activity.py`: bounded Garmin FIT strength-set decoder.
- `requirements.txt`: Python dependency list.
- `exports/garmin/normalized/daily_recovery_metrics.json`: generated normalized output, ignored by Git.
- `exports/garmin/normalized/raw_schema_summary.json`: generated field-path/type summary, ignored by Git.
- `exports/garmin/normalized/mapping_coverage.json`: generated field mapping coverage report, ignored by Git.
- `exports/garmin/normalized/provider_capabilities.json`: provider version and supported operation groups, without health values.
- `exports/garmin/raw/`: optional raw output, ignored by Git.
- `~/.config/garmin/connect-personal-api-key`: preferred Personal API key file.
- `~/.config/garmin/connect-personal-api-bearer-token.json`: official client bearer-token cache.
- `tokens/garmin/`: compatibility-provider token cache, ignored by Git.

## Setup

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Create a Personal API key in Garmin Connect Web and save it as a single line in:

```text
~/.config/garmin/connect-personal-api-key
```

Restrict the file on macOS/Linux:

```bash
chmod 600 ~/.config/garmin/connect-personal-api-key
```

The default `GARMIN_READ_PROVIDER=auto` selects this official read path when the key exists. `GARMIN_READ_PROVIDER=personal` requires it, while `legacy` forces a compatibility read.

The following local credentials are needed only for compatibility reads and workout writes:

```text
GARMIN_EMAIL=your-email@example.com
GARMIN_PASSWORD=your-password
```

Use `env.garmin.example` as the template. `.env.local` is ignored by Git.

Alternatively, start the local-only Garmin setup page:

```bash
.venv/bin/python scripts/garmin_local_login_ui.py
```

Then open:

```text
http://127.0.0.1:8765
```

This page can securely save the official Personal API key to
`~/.config/garmin/connect-personal-api-key` with mode `0600`. It also retains a
separate legacy login form that writes `.env.local` and can trigger a 3-day
import test for compatibility write and push workflows. Sensitive values are
not displayed on the result page.

Run a 7-day import:

```bash
python3 scripts/garmin_import.py --days 7
```

Run a 30-day import and save raw Garmin responses:

```bash
python3 scripts/garmin_import.py --days 30 --include-raw
```

Import recent completed Strength activities:

```bash
python3 scripts/garmin_activity_import.py --days 30 --strength-only --limit 5
```

The importer first uses Personal API activity details. If they omit strength
sets, it downloads the activity ZIP in memory and decodes its single FIT file
with Garmin's official FIT SDK. The ZIP/FIT is size-bounded, is never extracted
to disk, and the normalized session records
`garmin-connect-personal-api-python+garmin-fit-sdk` as its source.

If the selected history window contains no completed workout and the local
database has no earlier workout with an active set, the import still succeeds
but records `waiting_for_first_training`. Recovery synchronization remains
available. Training parsing, AI review, planning, and Garmin push wait until
the user's first completed workout is available. A session shell without
active sets records `first_training_needs_data` instead of becoming an anchor.

## Security

The preferred read path exchanges the Personal API key for a 24-hour bearer token. The key and token cache are credentials.

Prefer interactive password input. Avoid passing passwords through command-line arguments because they can appear in shell history or process listings.

Do not commit:

- `.env`;
- Garmin credentials;
- Garmin token cache;
- `exports/`;
- raw health data.

These are already covered by `.gitignore`.

If you use `.env.local`, delete it after testing or keep it only on your private machine.

The compatibility provider saves Garmin OAuth tokens under:

```text
tokens/garmin/
```

Future imports should reuse those tokens and avoid repeated password logins. This matters because Garmin may return `429 Too Many Requests` after repeated authentication attempts.

## Expected Output

```json
{
  "provider": "garmin",
  "source_tool": "garmin-connect-personal-api-python",
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

Null values are acceptable in the first test. In particular, Personal API does not currently expose dedicated Training Readiness or Recovery Time endpoints. The purpose is to confirm authentication, available methods, and raw response shapes without inventing missing Garmin values.

If `raw_available` is true but metric values are still null, rerun the importer and inspect:

```text
exports/garmin/normalized/raw_schema_summary.json
```

This file contains field names and types only. It intentionally omits health values so it is safer for field-mapping work.

The importer also writes:

```text
exports/garmin/normalized/mapping_coverage.json
```

Use this to confirm which normalized TrainingOS fields were populated.

The importer also records the installed provider version and detected method groups in:

```text
exports/garmin/normalized/provider_capabilities.json
```

Provider failures use stable error codes:

| Code | Retry automatically | Action |
| --- | --- | --- |
| `rate_limit` | Yes, after backoff | Do not repeat login immediately |
| `provider_outage` | Yes, after backoff | Keep the local plan and retry later |
| `authentication` | No | Ask the user to refresh login or MFA |
| `capability_unavailable` | No | Recheck provider version or use a fallback adapter |
| `schema` | No | Stop analysis or push until mapping is corrected |
| `confirmation_failed` | Yes, after backoff | Schedule write was not visible in calendar read-back |
| `ambiguous_write` | No | Check Garmin/watch before explicitly retrying device push |
| `unknown` | No | Preserve diagnostics and require review |

Workout push failures are written to the normal push-result JSON with `status: failed` and the structured error object. This gives scheduled tasks a deterministic decision without parsing terminal text.

## First Test Checklist

```text
Dependency install:
Personal API key configured:
Official bearer token obtained:
Legacy login/MFA if write testing:
7-day import:
Normalized JSON created:
Schema summary created:
Mapping coverage created:
Provider capabilities created:
Metrics populated:
Failures observed:
Next fix:
```
