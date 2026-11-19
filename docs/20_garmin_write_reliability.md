# Garmin Write Reliability

## Goal

Garmin writes must be restartable without blindly creating duplicate workouts or schedules.

TrainingOS uses a local SQLite journal plus remote read-back confirmation. The journal contains no credentials or health data.

## Idempotency Key

The default key is a SHA-256 hash of:

```text
schedule date + workout name + canonical payload hash
```

The daily pipeline supplies its own stable key derived from athlete, source training date, and target date.

One key can only refer to one payload, workout name, and schedule date. Reusing it for different content returns a conflict and leaves the original operation unchanged.

## Write Phases

`garmin_write_operations` persists these checkpoints:

```text
created
-> uploaded
-> scheduled
-> push_requested
-> confirmed
```

If a process stops after upload or schedule, the next run resumes from that checkpoint instead of uploading again.

The uploaded workout description contains a short TrainingOS idempotency marker. If an upload response is lost, TrainingOS reads the Garmin workout list and recovers the matching workout ID before deciding whether another upload is necessary.

## Remote Confirmation

After scheduling, TrainingOS reads the Garmin calendar for the target month and checks date, workout name, and workout ID when Garmin returns it.

`confirmed` means:

- the workout upload has a Garmin workout ID;
- the schedule appears in Garmin's calendar response;
- when requested, the device-push API returned successfully.

It does not prove that the watch has downloaded the workout. Device delivery still depends on Garmin Connect synchronization and can only be confirmed on the watch.

## Retry Policy

| Operation | Automatic retry |
| --- | --- |
| Garmin reads | Up to three attempts with exponential backoff for outages/timeouts |
| HTTP 429 / rate limit | No immediate retry; journal suggests a 30-minute cooldown |
| Authentication / schema / unsupported capability | No retry |
| Upload | No blind replay; search for the idempotency marker first |
| Schedule | No blind replay; read the calendar to determine whether it landed |
| Device push | No automatic replay after timeout because the result is ambiguous |

Provider outages receive a default five-minute deferred retry time in the journal. The scheduler may run again after `next_retry_at`.

## Ambiguous Device Push

If the device-push request times out, the journal phase becomes `push_unknown`. A normal rerun stops with `ambiguous_write` and does not call the device API again.

After checking Garmin Connect or the watch, an intentional retry requires:

```bash
--retry-ambiguous-push
```

This flag is confirmation for that uncertain write only. It does not bypass the TrainingOS pipeline trigger policy.

## Direct Command

```bash
.venv-garmin/bin/python scripts/garmin_workout_push.py \
  --payload exports/pipeline/garmin_workout_2026-10-05.json \
  --date 2026-10-05 \
  --replace-existing \
  --db data/trainingos.sqlite \
  --idempotency-key stable-caller-key
```

The machine-readable result includes the idempotency key, workout ID, schedule ID when available, confirmation data, and whether device push was requested.

## Data Retention

The journal keeps small operational metadata:

- hashes and idempotency keys;
- workout name and date;
- Garmin workout/schedule IDs;
- phase, attempt count, retry time, structured error, and result.

It does not store Garmin tokens, passwords, raw workout history, sleep data, HRV, or raw API payloads.
