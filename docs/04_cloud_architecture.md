# Cloud Architecture Proposal

## Target Architecture

```text
Garmin Epix Gen 2
        |
Garmin Connect
        |
Garmin Provider Sync
        |
Local SQLite  <---- Mobile/Web Logging App
        |
        +---- AI Coach
        |
        +---- Monthly Minimized Sync
                 |
                 +---- Supabase PostgreSQL
                 |
                 +---- Google Calendar Sync / Dashboard
```

## Core Decision

Local SQLite should be the default source of truth for private personal data.

Supabase should be an optional cloud layer for monthly minimized summaries, backup, cross-device access, and future collaboration.

Garmin, Google Calendar, mobile input, Supabase, and AI are all providers or consumers around the local-first data model.

## Components

### Local SQLite

Responsibilities:

- complete private workout plans;
- completed sessions;
- set-level logs;
- PR history;
- normalized Garmin daily metrics;
- AI recommendations and decision notes;
- sync status and retention state.

Local SQLite is not committed to Git.

### Supabase

Responsibilities:

- optional account and settings;
- monthly minimized training summaries;
- monthly recovery summaries;
- approved AI monthly summaries;
- cross-device backup and dashboard data.

Supabase should not store Garmin raw payloads, OAuth tokens, device identifiers, or private notes by default.

### Garmin

Responsibilities:

- sleep;
- HRV;
- resting heart rate;
- Body Battery;
- stress;
- training readiness;
- recovery time;
- calories;
- steps;
- workout heart rate summaries.

Garmin should be normalized into TrainingOS tables instead of becoming the database.

Garmin should execute and record workouts, but TrainingOS should generate the planned training rounds before training. This avoids relying on the watch to choose or correct exact gym equipment names during the session.

Initial Garmin ingestion should combine reusable open-source tools behind a provider boundary:

- `python-garminconnect` as the primary API wrapper;
- `GarminDB` as local database and schema reference;
- `garmin-data-export` as the LLM-friendly full/incremental export bridge;
- `garmin-connect-export` as an activity CSV/GPX/TCX fallback.

See [Garmin Provider Strategy](08_garmin_provider_strategy.md).

### Mobile/Web Logging App

Responsibilities:

- show today's workout;
- show last performance and target;
- show TrainingOS-generated training rounds before the workout;
- log or correct sets quickly after completion;
- support manual entry first;
- later support voice entry;
- later explore automatic prompts from rest detection or media pause.

If Garmin's built-in Strength activity is sufficient, the mobile/web app can start as a review and correction surface rather than the primary set-entry surface.

### Google Calendar

Responsibilities:

- planned workout events;
- reminders;
- optional completed workout summary;
- calendar visibility for long-term consistency.

### AI Coach

Responsibilities:

- calculate PR status;
- explain performance changes;
- recommend next targets;
- flag fatigue;
- suggest deload;
- generate weekly and monthly reports.

For MVP, AI review can be triggered through Apple Shortcuts and the ChatGPT app. For reliable V6 automation, AI review should run through a backend API workflow and save results first to local SQLite, then optionally to Supabase as a minimized monthly summary.

## Data Flow

### Planned Workout

```text
Garmin Recovery + PR History -> AI Coach -> Local SQLite Planned Rounds -> User
```

### Completed Workout

```text
Mobile/Web Log -> Local SQLite -> PR Calculation -> AI Review -> Next Target
```

### Garmin Recovery

```text
Garmin -> Provider Sync -> Local SQLite -> AI Readiness Context
```

### Calendar Update

```text
Completed Session -> Summary Formatter -> Optional Google Calendar Event Update
```

### Monthly Cloud Sync

```text
Local SQLite
-> Monthly minimized summary
-> Supabase
-> Delete temporary sync package
-> Delete raw Garmin cache beyond retention window
```

## MVP Architecture

The MVP does not need native iOS development.

Recommended MVP:

- local SQLite database;
- simple mobile-friendly web app;
- TrainingOS-generated planned training rounds;
- manual workout correction/logging;
- manually imported or generated ICS;
- Garmin data import through the approved provider stack, with manual entry as fallback;
- AI review through exported summary.

This tests the experience before investing in native notifications, watch integrations, or background media detection.

Supabase should be introduced after the local loop works, starting with monthly minimized summaries rather than full raw data sync.
