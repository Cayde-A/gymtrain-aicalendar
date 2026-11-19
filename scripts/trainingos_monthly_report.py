#!/usr/bin/env python3
"""Generate a deterministic private monthly TrainingOS report."""

from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from . import trainingos_db
    from .trainingos_weekly_review import RECOVERY_FIELDS
except ImportError:  # pragma: no cover - supports direct script execution.
    import trainingos_db  # type: ignore
    from trainingos_weekly_review import RECOVERY_FIELDS  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "exports" / "reports"


def month_range(month: str) -> tuple[str, str, int]:
    start = dt.date.fromisoformat(f"{month}-01")
    day_count = calendar.monthrange(start.year, start.month)[1]
    end = start.replace(day=day_count)
    return start.isoformat(), end.isoformat(), day_count


def build_monthly_report(connection: Any, month: str) -> dict[str, Any]:
    start_date, end_date, day_count = month_range(month)
    session_rows = connection.execute(
        """
        select id, completed_at, session_type, activity_name
        from completed_sessions
        where athlete_id = ? and substr(completed_at, 1, 10) between ? and ?
        order by completed_at
        """,
        (trainingos_db.DEFAULT_ATHLETE_ID, start_date, end_date),
    ).fetchall()
    session_ids = [str(row["id"]) for row in session_rows]
    session_dates = {str(row["id"]): str(row["completed_at"])[:10] for row in session_rows}
    sets: list[dict[str, Any]] = []
    if session_ids:
        placeholders = ",".join("?" for _ in session_ids)
        rows = connection.execute(
            f"""
            select
              set_logs.*, exercise_catalog.name as exercise_name,
              completed_sessions.completed_at
            from set_logs
            join exercise_catalog on exercise_catalog.id = set_logs.exercise_id
            join completed_sessions on completed_sessions.id = set_logs.completed_session_id
            where completed_session_id in ({placeholders})
            order by completed_sessions.completed_at, set_logs.set_order
            """,
            session_ids,
        ).fetchall()
        sets = [dict(row) for row in rows]
    working = [item for item in sets if str(item.get("set_type") or "").lower() != "rest"]
    logged = [item for item in working if item.get("weight_kg") is not None and item.get("reps") is not None]

    exercise_data: dict[str, dict[str, Any]] = {}
    session_performance: dict[tuple[str, str], float] = {}
    for item in working:
        name = str(item["exercise_name"])
        entry = exercise_data.setdefault(name, {"set_count": 0, "volume_kg": 0.0, "best_set": None})
        entry["set_count"] += 1
        if item.get("weight_kg") is not None and item.get("reps") is not None:
            entry["volume_kg"] += float(item["weight_kg"]) * int(item["reps"])
        estimated = item.get("estimated_1rm_kg")
        if estimated is not None:
            candidate = {
                "date": str(item["completed_at"])[:10],
                "weight_kg": item.get("weight_kg"),
                "reps": item.get("reps"),
                "estimated_1rm_kg": round(float(estimated), 2),
            }
            if entry["best_set"] is None or candidate["estimated_1rm_kg"] > entry["best_set"]["estimated_1rm_kg"]:
                entry["best_set"] = candidate
            key = (name, str(item["completed_session_id"]))
            session_performance[key] = max(float(estimated), session_performance.get(key, 0.0))

    exercise_volume = [
        {"exercise": name, "set_count": data["set_count"], "volume_kg": round(data["volume_kg"], 2)}
        for name, data in sorted(exercise_data.items(), key=lambda pair: (-pair[1]["volume_kg"], pair[0]))
    ]
    best_sets = [
        {"exercise": name, **data["best_set"]}
        for name, data in sorted(exercise_data.items())
        if data["best_set"] is not None
    ]
    trends = []
    for exercise_name in sorted(exercise_data):
        performances = sorted(
            [
            {
                "date": session_dates[session_id],
                "value": value,
            }
            for (name, session_id), value in session_performance.items()
            if name == exercise_name
            ],
            key=lambda item: item["date"],
        )
        if not performances:
            continue
        first, last = performances[0], performances[-1]
        trends.append(
            {
                "exercise": exercise_name,
                "first_estimated_1rm_kg": round(first["value"], 2),
                "last_estimated_1rm_kg": round(last["value"], 2),
                "change_kg": round(last["value"] - first["value"], 2),
                "observed_sessions": len(performances),
            }
        )

    pr_count = int(
        connection.execute(
            """
            select count(*) from pr_records
            where athlete_id = ? and substr(achieved_at, 1, 10) between ? and ?
            """,
            (trainingos_db.DEFAULT_ATHLETE_ID, start_date, end_date),
        ).fetchone()[0]
    )
    recovery_rows = connection.execute(
        """
        select * from daily_recovery_metrics
        where athlete_id = ? and metric_date between ? and ? order by metric_date
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
        where athlete_id = ? and metric_date between ? and ? order by metric_date
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
    session_type_counts = dict(sorted(Counter(str(row["session_type"]) for row in session_rows).items()))
    return {
        "version": "trainingos.monthly_report.v1",
        "month": month,
        "period": {"start_date": start_date, "end_date": end_date, "calendar_days": day_count},
        "training": {
            "training_days": len({str(row["completed_at"])[:10] for row in session_rows}),
            "session_count": len(session_rows),
            "session_type_counts": session_type_counts,
            "working_set_count": len(working),
            "total_volume_kg": round(sum(float(item["weight_kg"]) * int(item["reps"]) for item in logged), 2),
            "missing_reps_count": sum(item.get("reps") is None for item in working),
            "missing_weight_count": sum(item.get("weight_kg") is None for item in working),
            "missing_rpe_count": sum(item.get("rpe") is None for item in working),
        },
        "exercise_volume": exercise_volume,
        "best_sets": best_sets,
        "pr_count": pr_count,
        "estimated_1rm_trends": trends,
        "recovery": {
            "days_present": len(recovery_rows),
            "coverage_percent": round(len(recovery_rows) / day_count * 100, 1),
            "averages": recovery_averages,
        },
        "body_metrics": {"records_present": len(body_rows), "change_first_to_last": body_change},
        "ai_api_called": False,
    }


def render_markdown(report: dict[str, Any]) -> str:
    training = report["training"]
    lines = [
        "# TrainingOS Monthly Report",
        "",
        f"Month: {report['month']}",
        "",
        "## Training",
        "",
        f"- Training days: {training['training_days']}",
        f"- Sessions: {training['session_count']}",
        f"- Working sets: {training['working_set_count']}",
        f"- Logged volume: {training['total_volume_kg']} kg",
        f"- PR records: {report['pr_count']}",
        f"- Session types: {json.dumps(training['session_type_counts'], ensure_ascii=False, sort_keys=True)}",
        f"- Missing reps / weight / RPE: {training['missing_reps_count']} / {training['missing_weight_count']} / {training['missing_rpe_count']}",
        "",
        "## Exercise Volume",
        "",
    ]
    lines.extend(
        f"- {item['exercise']}: {item['set_count']} sets, {item['volume_kg']} kg"
        for item in report["exercise_volume"]
    )
    if not report["exercise_volume"]:
        lines.append("- No completed exercise data")
    lines.extend(["", "## Estimated 1RM Trends", ""])
    lines.extend(
        f"- {item['exercise']}: {item['first_estimated_1rm_kg']} -> {item['last_estimated_1rm_kg']} kg ({item['change_kg']:+g})"
        for item in report["estimated_1rm_trends"]
    )
    if not report["estimated_1rm_trends"]:
        lines.append("- No estimated 1RM observations")
    recovery = report["recovery"]
    lines.extend(
        [
            "",
            "## Recovery",
            "",
            f"- Coverage: {recovery['days_present']}/{report['period']['calendar_days']} days ({recovery['coverage_percent']}%)",
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
        lines.append("- Insufficient records for a monthly change")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a private local TrainingOS monthly report.")
    parser.add_argument("--db", default=str(trainingos_db.DEFAULT_DB_PATH))
    parser.add_argument("--month", required=True, help="Month in YYYY-MM format.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db)
    trainingos_db.init_db(db_path)
    with trainingos_db.connect(db_path) as connection:
        report = build_monthly_report(connection, args.month)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"monthly_report_{args.month}.json"
    markdown_path = output_dir / f"monthly_report_{args.month}.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"status": "written", "json": str(json_path), "markdown": str(markdown_path)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
