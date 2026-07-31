# Test Run: 2026-08-01 Garmin Retry

## Test Type

Garmin login/import retry.

## Result

Blocked by Garmin SSO rate limiting.

## Observed Result

```text
Garmin error: 429 Too Many Requests
Endpoint: sso.garmin.com/sso/signin
Token cache present: no
.env.local present: yes
```

## Interpretation

The local credentials file exists, but TrainingOS cannot create the first Garmin token cache yet because Garmin is still rejecting password login attempts.

This is not a TrainingOS schema or JSON output failure. It is an authentication rate-limit state.

## Decision

Do not continue repeated password login tests during this rate-limit window.

Next valid test should be:

```text
Wait for rate limit to clear
-> run one Garmin import
-> confirm tokens/garmin/oauth1_token.json
-> confirm tokens/garmin/oauth2_token.json
-> subsequent imports reuse tokens instead of password login
```

## Next Command

After waiting:

```bash
.venv/bin/python scripts/garmin_import.py --days 3 --include-raw
```

Expected success output:

```text
Wrote 3 normalized Garmin daily records.
Schema summary: exports/garmin/normalized/raw_schema_summary.json
```

Expected token files:

```text
tokens/garmin/oauth1_token.json
tokens/garmin/oauth2_token.json
```

