# MVP Implementation Plan

## MVP Goal

Test whether the TrainingOS experience works during real workouts before building deep integrations.

The MVP should answer:

- Is the calendar template usable in the gym?
- Can training data be captured quickly enough?
- Does PR-centered progression improve decision quality?
- Does AI review produce useful next-session targets?
- Which automation is worth building first?

## MVP Scope

Include:

- TrainingOS V4 calendar template.
- Local SQLite database prototype.
- Mobile-friendly workout logging form.
- PR and estimated 1RM calculation.
- Garmin Provider MVP using reusable open-source tools.
- Manual Garmin recovery fields as fallback.
- AI review prompt format.
- Monthly minimized sync package format.
- Weekly review process.

Exclude for first MVP:

- Native iOS app.
- Background music-pause detection.
- Production-grade Garmin API sync.
- Direct raw Garmin cloud upload.
- Full dashboard.
- Nutrition automation.

## MVP Workflow

1. Calendar reminds user of the planned session.
2. User opens the workout template.
3. User completes top set and back-off work.
4. User logs sets, RPE, and notes into local SQLite.
5. Garmin recovery context is imported through the provider MVP or entered manually if import fails.
6. AI reviews the session.
7. Next target is written back into the training record.
8. Calendar can optionally be updated with the session summary.

## Test Period

Recommended test period: 2-4 weeks.

Minimum useful dataset:

- 6-10 strength sessions;
- 2-4 cardio or swimming records;
- daily body weight if available;
- Garmin sleep/recovery context for training days.

## MVP Artifacts

- ICS event template.
- Workout logging template.
- AI review prompt.
- PR calculation rules.
- Weekly review checklist.
- Garmin provider import notes.
- Monthly minimized sync package.
- Usage flow test checklist.

See [Usage Flow Test v0.1](../artifacts/usage_flow_test_v0_1.md).

## Decision Gates

After MVP testing, decide:

- whether monthly Supabase summary sync is useful after local SQLite works;
- whether Google Calendar API sync is necessary;
- whether Garmin sync should be official API, CSV import, or third-party bridge;
- whether the first user interface should be web app, shortcut, or native app.

## Garmin Provider Test

Use this sequence for the MVP:

1. Confirm Garmin account access with `garmin-data-export`.
2. Pull one day of sleep, HRV, Body Battery, stress, and training readiness with `python-garminconnect`.
3. Export recent activities with `garmin-connect-export` for cross-checking.
4. Review GarminDB if local storage or historical import becomes complex.
5. Normalize successful data into the TrainingOS local SQLite schema.

If any source fails, follow the failure and same-source recheck protocol in [Garmin Provider Strategy](08_garmin_provider_strategy.md).
