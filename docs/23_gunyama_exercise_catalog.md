# Gunyama Exercise Catalog

## Evidence Boundary

The City of Sydney Leisure page confirms that the Gunyama Park fitness centre
has strength machines, a cardio zone, and free weights:

`https://cityofsydneyleisure.com.au/visit/gunyama-park-aquatic-and-recreation-centre`

It does not publish a machine-by-machine inventory. TrainingOS therefore keeps
two separate facts:

- venue capability: officially confirmed equipment categories;
- exercise availability: a candidate until observed and confirmed by the user.

Brand, model, station count, and exact attachments are not inferred.

## Seeded Catalog

The local catalog contains the 19 movements currently used by the Push, Legs,
Pull, Core A, and Core B presets. Each record includes:

- TrainingOS exercise name and primary muscle;
- required equipment category;
- Garmin category and exercise name;
- venue availability status;
- verification level, source, and date.

Every Garmin category/exercise pair is checked against the installed
`garminconnect` exercise catalog before seeding. Seeding is idempotent and does
not overwrite a previous user availability confirmation.

## Commands

Seed or refresh mappings:

```bash
.venv-garmin/bin/python scripts/gunyama_exercise_catalog.py
```

Confirm an observed station or usable setup:

```bash
.venv-garmin/bin/python scripts/gunyama_exercise_catalog.py \
  --confirm "Leg Press"
```

Record that a planned movement is unavailable:

```bash
.venv-garmin/bin/python scripts/gunyama_exercise_catalog.py \
  --unavailable "Cable Crossover"
```

## Planner Rule

`user_verified` exercises may be selected without a venue warning.
`candidate` exercises may remain in a draft but require confirmation before finalization.
`unavailable` exercises must not appear in a final Gunyama plan.

The first seed on 2026-10-04 created 15 candidate records. The catalog was then
expanded to all 19 preset movements, and all Garmin mappings are validated on
every seed. No specific station is inferred to be available from Garmin support
or the venue's category-level description.
