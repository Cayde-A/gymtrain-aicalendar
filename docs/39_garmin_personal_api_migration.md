# Garmin Personal API Migration

## Decision

TrainingOS uses a split Garmin integration:

```text
Garmin Connect Personal API (official, pull only)
  -> recovery metrics, activities, activity details, FIT downloads

python-garminconnect (compatibility write provider)
  -> workout upload, scheduling, replacement, and device push
```

The official Personal API is the preferred read provider whenever a Personal
API key is configured. The legacy provider remains a temporary read fallback
and the current write provider because Personal access does not include the
Training API.

## Provider Selection

`GARMIN_READ_PROVIDER` accepts:

- `auto`: prefer Personal API when a key is available, otherwise use legacy;
- `personal`: require the official Personal API;
- `legacy`: force the existing Garmin Connect transport.

The default is `auto`.

## Authentication

Create a Personal API key in Garmin Connect Web. Store it in one of these
locations:

1. `~/.config/garmin/connect-personal-api-key`;
2. a file selected by `GARMIN_PERSONAL_API_KEY_FILE`;
3. `GARMIN_PERSONAL_API_KEY` in the local environment.

The key and bearer-token cache are credentials. They must not be committed,
uploaded to Supabase, included in AI packets, or written to debug events.
Restrict credential files to the local user (`chmod 600` on POSIX systems).

The Garmin client exchanges the key for a 24-hour bearer token and caches it at
`~/.config/garmin/connect-personal-api-bearer-token.json` by default. Personal
API keys expire after the period selected in Garmin Connect and must be rotated
before expiry.

## Supported Read Capabilities

- daily summaries;
- sleep;
- HRV;
- Body Battery;
- stress, steps, heart rate, and calories through daily health responses;
- activity search and details;
- summarized strength exercise sets when supplied by activity details;
- associated workout metadata;
- original activity ZIP/FIT download capability.

The current Personal API does not expose a dedicated Training Readiness or
Recovery Time endpoint. TrainingOS first imports all supported official fields,
then uses an existing local `python-garminconnect` token only to fill missing
Training Readiness data. Hybrid records carry both source names. If the legacy
token is absent or expired, those normalized fields remain nullable; TrainingOS
reports coverage rather than inventing Garmin values.

## Stable TrainingOS Boundary

Changing Garmin transports must not change:

- SQLite table shapes;
- normalized recovery and completed-session records;
- weight/repetition correction rules;
- same-day grouping;
- PR calculation;
- AI trigger policy;
- workout push quality gates.

Every imported record stores `source_tool` so parity and regressions can be
audited without storing raw personal values in logs.

## Migration Gate

Before disabling legacy reads:

1. compare seven recovery days through both providers;
2. compare the two most recent Strength activities;
3. confirm set count, active sets, repetitions, exercise identity, and weight;
4. confirm gram-to-kilogram normalization still applies correctly;
5. verify idempotent reimport into local SQLite;
6. run one midnight pipeline without Garmin writes;
7. keep legacy read fallback until all checks pass.

If summarized sets are incomplete, download the official activity file and add
a FIT parser behind the same activity-normalization boundary. Do not bypass the
correction and data-quality workflow.

## Write Path

Personal API clients are read-only. `scripts/garmin_workout_push.py` therefore
continues to use the compatibility write provider and its existing
idempotency, confirmation, retry, schedule read-back, and audit controls.

A future multi-user product should request Garmin Starter or Enterprise access
and implement the official Training API as a separate write adapter. It must
not reuse a user's Personal API key for other users.

## References

- Garmin Personal API: <https://developer.garmin.com/gc-developer-program/personal/personal-api/>
- Garmin Personal API FAQ: <https://developer.garmin.com/gc-developer-program/personal/personal-faq>
- Garmin Personal API Swagger: <https://developer.garmin.com/gc-developer-program/personal/swagger-docs/>
- Official Python client: <https://github.com/garmin/connect-personal-api-python>
