# Database Schema Draft

This schema is a first draft for a local-first TrainingOS database.

The MVP should use local SQLite as the complete private source of truth. Supabase should initially receive only monthly minimized summaries.

The SQL below is written in PostgreSQL style for clarity and future Supabase compatibility. The same entities should be mirrored in SQLite with practical local types during MVP implementation.

## Entity Overview

```text
athletes
training_blocks
workout_templates
planned_sessions
completed_sessions
exercise_catalog
set_logs
pr_records
pipeline_runs
garmin_write_operations
daily_recovery_metrics
daily_sleep_metrics
daily_hrv_metrics
daily_energy_metrics
daily_vitals_metrics
daily_readiness_metrics
body_metrics
calendar_events
ai_reviews
raw_import_cache
monthly_sync_batches
cloud_monthly_summaries
privacy_retention_policies
```

## Draft SQL

```sql
create table athletes (
  id uuid primary key default gen_random_uuid(),
  display_name text not null,
  timezone text not null default 'Australia/Sydney',
  goal_body_weight_min_kg numeric,
  goal_body_weight_max_kg numeric,
  created_at timestamptz not null default now()
);

create table exercise_catalog (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  local_name text,
  category text not null,
  primary_muscle text,
  equipment text,
  location text,
  garmin_category text,
  garmin_exercise_name text,
  venue_availability_status text not null default 'unknown',
  verification_level text not null default 'unverified',
  verification_source text,
  last_verified_on date,
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

create unique index exercise_catalog_garmin_pair_idx
on exercise_catalog (garmin_category, garmin_exercise_name)
where garmin_category is not null and garmin_exercise_name is not null;

create table training_blocks (
  id uuid primary key default gen_random_uuid(),
  athlete_id uuid not null references athletes(id),
  name text not null,
  version text not null,
  start_date date,
  end_date date,
  goal text,
  created_at timestamptz not null default now()
);

create table workout_templates (
  id uuid primary key default gen_random_uuid(),
  training_block_id uuid not null references training_blocks(id),
  name text not null,
  week_label text,
  day_type text not null,
  template_notes text,
  created_at timestamptz not null default now()
);

create table planned_sessions (
  id uuid primary key default gen_random_uuid(),
  athlete_id uuid not null references athletes(id),
  workout_template_id uuid references workout_templates(id),
  planned_start timestamptz not null,
  planned_end timestamptz,
  status text not null default 'planned',
  location text,
  calendar_event_id text,
  created_at timestamptz not null default now()
);

create table completed_sessions (
  id uuid primary key default gen_random_uuid(),
  planned_session_id uuid references planned_sessions(id),
  athlete_id uuid not null references athletes(id),
  provider text,
  source_tool text,
  external_activity_id text,
  started_at timestamptz,
  completed_at timestamptz not null default now(),
  session_type text not null,
  readiness_notes text,
  fatigue_rating integer check (fatigue_rating between 1 and 10),
  pain_notes text,
  overall_rpe numeric,
  created_at timestamptz not null default now()
);

create table set_logs (
  id uuid primary key default gen_random_uuid(),
  completed_session_id uuid not null references completed_sessions(id),
  exercise_id uuid not null references exercise_catalog(id),
  set_order integer not null,
  set_type text not null,
  weight_kg numeric,
  reps integer,
  rpe numeric,
  is_top_set boolean not null default false,
  estimated_1rm_kg numeric generated always as (
    case
      when weight_kg is not null and reps is not null
      then weight_kg * (1 + reps::numeric / 30)
      else null
    end
  ) stored,
  notes text,
  created_at timestamptz not null default now()
);

create table pr_records (
  id uuid primary key default gen_random_uuid(),
  athlete_id uuid not null references athletes(id),
  exercise_id uuid not null references exercise_catalog(id),
  completed_session_id uuid references completed_sessions(id),
  set_log_id uuid references set_logs(id),
  pr_type text not null,
  weight_kg numeric not null,
  reps integer,
  estimated_1rm_kg numeric,
  achieved_at timestamptz not null,
  created_at timestamptz not null default now()
);

create table daily_recovery_metrics (
  id uuid primary key default gen_random_uuid(),
  athlete_id uuid not null references athletes(id),
  metric_date date not null,
  provider text not null default 'garmin',
  source_tool text,
  sleep_score numeric,
  sleep_duration_minutes integer,
  hrv_status text,
  resting_heart_rate integer,
  body_battery integer,
  stress_score numeric,
  training_readiness numeric,
  recovery_time_hours numeric,
  steps integer,
  calories integer,
  raw_payload jsonb,
  created_at timestamptz not null default now(),
  unique (athlete_id, metric_date, provider)
);

create table body_metrics (
  id uuid primary key default gen_random_uuid(),
  athlete_id uuid not null references athletes(id),
  metric_date date not null,
  body_weight_kg numeric,
  body_fat_percent numeric,
  waist_cm numeric,
  chest_cm numeric,
  hip_cm numeric,
  arm_cm numeric,
  leg_cm numeric,
  notes text,
  created_at timestamptz not null default now()
);

create table calendar_events (
  id uuid primary key default gen_random_uuid(),
  planned_session_id uuid references planned_sessions(id),
  provider text not null default 'google_calendar',
  external_event_id text not null,
  sync_status text not null default 'pending',
  last_synced_at timestamptz,
  created_at timestamptz not null default now(),
  unique (provider, external_event_id)
);

create table ai_reviews (
  id uuid primary key default gen_random_uuid(),
  completed_session_id uuid references completed_sessions(id),
  planned_session_id uuid references planned_sessions(id),
  review_type text not null default 'post_workout',
  decision text not null,
  summary text,
  next_target jsonb,
  risk_flags jsonb,
  created_at timestamptz not null default now()
);

create table pipeline_runs (
  id uuid primary key default gen_random_uuid(),
  athlete_id uuid not null references athletes(id),
  source_training_date date not null,
  target_date date not null,
  status text not null,
  review_id uuid references ai_reviews(id),
  plan_json jsonb,
  quality_report_json jsonb,
  garmin_payload_path text,
  push_result_path text,
  error_json jsonb,
  idempotency_key text not null unique,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table garmin_write_operations (
  id uuid primary key default gen_random_uuid(),
  athlete_id uuid not null references athletes(id),
  idempotency_key text not null unique,
  payload_hash text not null,
  workout_name text not null,
  schedule_date date not null,
  status text not null default 'pending',
  phase text not null default 'created',
  workout_id bigint,
  workout_schedule_id bigint,
  attempt_count integer not null default 0,
  next_retry_at timestamptz,
  last_error_json jsonb,
  result_json jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table raw_import_cache (
  id uuid primary key default gen_random_uuid(),
  athlete_id uuid not null references athletes(id),
  provider text not null,
  import_type text not null,
  source_date date,
  local_path text,
  payload_hash text,
  retention_until date not null,
  deleted_at timestamptz,
  created_at timestamptz not null default now()
);

create table monthly_sync_batches (
  id uuid primary key default gen_random_uuid(),
  athlete_id uuid not null references athletes(id),
  sync_month date not null,
  status text not null default 'pending',
  summary_payload_hash text,
  uploaded_at timestamptz,
  error_message text,
  created_at timestamptz not null default now(),
  unique (athlete_id, sync_month)
);

create table cloud_monthly_summaries (
  id uuid primary key default gen_random_uuid(),
  athlete_id uuid not null references athletes(id),
  sync_batch_id uuid references monthly_sync_batches(id),
  sync_month date not null,
  training_days integer,
  session_count integer,
  session_type_counts jsonb,
  exercise_volume_summary jsonb,
  best_sets jsonb,
  pr_count integer,
  estimated_1rm_trends jsonb,
  recovery_summary jsonb,
  ai_monthly_summary text,
  next_month_focus text,
  created_at timestamptz not null default now(),
  unique (athlete_id, sync_month)
);

create table privacy_retention_policies (
  id uuid primary key default gen_random_uuid(),
  athlete_id uuid not null references athletes(id),
  raw_cache_retention_days integer not null default 30,
  delete_sync_package_after_upload boolean not null default true,
  upload_raw_garmin_payloads boolean not null default false,
  upload_private_notes boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
```

## Categorized Daily Health Model

`daily_recovery_metrics` remains the stable, compact contract consumed by the
planning, quality-gate, and Garmin-push pipeline. Richer Garmin fields are
stored separately so that provider schema growth does not destabilize that
contract:

| Table | Responsibility | Example fields |
|---|---|---|
| `daily_sleep_metrics` | Sleep composition and sleep physiology | deep/light/REM/awake minutes, sleep SpO2, respiration |
| `daily_hrv_metrics` | HRV trend and personal baseline | last-night average, weekly average, baseline range |
| `daily_energy_metrics` | Movement and energy state | Body Battery range/charge/drain, calories, steps, floors, intensity minutes |
| `daily_vitals_metrics` | Daily cardiovascular and respiratory state | heart rate, stress, respiration, pulse ox |
| `daily_readiness_metrics` | Garmin readiness factors | score, level, factor percentages, short feedback |

All six daily tables use the same idempotency key:

```text
(athlete_id, metric_date, provider)
```

Detailed daily health rows remain local by default. The monthly Supabase
package continues to receive only allowlisted aggregate summaries.

## Local-First Privacy Rules

- Local SQLite stores complete private training and recovery history.
- Supabase stores monthly minimized summaries by default.
- Raw Garmin payloads stay local and temporary.
- Sync packages are deleted after successful upload.
- Tokens, local databases, raw exports, and real workout data are ignored by Git.

## Open Schema Questions

- Whether nutrition should be in V5 or delayed to V6.
- Whether Gunyama-specific equipment should be a separate table or metadata in `exercise_catalog`.
- Whether planned exercises need a separate `planned_exercises` table before MVP.
- Monthly sync includes allowlisted exercise-level sets, volume, best sets, and
  e1RM trends by default; raw sets, activity IDs, notes, and body metrics remain
  local.
