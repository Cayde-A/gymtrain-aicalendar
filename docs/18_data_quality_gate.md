# Data Quality Gate

## Purpose

TrainingOS must not analyze corrupted workout data or push a final plan based on missing recovery data. The quality gate provides one deterministic check shared by the review UI, scheduled workflow, and future API.

The gate does not use AI. It evaluates normalized local SQLite records only.

## Command

Check whether a completed training day is ready for analysis:

```bash
.venv-garmin/bin/python scripts/trainingos_quality.py \
  --date 2026-10-04
```

Check whether the training day and next-day recovery data are ready for final plan generation:

```bash
.venv-garmin/bin/python scripts/trainingos_quality.py \
  --date 2026-10-04 \
  --recovery-date 2026-10-05 \
  --output exports/quality/2026-10-05.json
```

Exit codes:

- `0`: the requested stage is ready;
- `2`: one or more blocking issues require correction or synchronization.

## Training Checks

Blocking issues:

- no completed session for the requested date;
- no active sets;
- missing or non-positive repetitions on an active set;
- weight below `0 kg` or above `500 kg`;
- unknown exercise identity;
- invalid or duplicate set order within a session.

Warnings:

- missing weight, because bodyweight and timed exercises may legitimately omit it.

Rest sets do not require repetitions or weight and are excluded from the active-set count.

## Recovery Checks

A final plan requires a target-date recovery record containing at least one decision-grade field:

- sleep score or duration;
- HRV status;
- resting heart rate;
- Body Battery;
- stress;
- training readiness;
- recovery time.

Known numeric fields are range checked. Missing recovery or out-of-range values block finalization, but do not prevent post-workout analysis of a valid completed session.

## Report Contract

The JSON report contains:

```json
{
  "version": "trainingos.quality_report.v1",
  "analysis_ready": true,
  "finalization_ready": false,
  "training": {
    "session_count": 1,
    "set_count": 8,
    "active_set_count": 8,
    "issues": []
  },
  "recovery": null
}
```

Every issue includes a stable code, severity, message, and limited local context. Reports do not include credentials, tokens, or raw Garmin payloads.

## Pipeline Rule

```text
Garmin import
-> correction
-> training quality gate
-> post-workout review
-> next-day recovery sync
-> recovery quality gate
-> final plan validation
-> trigger policy
-> Garmin push
```

No later stage may override a blocking quality issue. User correction or a successful resync must resolve it first.
