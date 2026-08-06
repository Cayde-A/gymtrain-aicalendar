#!/usr/bin/env python3
"""Local SQLite storage helpers for TrainingOS."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "trainingos.sqlite"
SCHEMA_PATH = ROOT / "schema" / "local_sqlite.sql"
DEFAULT_ATHLETE_ID = "local-athlete"
DEFAULT_AI_TRIGGER_POLICY_ID = "default-ai-trigger-policy"
AI_TRIGGER_ALLOWED_VALUES = {
    "post_workout_ai_mode": {
        "manual_copy_paste",
        "user_confirmed_api",
        "auto_api_after_correction",
    },
    "next_morning_adjustment_mode": {
        "manual_copy_paste",
        "user_confirmed_api",
        "auto_api_after_recovery_sync",
    },
    "garmin_push_mode": {
        "manual_only",
        "user_confirmed",
        "auto_after_final_plan",
    },
}
DEFAULT_AI_TRIGGER_POLICY = {
    "post_workout_ai_mode": "manual_copy_paste",
    "next_morning_adjustment_mode": "user_confirmed_api",
    "garmin_push_mode": "user_confirmed",
    "auto_api_enabled": 0,
    "max_ai_calls_per_day": 2,
}
API_TRIGGER_MODE_FIELDS = {
    "post_workout_ai": "post_workout_ai_mode",
    "next_morning_adjustment": "next_morning_adjustment_mode",
    "garmin_push": "garmin_push_mode",
}
AI_CALL_TRIGGER_NAMES = {"post_workout_ai", "next_morning_adjustment"}
MANUAL_ONLY_MODES = {"manual_copy_paste", "manual_only"}
USER_CONFIRMED_MODES = {"user_confirmed_api", "user_confirmed"}
AUTO_MODES = {"auto_api_after_correction", "auto_api_after_recovery_sync", "auto_after_final_plan"}
REP_MAX_PR_TYPES = {
    "1rm": 1,
    "3rm": 3,
    "5rm": 5,
    "8rm": 8,
}
DERIVED_PR_TYPES = {"estimated_1rm", "volume_pr"}

try:
    from . import trainingos_observability
except ImportError:  # pragma: no cover - supports direct script execution.
    import trainingos_observability  # type: ignore


def connect(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute("pragma foreign_keys = on")
    return connection


def init_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    with connect(db_path) as connection:
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        ensure_default_athlete(connection)
    trainingos_observability.record_event(
        "local_db_initialized",
        details={"db_path": str(db_path)},
    )


def ensure_default_athlete(connection: sqlite3.Connection) -> str:
    connection.execute(
        """
        insert into athletes (id, display_name)
        values (?, ?)
        on conflict(id) do nothing
        """,
        (DEFAULT_ATHLETE_ID, "Local Athlete"),
    )
    connection.execute(
        """
        insert into privacy_retention_policies (id, athlete_id)
        values (?, ?)
        on conflict(id) do nothing
        """,
        ("default-retention-policy", DEFAULT_ATHLETE_ID),
    )
    ensure_default_ai_trigger_policy(connection)
    return DEFAULT_ATHLETE_ID


def ensure_default_ai_trigger_policy(
    connection: sqlite3.Connection,
    athlete_id: str = DEFAULT_ATHLETE_ID,
) -> str:
    connection.execute(
        """
        insert into ai_trigger_policies (
          id, athlete_id, post_workout_ai_mode, next_morning_adjustment_mode,
          garmin_push_mode, auto_api_enabled, max_ai_calls_per_day
        )
        values (?, ?, ?, ?, ?, ?, ?)
        on conflict(id) do nothing
        """,
        (
            DEFAULT_AI_TRIGGER_POLICY_ID,
            athlete_id,
            DEFAULT_AI_TRIGGER_POLICY["post_workout_ai_mode"],
            DEFAULT_AI_TRIGGER_POLICY["next_morning_adjustment_mode"],
            DEFAULT_AI_TRIGGER_POLICY["garmin_push_mode"],
            DEFAULT_AI_TRIGGER_POLICY["auto_api_enabled"],
            DEFAULT_AI_TRIGGER_POLICY["max_ai_calls_per_day"],
        ),
    )
    return DEFAULT_AI_TRIGGER_POLICY_ID


def get_ai_trigger_policy(
    connection: sqlite3.Connection,
    athlete_id: str = DEFAULT_ATHLETE_ID,
) -> dict[str, Any]:
    ensure_default_ai_trigger_policy(connection, athlete_id)
    row = connection.execute(
        """
        select *
        from ai_trigger_policies
        where athlete_id = ?
        order by created_at desc
        limit 1
        """,
        (athlete_id,),
    ).fetchone()
    if row is None:
        return dict(DEFAULT_AI_TRIGGER_POLICY)
    policy = dict(row)
    policy["auto_api_enabled"] = bool(policy.get("auto_api_enabled"))
    return policy


def normalize_ai_trigger_policy(payload: dict[str, Any]) -> dict[str, Any]:
    policy = dict(DEFAULT_AI_TRIGGER_POLICY)
    for field_name, allowed_values in AI_TRIGGER_ALLOWED_VALUES.items():
        value = str(payload.get(field_name) or policy[field_name])
        if value not in allowed_values:
            value = str(policy[field_name])
        policy[field_name] = value
    policy["auto_api_enabled"] = 1 if payload.get("auto_api_enabled") else 0
    try:
        max_calls = int(payload.get("max_ai_calls_per_day") or policy["max_ai_calls_per_day"])
    except (TypeError, ValueError):
        max_calls = int(policy["max_ai_calls_per_day"])
    policy["max_ai_calls_per_day"] = max(0, min(max_calls, 20))
    return policy


def update_ai_trigger_policy(
    connection: sqlite3.Connection,
    payload: dict[str, Any],
    athlete_id: str = DEFAULT_ATHLETE_ID,
) -> dict[str, Any]:
    ensure_default_ai_trigger_policy(connection, athlete_id)
    policy = normalize_ai_trigger_policy(payload)
    connection.execute(
        """
        update ai_trigger_policies
        set post_workout_ai_mode = ?,
            next_morning_adjustment_mode = ?,
            garmin_push_mode = ?,
            auto_api_enabled = ?,
            max_ai_calls_per_day = ?,
            updated_at = current_timestamp
        where athlete_id = ?
        """,
        (
            policy["post_workout_ai_mode"],
            policy["next_morning_adjustment_mode"],
            policy["garmin_push_mode"],
            policy["auto_api_enabled"],
            policy["max_ai_calls_per_day"],
            athlete_id,
        ),
    )
    saved_policy = get_ai_trigger_policy(connection, athlete_id)
    trainingos_observability.record_event(
        "ai_trigger_policy_updated",
        details={
            "post_workout_ai_mode": saved_policy["post_workout_ai_mode"],
            "next_morning_adjustment_mode": saved_policy["next_morning_adjustment_mode"],
            "garmin_push_mode": saved_policy["garmin_push_mode"],
            "auto_api_enabled": saved_policy["auto_api_enabled"],
            "max_ai_calls_per_day": saved_policy["max_ai_calls_per_day"],
        },
    )
    return saved_policy


def count_ai_calls_for_date(
    connection: sqlite3.Connection,
    call_date: str | None = None,
    athlete_id: str = DEFAULT_ATHLETE_ID,
) -> int:
    if call_date is None:
        row = connection.execute("select substr(current_timestamp, 1, 10) as current_date").fetchone()
        target_date = str(row["current_date"])
    else:
        target_date = call_date
    row = connection.execute(
        """
        select count(*) as call_count
        from api_trigger_logs
        where athlete_id = ?
          and trigger_name in ('post_workout_ai', 'next_morning_adjustment')
          and status in ('allowed', 'executed')
          and substr(created_at, 1, 10) = ?
        """,
        (athlete_id, target_date),
    ).fetchone()
    return int(row["call_count"] if row else 0)


def evaluate_api_trigger(
    connection: sqlite3.Connection,
    trigger_name: str,
    user_confirmed: bool = False,
    athlete_id: str = DEFAULT_ATHLETE_ID,
) -> dict[str, Any]:
    policy = get_ai_trigger_policy(connection, athlete_id)
    mode_field = API_TRIGGER_MODE_FIELDS.get(trigger_name)
    if mode_field is None:
        return {
            "trigger_name": trigger_name,
            "mode": "unknown",
            "allowed": False,
            "status": "blocked",
            "reason": "unknown_trigger",
            "ai_calls_today": count_ai_calls_for_date(connection, athlete_id=athlete_id),
            "max_ai_calls_per_day": policy["max_ai_calls_per_day"],
        }
    mode = str(policy[mode_field])
    ai_calls_today = count_ai_calls_for_date(connection, athlete_id=athlete_id)
    max_calls = int(policy["max_ai_calls_per_day"])
    if trigger_name in AI_CALL_TRIGGER_NAMES and ai_calls_today >= max_calls:
        return {
            "trigger_name": trigger_name,
            "mode": mode,
            "allowed": False,
            "status": "blocked",
            "reason": "daily_ai_call_cap_reached",
            "ai_calls_today": ai_calls_today,
            "max_ai_calls_per_day": max_calls,
        }
    if mode in MANUAL_ONLY_MODES:
        allowed = False
        status = "manual"
        reason = "manual_mode_selected"
    elif mode in USER_CONFIRMED_MODES:
        allowed = bool(user_confirmed)
        status = "allowed" if allowed else "needs_confirmation"
        reason = "user_confirmed" if allowed else "user_confirmation_required"
    elif mode in AUTO_MODES:
        allowed = bool(policy["auto_api_enabled"])
        status = "allowed" if allowed else "blocked"
        reason = "auto_api_enabled" if allowed else "auto_api_disabled"
    else:
        allowed = False
        status = "blocked"
        reason = "unsupported_mode"
    return {
        "trigger_name": trigger_name,
        "mode": mode,
        "allowed": allowed,
        "status": status,
        "reason": reason,
        "ai_calls_today": ai_calls_today,
        "max_ai_calls_per_day": max_calls,
    }


def record_api_trigger_decision(
    connection: sqlite3.Connection,
    decision: dict[str, Any],
    context: dict[str, Any] | None = None,
    athlete_id: str = DEFAULT_ATHLETE_ID,
) -> str:
    ensure_default_athlete(connection)
    log_id = new_id("api_trigger")
    connection.execute(
        """
        insert into api_trigger_logs (
          id, athlete_id, trigger_name, mode, status, reason, context_json
        )
        values (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            log_id,
            athlete_id,
            decision.get("trigger_name"),
            decision.get("mode"),
            decision.get("status"),
            decision.get("reason"),
            json.dumps(context or {}, ensure_ascii=False, sort_keys=True),
        ),
    )
    trainingos_observability.record_event(
        "api_trigger_decision_recorded",
        details={
            "trigger_name": decision.get("trigger_name"),
            "status": decision.get("status"),
            "reason": decision.get("reason"),
        },
    )
    return log_id


def get_recent_api_trigger_logs(
    connection: sqlite3.Connection,
    limit: int = 20,
    athlete_id: str = DEFAULT_ATHLETE_ID,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        select *
        from api_trigger_logs
        where athlete_id = ?
        order by created_at desc
        limit ?
        """,
        (athlete_id, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def normalize_exercise_name(name: str | None) -> str:
    cleaned = (name or "Unknown Exercise").strip()
    return cleaned or "Unknown Exercise"


def get_or_create_exercise(
    connection: sqlite3.Connection,
    name: str | None,
    category: str = "strength",
) -> str:
    exercise_name = normalize_exercise_name(name)
    row = connection.execute(
        "select id from exercise_catalog where lower(name) = lower(?) limit 1",
        (exercise_name,),
    ).fetchone()
    if row:
        return str(row["id"])
    exercise_id = new_id("exercise")
    connection.execute(
        """
        insert into exercise_catalog (id, name, category)
        values (?, ?, ?)
        """,
        (exercise_id, exercise_name, category),
    )
    return exercise_id


def upsert_completed_session(
    connection: sqlite3.Connection,
    session: dict[str, Any],
    athlete_id: str = DEFAULT_ATHLETE_ID,
) -> str:
    provider = session.get("provider", "garmin")
    external_activity_id = str(session.get("external_activity_id") or "")
    if external_activity_id:
        row = connection.execute(
            """
            select id from completed_sessions
            where provider = ? and external_activity_id = ?
            """,
            (provider, external_activity_id),
        ).fetchone()
    else:
        row = None
    session_id = str(row["id"]) if row else str(session.get("id") or new_id("session"))
    values = {
        "id": session_id,
        "athlete_id": athlete_id,
        "provider": provider,
        "external_activity_id": external_activity_id or None,
        "started_at": session.get("started_at"),
        "completed_at": session.get("completed_at") or session.get("started_at"),
        "session_type": session.get("session_type") or "strength_training",
        "activity_name": session.get("activity_name"),
        "duration_seconds": session.get("duration_seconds"),
        "average_heart_rate": session.get("average_heart_rate"),
        "max_heart_rate": session.get("max_heart_rate"),
        "calories": session.get("calories"),
        "raw_payload_path": session.get("raw_payload_path"),
        "readiness_notes": session.get("readiness_notes"),
        "fatigue_rating": session.get("fatigue_rating"),
        "pain_notes": session.get("pain_notes"),
        "overall_rpe": session.get("overall_rpe"),
    }
    connection.execute(
        """
        insert into completed_sessions (
          id, athlete_id, provider, external_activity_id, started_at, completed_at,
          session_type, activity_name, duration_seconds, average_heart_rate,
          max_heart_rate, calories, raw_payload_path, readiness_notes,
          fatigue_rating, pain_notes, overall_rpe
        )
        values (
          :id, :athlete_id, :provider, :external_activity_id, :started_at, :completed_at,
          :session_type, :activity_name, :duration_seconds, :average_heart_rate,
          :max_heart_rate, :calories, :raw_payload_path, :readiness_notes,
          :fatigue_rating, :pain_notes, :overall_rpe
        )
        on conflict(id) do update set
          started_at = excluded.started_at,
          completed_at = excluded.completed_at,
          session_type = excluded.session_type,
          activity_name = excluded.activity_name,
          duration_seconds = excluded.duration_seconds,
          average_heart_rate = excluded.average_heart_rate,
          max_heart_rate = excluded.max_heart_rate,
          calories = excluded.calories,
          raw_payload_path = excluded.raw_payload_path,
          readiness_notes = coalesce(excluded.readiness_notes, completed_sessions.readiness_notes),
          fatigue_rating = coalesce(excluded.fatigue_rating, completed_sessions.fatigue_rating),
          pain_notes = coalesce(excluded.pain_notes, completed_sessions.pain_notes),
          overall_rpe = coalesce(excluded.overall_rpe, completed_sessions.overall_rpe)
        """,
        values,
    )
    return session_id


def replace_set_logs(
    connection: sqlite3.Connection,
    completed_session_id: str,
    sets: list[dict[str, Any]],
) -> None:
    connection.execute("delete from set_logs where completed_session_id = ?", (completed_session_id,))
    for index, set_log in enumerate(sets, start=1):
        exercise_id = get_or_create_exercise(connection, set_log.get("exercise_name"))
        connection.execute(
            """
            insert into set_logs (
              id, completed_session_id, exercise_id, set_order, set_type,
              weight_kg, reps, rpe, is_top_set, notes
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(set_log.get("id") or new_id("set")),
                completed_session_id,
                exercise_id,
                int(set_log.get("set_order") or index),
                set_log.get("set_type") or "working",
                set_log.get("weight_kg"),
                set_log.get("reps"),
                set_log.get("rpe"),
                1 if set_log.get("is_top_set") else 0,
                set_log.get("notes"),
            ),
        )


def get_session_exercise_ids(connection: sqlite3.Connection, session_id: str) -> set[str]:
    rows = connection.execute(
        """
        select distinct exercise_id
        from set_logs
        where completed_session_id = ?
        """,
        (session_id,),
    ).fetchall()
    return {str(row["exercise_id"]) for row in rows}


def pr_record_best_value(record: dict[str, Any]) -> float | None:
    pr_type = str(record.get("pr_type") or "")
    weight = record.get("weight_kg")
    reps = record.get("reps")
    estimated_1rm = record.get("estimated_1rm_kg")
    if weight is None:
        return None
    if pr_type in REP_MAX_PR_TYPES:
        return float(weight)
    if pr_type == "estimated_1rm":
        return float(estimated_1rm) if estimated_1rm is not None else None
    if pr_type == "volume_pr" and reps is not None:
        return float(weight) * int(reps)
    return None


def build_pr_candidates_for_session(
    connection: sqlite3.Connection,
    session_id: str,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        select
          set_logs.*,
          completed_sessions.athlete_id,
          completed_sessions.completed_at
        from set_logs
        join completed_sessions on completed_sessions.id = set_logs.completed_session_id
        where set_logs.completed_session_id = ?
          and set_logs.weight_kg is not null
          and set_logs.reps is not null
          and lower(coalesce(set_logs.set_type, '')) != 'rest'
          and set_logs.weight_kg > 0
          and set_logs.reps > 0
        order by set_logs.set_order
        """,
        (session_id,),
    ).fetchall()
    candidates: list[dict[str, Any]] = []
    for row in rows:
        set_log = dict(row)
        weight = float(set_log["weight_kg"])
        reps = int(set_log["reps"])
        estimated_1rm = set_log.get("estimated_1rm_kg")
        base = {
            "athlete_id": set_log["athlete_id"],
            "exercise_id": set_log["exercise_id"],
            "completed_session_id": session_id,
            "set_log_id": set_log["id"],
            "weight_kg": weight,
            "reps": reps,
            "estimated_1rm_kg": estimated_1rm,
            "achieved_at": set_log["completed_at"],
        }
        for pr_type, rep_threshold in REP_MAX_PR_TYPES.items():
            if reps >= rep_threshold:
                candidates.append({**base, "pr_type": pr_type, "best_value": weight})
        if estimated_1rm is not None:
            candidates.append({**base, "pr_type": "estimated_1rm", "best_value": float(estimated_1rm)})
        candidates.append({**base, "pr_type": "volume_pr", "best_value": weight * reps})
    best_candidates: dict[tuple[str, str], dict[str, Any]] = {}
    for candidate in candidates:
        key = (str(candidate["exercise_id"]), str(candidate["pr_type"]))
        existing = best_candidates.get(key)
        if existing is None or float(candidate["best_value"]) > float(existing["best_value"]):
            best_candidates[key] = candidate
    return list(best_candidates.values())


def upsert_exercise_pr_state(connection: sqlite3.Connection, candidate: dict[str, Any]) -> None:
    connection.execute(
        """
        insert into exercise_pr_state (
          id, athlete_id, exercise_id, pr_type, best_value, weight_kg, reps,
          estimated_1rm_kg, source_session_id, source_set_log_id, achieved_at
        )
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(athlete_id, exercise_id, pr_type) do update set
          best_value = excluded.best_value,
          weight_kg = excluded.weight_kg,
          reps = excluded.reps,
          estimated_1rm_kg = excluded.estimated_1rm_kg,
          source_session_id = excluded.source_session_id,
          source_set_log_id = excluded.source_set_log_id,
          achieved_at = excluded.achieved_at,
          updated_at = current_timestamp
        """,
        (
            new_id("pr_state"),
            candidate["athlete_id"],
            candidate["exercise_id"],
            candidate["pr_type"],
            candidate["best_value"],
            candidate["weight_kg"],
            candidate["reps"],
            candidate.get("estimated_1rm_kg"),
            candidate["completed_session_id"],
            candidate["set_log_id"],
            candidate["achieved_at"],
        ),
    )


def insert_pr_record(connection: sqlite3.Connection, candidate: dict[str, Any]) -> str:
    pr_record_id = new_id("pr")
    connection.execute(
        """
        insert into pr_records (
          id, athlete_id, exercise_id, completed_session_id, set_log_id,
          pr_type, weight_kg, reps, estimated_1rm_kg, achieved_at
        )
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            pr_record_id,
            candidate["athlete_id"],
            candidate["exercise_id"],
            candidate["completed_session_id"],
            candidate["set_log_id"],
            candidate["pr_type"],
            candidate["weight_kg"],
            candidate["reps"],
            candidate.get("estimated_1rm_kg"),
            candidate["achieved_at"],
        ),
    )
    return pr_record_id


def rebuild_pr_state_for_exercises(
    connection: sqlite3.Connection,
    exercise_ids: set[str],
    athlete_id: str = DEFAULT_ATHLETE_ID,
) -> None:
    if not exercise_ids:
        return
    placeholders = ",".join("?" for _ in exercise_ids)
    params = [athlete_id, *sorted(exercise_ids)]
    connection.execute(
        f"""
        delete from exercise_pr_state
        where athlete_id = ?
          and exercise_id in ({placeholders})
        """,
        params,
    )
    rows = connection.execute(
        f"""
        select *
        from pr_records
        where athlete_id = ?
          and exercise_id in ({placeholders})
        order by achieved_at, created_at
        """,
        params,
    ).fetchall()
    best_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        record = dict(row)
        best_value = pr_record_best_value(record)
        if best_value is None:
            continue
        key = (str(record["exercise_id"]), str(record["pr_type"]))
        existing = best_by_key.get(key)
        if existing is None or best_value > float(existing["best_value"]):
            best_by_key[key] = {
                "athlete_id": record["athlete_id"],
                "exercise_id": record["exercise_id"],
                "completed_session_id": record["completed_session_id"],
                "set_log_id": record["set_log_id"],
                "pr_type": record["pr_type"],
                "best_value": best_value,
                "weight_kg": record["weight_kg"],
                "reps": record["reps"],
                "estimated_1rm_kg": record["estimated_1rm_kg"],
                "achieved_at": record["achieved_at"],
            }
    for candidate in best_by_key.values():
        upsert_exercise_pr_state(connection, candidate)


def current_pr_state_map(
    connection: sqlite3.Connection,
    exercise_ids: set[str],
    athlete_id: str = DEFAULT_ATHLETE_ID,
) -> dict[tuple[str, str], dict[str, Any]]:
    if not exercise_ids:
        return {}
    placeholders = ",".join("?" for _ in exercise_ids)
    rows = connection.execute(
        f"""
        select *
        from exercise_pr_state
        where athlete_id = ?
          and exercise_id in ({placeholders})
        """,
        [athlete_id, *sorted(exercise_ids)],
    ).fetchall()
    return {(str(row["exercise_id"]), str(row["pr_type"])): dict(row) for row in rows}


def process_session_prs(
    connection: sqlite3.Connection,
    session_id: str,
    affected_exercise_ids: set[str] | None = None,
    athlete_id: str = DEFAULT_ATHLETE_ID,
) -> list[dict[str, Any]]:
    current_exercise_ids = get_session_exercise_ids(connection, session_id)
    exercise_ids = set(affected_exercise_ids or set()) | current_exercise_ids
    connection.execute("delete from pr_records where completed_session_id = ?", (session_id,))
    rebuild_pr_state_for_exercises(connection, exercise_ids, athlete_id)
    state = current_pr_state_map(connection, current_exercise_ids, athlete_id)
    new_prs = []
    for candidate in build_pr_candidates_for_session(connection, session_id):
        key = (str(candidate["exercise_id"]), str(candidate["pr_type"]))
        existing = state.get(key)
        if existing is not None and float(candidate["best_value"]) <= float(existing["best_value"]):
            continue
        pr_record_id = insert_pr_record(connection, candidate)
        upsert_exercise_pr_state(connection, candidate)
        candidate_result = dict(candidate)
        candidate_result["pr_record_id"] = pr_record_id
        new_prs.append(candidate_result)
        state[key] = {"best_value": candidate["best_value"]}
    trainingos_observability.record_event(
        "session_prs_processed",
        details={
            "session_id": session_id,
            "candidate_count": len(build_pr_candidates_for_session(connection, session_id)),
            "new_pr_count": len(new_prs),
        },
    )
    return new_prs


def rebuild_all_prs(
    connection: sqlite3.Connection,
    athlete_id: str = DEFAULT_ATHLETE_ID,
) -> dict[str, Any]:
    connection.execute("delete from exercise_pr_state where athlete_id = ?", (athlete_id,))
    connection.execute("delete from pr_records where athlete_id = ?", (athlete_id,))
    rows = connection.execute(
        """
        select id
        from completed_sessions
        where athlete_id = ?
        order by completed_at, created_at
        """,
        (athlete_id,),
    ).fetchall()
    session_count = 0
    pr_count = 0
    for row in rows:
        session_count += 1
        pr_count += len(process_session_prs(connection, str(row["id"]), athlete_id=athlete_id))
    result = {"session_count": session_count, "pr_count": pr_count}
    trainingos_observability.record_event("all_prs_rebuilt", details=result)
    return result


def clear_prs_for_session(connection: sqlite3.Connection, session_id: str) -> None:
    connection.execute("delete from exercise_pr_state where source_session_id = ?", (session_id,))
    connection.execute("delete from pr_records where completed_session_id = ?", (session_id,))


def get_pr_records_for_session(connection: sqlite3.Connection, session_id: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        select
          pr_records.*,
          exercise_catalog.name as exercise_name
        from pr_records
        join exercise_catalog on exercise_catalog.id = pr_records.exercise_id
        where completed_session_id = ?
        order by achieved_at desc, created_at desc
        """,
        (session_id,),
    ).fetchall()
    results = []
    for row in rows:
        record = dict(row)
        record["best_value"] = pr_record_best_value(record)
        results.append(record)
    return results


def get_current_pr_state_for_exercise(
    connection: sqlite3.Connection,
    exercise_id: str,
    athlete_id: str = DEFAULT_ATHLETE_ID,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        select
          exercise_pr_state.*,
          exercise_catalog.name as exercise_name
        from exercise_pr_state
        join exercise_catalog on exercise_catalog.id = exercise_pr_state.exercise_id
        where athlete_id = ?
          and exercise_id = ?
        order by pr_type
        """,
        (athlete_id, exercise_id),
    ).fetchall()
    return [dict(row) for row in rows]


def save_imported_workout(
    connection: sqlite3.Connection,
    workout: dict[str, Any],
    athlete_id: str = DEFAULT_ATHLETE_ID,
) -> str:
    ensure_default_athlete(connection)
    session_id = upsert_completed_session(connection, workout, athlete_id)
    old_exercise_ids = get_session_exercise_ids(connection, session_id)
    clear_prs_for_session(connection, session_id)
    replace_set_logs(connection, session_id, workout.get("sets", []))
    new_prs = process_session_prs(connection, session_id, old_exercise_ids, athlete_id)
    trainingos_observability.record_event(
        "workout_saved",
        details={
            "session_id": session_id,
            "provider": workout.get("provider"),
            "external_activity_id": workout.get("external_activity_id"),
            "activity_name": workout.get("activity_name"),
            "set_count": len(workout.get("sets", [])),
            "new_pr_count": len(new_prs),
        },
    )
    return session_id


def get_recent_sessions(connection: sqlite3.Connection, limit: int = 10) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        select *
        from completed_sessions
        order by completed_at desc
        limit ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def training_date_from_completed_at(value: str | None) -> str:
    return (value or "")[:10]


def get_recent_training_days(connection: sqlite3.Connection, limit: int = 20) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        select
          substr(completed_at, 1, 10) as training_date,
          count(*) as session_count,
          min(completed_at) as first_completed_at,
          max(completed_at) as last_completed_at,
          group_concat(coalesce(activity_name, session_type), ' / ') as activity_names
        from completed_sessions
        group by substr(completed_at, 1, 10)
        order by training_date desc
        limit ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_sessions_for_day(connection: sqlite3.Connection, training_date: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        select id
        from completed_sessions
        where substr(completed_at, 1, 10) = ?
        order by completed_at
        """,
        (training_date,),
    ).fetchall()
    sessions: list[dict[str, Any]] = []
    for row in rows:
        session = get_session_for_review(connection, str(row["id"]))
        if session is not None:
            sessions.append(session)
    return sessions


def get_session_for_review(connection: sqlite3.Connection, session_id: str) -> dict[str, Any] | None:
    session = connection.execute(
        "select * from completed_sessions where id = ?",
        (session_id,),
    ).fetchone()
    if not session:
        return None
    sets = connection.execute(
        """
        select set_logs.*, exercise_catalog.name as exercise_name
        from set_logs
        join exercise_catalog on exercise_catalog.id = set_logs.exercise_id
        where completed_session_id = ?
        order by set_order
        """,
        (session_id,),
    ).fetchall()
    result = dict(session)
    result["sets"] = [dict(row) for row in sets]
    result["pr_records"] = get_pr_records_for_session(connection, session_id)
    return result


def update_review_payload(
    connection: sqlite3.Connection,
    session_id: str,
    payload: dict[str, Any],
) -> None:
    old_exercise_ids = get_session_exercise_ids(connection, session_id)
    clear_prs_for_session(connection, session_id)
    connection.execute(
        """
        update completed_sessions
        set overall_rpe = ?,
            fatigue_rating = ?,
            pain_notes = ?,
            readiness_notes = ?
        where id = ?
        """,
        (
            payload.get("overall_rpe"),
            payload.get("fatigue_rating"),
            payload.get("pain_notes"),
            payload.get("readiness_notes"),
            session_id,
        ),
    )
    replace_set_logs(connection, session_id, payload.get("sets", []))
    new_prs = process_session_prs(connection, session_id, old_exercise_ids)
    trainingos_observability.record_event(
        "review_saved",
        details={
            "session_id": session_id,
            "set_count": len(payload.get("sets", [])),
            "has_pain_notes": bool(payload.get("pain_notes")),
            "has_readiness_notes": bool(payload.get("readiness_notes")),
            "new_pr_count": len(new_prs),
        },
    )


def build_ai_review_summary(connection: sqlite3.Connection, session_id: str) -> dict[str, Any]:
    session = get_session_for_review(connection, session_id)
    if session is None:
        raise ValueError(f"Unknown session: {session_id}")
    summary_sets = []
    for set_log in session["sets"]:
        summary_sets.append(
            {
                "exercise": set_log["exercise_name"],
                "set_order": set_log["set_order"],
                "set_type": set_log["set_type"],
                "weight_kg": set_log["weight_kg"],
                "reps": set_log["reps"],
                "rpe": set_log["rpe"],
                "estimated_1rm_kg": set_log["estimated_1rm_kg"],
                "notes": set_log["notes"],
            }
        )
    result = {
        "session": {
            "id": session["id"],
            "completed_at": session["completed_at"],
            "session_type": session["session_type"],
            "activity_name": session["activity_name"],
            "overall_rpe": session["overall_rpe"],
            "fatigue_rating": session["fatigue_rating"],
            "pain_notes": session["pain_notes"],
            "readiness_notes": session["readiness_notes"],
        },
        "sets": summary_sets,
    }
    trainingos_observability.record_event(
        "ai_summary_built",
        details={"session_id": session_id, "set_count": len(summary_sets)},
    )
    return result


def session_metrics(summary: dict[str, Any]) -> dict[str, Any]:
    sets = summary["sets"]
    working_sets = [item for item in sets if item.get("weight_kg") is not None and item.get("reps") is not None]
    total_volume = sum(float(item["weight_kg"]) * int(item["reps"]) for item in working_sets)
    best_estimated_1rm = None
    if working_sets:
        best_estimated_1rm = max(
            item.get("estimated_1rm_kg") or 0
            for item in working_sets
        )
    return {
        "set_count": len(sets),
        "logged_working_set_count": len(working_sets),
        "total_volume_kg": round(total_volume, 2),
        "best_estimated_1rm_kg": round(best_estimated_1rm, 2) if best_estimated_1rm else None,
        "missing_rpe_count": sum(1 for item in sets if item.get("rpe") is None),
        "missing_reps_count": sum(1 for item in sets if item.get("reps") is None),
        "missing_weight_count": sum(1 for item in sets if item.get("weight_kg") is None),
    }


def aggregate_day_metrics(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    all_sets = [set_log for session in sessions for set_log in session.get("sets", [])]
    working_sets = [item for item in all_sets if item.get("weight_kg") is not None and item.get("reps") is not None]
    total_volume = sum(float(item["weight_kg"]) * int(item["reps"]) for item in working_sets)
    best_estimated_1rm = None
    if working_sets:
        best_estimated_1rm = max(item.get("estimated_1rm_kg") or 0 for item in working_sets)
    return {
        "session_count": len(sessions),
        "set_count": len(all_sets),
        "logged_working_set_count": len(working_sets),
        "total_volume_kg": round(total_volume, 2),
        "best_estimated_1rm_kg": round(best_estimated_1rm, 2) if best_estimated_1rm else None,
        "missing_rpe_count": sum(1 for item in all_sets if item.get("rpe") is None),
        "missing_reps_count": sum(1 for item in all_sets if item.get("reps") is None),
        "missing_weight_count": sum(1 for item in all_sets if item.get("weight_kg") is None),
    }


def build_ai_review_packet(connection: sqlite3.Connection, session_id: str) -> dict[str, Any]:
    summary = build_ai_review_summary(connection, session_id)
    trigger_policy = get_ai_trigger_policy(connection)
    packet = {
        "task": "post_workout_review_and_initial_next_day_draft",
        "version": "trainingos.ai_review_packet.v1",
        "constraints": {
            "compute_budget": "low",
            "use_only_packet_data": True,
            "return_json_only": True,
            "plan_status": "initial_draft",
            "final_plan_requires_next_day_recovery": True,
            "do_not_push_garmin_workout_from_initial_draft": True,
            "api_calls_require_trigger_policy": True,
        },
        "trigger_policy": {
            "post_workout_ai_mode": trigger_policy["post_workout_ai_mode"],
            "next_morning_adjustment_mode": trigger_policy["next_morning_adjustment_mode"],
            "garmin_push_mode": trigger_policy["garmin_push_mode"],
            "auto_api_enabled": trigger_policy["auto_api_enabled"],
            "max_ai_calls_per_day": trigger_policy["max_ai_calls_per_day"],
        },
        "required_output_schema": {
            "analysis_summary": "string",
            "performance_direction": "increase|keep|reduce|deload",
            "risk_flags": ["string"],
            "data_quality_issues": ["string"],
            "initial_next_day_plan": {
                "status": "initial_draft",
                "session_type": "string",
                "focus": ["string"],
                "rounds": [
                    {
                        "exercise": "string",
                        "sets": "integer",
                        "reps": "string",
                        "load_guidance": "string",
                        "rpe_cap": "number|null",
                    }
                ],
            },
            "next_morning_adjustment_rules": ["string"],
        },
        "session": summary["session"],
        "metrics": session_metrics(summary),
        "sets": summary["sets"],
    }
    trainingos_observability.record_event(
        "ai_review_packet_built",
        details={"session_id": session_id, "set_count": len(summary["sets"])},
    )
    return packet


def build_day_ai_review_packet(connection: sqlite3.Connection, training_date: str) -> dict[str, Any]:
    sessions = get_sessions_for_day(connection, training_date)
    if not sessions:
        raise ValueError(f"Unknown training date: {training_date}")
    trigger_policy = get_ai_trigger_policy(connection)
    packet_sessions = []
    for session in sessions:
        packet_sessions.append(
            {
                "session": {
                    "id": session["id"],
                    "completed_at": session["completed_at"],
                    "session_type": session["session_type"],
                    "activity_name": session["activity_name"],
                    "overall_rpe": session["overall_rpe"],
                    "fatigue_rating": session["fatigue_rating"],
                    "pain_notes": session["pain_notes"],
                    "readiness_notes": session["readiness_notes"],
                },
                "sets": [
                    {
                        "exercise": set_log["exercise_name"],
                        "set_order": set_log["set_order"],
                        "set_type": set_log["set_type"],
                        "weight_kg": set_log["weight_kg"],
                        "reps": set_log["reps"],
                        "rpe": set_log["rpe"],
                        "estimated_1rm_kg": set_log["estimated_1rm_kg"],
                        "notes": set_log["notes"],
                    }
                    for set_log in session.get("sets", [])
                ],
            }
        )
    packet = {
        "task": "post_workout_review_day_group_and_initial_next_day_draft",
        "version": "trainingos.ai_review_day_packet.v1",
        "training_date": training_date,
        "constraints": {
            "compute_budget": "low",
            "use_only_packet_data": True,
            "return_json_only": True,
            "treat_same_day_sessions_as_one_workout": True,
            "plan_status": "initial_draft",
            "final_plan_requires_next_day_recovery": True,
            "do_not_push_garmin_workout_from_initial_draft": True,
            "api_calls_require_trigger_policy": True,
        },
        "trigger_policy": {
            "post_workout_ai_mode": trigger_policy["post_workout_ai_mode"],
            "next_morning_adjustment_mode": trigger_policy["next_morning_adjustment_mode"],
            "garmin_push_mode": trigger_policy["garmin_push_mode"],
            "auto_api_enabled": trigger_policy["auto_api_enabled"],
            "max_ai_calls_per_day": trigger_policy["max_ai_calls_per_day"],
        },
        "required_output_schema": {
            "analysis_summary": "string",
            "performance_direction": "increase|keep|reduce|deload",
            "risk_flags": ["string"],
            "data_quality_issues": ["string"],
            "initial_next_day_plan": {
                "status": "initial_draft",
                "session_type": "string",
                "focus": ["string"],
                "rounds": [
                    {
                        "exercise": "string",
                        "sets": "integer",
                        "reps": "string",
                        "load_guidance": "string",
                        "rpe_cap": "number|null",
                    }
                ],
            },
            "next_morning_adjustment_rules": ["string"],
        },
        "metrics": aggregate_day_metrics(sessions),
        "sessions": packet_sessions,
    }
    trainingos_observability.record_event(
        "ai_review_day_packet_built",
        details={"training_date": training_date, "session_count": len(sessions)},
    )
    return packet


def build_post_workout_analysis_prompt(connection: sqlite3.Connection, session_id: str) -> str:
    packet = build_ai_review_packet(connection, session_id)
    prompt_payload = json.dumps(packet, indent=2, ensure_ascii=False)
    return f"""You are TrainingOS Coach Agent.

Use the standardized TrainingOS AI review packet below.

Rules:
- Use only the packet data.
- Keep reasoning compact.
- Return JSON only.
- Generate an initial next-day plan draft.
- Do not mark the draft as final.
- The final plan must wait for next-day Garmin sleep, HRV, Body Battery, readiness, and recovery metrics.

Packet:

```json
{prompt_payload}
```
"""


def build_day_post_workout_analysis_prompt(connection: sqlite3.Connection, training_date: str) -> str:
    packet = build_day_ai_review_packet(connection, training_date)
    prompt_payload = json.dumps(packet, indent=2, ensure_ascii=False)
    return f"""You are TrainingOS Coach Agent.

Use the standardized TrainingOS same-day workout packet below.

Rules:
- Treat all sessions in the same training_date as one workout.
- Use only the packet data.
- Keep reasoning compact.
- Return JSON only.
- Generate an initial next-day plan draft.
- Do not mark the draft as final.
- The final plan must wait for next-day Garmin sleep, HRV, Body Battery, readiness, and recovery metrics.

Packet:

```json
{prompt_payload}
```
"""


def extract_json_object(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    if not cleaned:
        return None
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            parsed = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def save_ai_review_response(
    connection: sqlite3.Connection,
    session_id: str,
    response_text: str,
) -> str:
    parsed = extract_json_object(response_text)
    review_id = new_id("ai_review")
    if parsed:
        decision = str(parsed.get("performance_direction") or parsed.get("decision") or "keep")
        summary = str(parsed.get("analysis_summary") or parsed.get("summary") or "")
        risk_flags = parsed.get("risk_flags") or []
        next_target = {
            "initial_next_day_plan": parsed.get("initial_next_day_plan"),
            "next_morning_adjustment_rules": parsed.get("next_morning_adjustment_rules"),
            "data_quality_issues": parsed.get("data_quality_issues"),
            "raw_json": parsed,
        }
    else:
        decision = "manual_review"
        summary = response_text.strip()
        risk_flags = ["unstructured_ai_response"]
        next_target = {"raw_text": response_text}
    connection.execute(
        """
        insert into ai_reviews (
          id, completed_session_id, review_type, decision, summary,
          next_target_json, risk_flags_json
        )
        values (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            review_id,
            session_id,
            "post_workout_initial_draft",
            decision,
            summary,
            json.dumps(next_target, ensure_ascii=False, sort_keys=True),
            json.dumps(risk_flags, ensure_ascii=False, sort_keys=True),
        ),
    )
    trainingos_observability.record_event(
        "ai_review_saved",
        details={
            "session_id": session_id,
            "review_id": review_id,
            "structured": bool(parsed),
            "decision": decision,
        },
    )
    return review_id


def save_day_ai_review_response(
    connection: sqlite3.Connection,
    training_date: str,
    response_text: str,
) -> str:
    parsed = extract_json_object(response_text)
    review_id = new_id("ai_review")
    if parsed:
        decision = str(parsed.get("performance_direction") or parsed.get("decision") or "keep")
        summary = str(parsed.get("analysis_summary") or parsed.get("summary") or "")
        risk_flags = parsed.get("risk_flags") or []
        next_target = {
            "training_date": training_date,
            "initial_next_day_plan": parsed.get("initial_next_day_plan"),
            "next_morning_adjustment_rules": parsed.get("next_morning_adjustment_rules"),
            "data_quality_issues": parsed.get("data_quality_issues"),
            "raw_json": parsed,
        }
    else:
        decision = "manual_review"
        summary = response_text.strip()
        risk_flags = ["unstructured_ai_response"]
        next_target = {"training_date": training_date, "raw_text": response_text}
    connection.execute(
        """
        insert into ai_reviews (
          id, completed_session_id, review_type, decision, summary,
          next_target_json, risk_flags_json
        )
        values (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            review_id,
            None,
            "day_post_workout_initial_draft",
            decision,
            summary,
            json.dumps(next_target, ensure_ascii=False, sort_keys=True),
            json.dumps(risk_flags, ensure_ascii=False, sort_keys=True),
        ),
    )
    trainingos_observability.record_event(
        "ai_day_review_saved",
        details={
            "training_date": training_date,
            "review_id": review_id,
            "structured": bool(parsed),
            "decision": decision,
        },
    )
    return review_id


def get_ai_reviews_for_session(connection: sqlite3.Connection, session_id: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        select *
        from ai_reviews
        where completed_session_id = ?
        order by created_at desc
        """,
        (session_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_ai_reviews_for_day(connection: sqlite3.Connection, training_date: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        select *
        from ai_reviews
        where review_type = 'day_post_workout_initial_draft'
          and next_target_json like ?
        order by created_at desc
        """,
        (f'%"training_date": "{training_date}"%',),
    ).fetchall()
    return [dict(row) for row in rows]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage the TrainingOS local SQLite database.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path.")
    parser.add_argument("--init", action="store_true", help="Initialize the local database.")
    parser.add_argument("--list-sessions", action="store_true", help="List recent completed sessions.")
    parser.add_argument("--rebuild-prs", action="store_true", help="Rebuild PR records and current PR state.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db)
    if args.init:
        init_db(db_path)
        print(f"Initialized local database: {db_path}")
    if args.list_sessions:
        with connect(db_path) as connection:
            print(json.dumps(get_recent_sessions(connection), indent=2, ensure_ascii=False))
    if args.rebuild_prs:
        with connect(db_path) as connection:
            print(json.dumps(rebuild_all_prs(connection), indent=2, ensure_ascii=False))
    if not args.init and not args.list_sessions and not args.rebuild_prs:
        print("No action selected. Use --init or --list-sessions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
