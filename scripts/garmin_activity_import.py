#!/usr/bin/env python3
"""Import completed Garmin activities into TrainingOS local SQLite."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    from . import garmin_import, garmin_provider, trainingos_db, trainingos_observability
except ImportError:  # pragma: no cover - supports direct script execution.
    import garmin_import  # type: ignore
    import garmin_provider  # type: ignore
    import trainingos_db  # type: ignore
    import trainingos_observability  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
RAW_ACTIVITY_DIR = ROOT / "exports" / "garmin" / "raw" / "activities"
NORMALIZED_ACTIVITY_DIR = ROOT / "exports" / "garmin" / "normalized"
SET_FIELD_MAPPINGS = {
    "exercise_name": ["exerciseName", "exercise", "name", "exercises[].category"],
    "set_order": ["setOrder", "orderNumber", "setNumber"],
    "set_type": ["setType", "type"],
    "weight_kg": ["weight", "weightKg", "weightInKg", "weightKilograms"],
    "reps": ["reps", "repetitions", "repCount", "repetitionCount"],
    "rpe": ["rpe", "ratingOfPerceivedExertion"],
}
ACTIVITY_FIELD_MAPPINGS = {
    "external_activity_id": ["activityId", "activity_id", "id"],
    "activity_name": ["activityName", "activity_name", "name"],
    "started_at": ["startTimeLocal", "startTimeGMT", "startTime"],
    "duration_seconds": ["duration", "durationSeconds", "elapsedDuration"],
    "average_heart_rate": ["averageHR", "averageHeartRate", "avgHR"],
    "max_heart_rate": ["maxHR", "maxHeartRate"],
    "calories": ["calories", "caloriesConsumed", "activeKilocalories"],
}


def default_tokenstore() -> str:
    return str(garmin_provider.default_tokenstore())


def parse_args() -> argparse.Namespace:
    garmin_provider.load_dotenv_local()
    parser = argparse.ArgumentParser(description="Import completed Garmin activities into local SQLite.")
    parser.add_argument("--email", default=os.getenv("GARMIN_EMAIL"), help="Garmin email.")
    parser.add_argument("--password", default=os.getenv("GARMIN_PASSWORD"), help="Garmin password.")
    parser.add_argument(
        "--tokenstore",
        default=default_tokenstore(),
        help="Local Garmin token cache directory.",
    )
    parser.add_argument(
        "--read-provider",
        choices=("auto", "personal", "legacy"),
        default=os.getenv("GARMIN_READ_PROVIDER", "auto"),
        help="Garmin read transport. Auto prefers the official Personal API when a key is configured.",
    )
    parser.add_argument(
        "--personal-api-key-file",
        default=os.getenv("GARMIN_PERSONAL_API_KEY_FILE"),
        help="Optional Garmin Personal API key file.",
    )
    parser.add_argument("--db", default=str(trainingos_db.DEFAULT_DB_PATH), help="SQLite database path.")
    parser.add_argument("--days", type=int, default=7, help="Number of recent days to search.")
    parser.add_argument("--end-date", default=dt.date.today().isoformat(), help="Last date in YYYY-MM-DD format.")
    parser.add_argument("--activity-type", default=None, help="Optional Garmin activity type filter.")
    parser.add_argument("--strength-only", action="store_true", help="Keep only activities that look like strength training.")
    parser.add_argument("--limit", type=int, default=5, help="Maximum activities to import.")
    parser.add_argument("--include-raw", action="store_true", help="Save raw activity payloads locally.")
    return parser.parse_args()


def pick(payload: dict[str, Any], names: list[str]) -> Any:
    for name in names:
        if name in payload and payload[name] is not None:
            return payload[name]
    return None


def activity_id(activity: dict[str, Any]) -> str | None:
    value = pick(activity, ["activityId", "activity_id", "id"])
    return str(value) if value is not None else None


def activity_type_key(activity: dict[str, Any]) -> str:
    value = pick(activity, ["activityType", "activity_type", "type"])
    if isinstance(value, dict):
        return str(pick(value, ["typeKey", "type_key", "key", "displayName"]) or "unknown")
    if isinstance(value, str):
        return value
    return "unknown"


def is_strength_activity(activity: dict[str, Any]) -> bool:
    text = " ".join(
        str(value).lower()
        for value in [
            activity.get("activityName"),
            activity.get("activityType"),
            activity_type_key(activity),
        ]
    )
    return "strength" in text or "weight" in text


def fetch_activities(client: Any, start_date: str, end_date: str, activity_type: str | None) -> list[dict[str, Any]]:
    candidates = []
    if activity_type:
        candidates.append(("get_activities_by_date", (start_date, end_date, activity_type)))
    candidates.append(("get_activities_by_date", (start_date, end_date)))
    result = garmin_import.call_first_available(client, candidates)
    if not result.get("ok"):
        raise RuntimeError(f"Unable to fetch activities: {result.get('failures')}")
    data = result.get("data") or []
    if isinstance(data, dict):
        data = data.get("activityList") or data.get("activities") or []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def fetch_activity_payload(client: Any, activity: dict[str, Any]) -> dict[str, Any]:
    external_id = activity_id(activity)
    details = None
    exercise_sets = None
    if external_id:
        details_result = garmin_import.call_first_available(
            client,
            [
                ("get_activity", (external_id,)),
                ("get_activity_details", (external_id,)),
            ],
        )
        if details_result.get("ok"):
            details = details_result.get("data")
        sets_result = garmin_import.call_first_available(
            client,
            [
                ("get_activity_exercise_sets", (external_id,)),
            ],
        )
        if sets_result.get("ok"):
            exercise_sets = sets_result.get("data")
        if isinstance(details, dict):
            summarized_sets = (
                details.get("summarizedExerciseSets")
                or details.get("exerciseSets")
                or details.get("activityExerciseSets")
            )
            if summarized_sets:
                exercise_sets = summarized_sets
    return {
        "source_tool": garmin_provider.client_source_tool(client),
        "summary": activity,
        "details": details,
        "exercise_sets": exercise_sets,
    }


def first_number(payload: Any, names: set[str]) -> float | int | None:
    return garmin_import.deep_find_number(payload, names)


def first_string(payload: Any, names: set[str]) -> str | None:
    return garmin_import.deep_find_string(payload, names)


def exercise_name_from_set(item: dict[str, Any], fallback_name: str | None) -> str:
    direct_name = first_string(item, {"exercisename", "exercise", "name"})
    if direct_name:
        return direct_name
    exercises = item.get("exercises")
    if isinstance(exercises, list):
        for exercise in exercises:
            if not isinstance(exercise, dict):
                continue
            candidate = first_string(exercise, {"exercisename", "exercise", "name", "category"})
            if candidate and candidate.upper() != "UNKNOWN":
                return candidate
    category = first_string(item, {"category"})
    if category:
        return category
    return fallback_name or "Unknown Exercise"


def normalize_weight_kg(value: float | int | None) -> float | int | None:
    if value is None:
        return None
    # Garmin strength exercise sets may return grams even though the field is named "weight".
    if value >= 1000:
        return round(value / 1000, 3)
    return value


def mapped_names(field: str) -> set[str]:
    names = SET_FIELD_MAPPINGS[field]
    return {name.lower().replace("_", "").replace("-", "").replace("[].", "") for name in names}


def mapped_activity_names(field: str) -> set[str]:
    names = ACTIVITY_FIELD_MAPPINGS[field]
    return {name.lower().replace("_", "").replace("-", "") for name in names}


def normalize_set_log(item: dict[str, Any], fallback_name: str | None, index: int) -> dict[str, Any]:
    weight = first_number(item, mapped_names("weight_kg"))
    reps = first_number(item, mapped_names("reps"))
    return {
        "exercise_name": exercise_name_from_set(item, fallback_name),
        "set_order": int(first_number(item, mapped_names("set_order")) or index),
        "set_type": first_string(item, mapped_names("set_type")) or "working",
        "weight_kg": normalize_weight_kg(weight),
        "reps": int(reps) if isinstance(reps, (int, float)) else None,
        "rpe": first_number(item, mapped_names("rpe")),
        "is_top_set": False,
        "notes": None,
    }


def extract_sets(exercise_sets: Any, fallback_name: str | None) -> list[dict[str, Any]]:
    if isinstance(exercise_sets, dict):
        candidates = (
            exercise_sets.get("exerciseSets")
            or exercise_sets.get("activityExerciseSets")
            or exercise_sets.get("sets")
            or exercise_sets.get("data")
        )
    else:
        candidates = exercise_sets
    if not isinstance(candidates, list):
        return []

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(candidates, start=1):
        if not isinstance(item, dict):
            continue
        normalized.append(normalize_set_log(item, fallback_name, index))
    return normalized


def normalize_activity(payload: dict[str, Any], raw_payload_path: str | None = None) -> dict[str, Any]:
    summary = payload.get("summary") or {}
    details = payload.get("details") or {}
    merged = {"summary": summary, "details": details}
    name = pick(summary, ["activityName", "activity_name", "name"]) or pick(details, ["activityName", "name"])
    external_id = activity_id(summary) or activity_id(details)
    started_at = (
        pick(summary, ["startTimeLocal", "startTimeGMT", "startTime"])
        or pick(details, ["startTimeLocal", "startTimeGMT", "startTime"])
    )
    completed_at = started_at or dt.datetime.now().isoformat(timespec="seconds")
    sets = extract_sets(payload.get("exercise_sets"), str(name) if name else None)
    return {
        "provider": "garmin",
        "source_tool": payload.get("source_tool", garmin_provider.SOURCE_TOOL),
        "external_activity_id": external_id,
        "started_at": started_at,
        "completed_at": completed_at,
        "session_type": activity_type_key(summary),
        "activity_name": name,
        "duration_seconds": first_number(merged, mapped_activity_names("duration_seconds")),
        "average_heart_rate": first_number(merged, mapped_activity_names("average_heart_rate")),
        "max_heart_rate": first_number(merged, mapped_activity_names("max_heart_rate")),
        "calories": first_number(merged, mapped_activity_names("calories")),
        "raw_payload_path": raw_payload_path,
        "sets": sets,
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    end = dt.date.fromisoformat(args.end_date)
    start = end - dt.timedelta(days=max(args.days - 1, 0))
    trainingos_observability.record_event(
        "garmin_activity_import_started",
        details={
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "limit": args.limit,
            "activity_type": args.activity_type,
            "strength_only": args.strength_only,
        },
    )
    print(f"TrainingOS import: logging in and reading Garmin activities from {start.isoformat()} to {end.isoformat()}.")
    client = garmin_provider.login_read(
        args.email,
        args.password,
        args.tokenstore,
        provider=args.read_provider,
        personal_api_key_file=args.personal_api_key_file,
    )
    trainingos_observability.record_event(
        "garmin_login_completed",
        details=garmin_provider.provider_metadata(client),
    )
    activities = fetch_activities(client, start.isoformat(), end.isoformat(), args.activity_type)
    fetched_count = len(activities)
    if args.strength_only:
        activities = [activity for activity in activities if is_strength_activity(activity)]
    filtered_count = len(activities)
    activities = activities[: args.limit]
    trainingos_observability.record_event(
        "garmin_activities_fetched",
        details={
            "fetched_count": fetched_count,
            "filtered_count": filtered_count,
            "selected_count": len(activities),
        },
    )
    print(f"TrainingOS import: fetched {fetched_count}, selected {len(activities)} for local import.")

    trainingos_db.init_db(Path(args.db))
    imported: list[dict[str, Any]] = []
    with trainingos_db.connect(Path(args.db)) as connection:
        for activity in activities:
            external_id = activity_id(activity) or trainingos_db.new_id("activity")
            trainingos_observability.record_event(
                "garmin_activity_payload_fetch_started",
                details={
                    "external_activity_id": external_id,
                    "activity_name": activity.get("activityName"),
                },
            )
            payload = fetch_activity_payload(client, activity)
            raw_path = None
            if args.include_raw:
                raw_path_obj = RAW_ACTIVITY_DIR / f"activity_{external_id}.json"
                write_json(raw_path_obj, payload)
                raw_path = str(raw_path_obj)
            normalized = normalize_activity(payload, raw_path)
            session_id = trainingos_db.save_imported_workout(connection, normalized)
            normalized["local_session_id"] = session_id
            imported.append(normalized)
            trainingos_observability.record_event(
                "garmin_activity_imported",
                details={
                    "external_activity_id": external_id,
                    "local_session_id": session_id,
                    "activity_name": normalized.get("activity_name"),
                    "set_count": len(normalized.get("sets", [])),
                },
            )

    write_json(NORMALIZED_ACTIVITY_DIR / "completed_activities.json", imported)
    trainingos_observability.record_event(
        "garmin_activity_import_completed",
        details={"imported_count": len(imported), "db_path": args.db},
    )
    print(f"Imported {len(imported)} Garmin completed activities into local SQLite.")
    print(f"Database: {args.db}")
    print(f"Normalized output: {NORMALIZED_ACTIVITY_DIR / 'completed_activities.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
