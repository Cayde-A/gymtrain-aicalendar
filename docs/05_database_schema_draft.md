# Database Schema Draft

This schema is a first draft for Supabase PostgreSQL. It focuses on workout planning, set-level logging, PR tracking, Garmin recovery context, and AI recommendations.

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
daily_recovery_metrics
body_metrics
calendar_events
ai_reviews
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
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

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
  completed_session_id uuid not null references completed_sessions(id),
  review_type text not null default 'post_workout',
  decision text not null,
  summary text,
  next_target jsonb,
  risk_flags jsonb,
  created_at timestamptz not null default now()
);
```

## Open Schema Questions

- Whether nutrition should be in V5 or delayed to V6.
- Whether Gunyama-specific equipment should be a separate table or metadata in `exercise_catalog`.
- Whether planned exercises need a separate `planned_exercises` table before MVP.
- Whether Garmin data will arrive from official API, export, third-party sync, or manual entry first.

