# Artifacts

This folder tracks reusable project artifacts.

## Available Artifacts

- `TrainingOS_V4_Framework.ics`: generated 48-day Google Calendar training framework using the current six-day split.
- `workout_log_template`: set-level training log template.
- `ai_review_prompt`: post-workout review prompt.
- `weekly_review_template`: weekly progress and fatigue review.
- `monthly_report_template`: body, recovery, and PR summary.
- `supabase_schema.sql`: implementation-ready database schema.
- `usage_flow_test_v0_1.md`: current MVP usage flow test.
- `test_run_2026-07-31_dry_run.md`: first dry-run result using sample data.

Regenerate the ICS artifact with:

```bash
.venv-garmin/bin/python scripts/trainingos_ics.py \
  --start-date 2026-10-05 \
  --cycles 8
```

## Artifact Rules

- Calendar files define planned structure.
- Logs define completed reality.
- Database is the source of truth once V5/V6 begins.
- AI recommendations should always reference the data version they used.
