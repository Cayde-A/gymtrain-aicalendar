# Daily Pipeline

## First Training Gate

Before quality checks or AI packet creation, the pipeline looks for a completed
session on or before the source date with at least one non-rest set.

When Garmin sync is enabled and the normal recent window finds no local anchor,
the pipeline performs one extended 180-day Strength lookup, limited to five
activities. This covers training interruptions without making every daily sync
expensive. `--anchor-lookback-days` can adjust or disable the expansion by
setting it no higher than `--activity-days`.

- No completed sessions: `waiting_for_first_training`, exit code `3`.
- Session exists but has no active sets: `first_training_needs_data`, exit code `3`.
- Valid anchor exists: continue to the normal quality and review gates.

Both waiting states permit recovery synchronization but skip parsing, AI calls,
plan generation, and Garmin writes. The gate clears automatically after the
first valid workout is imported or entered manually.

## Purpose

`trainingos_pipeline.py` is the observable state machine for the current TrainingOS daily workflow:

```text
optional Garmin import
-> deterministic data-quality gate
-> day-level AI review packet
-> saved structured review
-> target-date recovery gate
-> deterministic finalization and volume adjustment
-> muscle-overlap validation
-> Garmin payload
-> trigger policy
-> optional Garmin push
```

Every run is persisted in local SQLite `pipeline_runs` and written as a JSON report under `exports/pipeline/`.

## Safe First Run

Generate the review packet from data already stored locally:

```bash
.venv-garmin/bin/python scripts/trainingos_pipeline.py \
  --date 2026-10-04 \
  --target-date 2026-10-05
```

Expected status when no review has been saved: `needs_ai_review`.

The command writes `ai_review_packet_2026-10-04.json`. With the default manual policy, send that packet to ChatGPT and save the JSON response locally.

## Continue With A Review

```bash
.venv-garmin/bin/python scripts/trainingos_pipeline.py \
  --date 2026-10-04 \
  --target-date 2026-10-05 \
  --ai-response /private/path/review.json
```

The same response is not inserted twice when the command is rerun.

If target-date recovery is missing, the command stops at `needs_recovery_sync`. Once recovery data is available, it converts the reviewed initial plan into a final preset plan and applies one deterministic recovery adjustment:

- `keep`: preserve preset volume;
- `reduce_volume`: remove one set from each exercise;
- `deload`: reduce each exercise to approximately half its preset sets.

These rules alter set count only. They do not invent weights or overwrite PR state.

For the dedicated next-morning entry point, use:

```bash
.venv-garmin/bin/python scripts/trainingos_morning_finalize.py \
  --training-date 2026-10-04 \
  --date 2026-10-05 \
  --sync-garmin
```

This reuses the saved review and daily pipeline. The final adjustment is
deterministic and does not call an AI API.

## Garmin Import

To fetch recovery and completed strength data before evaluation:

```bash
.venv-garmin/bin/python scripts/trainingos_pipeline.py \
  --date 2026-10-04 \
  --target-date 2026-10-05 \
  --sync-garmin
```

This performs Garmin reads and may require login or MFA when local tokens are unavailable. Import failure stops the workflow before analysis.

## Garmin Payload Dry Run

```bash
.venv-garmin/bin/python scripts/trainingos_pipeline.py \
  --date 2026-10-04 \
  --target-date 2026-10-05 \
  --ai-response /private/path/review.json \
  --dry-run-push
```

Dry run does not write to Garmin. It still requires valid training data, recovery data, review output, final-plan mapping, and overlap checks.

## Live Garmin Push

With the default `user_confirmed` policy, a live write requires both flags:

```bash
.venv-garmin/bin/python scripts/trainingos_pipeline.py \
  --date 2026-10-04 \
  --target-date 2026-10-05 \
  --ai-response /private/path/review.json \
  --push \
  --confirm-push
```

If `--push` is supplied without confirmation, the state is `needs_push_confirmation` and no Garmin command runs.

When policy mode is `auto_after_final_plan` and `auto_api_enabled` is on, a passing final plan may push without command-line confirmation. This is an explicit user-controlled setting, not the default.

## Supported Presets

- `legs_after_push` -> legs;
- `push_chest_conservative` -> chest;
- `pull_back_conservative` -> back;
- `core_between_push_legs` -> interstitial core;
- `core_between_legs_pull` -> interstitial core.

The Pull preset uses Garmin catalog pairs for lat pull-down, seated cable row, face pull, and cable biceps curl.

An explicit `--preset` can override the reviewed primary group for a manual test. The final overlap gate still applies.

## Blocking Rules

The pipeline never advances past:

- normalized training or recovery quality blockers;
- an unstructured review;
- non-empty AI `data_quality_issues`;
- missing target-date recovery;
- unsupported plan-to-preset mapping;
- chest/shoulder followed by back, arms, or another pressing primary day;
- repeated primary large muscle group on adjacent days;
- a denied Garmin trigger decision.

## Status And Exit Codes

| Status | Exit | Meaning |
| --- | ---: | --- |
| `quality_blocked` | 2 | Correct imported data first |
| `needs_ai_review` | 3 | Manual review packet is ready |
| `needs_recovery_sync` | 3 | Initial review exists; target recovery is missing |
| `needs_venue_confirmation` | 3 | Candidate venue equipment requires user confirmation |
| `review_quality_blocked` | 2 | AI reported unresolved data-quality issues |
| `plan_blocked` | 2 | Preset mapping or muscle-overlap validation failed |
| `needs_push_confirmation` | 3 | Trigger policy requires confirmation |
| `final_plan_ready` | 0 | Final plan and Garmin payload are saved locally |
| `dry_run_complete` | 0 | Garmin payload dry run passed |
| `pushed` | 0 | Garmin write command completed successfully |
| `sync_failed` / `push_failed` | 4 | Provider action failed |

## Persistence And Idempotency

One logical pipeline record is maintained per athlete, source training date, and target date. Repeating a run updates that record instead of creating another one. Review responses are also reused when their structured JSON matches an existing day review.

The pipeline passes a stable idempotency key and the same local database to the Garmin writer. Upload, schedule, and device-push checkpoints survive process restarts. See [Garmin Write Reliability](20_garmin_write_reliability.md).
