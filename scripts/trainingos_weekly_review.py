#!/usr/bin/env python3
"""Generate a deterministic local weekly TrainingOS review."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

try:
    from . import trainingos_db
except ImportError:  # pragma: no cover - supports direct script execution.
    import trainingos_db  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "exports" / "reviews"
RECOVERY_FIELDS = (
    "sleep_score",
    "sleep_duration_minutes",
    "resting_heart_rate",
    "body_battery",
    "stress_score",
    "training_readiness",
    "recovery_time_hours",
)


def build_weekly_review(connection: Any, week_ending: str) -> dict[str, Any]:
    end = dt.date.fromisoformat(week_ending)
    start = end - dt.timedelta(days=6)
    start_date = start.isoformat()
    end_date = end.isoformat()
    sessions = connection.execute(
        """
        select * from completed_sessions
        where athlete_id = ? and substr(completed_at, 1, 10) between ? and ?
        order by completed_at
        """,
        (trainingos_db.DEFAULT_ATHLETE_ID, start_date, end_date),
    ).fetchall()
    session_ids = [str(row["id"]) for row in sessions]
    sets: list[dict[str, Any]] = []
    if session_ids:
        placeholders = ",".join("?" for _ in session_ids)
        rows = connection.execute(
            f"""
            select set_logs.*, exercise_catalog.name as exercise_name
            from set_logs
            join exercise_catalog on exercise_catalog.id = set_logs.exercise_id
            where completed_session_id in ({placeholders})
            order by completed_session_id, set_order
            """,
            session_ids,
        ).fetchall()
        sets = [dict(row) for row in rows]
    working = [item for item in sets if str(item.get("set_type") or "").lower() != "rest"]
    logged = [item for item in working if item.get("weight_kg") is not None and item.get("reps") is not None]

    exercise_summary: dict[str, dict[str, Any]] = {}
    for item in working:
        name = str(item["exercise_name"])
        summary = exercise_summary.setdefault(name, {"set_count": 0, "volume_kg": 0.0})
        summary["set_count"] += 1
        if item.get("weight_kg") is not None and item.get("reps") is not None:
            summary["volume_kg"] += float(item["weight_kg"]) * int(item["reps"])
    exercises = [
        {"exercise": name, "set_count": values["set_count"], "volume_kg": round(values["volume_kg"], 2)}
        for name, values in sorted(
            exercise_summary.items(), key=lambda pair: (-float(pair[1]["volume_kg"]), pair[0])
        )
    ]

    pr_count = connection.execute(
        """
        select count(*) from pr_records
        where athlete_id = ? and substr(achieved_at, 1, 10) between ? and ?
        """,
        (trainingos_db.DEFAULT_ATHLETE_ID, start_date, end_date),
    ).fetchone()[0]
    recovery_rows = connection.execute(
        """
        select * from daily_recovery_metrics
        where athlete_id = ? and metric_date between ? and ?
        order by metric_date
        """,
        (trainingos_db.DEFAULT_ATHLETE_ID, start_date, end_date),
    ).fetchall()
    recovery_averages = {}
    for field in RECOVERY_FIELDS:
        values = [float(row[field]) for row in recovery_rows if row[field] is not None]
        recovery_averages[field] = round(sum(values) / len(values), 2) if values else None

    body_rows = connection.execute(
        """
        select * from body_metrics
        where athlete_id = ? and metric_date between ? and ?
        order by metric_date
        """,
        (trainingos_db.DEFAULT_ATHLETE_ID, start_date, end_date),
    ).fetchall()
    body_change = {}
    if len(body_rows) >= 2:
        first, last = body_rows[0], body_rows[-1]
        body_change = {
            field: round(float(last[field]) - float(first[field]), 2)
            for field in trainingos_db.BODY_METRIC_RANGES
            if first[field] is not None and last[field] is not None
        }

    return {
        "version": "trainingos.weekly_review.v1",
        "period": {"start_date": start_date, "end_date": end_date},
        "training": {
            "training_days": len({str(row["completed_at"])[:10] for row in sessions}),
            "session_count": len(sessions),
            "working_set_count": len(working),
            "logged_working_set_count": len(logged),
            "total_volume_kg": round(
                sum(float(item["weight_kg"]) * int(item["reps"]) for item in logged), 2
            ),
            "missing_reps_count": sum(item.get("reps") is None for item in working),
            "missing_weight_count": sum(item.get("weight_kg") is None for item in working),
            "missing_rpe_count": sum(item.get("rpe") is None for item in working),
        },
        "exercises": exercises,
        "pr_count": int(pr_count),
        "recovery": {
            "days_present": len(recovery_rows),
            "coverage_percent": round(len(recovery_rows) / 7 * 100, 1),
            "averages": recovery_averages,
        },
        "body_metrics": {
            "records_present": len(body_rows),
            "change_first_to_last": body_change,
        },
        "ai_api_called": False,
    }


def render_markdown(report: dict[str, Any]) -> str:
    period = report["period"]
    training = report["training"]
    recovery = report["recovery"]
    lines = [
        "# TrainingOS Weekly Review",
        "",
        f"Period: {period['start_date']} to {period['end_date']}",
        "",
        "## Training",
        "",
        f"- Training days: {training['training_days']}",
        f"- Sessions: {training['session_count']}",
        f"- Working sets: {training['working_set_count']}",
        f"- Logged volume: {training['total_volume_kg']} kg",
        f"- PR records: {report['pr_count']}",
        f"- Missing reps / weight / RPE: {training['missing_reps_count']} / {training['missing_weight_count']} / {training['missing_rpe_count']}",
        "",
        "## Exercise Load",
        "",
    ]
    lines.extend(
        f"- {item['exercise']}: {item['set_count']} sets, {item['volume_kg']} kg"
        for item in report["exercises"]
    )
    if not report["exercises"]:
        lines.append("- No completed exercise data")
    lines.extend(
        [
            "",
            "## Recovery",
            "",
            f"- Coverage: {recovery['days_present']}/7 days ({recovery['coverage_percent']}%)",
        ]
    )
    lines.extend(
        f"- {field}: {value if value is not None else 'unavailable'}"
        for field, value in recovery["averages"].items()
    )
    lines.extend(["", "## Body Metrics", ""])
    changes = report["body_metrics"]["change_first_to_last"]
    lines.extend(f"- {field}: {value:+g}" for field, value in changes.items())
    if not changes:
        lines.append("- Insufficient records for a weekly change")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a local TrainingOS weekly review.")
    parser.add_argument("--db", default=str(trainingos_db.DEFAULT_DB_PATH))
    parser.add_argument("--week-ending", required=True)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    trainingos_db.init_db(Path(args.db))
    with trainingos_db.connect(Path(args.db)) as connection:
        report = build_weekly_review(connection, args.week_ending)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"weekly_review_{report['period']['start_date']}_{report['period']['end_date']}"
    json_path = output_dir / f"{stem}.json"
    markdown_path = output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"status": "written", "json": str(json_path), "markdown": str(markdown_path)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
