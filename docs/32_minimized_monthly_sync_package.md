# Minimized Monthly Sync Package

TrainingOS generates a temporary Supabase-ready package from the private local
monthly report. Generation does not upload anything.

## Command

```bash
.venv-garmin/bin/python scripts/trainingos_monthly_sync_package.py \
  --month 2026-10
```

The package is written to `exports/sync/monthly_sync_2026-10.json`. A matching
`monthly_sync_batches` row is stored as `pending`, with a stable SHA-256 hash.
Repeating the command for unchanged source data produces the same package, hash,
batch, and local summary record.

## Exact Allowlist

- schema version and month;
- training days and session count;
- session-type counts;
- per-exercise set count and total volume;
- best set per exercise;
- PR record count;
- estimated-1RM trends;
- monthly recovery coverage and averages.

The generator requires the complete top-level key set to match this allowlist.
A recursive scanner rejects keys associated with credentials, raw payloads,
identifiers, routes, notes, prompts, set logs, or body metrics.

## Default Exclusions

- athlete, Garmin user, activity, session, set-log, and device identifiers;
- Garmin credentials and raw payloads;
- GPS and route data;
- all free-text notes and AI prompts;
- body measurements and body-metric notes;
- day-level recovery records and minute-level time series.

Exercise names are retained because the approved cloud schema needs
exercise-level aggregate trends. Individual set rows and activity provenance are
not retained.

## Upload Boundary

This feature stops at `pending_upload`. A later Supabase adapter must:

1. use authenticated user context rather than adding a local identifier to the
   package;
2. upload the unchanged, hash-verified package;
3. mark the local batch uploaded only after read-back confirmation;
4. delete the temporary package when policy permits;
5. leave the complete SQLite history local.

Supabase credentials and a project are not required to generate or test the
package. The authenticated upload boundary is implemented separately in
[Supabase Monthly Upload](38_supabase_monthly_upload.md).
