# Google Calendar API Adapter

TrainingOS uses one schedule model for both ICS export and Google Calendar API
payloads. This prevents calendar behavior from diverging between manual import
and authenticated sync.

Official references:

- [Events insert](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert)
- [Extended properties and patch](https://developers.google.com/workspace/calendar/api/guides/extended-properties)
- [Calendar OAuth scopes](https://developers.google.com/workspace/calendar/api/auth)

## Framework Dry Run

```bash
.venv-garmin/bin/python scripts/trainingos_google_calendar.py \
  --start-date 2026-10-05 \
  --cycles 8
```

This writes six recurring event payloads under `exports/calendar/`. Each event
uses Australia/Sydney time, a six-day recurrence, a finite count, a 45-minute
popup reminder, private visibility, and a private TrainingOS key.

The Google event ID is deterministic from framework version, event key, and
framework start date. It uses Google's supported base32hex character range.
Live sync performs GET then insert for a missing event, or PATCH for an existing
event. Successful events are recorded in local `calendar_events`.

## Completed Summary Dry Run

```bash
.venv-garmin/bin/python scripts/trainingos_google_calendar.py \
  --completed-session LOCAL_SESSION_ID \
  --event-id GOOGLE_EVENT_ID
```

The patch contains activity type, per-exercise set count and best logged set, PR
record count, and the structured review decision. It excludes external activity
ID, local session ID, pain and readiness notes, set notes, and AI free text. A
hash marker links the completion locally without exposing the session ID.

## Live Write Gate

Live writes require all three inputs:

```text
--push
--confirm
GOOGLE_CALENDAR_ACCESS_TOKEN
```

Use the narrowest scope compatible with the selected calendar, preferably
`calendar.events.owned` when the app only edits owned calendars, or
`calendar.events` when broader event access is intentionally required. Tokens
remain outside project files.

The current automated tests use a fake remote transport to prove first-create,
repeat-update, completion patch, private-property preservation, structured HTTP
failure, and local row idempotency. A real account write remains pending explicit
OAuth authorization.
