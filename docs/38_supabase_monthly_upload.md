# Supabase Monthly Upload

TrainingOS can upload only the approved monthly summary package to Supabase. Complete workout history, raw Garmin payloads, free-text notes, body measurements, credentials, and device identifiers remain local.

## Security Model

The local adapter uses:

- a Supabase publishable key;
- a signed-in user's short-lived access token;
- Postgres grants and Row Level Security;
- the remote `auth.users` identity returned by Supabase;
- one row per authenticated user and month.

Do not use a Supabase secret key or legacy `service_role` key. Those credentials bypass RLS and are not appropriate for this local client.

## Remote Schema

Apply [supabase_monthly_summaries.sql](../schema/supabase_monthly_summaries.sql) to the intended Supabase project. It:

- creates `public.trainingos_monthly_summaries`;
- enables RLS;
- revokes all anonymous and authenticated defaults;
- grants authenticated users only select, insert, and update;
- restricts each operation to `auth.uid() = user_id`;
- uses `(user_id, sync_month)` as the idempotency key.

Review the SQL against the project before applying it. Live schema creation requires the user's Supabase project and approval.

## Dry Run

```bash
.venv-garmin/bin/python scripts/trainingos_supabase_sync.py \
  --month YYYY-MM
```

The default path builds and validates the minimized package, records a local pending batch, and makes no network call.

## Authenticated Upload

Provide the project origin, publishable key, and a current user access token through environment variables:

```text
SUPABASE_URL=https://PROJECT_REF.supabase.co
SUPABASE_PUBLISHABLE_KEY=...
SUPABASE_ACCESS_TOKEN=...
```

Then explicitly enable and confirm the write:

```bash
.venv-garmin/bin/python scripts/trainingos_supabase_sync.py \
  --month YYYY-MM \
  --push \
  --confirm
```

The adapter performs this sequence:

1. rebuild and validate the exact allowlisted package;
2. compute its canonical SHA-256;
3. call `/auth/v1/user` to resolve the authenticated user;
4. upsert by `user_id,sync_month` using PostgREST conflict resolution;
5. read back only `sync_month,payload_sha256`;
6. mark the local batch `uploaded` only when the hash matches.
7. when the local retention policy allows it, delete only the temporary package
   whose month and SHA-256 match the confirmed uploaded batch.

Cleanup refuses files outside the configured sync directory, symbolic links,
invalid packages, hash mismatches, and batches without confirmed read-back. A
missing package is harmless and reported as `not_found`.

Failures store only a sanitized local status such as `auth_http_401`, `upload_http_403`, or `readback_hash_mismatch`. Provider response bodies and credentials are not persisted.

## Remaining Live Verification

Automated tests use a fake transport. Provisioning the project, applying the SQL, signing in, repeating an upsert, and confirming RLS isolation require user-owned Supabase credentials and explicit external-write approval.

## Official References

- [Supabase Data REST API](https://supabase.com/docs/guides/api)
- [Supabase API keys](https://supabase.com/docs/guides/getting-started/api-keys)
- [Supabase Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security)
- [Securing the Supabase Data API](https://supabase.com/docs/guides/api/securing-your-api)
