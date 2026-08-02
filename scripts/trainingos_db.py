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
    return DEFAULT_ATHLETE_ID


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


def save_imported_workout(
    connection: sqlite3.Connection,
    workout: dict[str, Any],
    athlete_id: str = DEFAULT_ATHLETE_ID,
) -> str:
    ensure_default_athlete(connection)
    session_id = upsert_completed_session(connection, workout, athlete_id)
    replace_set_logs(connection, session_id, workout.get("sets", []))
    trainingos_observability.record_event(
        "workout_saved",
        details={
            "session_id": session_id,
            "provider": workout.get("provider"),
            "external_activity_id": workout.get("external_activity_id"),
            "activity_name": workout.get("activity_name"),
            "set_count": len(workout.get("sets", [])),
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
    return result


def update_review_payload(
    connection: sqlite3.Connection,
    session_id: str,
    payload: dict[str, Any],
) -> None:
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
    trainingos_observability.record_event(
        "review_saved",
        details={
            "session_id": session_id,
            "set_count": len(payload.get("sets", [])),
            "has_pain_notes": bool(payload.get("pain_notes")),
            "has_readiness_notes": bool(payload.get("readiness_notes")),
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


def build_post_workout_analysis_prompt(connection: sqlite3.Connection, session_id: str) -> str:
    summary = build_ai_review_summary(connection, session_id)
    prompt_payload = json.dumps(summary, indent=2, ensure_ascii=False)
    return f"""You are TrainingOS Coach Agent.

Analyze the corrected completed workout below and generate an initial next-day training plan.

Important workflow rule:
- Generate a first-draft next-day plan after the post-workout review.
- Mark the plan as "initial_draft", not final.
- Tomorrow's final plan must be adjusted after next-day Garmin sleep, HRV, Body Battery, readiness, and recovery metrics are imported.
- Include clear adjustment rules for the next morning.
- Do not push a final Garmin workout from this draft without the next-day recovery update.

Return:
1. Session summary
2. PR / estimated 1RM notes
3. Performance direction: Increase / Keep / Reduce / Deload
4. Fatigue and pain risk flags
5. Data quality issues that still need user correction
6. Initial next-day training plan draft
7. Next-morning adjustment rules based on sleep, HRV, Body Battery, readiness, and recovery time
8. A compact JSON result for saving into ai_reviews, including:
   - analysis_summary
   - performance_direction
   - risk_flags
   - initial_next_day_plan
   - next_morning_adjustment_rules

Corrected workout:

```json
{prompt_payload}
```
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage the TrainingOS local SQLite database.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path.")
    parser.add_argument("--init", action="store_true", help="Initialize the local database.")
    parser.add_argument("--list-sessions", action="store_true", help="List recent completed sessions.")
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
    if not args.init and not args.list_sessions:
        print("No action selected. Use --init or --list-sessions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
