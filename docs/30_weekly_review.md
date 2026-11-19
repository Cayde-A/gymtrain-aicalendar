# Weekly Review

The weekly review is a deterministic local aggregate. It does not call an AI API
and does not include pain notes, readiness notes, or body-metric notes.

## Command

```bash
.venv-garmin/bin/python scripts/trainingos_weekly_review.py \
  --week-ending 2026-10-04
```

The seven-day inclusive period runs from Monday through the supplied Sunday when
`--week-ending` is a Sunday. The command writes matching JSON and Markdown files
under `exports/reviews/`.

## Included Metrics

- training days and completed sessions;
- working sets, logged volume, and missing reps, weight, or RPE counts;
- per-exercise set count and volume;
- PR record count;
- recovery-day coverage and available metric averages;
- first-to-last body measurement changes when the week has at least two records.

Empty weeks still generate a complete report with zero counts and explicit
`unavailable` values. This keeps scheduled reporting observable without
inventing trends from absent data.

The JSON includes `ai_api_called: false`. A future user-confirmed AI summary can
consume this aggregate, but the base weekly report remains reproducible and does
not spend model compute.
