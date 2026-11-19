# gccli Parity and Adoption Gate

## Purpose

`gccli` is evaluated as a reusable Garmin transport for deterministic local
jobs. It does not replace TrainingOS normalization, quality gates, planning,
privacy controls, or audited workout writes.

The adopted version for this spike is `gccli 1.10.0`. It is installed through
the upstream Homebrew tap and stores OAuth tokens in the operating-system
keychain.

## Implemented Boundary

`scripts/gccli_adapter.py` provides:

- structured JSON command execution;
- optional account selection;
- authentication, rate-limit, schema, outage, and unavailable-command errors;
- recent activity and strength-set reads;
- daily summary, sleep, HRV, Body Battery, and training-readiness reads;
- exercise catalog lookup;
- local workout JSON validation with no remote write.

The adapter returns provider JSON. Existing TrainingOS normalizers remain the
only path into local domain tables.

## Safety Rules

- No `workouts upload`, schedule, update, or delete command is executed by the
  parity tool.
- The report contains counts, exact-match totals, and quality issue counts; it
  omits activity IDs and metric values.
- `gccli` workout writes remain disabled in adapter capability metadata until
  live parity and write-idempotency tests pass.
- The current audited Python Garmin push path remains the only live write path.

## Live Parity Command

Generate a workout payload without uploading it:

```bash
.venv-garmin/bin/python scripts/trainingos_garmin_payload.py \
  --date YYYY-MM-DD \
  --preset legs_after_push \
  --output /tmp/trainingos-gccli-dry-run.json
```

After completing `gccli auth login`, run:

```bash
.venv-garmin/bin/python scripts/gccli_parity.py \
  --activities 2 \
  --days 7 \
  --end-date YYYY-MM-DD \
  --live-python-baseline \
  --workout /tmp/trainingos-gccli-dry-run.json
```

The report is written to
`exports/garmin/normalized/gccli_parity_report.json`. It is local test output
and must not contain raw personal values.

## Adoption Gate

The scheduled-job adapter can be enabled only when all conditions hold:

1. Two recent strength activities are returned and their sets normalize.
2. Seven recovery days are returned and normalize through the existing field
   mapping.
3. Missing reps and abnormal post-normalization weights are reported.
4. The generated Strength workout passes local dry-run validation.
5. Repeating imports does not duplicate local sessions or sets.
6. A separate live-write test proves upload and schedule idempotency with
   confirmation reads.

Until all six conditions pass, `gccli` is a diagnostic/read candidate rather
than the TrainingOS production write transport.

## Verified Result

On 2026-10-04, the read and dry-run portion of the gate passed with `gccli
1.10.0`:

- two of two recent Strength activities matched the live
  `python-garminconnect` baseline across activity name, start time, duration,
  average heart rate, maximum heart rate, and calories;
- seven of seven recovery days matched across all ten normalized fields;
- 30 active sets contained no missing repetitions or abnormal normalized
  weights;
- the generated Strength workout passed local validation without a remote
  write;
- repeating a normalized gccli activity import produced one session and one
  set collection rather than duplicates;
- all 98 repository tests passed.

This verifies `gccli` for read-only adapter use. Condition 6, live write
idempotency, remains intentionally separate. Therefore `workout_upload` and
`workout_schedule` stay disabled in gccli adapter capability metadata, and the
existing audited Python write path remains active.
