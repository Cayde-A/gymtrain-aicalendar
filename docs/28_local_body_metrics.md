# Local Body Metrics

TrainingOS stores body measurements only in the local SQLite database. The
current feature does not upload measurements to Supabase or another cloud
service, and observability events contain only the date and populated field
count.

## Supported Fields

- body weight in kilograms;
- body fat percentage;
- waist, chest, hip, arm, and leg circumference in centimetres;
- an optional local note.

At least one numeric measurement is required. Plausibility ranges reject common
unit or input mistakes. Saving the same date again updates that day's record
instead of creating another row.

## Web Entry

Start the local review UI and open:

```text
http://127.0.0.1:8787/body
```

The form is mobile-friendly and displays the 20 most recent local records.

## CLI Entry

```bash
.venv-garmin/bin/python scripts/trainingos_body_metrics.py \
  --date 2026-10-04 \
  --weight-kg 80.2 \
  --body-fat-percent 15.1 \
  --waist-cm 84
```

List recent records:

```bash
.venv-garmin/bin/python scripts/trainingos_body_metrics.py --list --limit 30
```

## AI Packet Use

Session and same-day review packets include the most recent body record on or
before the training date and field-level changes from the prior record. Notes
are excluded from this compact context. If no record exists, the packet reports
`status: unavailable`; missing body data never blocks training review or Garmin
plan generation.

Future monthly cloud synchronization must use minimized aggregates or explicit
field consent. This feature does not change the existing local-first privacy
boundary.
