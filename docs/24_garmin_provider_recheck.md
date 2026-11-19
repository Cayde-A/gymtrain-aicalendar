# Garmin Provider Failure Recheck

## Command

Inspect versions, token availability, authentication, and capabilities without
network reads:

```bash
.venv-garmin/bin/python scripts/garmin_provider_recheck.py
```

Run the smallest live path through the official Personal API, compatibility provider, and gccli:

```bash
.venv-garmin/bin/python scripts/garmin_provider_recheck.py \
  --date YYYY-MM-DD \
  --live
```

Each live transport reads one daily summary and one activity list. The report
stores only result types, field/record counts, structured errors, and a
recommendation. It does not store metric values, activity IDs, or account
identifiers.

## Recommendation Matrix

| Condition | Action |
|---|---|
| Personal API and fallback healthy | Continue Personal API primary |
| Personal API unavailable, legacy healthy | Use temporary legacy read fallback |
| Personal and legacy unavailable, gccli healthy | Use gccli for reads only |
| Personal authentication fails | Check API key, expiry, and bearer-token cache |
| Rate limit | Wait; do not repeatedly login or retry |
| Schema error | Check same-source release/issues and patch adapter only |
| Both live reads fail | Check Garmin outage, then use export fallback |

`gccli` workout upload/schedule remains disabled regardless of read fallback.

## Same-Source Review Checklist

When a probe fails, record the structured error and review the affected source
before replacing it:

1. Check the installed version in the report.
2. Check the source's latest release and changelog.
3. Search open and closed issues for the exact error and endpoint.
4. Review recent authentication, OAuth, `garth`, `curl_cffi`, and schema changes.
5. Re-run login only for an authentication error, never for rate limiting.
6. Re-run the smallest live probe.
7. Patch only the provider adapter and preserve normalized table shapes.
8. Use the other approved read transport or historical export if unresolved.

Primary sources:

- `https://github.com/garmin/connect-personal-api-python`
- `https://github.com/cyberjunky/python-garminconnect`
- `https://github.com/bpauli/gccli`

## Verified Result

On 2026-10-04, `python-garminconnect 0.3.17` and `gccli 1.10.0` both passed the
daily-summary and activity-list probes. Both summaries exposed 94 top-level
fields, and the recommendation was `continue_primary`.

On 2026-11-19, the official Personal API client `1.0.0` was installed and its
read capabilities were covered by local adapter tests. A live Personal API
probe remains pending until the user creates a Personal API key; until then the
report recommends `use_legacy_read_fallback`.
