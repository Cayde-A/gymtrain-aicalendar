#!/usr/bin/env python3
"""Run a value-free gccli parity check against current normalized exports."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

try:
    from . import garmin_activity_import, garmin_import, garmin_provider
    from .garmin_provider import GarminProviderError
    from .gccli_adapter import GccliAdapter
except ImportError:  # pragma: no cover - supports direct execution.
    import garmin_activity_import  # type: ignore
    import garmin_import  # type: ignore
    import garmin_provider  # type: ignore
    from garmin_provider import GarminProviderError  # type: ignore
    from gccli_adapter import GccliAdapter  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECOVERY = ROOT / "exports" / "garmin" / "normalized" / "daily_recovery_metrics.json"
DEFAULT_ACTIVITIES = ROOT / "exports" / "garmin" / "normalized" / "completed_activities.json"
DEFAULT_REPORT = ROOT / "exports" / "garmin" / "normalized" / "gccli_parity_report.json"
RECOVERY_FIELDS = tuple(garmin_import.NORMALIZED_FIELDS)
ACTIVITY_FIELDS = (
    "activity_name",
    "started_at",
    "duration_seconds",
    "average_heart_rate",
    "max_heart_rate",
    "calories",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare gccli reads with TrainingOS normalized exports.")
    parser.add_argument("--account", default=None, help="Optional gccli account email.")
    parser.add_argument("--activities", type=int, default=2, help="Recent strength activities to compare.")
    parser.add_argument("--days", type=int, default=7, help="Recovery days to compare.")
    parser.add_argument("--end-date", default=dt.date.today().isoformat(), help="Last recovery date.")
    parser.add_argument("--workout", required=True, help="Workout JSON to validate without uploading.")
    parser.add_argument("--current-recovery", default=str(DEFAULT_RECOVERY))
    parser.add_argument("--current-activities", default=str(DEFAULT_ACTIVITIES))
    parser.add_argument(
        "--live-python-baseline",
        action="store_true",
        help="Read the same window through python-garminconnect without saving raw values.",
    )
    parser.add_argument("--output", default=str(DEFAULT_REPORT))
    return parser.parse_args()


def load_list(path: str | Path) -> list[dict[str, Any]]:
    payload_path = Path(path)
    if not payload_path.exists():
        return []
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


def equality_counts(
    current: list[dict[str, Any]],
    candidate: list[dict[str, Any]],
    key: str,
    fields: tuple[str, ...],
) -> dict[str, Any]:
    current_by_key = {str(item.get(key)): item for item in current if item.get(key) is not None}
    matched = 0
    field_matches = {field: 0 for field in fields}
    for item in candidate:
        baseline = current_by_key.get(str(item.get(key)))
        if baseline is None:
            continue
        matched += 1
        for field in fields:
            if item.get(field) == baseline.get(field):
                field_matches[field] += 1
    return {
        "matched_records": matched,
        "candidate_records": len(candidate),
        "baseline_records": len(current),
        "exact_field_matches": field_matches,
    }


def build_activity_candidates(adapter: GccliAdapter, limit: int) -> list[dict[str, Any]]:
    # Garmin rejects strength_training as a server-side activity type because it
    # is an activity sub-type. Keep the read bounded and filter with the same
    # TrainingOS rule used by the primary importer.
    summaries = adapter.activities(limit=max(20, limit * 5))
    if not isinstance(summaries, list):
        return []
    normalized: list[dict[str, Any]] = []
    strength_summaries = [
        summary
        for summary in summaries
        if isinstance(summary, dict) and garmin_activity_import.is_strength_activity(summary)
    ]
    for summary in strength_summaries[:limit]:
        if not isinstance(summary, dict):
            continue
        external_id = garmin_activity_import.activity_id(summary)
        if external_id is None:
            continue
        details = adapter.activity_details(external_id)
        sets = adapter.activity_sets(external_id)
        normalized.append(
            garmin_activity_import.normalize_activity(
                {"summary": summary, "details": details, "exercise_sets": sets}
            )
        )
    return normalized


def build_recovery_candidates(adapter: GccliAdapter, end_date: str, days: int) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for day in garmin_import.date_range(end_date, days):
        metric = garmin_import.normalize_day(adapter.recovery_day(day.isoformat()))
        metric["source_tool"] = "gccli"
        normalized.append(metric)
    return normalized


def build_live_python_baseline(
    end_date: str, days: int, activity_limit: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    client = garmin_provider.login(None, None, garmin_provider.default_tokenstore())
    end = dt.date.fromisoformat(end_date)
    start = end - dt.timedelta(days=89)
    summaries = garmin_activity_import.fetch_activities(
        client, start.isoformat(), end.isoformat(), None
    )
    strength = [item for item in summaries if garmin_activity_import.is_strength_activity(item)]
    activities = [
        garmin_activity_import.normalize_activity(
            garmin_activity_import.fetch_activity_payload(client, summary)
        )
        for summary in strength[:activity_limit]
    ]
    recovery = [
        garmin_import.normalize_day(garmin_import.fetch_day(client, day))
        for day in garmin_import.date_range(end_date, days)
    ]
    return activities, recovery


def data_quality_summary(activities: list[dict[str, Any]]) -> dict[str, int]:
    sets = [item for activity in activities for item in activity.get("sets", [])]
    active_sets = [item for item in sets if str(item.get("set_type", "")).lower() != "rest"]
    return {
        "completed_sessions": len(activities),
        "set_count": len(sets),
        "active_sets": len(active_sets),
        "missing_reps": sum(item.get("reps") is None for item in active_sets),
        "abnormal_weight": sum(
            isinstance(item.get("weight_kg"), (int, float)) and item["weight_kg"] > 1000
            for item in active_sets
        ),
    }


def run(args: argparse.Namespace, adapter: GccliAdapter | None = None) -> tuple[int, dict[str, Any]]:
    adapter = adapter or GccliAdapter(account=args.account)
    try:
        adapter.auth_status()
        activities = build_activity_candidates(adapter, args.activities)
        recovery = build_recovery_candidates(adapter, args.end_date, args.days)
        if getattr(args, "live_python_baseline", False):
            baseline_activities, baseline_recovery = build_live_python_baseline(
                args.end_date, args.days, args.activities
            )
        else:
            baseline_activities = load_list(args.current_activities)
            baseline_recovery = load_list(args.current_recovery)
    except GarminProviderError as exc:
        return 2, {
            "status": "blocked",
            "source_tool": "gccli",
            "error": exc.to_dict(),
            "contains_personal_values": False,
        }

    dry_run = adapter.dry_run_workout_file(args.workout)
    activity_parity = equality_counts(
        baseline_activities, activities, "external_activity_id", ACTIVITY_FIELDS
    )
    recovery_parity = equality_counts(
        baseline_recovery, recovery, "metric_date", RECOVERY_FIELDS
    )
    complete = (
        len(activities) == args.activities
        and len(recovery) == args.days
        and bool(dry_run.get("ok"))
        and (
            not getattr(args, "live_python_baseline", False)
            or (
                activity_parity["matched_records"] == args.activities
                and recovery_parity["matched_records"] == args.days
            )
        )
    )
    report = {
        "status": "passed" if complete else "failed",
        "source_tool": "gccli",
        "provider_version": adapter.version(),
        "contains_personal_values": False,
        "requested": {"activities": args.activities, "recovery_days": args.days},
        "baseline": "live_python_garminconnect"
        if getattr(args, "live_python_baseline", False)
        else "local_normalized_exports",
        "activity_quality": data_quality_summary(activities),
        "activity_parity": activity_parity,
        "recovery_parity": recovery_parity,
        "workout_dry_run": {
            "ok": bool(dry_run.get("ok")),
            "remote_write": False,
            "errors": dry_run.get("errors", []),
        },
    }
    return (0 if complete else 3), report


def main() -> int:
    args = parse_args()
    code, report = run(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"Report: {output}")
    return code


if __name__ == "__main__":
    sys.exit(main())
