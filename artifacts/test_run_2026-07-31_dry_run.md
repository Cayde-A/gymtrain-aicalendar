# Test Run: 2026-07-31 Dry Run

## Test Type

Dry run using sample workout data.

## Version

TrainingOS `0.1.3`

## Result

Partial pass.

The information flow is coherent, but real integration steps remain untested because Garmin sync, Supabase, Google Calendar API, and Apple Shortcuts are not connected yet.

## Step Results

| Step | Result | Notes |
|---|---|---|
| Planned session | Pass | Template can express session type, top set, back-off, cardio, and notes. |
| Garmin recording | Not tested | Requires real Garmin Strength activity and Garmin Connect sync. |
| Manual fallback log | Pass | Workout log template captures enough data for AI review. |
| Recovery context | Pass with manual data | Manual Garmin metrics can be attached to the workout date. |
| AI review | Pass in dry run | Sample data supports estimated 1RM and next target decision. |
| Next-day plan | Pass in dry run | AI output can become next target. |
| Calendar summary | Pass in dry run | Summary format is short enough for event notes. |

## Sample Calculation

```text
Exercise: Chest Press
Top Set: 90 kg x 5
Estimated 1RM = 90 x (1 + 5 / 30)
Estimated 1RM = 105 kg
```

## Dry-Run AI Decision

```text
Decision: Small Increase or Keep
Next top-set target: 92.5 kg x 3-5
Back-off target: 80 kg x 6-7 x 3
Condition: only increase if warm-ups feel fast and recovery remains acceptable
```

## Main Friction Found

- Garmin exercise names may not match TrainingOS exercise catalog exactly.
- Garmin may not reliably capture RPE, pain, technique notes, or subjective fatigue.
- ChatGPT App Shortcut flow may not automatically save the AI result back into the database.
- Calendar write-back should remain optional until Google Calendar API is connected.

## Required MVP Additions

- A correction surface for Garmin-imported exercises and set data.
- A stable `exercise_aliases` mapping for Garmin names to TrainingOS names.
- A one-screen post-workout review form for RPE, pain, technique, and fatigue.
- A saved AI review record format before full Supabase automation.

## Next Test

Run a real workout test:

```text
Garmin Strength activity
-> Garmin Connect sync
-> manually export or inspect activity
-> fill TrainingOS workout log
-> run AI review prompt
-> record next target
```

