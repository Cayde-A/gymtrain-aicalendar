# Local Dashboard

The TrainingOS PWA opens on a read-only operational dashboard at:

```text
http://127.0.0.1:8787/
```

The separate training-day list remains available at `/training`.

## Dashboard Sections

- rolling 30-day training days, sessions, working sets, volume, PR records, and
  missing rep/weight count;
- latest available sleep score, Body Battery, training readiness, and body
  weight;
- current eight-week program week and phase;
- ten most recently updated estimated-1RM PR states;
- ten recent training days;
- five recent daily pipeline outcomes with target muscle group and recovery
  adjustment.

## Read-Only Boundary

Opening the dashboard does not:

- import Garmin data;
- create a new program cycle;
- call AI;
- create a plan;
- push Garmin or Calendar data;
- update body metrics or training records.

It reads normalized local tables and excludes free-text notes, credentials, raw
payload paths, and external activity identifiers. Dynamic dashboard responses
are network-first and are not placed in the PWA cache.
