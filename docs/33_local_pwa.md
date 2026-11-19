# Local PWA Shell

The existing correction Web UI is now a Progressive Web App shell. It keeps the
same local Python server and SQLite database while adding install metadata,
standalone display, an application icon, and an offline fallback.

## Endpoints

- `/manifest.webmanifest`: application name, colors, scope, start URL, and icon;
- `/service-worker.js`: static-shell cache and network policy;
- `/app-icon.svg`: maskable TrainingOS icon;
- `/offline`: value-free offline fallback.

Every rendered page links the manifest and registers the service worker after
load.

## Privacy Cache Policy

The service worker caches only:

```text
/offline
/manifest.webmanifest
/app-icon.svg
```

Navigation to `/`, `/day`, `/session`, `/analysis`, `/body`, `/settings`, and
`/debug` is always network-first. Responses from those pages are never inserted
into Cache Storage. If the local service is unavailable, navigation receives the
static offline page rather than stale private records.

## Installation Boundary

Start the local server and open:

```text
http://127.0.0.1:8787/
```

Browsers treat localhost as a trustworthy origin, so supported desktop browsers
can install the app in standalone mode. Installation on a separate phone
requires serving the same app through a trusted HTTPS origin; exposing the
SQLite service directly over an unauthenticated LAN address is not approved.

The PWA currently remains a correction and review surface. It does not queue
offline writes, because persisting sensitive form data in browser storage would
expand the privacy and conflict-resolution scope.
