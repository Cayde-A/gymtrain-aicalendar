# Gunyama Final Plan Validation

TrainingOS validates venue availability after recovery and muscle-overlap checks,
but before it creates a Garmin workout payload. This prevents an automated push
from scheduling a movement whose equipment has not been checked.

## Status Rules

- `user_verified`: accepted without a warning.
- `candidate`: finalization stops with `needs_venue_confirmation` unless the user
  explicitly confirms candidate equipment for that run.
- `unavailable`: finalization is blocked even when one-run candidate confirmation
  is supplied.
- missing catalog record: treated as `candidate`, never silently accepted.

The blocked response includes candidate exercise names and known substitutions.
Substitutions are suggestions only; TrainingOS does not silently replace an
exercise because that could change the planned stimulus or duplicate another
movement in the session.

## Persistent Confirmation

After checking the gym floor, record the observation in the local catalog:

```bash
.venv-garmin/bin/python scripts/gunyama_exercise_catalog.py \
  --confirm "Leg Press"
```

Or mark a movement unavailable:

```bash
.venv-garmin/bin/python scripts/gunyama_exercise_catalog.py \
  --unavailable "Cable Crossover"
```

These decisions survive idempotent catalog refreshes.

## One-Run Confirmation

For equipment observed during the current visit without changing the persistent
catalog, add this pipeline option:

```bash
--confirm-candidate-equipment
```

The resulting plan records `venue_validation.status` as `confirmed_for_run` and
lists the candidate exercises that were accepted. Automated scheduled runs do
not add this option, so they pause for user confirmation instead of assuming
availability.

Pass an empty `--venue` only when venue validation is intentionally not
applicable. The default is Gunyama Park Aquatic and Recreation Centre.
