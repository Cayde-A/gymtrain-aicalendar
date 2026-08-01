# Cloud Architecture Proposal

## Target Architecture

```text
Garmin Epix Gen 2
        |
Garmin Connect
        |
Garmin Provider Sync
        |
Supabase PostgreSQL  <---- Mobile/Web Logging App
        |
        +---- Google Calendar Sync
        |
        +---- Dashboard
        |
        +---- AI Coach
```

## Core Decision

Supabase should become the single source of truth.

Garmin, Google Calendar, mobile input, and AI are all providers or consumers around the database.

## Components

### Supabase

Responsibilities:

- users and settings;
- workout plans;
- completed sessions;
- set-level logs;
- PR history;
- Garmin daily metrics;
- body metrics;
- AI recommendations.

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

For MVP, AI review can be triggered through Apple Shortcuts and the ChatGPT app. For reliable V6 automation, AI review should run through a backend API workflow and save results directly to Supabase.

## Data Flow

### Planned Workout

```text
Garmin Recovery + PR History -> AI Coach -> Supabase Planned Rounds -> User
```

### Completed Workout

```text
Mobile/Web Log -> Supabase -> PR Calculation -> AI Review -> Next Target
```

### Garmin Recovery

```text
Garmin -> Provider Sync -> Supabase -> AI Readiness Context
```

### Calendar Update

```text
Completed Session -> Summary Formatter -> Google Calendar Event Update
```

## MVP Architecture

The MVP does not need native iOS development.

Recommended MVP:

- Supabase database;
- simple mobile-friendly web app;
- TrainingOS-generated planned training rounds;
- manual workout correction/logging;
- manually imported or generated ICS;
- Garmin data import through the approved provider stack, with manual entry as fallback;
- AI review through exported summary.

This tests the experience before investing in native notifications, watch integrations, or background media detection.
