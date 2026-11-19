# Morning Plan Finalization

The post-workout review creates an initial next-day draft. The morning workflow
finalizes that draft only after target-date recovery data is available.

## Command

```bash
.venv-garmin/bin/python scripts/trainingos_morning_finalize.py \
  --training-date 2026-10-04 \
  --date 2026-10-05 \
  --sync-garmin
```

The command reuses `trainingos_pipeline.py`; it does not duplicate planning or
validation rules. It also does not make an AI API call. The saved structured
review remains the source draft, while deterministic local rules apply:

1. training and recovery quality gates;
2. adjacent-day muscle-overlap constraints;
3. current eight-week cycle phase and volume ceiling;
4. recovery-based keep, reduced-volume, or deload adjustment;
5. main-exercise PR progression guidance;
6. Gunyama equipment availability;
7. Garmin trigger policy and write idempotency.

## User-Action States

- `needs_ai_review`: the previous workout has no saved structured review.
- `needs_recovery_sync`: target-date recovery is missing or incomplete.
- `needs_venue_confirmation`: one or more planned exercises are still venue
  candidates; confirm them persistently or add `--confirm-candidate-equipment`.
- `needs_push_confirmation`: a valid final plan exists, but the Garmin trigger
  requires explicit confirmation.

Successful local finalization returns `final_plan_ready`. Add `--dry-run-push`
to validate the generated Garmin payload, or `--push --confirm-push` for a live
write under the default user-confirmed policy.

The compact JSON output always reports `ai_api_called: false`, along with the
recovery adjustment, program week and phase, progression action, venue status,
payload path, and push result.
