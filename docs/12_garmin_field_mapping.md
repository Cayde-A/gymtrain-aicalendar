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
| `sleep_score` | `sleep.dailySleepDTO.sleepScores.overall.value`, `sleep.sleepScores.overall.value` |
| `sleep_duration_minutes` | `sleep.dailySleepDTO.sleepTimeSeconds`, `sleep.sleepTimeSeconds` converted to minutes |
| `hrv_status` | `hrv.hrvSummary.status` |
| `resting_heart_rate` | `stats.restingHeartRate`, `stats.data[].heartRate.restingValue`, `stats[].heartRate.restingValue` |
| `body_battery` | `stats.bodyBatteryMostRecentValue`, `stats.data[].bodyBattery.latestValue`, `stats[].bodyBattery.latestValue`, fallback to `body_battery[].bodyBatteryValuesArray[][]` |
| `stress_score` | `stats.averageStressLevel`, `stats.data[].stress.avgLevel`, `stats[].stress.avgLevel` |
| `training_readiness` | `training_readiness[].score` |
| `recovery_time_hours` | `training_readiness[].recoveryTime` in minutes, divided by 60 |
| `steps` | `stats.totalSteps`, `stats.data[].movement.steps.value`, `stats[].movement.steps.value` |
| `calories` | `stats.totalKilocalories`, `stats.data[].calories.burnedTotal`, `stats[].calories.burnedTotal` |

## Categorized Detail Mapping

The importer also writes five category records per date. These records support
visualization and analysis while the compact recovery mapping above remains
stable.

| Category | TrainingOS fields | Garmin source groups |
|---|---|---|
| Sleep | deep/light/REM/awake/nap minutes, sleep stress/HR, SpO2, respiration, sleep need | `sleep.*`, `sleep.dailySleepDTO.*` |
| HRV | status, weekly average, last-night average/high, baseline bounds | `hrv.hrvSummary.*` |
| Energy | Body Battery min/max/charge/drain/latest, calories, steps, floors, intensity minutes | `stats.data[].bodyBattery`, `calories`, `movement`, `intensityMinutes` |
| Vitals | heart-rate range/resting, stress, respiration, pulse ox | `stats.data[].heartRate`, `stress`, `respiration`, `pulseOx` |
| Readiness | score, level, factor percentages, feedback | `training_readiness[]` |

Seconds-based sleep fields are converted to minutes. Missing provider values
remain null and are not inferred.

## Current Completed Activity Mapping

Completed Garmin activities are imported through:

```text
get_activities_by_date
-> get_activity / get_activity_details
-> get_activity_exercise_sets
```

### Activity Summary

| TrainingOS Field | Garmin Source Field | Conversion |
|---|---|---|
| `external_activity_id` | `activityId`, `activity_id`, `id` | string |
| `activity_name` | `activityName`, `activity_name`, `name` | no conversion |
| `session_type` | `activityType.typeKey` | no conversion |
| `started_at` | `startTimeLocal`, `startTimeGMT`, `startTime` | no conversion |
| `completed_at` | same as `started_at` for MVP | no conversion |
| `duration_seconds` | `duration`, `durationSeconds`, `elapsedDuration` | no conversion |
| `average_heart_rate` | `averageHR`, `averageHeartRate`, `avgHR` | bpm, no conversion |
| `max_heart_rate` | `maxHR`, `maxHeartRate` | bpm, no conversion |
| `calories` | `calories`, `caloriesConsumed`, `activeKilocalories` | no conversion |

### Strength Set Logs

| TrainingOS Field | Garmin Source Field | Conversion / Rule |
|---|---|---|
| `exercise_name` | `exerciseName`, `exercise`, `name`, `exercises[].category` | use Garmin candidate; user correction required when confidence/name is poor |
| `set_order` | `setOrder`, `orderNumber`, `setNumber` | integer |
| `set_type` | `setType`, `type` | text, default `working` |
| `weight_kg` | `weight`, `weightKg`, `weightInKg`, `weightKilograms` | if value is `>= 1000`, treat as grams and divide by `1000` |
| `reps` | `reps`, `repetitions`, `repCount`, `repetitionCount` | integer |
| `rpe` | `rpe`, `ratingOfPerceivedExertion` | numeric |

Observed Garmin behavior:

```text
weight = 108000.0
-> TrainingOS weight_kg = 108.0

repetitionCount = 10
-> TrainingOS reps = 10
```

Garmin may return only exercise candidates such as:

```text
UNKNOWN
SIT_UP
CRUNCH
```

When this happens, TrainingOS should preserve the best available candidate but rely on the correction UI for the real gym exercise.

## Generated Reports

The importer writes:

```text
exports/garmin/normalized/daily_recovery_metrics.json
exports/garmin/normalized/daily_health_details.json
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
-> Update SET_FIELD_MAPPINGS or ACTIVITY_FIELD_MAPPINGS in scripts/garmin_activity_import.py
-> Keep normalized output shape stable
```

## Workout Cue Mapping

TrainingOS may attach local movement cues to generated Garmin workout steps.

Mapping:

| TrainingOS Field | Garmin Workout Field | Rule |
|---|---|---|
| `exerciseName` | `exerciseName` | Garmin exercise identifier |
| `category` | `category` | Garmin exercise category |
| `movement_cue` | `description` | TrainingOS-owned short text cue |

Do not copy Garmin animated workout text, images, or videos into TrainingOS.

If Garmin does not display the step description on a specific watch, keep the cue visible in TrainingOS Web/App/Shortcut and still push the structured workout normally.
