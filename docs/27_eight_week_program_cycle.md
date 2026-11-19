# Eight-Week PR Program Cycle

TrainingOS persists each two-month V4 program as one 56-day `training_blocks`
record and eight idempotent `workout_templates`. The current week is calculated
from the plan date, so no mutable week counter can drift when a day is skipped.

## Weekly Structure

| Week | Phase | Top-set reps | Volume ceiling | PR attempt |
|---|---|---:|---:|---|
| 1 | accumulation | 5 | 100% | allowed |
| 2 | accumulation | 5 | 100% | allowed |
| 3 | intensification | 4 | 90% | allowed |
| 4 | deload | none | 55% | blocked |
| 5 | accumulation | 5 | 100% | allowed |
| 6 | intensification | 4 | 90% | allowed |
| 7 | realization | 3 | 80% | allowed |
| 8 | deload | none | 55% | blocked |

Set counts use the stricter result from recovery adjustment and the weekly
volume ceiling. TrainingOS does not calculate an exact working weight because
machine increments and same-day warm-up quality remain execution inputs.

## Progression Decision Order

For the plan's first primary movement:

1. A scheduled recovery week returns `deload`.
2. A recovery-gate deload returns `deload`.
3. Moderate recovery returns `keep` and reduces volume first.
4. No prior exercise history returns `establish_baseline`.
5. Two consecutive estimated-1RM declines return `reduce_5_percent`.
6. Latest RPE 9 or higher returns `keep`.
7. A latest estimated-1RM PR at RPE below 9 returns `increase_small` at 2.5%.
8. A completed result at RPE 8 or lower also returns `increase_small` at 2.5%.
9. Otherwise the action is `keep`.

The final plan records the rule result and its reason. The Garmin workout
description includes cycle week, phase, and action, while load selection remains
manual and conservative.

## Commands

Explicitly begin a cycle:

```bash
.venv-garmin/bin/python scripts/trainingos_program_cycle.py \
  --date 2026-10-05 \
  --create \
  --goal "PR progression with controlled fatigue"
```

Inspect the active week for a date:

```bash
.venv-garmin/bin/python scripts/trainingos_program_cycle.py \
  --date 2026-10-26
```

If the daily pipeline has no active V4 cycle, it starts one on the target plan
date. Repeating creation for the same athlete, date, and cycle version updates
the same block and templates instead of duplicating them.
