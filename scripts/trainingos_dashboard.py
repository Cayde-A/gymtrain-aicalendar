#!/usr/bin/env python3
"""Build a value-limited local dashboard snapshot from normalized SQLite data."""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

try:
    from . import trainingos_db, trainingos_program_cycle
except ImportError:  # pragma: no cover - supports direct script execution.
    import trainingos_db  # type: ignore
    import trainingos_program_cycle  # type: ignore


def active_cycle_context(connection: Any, today: str) -> dict[str, Any] | None:
    cycle = trainingos_program_cycle.active_cycle(connection, today)
    if cycle is None:
        return None
    start = dt.date.fromisoformat(str(cycle["start_date"]))
    target = dt.date.fromisoformat(today)
    week = min(8, max(1, (target - start).days // 7 + 1))
    rule = trainingos_program_cycle.WEEK_RULES[week - 1]
    return {
        "name": cycle["name"],
        "goal": cycle["goal"],
        "start_date": cycle["start_date"],
        "end_date": cycle["end_date"],
        "week": week,
        "phase": rule["phase"],
        "pr_allowed": rule["pr_allowed"],
    }


def dashboard_snapshot(connection: Any, today: str | None = None) -> dict[str, Any]:
    target = dt.date.fromisoformat(today) if today else dt.date.today()
    start = target - dt.timedelta(days=29)
    session_rows = connection.execute(
        """
        select id, completed_at from completed_sessions
        where athlete_id = ? and substr(completed_at, 1, 10) between ? and ?
        """,
        (trainingos_db.DEFAULT_ATHLETE_ID, start.isoformat(), target.isoformat()),
    ).fetchall()
    session_ids = [str(row["id"]) for row in session_rows]
    set_summary = {"set_count": 0, "volume_kg": 0.0, "missing_reps": 0, "missing_weight": 0}
    if session_ids:
        placeholders = ",".join("?" for _ in session_ids)
        sets = connection.execute(
            f"""
            select * from set_logs
            where completed_session_id in ({placeholders})
              and lower(coalesce(set_type, '')) != 'rest'
            """,
            session_ids,
        ).fetchall()
        set_summary["set_count"] = len(sets)
        set_summary["volume_kg"] = round(
            sum(
                float(row["weight_kg"]) * int(row["reps"])
                for row in sets
                if row["weight_kg"] is not None and row["reps"] is not None
            ),
            2,
        )
        set_summary["missing_reps"] = sum(row["reps"] is None for row in sets)
        set_summary["missing_weight"] = sum(row["weight_kg"] is None for row in sets)
    pr_count = int(
        connection.execute(
            """
            select count(*) from pr_records
            where athlete_id = ? and substr(achieved_at, 1, 10) between ? and ?
            """,
            (trainingos_db.DEFAULT_ATHLETE_ID, start.isoformat(), target.isoformat()),
        ).fetchone()[0]
    )
    recovery_row = connection.execute(
        """
        select metric_date, sleep_score, sleep_duration_minutes, hrv_status, resting_heart_rate,
               body_battery, stress_score, training_readiness, recovery_time_hours
        from daily_recovery_metrics
        where athlete_id = ? and metric_date <= ?
        order by metric_date desc limit 1
        """,
        (trainingos_db.DEFAULT_ATHLETE_ID, target.isoformat()),
    ).fetchone()
    trend_start = target - dt.timedelta(days=13)
    recovery_trends = connection.execute(
        """
        select metric_date, sleep_score, body_battery, training_readiness,
               resting_heart_rate, stress_score
        from daily_recovery_metrics
        where athlete_id = ? and metric_date between ? and ?
        order by metric_date
        """,
        (trainingos_db.DEFAULT_ATHLETE_ID, trend_start.isoformat(), target.isoformat()),
    ).fetchall()
    health_details: dict[str, dict[str, Any] | None] = {}
    for category, (table, _fields) in trainingos_db.DAILY_HEALTH_DETAIL_FIELDS.items():
        row = connection.execute(
            f"""
            select * from {table}
            where athlete_id = ? and metric_date <= ?
            order by metric_date desc limit 1
            """,
            (trainingos_db.DEFAULT_ATHLETE_ID, target.isoformat()),
        ).fetchone()
        health_details[category] = dict(row) if row else None
    pr_rows = connection.execute(
        """
        select exercise_catalog.name as exercise, exercise_pr_state.best_value,
               exercise_pr_state.weight_kg, exercise_pr_state.reps,
               exercise_pr_state.achieved_at
        from exercise_pr_state
        join exercise_catalog on exercise_catalog.id = exercise_pr_state.exercise_id
        where exercise_pr_state.athlete_id = ?
          and exercise_pr_state.pr_type = 'estimated_1rm'
        order by exercise_pr_state.updated_at desc
        limit 10
        """,
        (trainingos_db.DEFAULT_ATHLETE_ID,),
    ).fetchall()
    pipeline_rows = connection.execute(
        """
        select source_training_date, target_date, status, plan_json, updated_at
        from pipeline_runs where athlete_id = ?
        order by updated_at desc limit 5
        """,
        (trainingos_db.DEFAULT_ATHLETE_ID,),
    ).fetchall()
    pipelines = []
    for row in pipeline_rows:
        plan = {}
        try:
            plan = json.loads(row["plan_json"] or "{}")
        except json.JSONDecodeError:
            pass
        pipelines.append(
            {
                "source_training_date": row["source_training_date"],
                "target_date": row["target_date"],
                "status": row["status"],
                "primary_group": plan.get("primary_large_muscle_group"),
                "recovery_adjustment": plan.get("recovery_adjustment"),
                "updated_at": row["updated_at"],
            }
        )
    return {
        "version": "trainingos.dashboard.v2",
        "as_of": target.isoformat(),
        "training_anchor": trainingos_db.training_anchor_state(connection, target.isoformat()),
        "window": {"start_date": start.isoformat(), "end_date": target.isoformat()},
        "training": {
            "training_days": len({str(row["completed_at"])[:10] for row in session_rows}),
            "session_count": len(session_rows),
            **set_summary,
            "pr_record_count": pr_count,
        },
        "latest_recovery": dict(recovery_row) if recovery_row else None,
        "recovery_trends": [dict(row) for row in recovery_trends],
        "health_details": health_details,
        "body_metrics": trainingos_db.body_metrics_context(connection, target.isoformat()),
        "program_cycle": active_cycle_context(connection, target.isoformat()),
        "estimated_1rm_prs": [dict(row) for row in pr_rows],
        "recent_training_days": trainingos_db.get_recent_training_days(connection, 10),
        "recent_pipeline_runs": pipelines,
    }
