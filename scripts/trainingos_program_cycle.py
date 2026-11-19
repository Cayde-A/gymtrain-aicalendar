#!/usr/bin/env python3
"""Persist an eight-week V4 cycle and derive deterministic progression guidance."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

try:
    from . import trainingos_db
except ImportError:  # pragma: no cover - supports direct script execution.
    import trainingos_db  # type: ignore


CYCLE_VERSION = "v4.8-week.1"
CYCLE_DAYS = 56
WEEK_RULES = (
    {"week": 1, "phase": "accumulation", "top_set_reps": 5, "volume_multiplier": 1.0, "pr_allowed": True},
    {"week": 2, "phase": "accumulation", "top_set_reps": 5, "volume_multiplier": 1.0, "pr_allowed": True},
    {"week": 3, "phase": "intensification", "top_set_reps": 4, "volume_multiplier": 0.9, "pr_allowed": True},
    {"week": 4, "phase": "deload", "top_set_reps": None, "volume_multiplier": 0.55, "pr_allowed": False},
    {"week": 5, "phase": "accumulation", "top_set_reps": 5, "volume_multiplier": 1.0, "pr_allowed": True},
    {"week": 6, "phase": "intensification", "top_set_reps": 4, "volume_multiplier": 0.9, "pr_allowed": True},
    {"week": 7, "phase": "realization", "top_set_reps": 3, "volume_multiplier": 0.8, "pr_allowed": True},
    {"week": 8, "phase": "deload", "top_set_reps": None, "volume_multiplier": 0.55, "pr_allowed": False},
)


def stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def create_cycle(
    connection: Any,
    start_date: str,
    goal: str = "PR progression with controlled fatigue",
    athlete_id: str = trainingos_db.DEFAULT_ATHLETE_ID,
) -> dict[str, Any]:
    start = dt.date.fromisoformat(start_date)
    end = start + dt.timedelta(days=CYCLE_DAYS - 1)
    cycle_id = stable_id("block", athlete_id, start.isoformat(), CYCLE_VERSION)
    connection.execute(
        """
        insert into training_blocks (id, athlete_id, name, version, start_date, end_date, goal)
        values (?, ?, ?, ?, ?, ?, ?)
        on conflict(id) do update set
          name = excluded.name,
          version = excluded.version,
          start_date = excluded.start_date,
          end_date = excluded.end_date,
          goal = excluded.goal
        """,
        (
            cycle_id,
            athlete_id,
            "TrainingOS V4 Eight-Week PR Cycle",
            CYCLE_VERSION,
            start.isoformat(),
            end.isoformat(),
            goal,
        ),
    )
    for rule in WEEK_RULES:
        template_id = stable_id("template", cycle_id, str(rule["week"]))
        connection.execute(
            """
            insert into workout_templates (
              id, training_block_id, name, week_label, day_type, template_notes
            )
            values (?, ?, ?, ?, ?, ?)
            on conflict(id) do update set
              name = excluded.name,
              week_label = excluded.week_label,
              day_type = excluded.day_type,
              template_notes = excluded.template_notes
            """,
            (
                template_id,
                cycle_id,
                f"Week {rule['week']} - {rule['phase']}",
                f"week_{rule['week']}",
                str(rule["phase"]),
                json.dumps(rule, sort_keys=True),
            ),
        )
    return {
        "id": cycle_id,
        "version": CYCLE_VERSION,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "goal": goal,
    }


def active_cycle(
    connection: Any,
    target_date: str,
    athlete_id: str = trainingos_db.DEFAULT_ATHLETE_ID,
) -> dict[str, Any] | None:
    row = connection.execute(
        """
        select *
        from training_blocks
        where athlete_id = ? and version = ?
          and start_date <= ? and end_date >= ?
        order by start_date desc
        limit 1
        """,
        (athlete_id, CYCLE_VERSION, target_date, target_date),
    ).fetchone()
    return dict(row) if row else None


def ensure_active_cycle(
    connection: Any,
    target_date: str,
    athlete_id: str = trainingos_db.DEFAULT_ATHLETE_ID,
) -> dict[str, Any]:
    cycle = active_cycle(connection, target_date, athlete_id)
    if cycle is None:
        create_cycle(connection, target_date, athlete_id=athlete_id)
        cycle = active_cycle(connection, target_date, athlete_id)
    if cycle is None:  # pragma: no cover - defensive database guard.
        raise RuntimeError("Unable to create an active program cycle")
    return cycle


def cycle_context(
    connection: Any,
    target_date: str,
    athlete_id: str = trainingos_db.DEFAULT_ATHLETE_ID,
) -> dict[str, Any]:
    target = dt.date.fromisoformat(target_date)
    cycle = ensure_active_cycle(connection, target_date, athlete_id)
    start = dt.date.fromisoformat(str(cycle["start_date"]))
    week_number = min(8, max(1, (target - start).days // 7 + 1))
    rule = dict(WEEK_RULES[week_number - 1])
    return {
        "cycle_id": cycle["id"],
        "version": cycle["version"],
        "goal": cycle["goal"],
        "start_date": cycle["start_date"],
        "end_date": cycle["end_date"],
        **rule,
    }


def exercise_history(connection: Any, exercise_name: str, before_date: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        select
          completed_sessions.id as session_id,
          completed_sessions.completed_at,
          set_logs.estimated_1rm_kg,
          set_logs.rpe
        from set_logs
        join completed_sessions on completed_sessions.id = set_logs.completed_session_id
        join exercise_catalog on exercise_catalog.id = set_logs.exercise_id
        where lower(exercise_catalog.name) = lower(?)
          and substr(completed_sessions.completed_at, 1, 10) < ?
          and set_logs.estimated_1rm_kg is not null
          and lower(coalesce(set_logs.set_type, '')) != 'rest'
        order by completed_sessions.completed_at desc, set_logs.set_order
        """,
        (exercise_name, before_date),
    ).fetchall()
    sessions: list[dict[str, Any]] = []
    by_session: dict[str, dict[str, Any]] = {}
    for row in rows:
        session_id = str(row["session_id"])
        if session_id not in by_session:
            summary = {
                "session_id": session_id,
                "completed_at": row["completed_at"],
                "best_estimated_1rm_kg": float(row["estimated_1rm_kg"]),
                "max_rpe": float(row["rpe"]) if row["rpe"] is not None else None,
            }
            by_session[session_id] = summary
            sessions.append(summary)
            continue
        summary = by_session[session_id]
        summary["best_estimated_1rm_kg"] = max(
            float(summary["best_estimated_1rm_kg"]), float(row["estimated_1rm_kg"])
        )
        if row["rpe"] is not None:
            summary["max_rpe"] = max(float(summary["max_rpe"] or 0), float(row["rpe"]))
    return sessions


def progression_decision(
    connection: Any,
    exercise_name: str,
    target_date: str,
    cycle: dict[str, Any],
    recovery_adjustment: str,
) -> dict[str, Any]:
    if not cycle["pr_allowed"] or cycle["phase"] == "deload":
        return {"action": "deload", "load_change_percent": -17.5, "reason": "scheduled_recovery_week"}
    if recovery_adjustment == "deload":
        return {"action": "deload", "load_change_percent": -17.5, "reason": "recovery_gate"}
    if recovery_adjustment == "reduce_volume":
        return {"action": "keep", "load_change_percent": 0, "reason": "moderate_recovery_reduce_volume_first"}

    history = exercise_history(connection, exercise_name, target_date)
    if not history:
        return {"action": "establish_baseline", "load_change_percent": 0, "reason": "no_prior_performance"}
    latest = history[0]
    if len(history) >= 3:
        values = [float(item["best_estimated_1rm_kg"]) for item in history[:3]]
        if values[0] < values[1] < values[2]:
            return {"action": "reduce_5_percent", "load_change_percent": -5, "reason": "two_consecutive_declines"}
    if latest["max_rpe"] is not None and float(latest["max_rpe"]) >= 9:
        return {"action": "keep", "load_change_percent": 0, "reason": "latest_rpe_at_or_above_9"}

    pr_row = connection.execute(
        """
        select exercise_pr_state.source_session_id
        from exercise_pr_state
        join exercise_catalog on exercise_catalog.id = exercise_pr_state.exercise_id
        where lower(exercise_catalog.name) = lower(?)
          and exercise_pr_state.pr_type = 'estimated_1rm'
        limit 1
        """,
        (exercise_name,),
    ).fetchone()
    if pr_row and str(pr_row["source_session_id"]) == latest["session_id"]:
        return {"action": "increase_small", "load_change_percent": 2.5, "reason": "latest_session_set_estimated_1rm_pr"}
    if latest["max_rpe"] is not None and float(latest["max_rpe"]) <= 8:
        return {"action": "increase_small", "load_change_percent": 2.5, "reason": "target_completed_with_rpe_at_or_below_8"}
    return {"action": "keep", "load_change_percent": 0, "reason": "insufficient_signal_for_change"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or inspect a TrainingOS eight-week program cycle.")
    parser.add_argument("--db", default=str(trainingos_db.DEFAULT_DB_PATH))
    parser.add_argument("--date", required=True, help="Cycle start or target date in YYYY-MM-DD format.")
    parser.add_argument("--goal", default="PR progression with controlled fatigue")
    parser.add_argument("--create", action="store_true", help="Start a new cycle on --date.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db)
    trainingos_db.init_db(db_path)
    with trainingos_db.connect(db_path) as connection:
        if args.create:
            create_cycle(connection, args.date, args.goal)
        context = cycle_context(connection, args.date)
    print(json.dumps(context, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
