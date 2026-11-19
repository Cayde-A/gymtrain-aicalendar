-- TrainingOS local-first SQLite schema.
-- This database stores private training and recovery history locally.

pragma foreign_keys = on;

create table if not exists athletes (
  id text primary key,
  display_name text not null,
  timezone text not null default 'Australia/Sydney',
  goal_body_weight_min_kg real,
  goal_body_weight_max_kg real,
  created_at text not null default current_timestamp
);

create table if not exists exercise_catalog (
  id text primary key,
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
  last_verified_on text,
  is_active integer not null default 1,
  created_at text not null default current_timestamp
);

create table if not exists training_blocks (
  id text primary key,
  athlete_id text not null references athletes(id),
  name text not null,
  version text not null,
  start_date text,
  end_date text,
  goal text,
  created_at text not null default current_timestamp
);

create table if not exists workout_templates (
  id text primary key,
  training_block_id text not null references training_blocks(id),
  name text not null,
  week_label text,
  day_type text not null,
  template_notes text,
  created_at text not null default current_timestamp
);

create table if not exists planned_sessions (
  id text primary key,
  athlete_id text not null references athletes(id),
  workout_template_id text references workout_templates(id),
  planned_start text not null,
  planned_end text,
  status text not null default 'planned',
  location text,
  calendar_event_id text,
  garmin_workout_id text,
  created_at text not null default current_timestamp
);

create table if not exists completed_sessions (
  id text primary key,
  planned_session_id text references planned_sessions(id),
  athlete_id text not null references athletes(id),
  provider text,
  source_tool text,
  external_activity_id text,
  started_at text,
  completed_at text not null,
  session_type text not null,
  activity_name text,
  duration_seconds real,
  average_heart_rate integer,
  max_heart_rate integer,
  calories integer,
  raw_payload_path text,
  readiness_notes text,
  fatigue_rating integer check (fatigue_rating between 1 and 10),
  pain_notes text,
  overall_rpe real,
  created_at text not null default current_timestamp,
  unique (provider, external_activity_id)
);

create table if not exists set_logs (
  id text primary key,
  completed_session_id text not null references completed_sessions(id),
  exercise_id text not null references exercise_catalog(id),
  set_order integer not null,
  set_type text not null,
  weight_kg real,
  reps integer,
  rpe real,
  is_top_set integer not null default 0,
  estimated_1rm_kg real generated always as (
    case
      when weight_kg is not null and reps is not null
      then weight_kg * (1 + reps / 30.0)
      else null
    end
  ) stored,
  notes text,
  created_at text not null default current_timestamp
);

create table if not exists pr_records (
  id text primary key,
  athlete_id text not null references athletes(id),
  exercise_id text not null references exercise_catalog(id),
  completed_session_id text references completed_sessions(id),
  set_log_id text references set_logs(id),
  pr_type text not null,
  weight_kg real not null,
  reps integer,
  estimated_1rm_kg real,
  achieved_at text not null,
  created_at text not null default current_timestamp
);

create table if not exists exercise_pr_state (
  id text primary key,
  athlete_id text not null references athletes(id),
  exercise_id text not null references exercise_catalog(id),
  pr_type text not null,
  best_value real not null,
  weight_kg real not null,
  reps integer,
  estimated_1rm_kg real,
  source_session_id text references completed_sessions(id),
  source_set_log_id text references set_logs(id),
  achieved_at text not null,
  updated_at text not null default current_timestamp,
  unique (athlete_id, exercise_id, pr_type)
);

create table if not exists daily_recovery_metrics (
  id text primary key,
  athlete_id text not null references athletes(id),
  metric_date text not null,
  provider text not null default 'garmin',
  source_tool text,
  sleep_score real,
  sleep_duration_minutes integer,
  hrv_status text,
  resting_heart_rate integer,
  body_battery integer,
  stress_score real,
  training_readiness real,
  recovery_time_hours real,
  steps integer,
  calories integer,
  raw_payload_path text,
  created_at text not null default current_timestamp,
  unique (athlete_id, metric_date, provider)
);

create table if not exists daily_sleep_metrics (
  id text primary key,
  athlete_id text not null references athletes(id),
  metric_date text not null,
  provider text not null default 'garmin',
  source_tool text,
  deep_sleep_minutes integer,
  light_sleep_minutes integer,
  rem_sleep_minutes integer,
  awake_minutes integer,
  nap_minutes integer,
  average_sleep_stress real,
  average_sleep_heart_rate real,
  average_spo2 real,
  minimum_spo2 real,
  maximum_spo2 real,
  average_respiration real,
  minimum_respiration real,
  maximum_respiration real,
  sleep_need_minutes integer,
  created_at text not null default current_timestamp,
  unique (athlete_id, metric_date, provider)
);

create table if not exists daily_hrv_metrics (
  id text primary key,
  athlete_id text not null references athletes(id),
  metric_date text not null,
  provider text not null default 'garmin',
  source_tool text,
  status text,
  weekly_average_ms real,
  last_night_average_ms real,
  last_night_5min_high_ms real,
  baseline_low_upper_ms real,
  baseline_balanced_low_ms real,
  baseline_balanced_upper_ms real,
  baseline_marker real,
  created_at text not null default current_timestamp,
  unique (athlete_id, metric_date, provider)
);

create table if not exists daily_energy_metrics (
  id text primary key,
  athlete_id text not null references athletes(id),
  metric_date text not null,
  provider text not null default 'garmin',
  source_tool text,
  body_battery_min integer,
  body_battery_max integer,
  body_battery_charged integer,
  body_battery_drained integer,
  body_battery_latest integer,
  resting_calories integer,
  active_calories integer,
  total_calories integer,
  steps integer,
  floors_ascended real,
  floors_descended real,
  moderate_intensity_minutes integer,
  vigorous_intensity_minutes integer,
  created_at text not null default current_timestamp,
  unique (athlete_id, metric_date, provider)
);

create table if not exists daily_vitals_metrics (
  id text primary key,
  athlete_id text not null references athletes(id),
  metric_date text not null,
  provider text not null default 'garmin',
  source_tool text,
  heart_rate_min integer,
  heart_rate_max integer,
  heart_rate_resting integer,
  stress_average real,
  stress_maximum real,
  respiration_average real,
  respiration_minimum real,
  respiration_maximum real,
  respiration_latest real,
  pulse_ox_average real,
  pulse_ox_minimum real,
  pulse_ox_latest real,
  created_at text not null default current_timestamp,
  unique (athlete_id, metric_date, provider)
);

create table if not exists daily_readiness_metrics (
  id text primary key,
  athlete_id text not null references athletes(id),
  metric_date text not null,
  provider text not null default 'garmin',
  source_tool text,
  score real,
  level text,
  sleep_score_factor_percent real,
  recovery_time_factor_percent real,
  hrv_factor_percent real,
  acute_load_factor_percent real,
  stress_history_factor_percent real,
  sleep_history_factor_percent real,
  feedback_short text,
  created_at text not null default current_timestamp,
  unique (athlete_id, metric_date, provider)
);

create table if not exists body_metrics (
  id text primary key,
  athlete_id text not null references athletes(id),
  metric_date text not null,
  body_weight_kg real,
  body_fat_percent real,
  waist_cm real,
  chest_cm real,
  hip_cm real,
  arm_cm real,
  leg_cm real,
  notes text,
  created_at text not null default current_timestamp
);

create table if not exists calendar_events (
  id text primary key,
  planned_session_id text references planned_sessions(id),
  provider text not null default 'google_calendar',
  external_event_id text not null,
  sync_status text not null default 'pending',
  last_synced_at text,
  created_at text not null default current_timestamp,
  unique (provider, external_event_id)
);

create table if not exists ai_reviews (
  id text primary key,
  completed_session_id text references completed_sessions(id),
  planned_session_id text references planned_sessions(id),
  review_type text not null default 'post_workout',
  decision text not null,
  summary text,
  next_target_json text,
  risk_flags_json text,
  created_at text not null default current_timestamp
);

create table if not exists raw_import_cache (
  id text primary key,
  athlete_id text not null references athletes(id),
  provider text not null,
  import_type text not null,
  source_date text,
  local_path text,
  payload_hash text,
  retention_until text not null,
  deleted_at text,
  created_at text not null default current_timestamp
);

create table if not exists monthly_sync_batches (
  id text primary key,
  athlete_id text not null references athletes(id),
  sync_month text not null,
  status text not null default 'pending',
  summary_payload_hash text,
  uploaded_at text,
  error_message text,
  created_at text not null default current_timestamp,
  unique (athlete_id, sync_month)
);

create table if not exists cloud_monthly_summaries (
  id text primary key,
  athlete_id text not null references athletes(id),
  sync_batch_id text references monthly_sync_batches(id),
  sync_month text not null,
  training_days integer,
  session_count integer,
  session_type_counts_json text,
  exercise_volume_summary_json text,
  best_sets_json text,
  pr_count integer,
  estimated_1rm_trends_json text,
  recovery_summary_json text,
  ai_monthly_summary text,
  next_month_focus text,
  created_at text not null default current_timestamp,
  unique (athlete_id, sync_month)
);

create table if not exists privacy_retention_policies (
  id text primary key,
  athlete_id text not null references athletes(id),
  raw_cache_retention_days integer not null default 30,
  delete_sync_package_after_upload integer not null default 1,
  upload_raw_garmin_payloads integer not null default 0,
  upload_private_notes integer not null default 0,
  created_at text not null default current_timestamp,
  updated_at text not null default current_timestamp
);

create table if not exists ai_trigger_policies (
  id text primary key,
  athlete_id text not null references athletes(id),
  post_workout_ai_mode text not null default 'manual_copy_paste',
  next_morning_adjustment_mode text not null default 'user_confirmed_api',
  garmin_push_mode text not null default 'user_confirmed',
  auto_api_enabled integer not null default 0,
  max_ai_calls_per_day integer not null default 2,
  created_at text not null default current_timestamp,
  updated_at text not null default current_timestamp
);

create table if not exists api_trigger_logs (
  id text primary key,
  athlete_id text not null references athletes(id),
  trigger_name text not null,
  mode text not null,
  status text not null,
  reason text,
  context_json text,
  created_at text not null default current_timestamp
);

create table if not exists pipeline_runs (
  id text primary key,
  athlete_id text not null references athletes(id),
  source_training_date text not null,
  target_date text not null,
  status text not null,
  review_id text references ai_reviews(id),
  plan_json text,
  quality_report_json text,
  garmin_payload_path text,
  push_result_path text,
  error_json text,
  idempotency_key text not null unique,
  created_at text not null default current_timestamp,
  updated_at text not null default current_timestamp
);

create table if not exists garmin_write_operations (
  id text primary key,
  athlete_id text not null references athletes(id),
  idempotency_key text not null unique,
  payload_hash text not null,
  workout_name text not null,
  schedule_date text not null,
  status text not null default 'pending',
  phase text not null default 'created',
  workout_id integer,
  workout_schedule_id integer,
  attempt_count integer not null default 0,
  next_retry_at text,
  last_error_json text,
  result_json text,
  created_at text not null default current_timestamp,
  updated_at text not null default current_timestamp
);

create index if not exists idx_planned_sessions_athlete_start
  on planned_sessions (athlete_id, planned_start);

create index if not exists idx_completed_sessions_athlete_completed
  on completed_sessions (athlete_id, completed_at);

create index if not exists idx_set_logs_session_order
  on set_logs (completed_session_id, set_order);

create index if not exists idx_pr_records_exercise_type
  on pr_records (athlete_id, exercise_id, pr_type);

create index if not exists idx_exercise_pr_state_exercise
  on exercise_pr_state (athlete_id, exercise_id);

create index if not exists idx_daily_recovery_athlete_date
  on daily_recovery_metrics (athlete_id, metric_date);

create index if not exists idx_daily_sleep_athlete_date
  on daily_sleep_metrics (athlete_id, metric_date);

create index if not exists idx_daily_hrv_athlete_date
  on daily_hrv_metrics (athlete_id, metric_date);

create index if not exists idx_daily_energy_athlete_date
  on daily_energy_metrics (athlete_id, metric_date);

create index if not exists idx_daily_vitals_athlete_date
  on daily_vitals_metrics (athlete_id, metric_date);

create index if not exists idx_daily_readiness_athlete_date
  on daily_readiness_metrics (athlete_id, metric_date);

create index if not exists idx_raw_import_cache_retention
  on raw_import_cache (retention_until, deleted_at);

create index if not exists idx_api_trigger_logs_athlete_created
  on api_trigger_logs (athlete_id, created_at);

create index if not exists idx_pipeline_runs_athlete_target
  on pipeline_runs (athlete_id, target_date);

create index if not exists idx_garmin_write_operations_status_retry
  on garmin_write_operations (status, next_retry_at);
