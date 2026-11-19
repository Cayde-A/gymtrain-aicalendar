#!/usr/bin/env python3
"""Deterministic data-quality gates for TrainingOS analysis and planning."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

try:
    from . import trainingos_db, trainingos_observability
except ImportError:  # pragma: no cover - supports direct script execution.
    import trainingos_db  # type: ignore
    import trainingos_observability  # type: ignore


MAX_REASONABLE_WEIGHT_KG = 500.0
RECOVERY_RANGES = {
    "sleep_score": (0, 100),
    "sleep_duration_minutes": (0, 1440),
    "resting_heart_rate": (25, 220),
    "body_battery": (0, 100),
    "stress_score": (0, 100),
    "training_readiness": (0, 100),
    "recovery_time_hours": (0, 240),
}
RECOVERY_DECISION_FIELDS = (
    "sleep_score",
    "sleep_duration_minutes",
    "hrv_status",
    "resting_heart_rate",
    "body_battery",
    "stress_score",
    "training_readiness",
    "recovery_time_hours",
)


@dataclass(frozen=True)
class QualityIssue:
    code: str
    severity: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_rest_set(set_log: dict[str, Any]) -> bool:
    return str(set_log.get("set_type") or "").strip().lower() == "rest"


def evaluate_training_day(connection: Any, training_date: str) -> dict[str, Any]:
    sessions = trainingos_db.get_sessions_for_day(connection, training_date)
    issues: list[QualityIssue] = []
    active_set_count = 0

    if not sessions:
        issues.append(
            QualityIssue(
                code="training_day_missing",
                severity="blocker",
                message="No completed training session exists for the requested date.",
                context={"training_date": training_date},
            )
        )

    for session in sessions:
        seen_orders: set[int] = set()
        for set_log in session.get("sets", []):
            if is_rest_set(set_log):
                continue
            active_set_count += 1
            context = {
                "session_id": session.get("id"),
                "set_id": set_log.get("id"),
                "set_order": set_log.get("set_order"),
                "exercise": set_log.get("exercise_name"),
            }
            set_order = set_log.get("set_order")
            if not isinstance(set_order, int) or set_order <= 0:
                issues.append(QualityIssue("invalid_set_order", "blocker", "Active set order must be positive.", context))
            elif set_order in seen_orders:
                issues.append(QualityIssue("duplicate_set_order", "blocker", "Set order is duplicated within a session.", context))
            else:
                seen_orders.add(set_order)

            exercise_name = str(set_log.get("exercise_name") or "").strip()
            if not exercise_name or exercise_name.lower() == "unknown exercise":
                issues.append(QualityIssue("unknown_exercise", "blocker", "Exercise must be corrected before analysis.", context))

            reps = set_log.get("reps")
            if reps is None:
                issues.append(QualityIssue("missing_reps", "blocker", "Active set is missing repetitions.", context))
            elif not isinstance(reps, int) or reps <= 0:
                issues.append(QualityIssue("invalid_reps", "blocker", "Active set repetitions must be positive.", context))

            weight = set_log.get("weight_kg")
            if weight is None:
                issues.append(
                    QualityIssue(
                        "missing_weight",
                        "warning",
                        "Weight is missing; confirm whether this is a bodyweight exercise.",
                        context,
                    )
                )
            elif not isinstance(weight, (int, float)) or weight < 0 or weight > MAX_REASONABLE_WEIGHT_KG:
                issues.append(QualityIssue("abnormal_weight", "blocker", "Weight is outside the accepted kilogram range.", context))

    if sessions and active_set_count == 0:
        issues.append(
            QualityIssue(
                code="active_sets_missing",
                severity="blocker",
                message="Training day contains no active sets.",
                context={"training_date": training_date},
            )
        )

    blockers = [issue for issue in issues if issue.severity == "blocker"]
    return {
        "training_date": training_date,
        "session_count": len(sessions),
        "set_count": sum(len(session.get("sets", [])) for session in sessions),
        "active_set_count": active_set_count,
        "analysis_ready": not blockers,
        "issues": [issue.to_dict() for issue in issues],
    }


def get_recovery_metric(connection: Any, recovery_date: str) -> dict[str, Any] | None:
    row = connection.execute(
        """
        select *
        from daily_recovery_metrics
        where athlete_id = ? and metric_date = ?
        order by created_at desc
        limit 1
        """,
        (trainingos_db.DEFAULT_ATHLETE_ID, recovery_date),
    ).fetchone()
    return dict(row) if row else None


def evaluate_recovery(connection: Any, recovery_date: str) -> dict[str, Any]:
    metric = get_recovery_metric(connection, recovery_date)
    issues: list[QualityIssue] = []
    if metric is None:
        issues.append(
            QualityIssue(
                code="recovery_missing",
                severity="blocker",
                message="No recovery record exists for the target date.",
                context={"recovery_date": recovery_date},
            )
        )
    else:
        available_fields = [field_name for field_name in RECOVERY_DECISION_FIELDS if metric.get(field_name) is not None]
        if not available_fields:
            issues.append(
                QualityIssue(
                    code="recovery_empty",
                    severity="blocker",
                    message="Recovery record contains no decision-grade metrics.",
                    context={"recovery_date": recovery_date},
                )
            )
        for field_name, (minimum, maximum) in RECOVERY_RANGES.items():
            value = metric.get(field_name)
            if value is None:
                continue
            if not isinstance(value, (int, float)) or value < minimum or value > maximum:
                issues.append(
                    QualityIssue(
                        code="recovery_value_out_of_range",
                        severity="blocker",
                        message=f"Recovery field {field_name} is outside the accepted range.",
                        context={"recovery_date": recovery_date, "field": field_name, "value": value},
                    )
                )

    blockers = [issue for issue in issues if issue.severity == "blocker"]
    return {
        "recovery_date": recovery_date,
        "recovery_ready": not blockers,
        "available_fields": (
            [field_name for field_name in RECOVERY_DECISION_FIELDS if metric and metric.get(field_name) is not None]
        ),
        "issues": [issue.to_dict() for issue in issues],
    }


def build_quality_report(connection: Any, training_date: str, recovery_date: str | None = None) -> dict[str, Any]:
    training = evaluate_training_day(connection, training_date)
    recovery = evaluate_recovery(connection, recovery_date) if recovery_date else None
    report = {
        "version": "trainingos.quality_report.v1",
        "training": training,
        "recovery": recovery,
        "analysis_ready": training["analysis_ready"],
        "finalization_ready": bool(training["analysis_ready"] and recovery and recovery["recovery_ready"]),
    }
    trainingos_observability.record_event(
        "data_quality_evaluated",
        details={
            "training_date": training_date,
            "recovery_date": recovery_date,
            "analysis_ready": report["analysis_ready"],
            "finalization_ready": report["finalization_ready"],
            "training_issue_count": len(training["issues"]),
            "recovery_issue_count": len(recovery["issues"]) if recovery else 0,
        },
    )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate TrainingOS data quality before analysis or plan finalization.")
    parser.add_argument("--date", required=True, help="Completed training date in YYYY-MM-DD format.")
    parser.add_argument("--recovery-date", help="Recovery date required for final plan readiness.")
    parser.add_argument("--db", default=str(trainingos_db.DEFAULT_DB_PATH), help="SQLite database path.")
    parser.add_argument("--output", help="Optional path for the JSON quality report.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    trainingos_db.init_db(Path(args.db))
    with trainingos_db.connect(Path(args.db)) as connection:
        report = build_quality_report(connection, args.date, args.recovery_date)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    required_ready = report["finalization_ready"] if args.recovery_date else report["analysis_ready"]
    return 0 if required_ready else 2


if __name__ == "__main__":
    sys.exit(main())
