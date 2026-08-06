# PR Tracking Design

TrainingOS uses PR tracking as the main signal for dynamic progression.

The design separates current PR state from historical PR events.

## Current State

`exercise_pr_state` stores the current best value.

There is only one row per:

```text
athlete
exercise
pr_type
```

Stored fields:

```text
exercise
pr_type
best_value
weight_kg
reps
estimated_1rm_kg
source_session
source_set
achieved_at
```

This is the local database version of a stack top: it represents the current highest known value.

## History

`pr_records` stores historical PR events.

It is append-only for real improvements, but session correction can remove and recalculate PR events from that corrected session.

## PR Types

The MVP tracks:

- `1rm`
- `3rm`
- `5rm`
- `8rm`
- `estimated_1rm`
- `volume_pr`

For rep-max PRs, a set qualifies when reps are greater than or equal to the threshold.

Example:

```text
100 kg x 5
-> qualifies for 1rm, 3rm, and 5rm
```

This means the system records the best load demonstrated for at least that rep threshold.

## Update Rule

After import or user correction:

```text
Read session sets
-> build candidate PRs
-> compare candidate best_value with exercise_pr_state
-> if candidate > current best, update state
-> append pr_records for the improvement
-> if candidate <= current best, do nothing
```

This matches the intended local-first stack-like behavior:

```text
new value greater
-> push/update current PR

new value lower or equal
-> no state change
```

## Correction Safety

If a session is corrected after it previously created a PR, TrainingOS:

```text
removes PR events from that session
-> removes PR state entries sourced from that session
-> rebuilds affected exercise state from remaining history
-> processes the corrected session again
```

This prevents a false PR from staying in the current state after a weight, rep, or exercise-name correction.

## Rebuild

Existing local history can be rebuilt with:

```bash
python3 scripts/trainingos_db.py --rebuild-prs
```

The rebuild clears PR state and PR history, then processes sessions chronologically.

## Product Use

The local review UI shows PR records for a corrected session.

Future rule-based planning should use `exercise_pr_state` as the fast current source and `pr_records` as the historical trend source.
