#!/usr/bin/env python3
"""Import historical garmin-data-export cache or compact text into TrainingOS."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    from . import garmin_activity_import, garmin_import, trainingos_db
except ImportError:  # pragma: no cover - supports direct script execution.
    import garmin_activity_import  # type: ignore
    import garmin_import  # type: ignore
    import trainingos_db  # type: ignore


SOURCE_TOOL = "garmin-data-export"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "exports" / "garmin" / "normalized" / "historical_import_report.json"
SECTION_NAMES = (
    "Profile",
    "Daily Health",
    "Activities",
    "Body Composition",
    "Training Metrics",
    "Goals and Records",
    "Trends",
    "Golf",
    "Gear",
    "Training Plans",
    "Workouts",
    "Hydration",
    "Nutrition",
    "Women's Health",
)

DAILY_DISPLAY_TO_KEY = {
    "Daily Summary": "summary",
    "Sleep": "sleep",
    "Heart Rate Variability": "hrv",
    "Body Battery": "body_battery",
    "Training Readiness": "training_readiness",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def section_payloads(text: str, section: str, opening: str) -> list[Any]:
    title = re.compile(rf"(?m)^{re.escape(section)}(?: \(Part[^\n]*\))?\s*$")
    decoded: list[Any] = []
    decoder = json.JSONDecoder()
    for match in title.finditer(text):
        start = match.end()
        later_sections = [
            candidate.start()
            for name in SECTION_NAMES
            for candidate in re.finditer(rf"(?m)^{re.escape(name)}(?: \(Part[^\n]*\))?\s*$", text[start:])
            if candidate.start() > 0
        ]
        end = start + min(later_sections) if later_sections else len(text)
        block = text[start:end]
        schema_position = block.find("Schema:")
        search_from = schema_position if schema_position >= 0 else 0
        json_position = block.find(opening, search_from)
        if json_position < 0:
            continue
        try:
            payload, _ = decoder.raw_decode(block[json_position:])
        except json.JSONDecodeError:
            continue
        decoded.append(payload)
    return decoded


def discover_cache(export_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cache_root = export_root / ".cache" if (export_root / ".cache").exists() else export_root
    daily: list[dict[str, Any]] = []
    activities: list[dict[str, Any]] = []
    daily_dir = cache_root / "daily"
    activity_dir = cache_root / "activities"
    if daily_dir.exists():
        for path in sorted(daily_dir.glob("[0-9][0-9][0-9][0-9]-*.json")):
            payload = read_json(path)
            if isinstance(payload, dict):
                daily.append({"date": path.stem, "data": payload})
    if activity_dir.exists():
        for path in sorted(activity_dir.glob("*.json")):
            payload = read_json(path)
            if isinstance(payload, dict):
                activities.append(payload)
    return daily, activities


def discover_compact_text(export_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    files = [export_root] if export_root.is_file() else sorted(export_root.glob("garmin_export_*.txt"))
    days_by_date: dict[str, dict[str, Any]] = {}
    activities_by_id: dict[str, dict[str, Any]] = {}
    for path in files:
        text = path.read_text(encoding="utf-8")
        for payload in section_payloads(text, "Daily Health", "{"):
            if not isinstance(payload, dict):
                continue
            for date_text, day in payload.items():
                if isinstance(day, dict):
                    days_by_date[str(date_text)] = day
        for payload in section_payloads(text, "Activities", "["):
            if not isinstance(payload, list):
                continue
            for activity in payload:
                if not isinstance(activity, dict):
                    continue
                summary = activity.get("summary") or {}
                activity_id = garmin_activity_import.activity_id(summary)
                key = activity_id or json.dumps(summary, sort_keys=True, default=str)
                activities_by_id[key] = activity
    return (
        [{"date": date_text, "data": data} for date_text, data in sorted(days_by_date.items())],
        list(activities_by_id.values()),
    )


def discover(export_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    if export_path.is_dir():
        daily, activities = discover_cache(export_path)
        if daily or activities:
            return daily, activities, "json_cache"
    daily, activities = discover_compact_text(export_path)
    return daily, activities, "compact_text"


def recovery_envelope(item: dict[str, Any]) -> dict[str, Any]:
    data = item["data"]
    normalized_keys = {
        DAILY_DISPLAY_TO_KEY.get(str(key), str(key)): value for key, value in data.items()
    }

    def wrapped(key: str) -> dict[str, Any]:
        value = normalized_keys.get(key)
        return {
            "ok": value is not None,
            "source_method": f"{SOURCE_TOOL}:{key}",
            "data": value,
        }

    return {
        "date": item["date"],
        "stats": wrapped("summary"),
        "sleep": wrapped("sleep"),
        "hrv": wrapped("hrv"),
        "body_battery": wrapped("body_battery"),
        "training_readiness": wrapped("training_readiness"),
    }


def normalize_recovery(item: dict[str, Any]) -> dict[str, Any]:
    normalized = garmin_import.normalize_day(recovery_envelope(item))
    normalized["source_tool"] = SOURCE_TOOL
    return normalized


def normalize_activity(item: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "summary": item.get("summary") or {},
        "details": item.get("detail") or item.get("details") or {},
        "exercise_sets": item.get("exercise_sets"),
    }
    normalized = garmin_activity_import.normalize_activity(payload)
    normalized["source_tool"] = SOURCE_TOOL
    return normalized


def import_export(
    export_path: Path,
    db_path: Path,
    *,
    strength_only: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    daily_raw, activity_raw, format_name = discover(export_path)
    recovery = [normalize_recovery(item) for item in daily_raw]
    selected_activity_raw = activity_raw
    if strength_only:
        selected_activity_raw = [
            item
            for item in activity_raw
            if garmin_activity_import.is_strength_activity(item.get("summary") or {})
        ]
    activities = [normalize_activity(item) for item in selected_activity_raw]
    active_sets = [
        set_log
        for activity in activities
        for set_log in activity.get("sets", [])
        if str(set_log.get("set_type", "")).lower() != "rest"
    ]
    report: dict[str, Any] = {
        "status": "preview" if dry_run else "completed",
        "source_tool": SOURCE_TOOL,
        "format": format_name,
        "recovery_records": len(recovery),
        "activity_records": len(activities),
        "set_count": sum(len(item.get("sets", [])) for item in activities),
        "active_sets": len(active_sets),
        "missing_reps": sum(item.get("reps") is None for item in active_sets),
        "abnormal_weight": sum(
            isinstance(item.get("weight_kg"), (int, float)) and item["weight_kg"] > 1000
            for item in active_sets
        ),
        "contains_personal_values": False,
    }
    if dry_run:
        return report
    trainingos_db.init_db(db_path)
    with trainingos_db.connect(db_path) as connection:
        for metric in recovery:
            trainingos_db.upsert_daily_recovery_metric(connection, metric)
        for activity in activities:
            trainingos_db.save_imported_workout(connection, activity)
        report["stored_recovery_records"] = connection.execute(
            "select count(*) from daily_recovery_metrics where provider = 'garmin'"
        ).fetchone()[0]
        report["stored_activity_records"] = connection.execute(
            "select count(*) from completed_sessions where provider = 'garmin'"
        ).fetchone()[0]
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import a garmin-data-export directory or compact text file.")
    parser.add_argument("path", help="Export directory, .cache directory, or compact/split .txt file.")
    parser.add_argument("--db", default=str(trainingos_db.DEFAULT_DB_PATH))
    parser.add_argument("--include-all-activities", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", default=str(DEFAULT_REPORT))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = import_export(
        Path(args.path),
        Path(args.db),
        strength_only=not args.include_all_activities,
        dry_run=args.dry_run,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Report: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
