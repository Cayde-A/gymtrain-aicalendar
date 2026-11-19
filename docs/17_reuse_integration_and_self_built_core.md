# Reuse Integration and TrainingOS-Owned Core

## Decision

TrainingOS should reuse transport, export, scheduling, storage, and UI infrastructure. It should own the training domain model and every rule that changes a user's plan.

The integration model is layered rather than merging several Garmin projects into one runtime:

```text
Reusable transports and libraries
  python-garminconnect / future gccli adapter / export fallback
                         |
                         v
TrainingOS Garmin Provider boundary
  authentication + raw reads/writes + capability reporting
                         |
                         v
TrainingOS-owned normalization and quality gates
  field mapping + units + missing reps + duplicate handling
                         |
                         v
TrainingOS-owned domain core
  SQLite + corrections + PR state + planning + trigger policy
                         |
              +----------+----------+
              |                     |
              v                     v
      Garmin workout push       Calendar / AI / cloud summary
```

This keeps one reusable implementation from becoming the data model or training engine.

## Reuse Matrix

| Component | Decision | TrainingOS use | Boundary |
| --- | --- | --- | --- |
| [Garmin Personal API Python](https://github.com/garmin/connect-personal-api-python) | Adopted | Preferred official health/activity reads and FIT download capability | Read adapter in `scripts/garmin_provider.py` |
| [python-garminconnect](https://github.com/cyberjunky/python-garminconnect) | Adopted compatibility layer | Workout writes and temporary read fallback | Write adapter in `scripts/garmin_provider.py` |
| [gccli](https://github.com/bpauli/gccli) | Adapter spike next | JSON CLI, OS keychain, exercise catalog, workout upload/schedule | Subprocess adapter returning normalized JSON; do not call it from planner rules |
| [garmin_mcp](https://github.com/Taxuspt/garmin_mcp) | Development tool | Interactive endpoint inspection and independent result checks | Local debugging only; not the scheduled production path |
| [garmin-data-export](https://github.com/sirredbeard/garmin-data-export) | Fallback | Initial historical backfill and recovery when incremental API access breaks | Import exported files through a TrainingOS parser |
| GarminDB | Reference only | Schema, incremental import, and local analysis patterns | Do not copy GPL code into this repository |
| garmin-connect-export | Fallback/reference | Activity CSV/GPX/TCX cross-check | Treat as a secondary source, not the source of truth |
| SQLite | Adopted | Complete local private source of truth | Access through `trainingos_db.py` |
| `icalendar` + Google Calendar client | Planned reuse | ICS generation and optional Calendar API sync | Calendar adapter; no training decisions |
| APScheduler or OS scheduler | Planned reuse | Midnight sync and plan orchestration | Invoke idempotent TrainingOS commands |
| Supabase client | Planned reuse | Monthly minimized summaries and optional cross-device access | Never upload raw Garmin payloads or credentials |
| OpenAI structured output | Planned reuse | Constrained review and explanation | TrainingOS builds inputs, validates output, and applies policy |
| CasettaFit / FitnessTrack | Pattern reference | Mobile correction UX and progression test ideas | Reimplement against the TrainingOS schema and rules |

## Already Integrated

- Shared Garmin authentication and token selection live in `scripts/garmin_provider.py`.
- Recovery import, completed activity import, and workout push use the shared provider entry.
- The provider reports supported Garmin operation groups and the installed transport version.
- Authentication, reads, upload, schedule, replacement, and device-push failures use structured error codes with retryability metadata.
- `python-garminconnect` is pinned to the supported `0.3.x` line instead of a moving GitHub branch.
- Garmin raw data is normalized before SQLite writes.
- Completed sets pass through explicit field mappings and gram-to-kilogram correction.
- A deterministic data-quality gate blocks analysis or finalization when normalized records are incomplete or abnormal.
- Workout payload generation and Garmin scheduling remain separate from training-plan decisions.

## TrainingOS-Owned Core

The following parts must remain first-party because they encode the product's behavior, user corrections, and safety constraints.

### 1. Canonical data model

Own:

- sessions, sets, recovery metrics, exercise identity, and source provenance;
- same-day activity grouping;
- duplicate-safe imports and correction history;
- local complete record versus minimized cloud summary.

Reason: external tools use different field names, units, and session boundaries. TrainingOS needs a stable model even when a provider changes.

### 2. Garmin normalization and data-quality gates

Own:

- Garmin field-to-domain mappings;
- gram-to-kilogram conversion;
- missing repetition detection;
- unknown exercise handling;
- active-set counts and abnormal-value checks;
- push eligibility when required data is incomplete.

Reason: these rules are specific to observed TrainingOS data and determine whether automated analysis is trustworthy.

### 3. Exercise identity and correction workflow

Own:

- canonical exercise names and aliases;
- user correction UI;
- equipment-specific mapping;
- Garmin exercise catalog mapping and TrainingOS text cues.

Reason: Garmin's labels are execution metadata, not the user's long-term exercise identity.

### 4. PR engine

Own:

- one current best state per exercise and PR type;
- immutable PR history records;
- 1RM, rep-range PR, and estimated 1RM candidate rules;
- update-only-on-improvement behavior;
- recalculation after a user correction.

Reason: PR semantics drive progression and must be deterministic, testable, and independent of AI.

### 5. Training planner

Own:

- one primary large muscle group per session;
- adjacent-day overlap constraints;
- legs priority after chest/shoulder work;
- core insertion without impairing the next primary session;
- recovery-based volume/intensity adjustment;
- two-month program-cycle state and progression rules.

Reason: this is the core TrainingOS methodology and should not be delegated to a generic workout application or an unconstrained model response.

### 6. AI and automation policy

Own:

- compact review packet construction;
- structured response schema and validation;
- manual versus automatic trigger selection;
- daily call limits and idempotency keys;
- final-plan quality gate before Garmin push;
- audit events for import, analysis, replacement, and push.

Reason: the AI explains and proposes; TrainingOS decides whether the proposal can change stored or external state.

### 7. Privacy lifecycle

Own:

- local-first retention rules;
- monthly summary minimization;
- raw cache cleanup only after verified import;
- explicit exclusion of credentials, tokens, device identifiers, raw payloads, and private notes from Git and cloud sync.

Reason: privacy guarantees span every adapter and cannot be inherited from one dependency.

## Integration Contracts

Every Garmin transport adapter must support capability discovery and return one of these stable outputs:

- normalized daily recovery records;
- normalized activity summaries and set logs;
- workout upload, schedule, replace, and optional device-push results;
- structured errors classified as authentication, rate limit, schema, unavailable capability, or provider outage.

An adapter must not:

- write directly to domain tables;
- calculate PRs;
- select the next muscle group;
- call AI;
- push a draft plan without the TrainingOS quality and trigger checks.

## Integration Sequence

### Stage A: split-provider baseline

- Prefer Garmin Personal API for reads when a personal key is configured.
- Keep `python-garminconnect` for writes and temporary read fallback.
- Route all authentication through `garmin_provider.py`.
- Use capability discovery and structured provider errors for scheduler decisions.
- Preserve the current normalizers, correction flow, planner, and push payloads.

### Stage B: Personal API parity gate

- Compare seven recovery days and two Strength activities across both providers.
- Verify completed-set count, repetitions, weight units, and exercise identity.
- Confirm idempotent SQLite reimport and one read-only midnight pipeline run.
- Add official FIT parsing only if activity details omit decision-grade set data.

### Stage C: gccli parity spike

- Authenticate a test account through the OS keychain.
- Compare two recent activities and seven days of recovery data with current normalized output.
- Compare exercise catalog lookup and one dry-run workout payload.
- Adopt gccli for scheduled jobs only after parity and idempotency tests pass.

### Stage D: export fallback

- Add a file-import adapter for historical backfill.
- Record source tool and import timestamp on every record.
- Run the same normalization and quality checks as live imports.

### Stage E: calendar and cloud

- Add Calendar and Supabase adapters after the local training loop is stable.
- Sync only approved plan metadata and minimized monthly summaries.

## Acceptance Criteria

- Changing Garmin transports does not change domain table shapes or planner output.
- Reimporting the same activity is idempotent.
- Weight, reps, exercise identity, and same-day grouping are validated before AI analysis.
- A failed recovery read can produce a draft but cannot silently trigger a final automatic push.
- Every external write has a local audit result and can be traced to a final plan.
- All adopted dependencies have a compatible license and pinned version or reproducible install source.

## License Rule

MIT, BSD, and Apache-2.0 dependencies may be integrated with their notices preserved. GPL or AGPL projects are references unless TrainingOS deliberately adopts the corresponding distribution obligations. Exercise images are not bundled unless each asset has verified provenance and redistribution rights.
