# Roadmap V4 to V6

## V4: Training Method and Calendar

Goal: make the current plan usable and measurable.

Milestones:

- V4.0: Project baseline and documentation.
- V4.1: Finalize weekly training structure.
- V4.2: Generate ICS calendar templates.
- V4.3: Define post-workout logging template.
- V4.4: Add PR tracking and estimated 1RM review process.
- V4.5: Run 2-4 weeks of real-world testing.

Exit criteria:

- Calendar works on mobile.
- User can follow sessions without editing the plan each time.
- Completed workout data can be reviewed consistently.
- AI can recommend next-session progression.

## V5: Local-First Database

Goal: move from notes and calendar fields into a structured source of truth.

Milestones:

- V5.0: Build local SQLite as the complete private source of truth.
- V5.1: Build workout log and PR database on top of SQLite.
- V5.2: Add Garmin import fields.
- V5.3: Add dashboard for strength, recovery, and body metrics.
- V5.4: Add monthly minimized summary report.
- V5.5: Add automatic progression suggestions.
- V5.6: Add Apple Shortcut for post-workout ChatGPT review.
- V5.7: Generate morning preset training rounds from Garmin recovery and PR history.
- V5.8: Add local raw-cache retention and cleanup.

Exit criteria:

- Set-level data is structured.
- PRs are detected automatically.
- Recovery metrics can be compared with performance.
- Calendar no longer carries the burden of historical data.

## V6: Privacy-Aware Cloud TrainingOS

Goal: add cloud capabilities without making raw personal data the default cloud record.

Milestones:

- V6.0: Supabase monthly summary schema and authentication.
- V6.1: Mobile-friendly workout logging app.
- V6.2: Google Calendar API sync.
- V6.3: Garmin provider sync.
- V6.4: AI post-workout review and next-target generation.
- V6.5: Dashboard.
- V6.6: Voice input experiment.
- V6.7: Rest-detection or media-pause prompt experiment.
- V6.8: Move next-day training generation to backend automation.
- V6.9: Export approved planned rounds into Garmin-compatible workout structure if feasible.
- V6.10: Add monthly minimized Supabase sync and post-sync cache cleanup.

Exit criteria:

- Today's workout appears automatically.
- Today's training rounds are generated before training.
- Each set can be logged quickly on mobile.
- Garmin recovery context is attached to the session.
- Calendar is updated after completion.
- AI produces actionable next targets.
- Monthly cloud sync works without uploading raw Garmin payloads or private notes.
