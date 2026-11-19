# Garmin Raw Cache Retention and Cleanup

## Scope

The cleanup command manages only local files under
`exports/garmin/raw`. It never deletes:

- normalized exports;
- the SQLite database;
- Garmin OAuth tokens;
- temporary monthly sync packages;
- Garmin Connect cloud data.

The default retention period is read from
`privacy_retention_policies.raw_cache_retention_days` and defaults to 30 days.

## Verification Rules

An old file becomes eligible only when TrainingOS can prove it has been
normalized:

- an activity filename must contain a Garmin activity ID already present in
  `completed_sessions`;
- every date inside a daily raw response must already exist in
  `daily_recovery_metrics`;
- unknown formats, unreadable JSON, unnormalized records, recent files, and
  symbolic links are retained.

The aggregate report contains counts and byte totals, not filenames, activity
IDs, or health values.

## Usage

Preview with no deletion:

```bash
.venv-garmin/bin/python scripts/garmin_cache_cleanup.py
```

Apply the current SQLite retention policy and verify every removal:

```bash
.venv-garmin/bin/python scripts/garmin_cache_cleanup.py --apply
```

Temporarily override the policy:

```bash
.venv-garmin/bin/python scripts/garmin_cache_cleanup.py \
  --retention-days 45 \
  --apply
```

The result is written to
`exports/garmin/normalized/cache_cleanup_report.json`. A successful applied
run reports `status=completed` and `deletion_verified=true`. A failed removal
reports `partial_failure` and exits with code 3.

## Automation Gate

For the current local-only system, preview may run at any time. Applied cleanup
should run after normalized import has succeeded. Once monthly Supabase sync is
implemented, the scheduler must additionally require a confirmed monthly sync
before applying cleanup for that month.

The first real preview on 2026-10-04 found three raw files: two were old and
verified as eligible, while one was protected because normalization could not
be proven. No user cache file was deleted during feature verification.
