# Garmin Field Mapping

## Purpose

Field mapping converts Garmin raw response paths into stable TrainingOS fields.

TrainingOS should depend on normalized names such as:

```text
sleep_score
sleep_duration_minutes
body_battery
training_readiness
```

It should not depend directly on Garmin raw names such as:

```text
sleep.dailySleepDTO.sleepScores.overall.value
stats.bodyBatteryMostRecentValue
training_readiness[].score
```

## Current Daily Recovery Mapping

| TrainingOS Field | Garmin Source Path |
|---|---|
| `sleep_score` | `sleep.dailySleepDTO.sleepScores.overall.value` |
| `sleep_duration_minutes` | `sleep.dailySleepDTO.sleepTimeSeconds` converted to minutes |
| `hrv_status` | `hrv.hrvSummary.status` |
| `resting_heart_rate` | `stats.restingHeartRate` |
| `body_battery` | `stats.bodyBatteryMostRecentValue`, fallback to `body_battery[].bodyBatteryValuesArray[][]` |
| `stress_score` | `stats.averageStressLevel` |
| `training_readiness` | `training_readiness[].score` |
| `recovery_time_hours` | `training_readiness[].recoveryTime` converted to hours |
| `steps` | `stats.totalSteps` |
| `calories` | `stats.totalKilocalories` |

## Generated Reports

The importer writes:

```text
exports/garmin/normalized/daily_recovery_metrics.json
exports/garmin/normalized/raw_schema_summary.json
exports/garmin/normalized/mapping_coverage.json
```

`mapping_coverage.json` reports field coverage without exposing full raw data.

Example:

```text
sleep_score: 3/3
body_battery: 3/3
training_readiness: 3/3
```

## Maintenance Rule

If a normalized field starts returning null:

```text
Check mapping_coverage.json
-> Check raw_schema_summary.json
-> Update FIELD_MAPPINGS in scripts/garmin_import.py
-> Keep normalized output shape stable
```

