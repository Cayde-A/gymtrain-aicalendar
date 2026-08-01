# TrainingOS

TrainingOS is a personal training platform project for turning a static fitness plan into a long-term, data-driven training system.

The project starts from TrainingOS V4: a PR-centered training methodology with Google Calendar/ICS scheduling and manual training follow-up. It then evolves toward V5/V6: a cloud-backed system using Supabase, Garmin data, mobile training capture, dashboards, and AI coaching.

## Project Goals

- Keep the training plan usable in real life, especially during fat loss.
- Use PR and estimated 1RM trends as the main performance signal.
- Keep training weights dynamic instead of hardcoded into the calendar.
- Use Google Calendar/ICS for reminders and training structure.
- Use a single database as the long-term source of truth.
- Integrate Garmin as a physiology data provider, not as the core database.
- Build toward an AI-assisted training loop that can adjust future sessions.

## Project Map

- [Vision and Goals](docs/01_vision_goals.md)
- [V4 PR Training Methodology](docs/02_v4_training_methodology.md)
- [Google Calendar and ICS Integration](docs/03_calendar_ics_integration.md)
- [Cloud Architecture Proposal](docs/04_cloud_architecture.md)
- [Database Schema Draft](docs/05_database_schema_draft.md)
- [Roadmap V4 to V6](docs/06_roadmap_v4_to_v6.md)
- [MVP Implementation Plan](docs/07_mvp_implementation_plan.md)
- [Garmin Provider Strategy](docs/08_garmin_provider_strategy.md)
- [Garmin, Shortcuts, and ChatGPT Usage Flow](docs/09_usage_flow_garmin_shortcuts_chatgpt.md)
- [Garmin Auto Import Plan](docs/10_garmin_auto_import_plan.md)
- [Garmin Import MVP](docs/11_garmin_import_mvp.md)
- [Garmin Field Mapping](docs/12_garmin_field_mapping.md)
- [Backlog](BACKLOG.md)
- [Artifacts](artifacts/README.md)
- [Changelog](CHANGELOG.md)

## Current Baseline

Current version: `V4.0 Project Baseline`

V4 should be treated as the first testable operating model:

1. Google Calendar provides the weekly training structure.
2. Each workout follows PR-centered dynamic progression.
3. Workout results are captured after each session.
4. AI reviews session data and recommends the next adjustment.
5. Garmin data is considered recovery context, initially manual or exported.

## Running tests

Unit tests are located in `tests/`.

From the repository root run:

```bash
python3 -m unittest discover -s tests
```
