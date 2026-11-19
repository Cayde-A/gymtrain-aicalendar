# Google Calendar and ICS Integration

## Role of Calendar

Google Calendar should be the scheduling and reminder layer.

It should contain:

- training day;
- session type;
- workout template;
- dynamic fields for weights and notes;
- reminder time;
- recovery and logging prompts.

It should not be the long-term source of truth for all set-level data.

## V4 ICS Design

V4 ICS supports:

- six-day recurring cycle across eight cycles;
- fixed training window, initially 11:00-12:30;
- Gunyama Park Aquatic and Recreation Centre location;
- Chest -> Core A -> Legs -> Core B -> Pull -> Recovery/Sync order;
- one explicit primary target per event;
- dynamic rather than fixed weight targets;
- overlap, fallback, logging, and recovery-finalization prompts.

Generate the current framework:

```bash
.venv-garmin/bin/python scripts/trainingos_ics.py \
  --start-date 2026-10-05 \
  --cycles 8
```

The generated artifact is `artifacts/TrainingOS_V4_Framework.ics`. Each event
recurs every six days, uses the `Australia/Sydney` timezone, and has a 45-minute
reminder. Importing it creates a finite 48-day framework rather than a permanent
calendar rule that could outlive the current training block.

## Event Template

```text
TrainingOS V4 - Push / Chest

Location:
Gunyama Park Aquatic and Recreation Centre

Readiness:
Morning Weight:
Sleep:
Garmin Recovery:
Body Battery:
HRV:

Primary target: Chest
Overlap rule: keep shoulder and triceps accessory volume limited
Morning inputs: sleep, HRV, Body Battery, readiness, recent PR state
Load: dynamic; do not copy a fixed weight from the calendar
Record: sets, reps, weight, RPE, pain, and technique notes
Fallback: reduce volume or use technique work; do not force a PR
```

## Integration Levels

### Level 1: Manual ICS

Generate an `.ics` file and import it into Google Calendar.

Best for:

- immediate testing;
- stable reminders;
- confirming training flow.

### Level 2: Scripted ICS Regeneration

Maintain a structured training plan and regenerate ICS when the template changes.

Best for:

- updating blocks;
- adding deload weeks;
- changing schedule without editing events one by one.

### Level 3: Google Calendar API

TrainingOS maps the same six-event model used by ICS to Google Calendar event
resources. Deterministic event IDs make repeated framework syncs update existing
events instead of creating duplicates. Private extended properties retain the
TrainingOS framework key.

Dry-run the mapping:

```bash
.venv-garmin/bin/python scripts/trainingos_google_calendar.py \
  --start-date 2026-10-05
```

TrainingOS can also patch a completed summary into a known Google event without
including local notes or raw set data:

```bash
.venv-garmin/bin/python scripts/trainingos_google_calendar.py \
  --completed-session LOCAL_SESSION_ID \
  --event-id GOOGLE_EVENT_ID
```

Example completed event:

```text
Completed
Chest Press: 95 kg x 5, new 5RM
Estimated 1RM: 111 kg
AI Review: Increase next top set by 2.5 kg
```

## Mobile Import Note

Google Calendar mobile apps generally do not directly import `.ics` files. The practical path is to import the file through Google Calendar web, then let it sync to mobile.

The API implementation follows Google's official
[`events.insert`](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert),
[`events.patch` and extended properties](https://developers.google.com/workspace/calendar/api/guides/extended-properties),
and [Calendar OAuth scope guidance](https://developers.google.com/workspace/calendar/api/auth).
