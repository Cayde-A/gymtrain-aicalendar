# Monthly Report

The monthly report is generated from normalized local SQLite records and remains
on the device. It does not call AI or upload to Supabase.

## Command

```bash
.venv-garmin/bin/python scripts/trainingos_monthly_report.py \
  --month 2026-10
```

The command writes:

```text
exports/reports/monthly_report_2026-10.json
exports/reports/monthly_report_2026-10.md
```

## Included Metrics

- training days, session count, and session-type counts;
- working-set count, total logged volume, and missing-field counts;
- per-exercise set count and volume;
- best set per exercise using estimated 1RM;
- first-to-last monthly estimated-1RM trend per exercise;
- PR record count;
- recovery-day coverage and available monthly averages;
- first-to-last body measurement changes when at least two records exist.

No activity IDs, raw Garmin payloads, credentials, free-text notes, pain notes,
or body-metric notes are included. Empty months produce a complete report with
explicit zero and unavailable values.

This report is the source for the future minimized monthly sync package. The
sync package must apply an additional allowlist and must never upload the report
wholesale.
