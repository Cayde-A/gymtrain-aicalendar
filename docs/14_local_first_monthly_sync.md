# Local-First Monthly Sync Strategy

## Decision

TrainingOS should use a local-first privacy model.

The complete personal record lives in a local SQLite database. Supabase is an optional cloud layer for monthly minimized summaries, cross-device access, backup, and future collaboration.

```text
Daily use
Garmin / manual input
-> Local SQLite
-> local raw cache

Monthly sync
Local SQLite
-> minimized monthly summary
-> Supabase

After confirmed upload
-> delete raw Garmin cache
-> delete temporary sync package
-> keep local SQLite history
```

## Data Ownership

### Local SQLite

Local SQLite is the complete source of truth for the individual user.

It may store:

- planned sessions;
- completed sessions;
- set logs;
- PR records;
- corrected Garmin activity data;
- normalized daily recovery metrics;
- AI reviews and decision notes;
- sync history.

### Local Raw Cache

Raw cache is temporary and should be cleared regularly.

It may include:

- raw Garmin JSON;
- temporary activity exports;
- provider response snapshots;
- generated sync packages before upload.

Recommended retention:

```text
Raw Garmin cache: 30 days
Temporary sync packages: delete after successful upload
Garmin tokens: keep locally while needed, never commit
```

### Supabase

Supabase stores minimized monthly summaries, not raw personal data by default.

Recommended cloud fields:

- month;
- training days;
- session count by type;
- exercise-level total sets;
- exercise-level total volume;
- best set per exercise;
- PR count;
- estimated 1RM trend;
- average sleep duration;
- average HRV or HRV status count;
- average resting heart rate;
- average stress score;
- average Body Battery if available;
- AI monthly summary;
- next-month focus.

Default excluded cloud data:

- Garmin raw JSON;
- Garmin tokens;
- Garmin user ID;
- device identifiers;
- GPS routes;
- minute-level heart-rate series;
- private notes;
- raw ChatGPT prompts containing personal details.

## Monthly Sync Flow

1. Read the local SQLite database.
2. Build a monthly summary from normalized records.
3. Remove direct identifiers and private notes.
4. Save a temporary sync package locally.
5. Upload the minimized package to Supabase.
6. Record sync success in local SQLite.
7. Delete the temporary sync package.
8. Delete raw Garmin cache older than the retention window.

## Failure Handling

If upload fails:

- keep the temporary sync package locally;
- mark the sync batch as `failed`;
- do not delete raw cache for that month yet;
- retry later with the same batch id.

If Garmin import fails:

- keep the previous successful normalized records;
- create a local import failure record;
- use manual recovery entry as fallback for the next training decision.

## Git Rules

GitHub should contain only reusable project assets:

- docs;
- scripts;
- schema;
- test fixtures with fake data;
- sample configuration templates.

GitHub should not contain:

- local SQLite databases;
- raw Garmin exports;
- OAuth tokens;
- real workout results;
- sync packages;
- personal AI analysis.

## MVP Acceptance Criteria

The privacy-aware sync MVP is successful when:

- daily use works without uploading data;
- local SQLite stores normalized training and recovery history;
- one monthly minimized summary can be generated;
- the summary can be uploaded to Supabase;
- raw Garmin cache older than the retention window is deleted after successful sync;
- no private data appears in Git status.
