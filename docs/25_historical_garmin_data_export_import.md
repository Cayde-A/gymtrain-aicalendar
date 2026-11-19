# Historical garmin-data-export Import

## Reused Source

TrainingOS supports files produced by
`https://github.com/sirredbeard/garmin-data-export` (Apache 2.0).

The upstream project exports complete Garmin responses in two useful forms:

- JSON cache files under `.cache/daily` and `.cache/activities`;
- compact, split, and update text files with `Daily Health` and `Activities`
  JSON sections.

TrainingOS reads those files; it does not copy the upstream exporter or ask it
to write directly to domain tables.

## Import Boundary

`scripts/garmin_data_export_import.py`:

1. discovers cache JSON first, then compact text sections;
2. sends recovery and activity payloads through the existing normalizers;
3. converts Garmin gram-based strength weights through the existing mapping;
4. imports Strength activities by default;
5. upserts recovery by date/provider and sessions by provider/activity ID;
6. records `source_tool=garmin-data-export`;
7. emits a value-free report with record, set, missing-rep, and abnormal-weight
   counts.

Raw export files remain outside Git and are not copied into the repository.

## Commands

Preview an export directory or `.cache` directory:

```bash
.venv-garmin/bin/python scripts/garmin_data_export_import.py \
  /private/path/to/export \
  --dry-run
```

Import Strength history into local SQLite:

```bash
.venv-garmin/bin/python scripts/garmin_data_export_import.py \
  /private/path/to/export
```

Import a compact/update file directly:

```bash
.venv-garmin/bin/python scripts/garmin_data_export_import.py \
  /private/path/to/garmin_export_YYYY-MM-DD_HHMMSS_compact_update.txt
```

Use `--include-all-activities` only when non-strength sessions also belong in
TrainingOS. The report is stored at
`exports/garmin/normalized/historical_import_report.json`.

## Validation

Automated fixtures cover cache JSON, compact/update text, Strength filtering,
gram-to-kilogram conversion, source provenance, dry-run behavior, and repeated
imports. Re-importing the same fixture produces one recovery record and one
session rather than duplicates.
