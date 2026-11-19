#!/usr/bin/env python3
"""TrainingOS Garmin local import MVP.

This script performs an interactive Garmin Connect login, fetches recent daily
metrics through python-garminconnect when available, and writes:

- exports/garmin/raw/*.json
- exports/garmin/normalized/daily_recovery_metrics.json

It intentionally avoids storing credentials. Token/cache behavior is delegated
to the Garmin library version in use.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    from .garmin_provider import (
        DEFAULT_TOKENSTORE,
        call_first_available,
        has_tokens,
        import_garmin_client,
        load_dotenv_local,
        login,
        login_read,
        client_source_tool,
        provider_metadata,
    )
except ImportError:  # pragma: no cover - supports direct script execution.
    from garmin_provider import (  # type: ignore
        DEFAULT_TOKENSTORE,
        call_first_available,
        has_tokens,
        import_garmin_client,
        load_dotenv_local,
        login,
        login_read,
        client_source_tool,
        provider_metadata,
    )


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "exports" / "garmin" / "raw"
NORMALIZED_DIR = ROOT / "exports" / "garmin" / "normalized"
DAILY_HEALTH_DETAILS_PATH = NORMALIZED_DIR / "daily_health_details.json"
NORMALIZED_FIELDS = [
    "sleep_score",
    "sleep_duration_minutes",
    "hrv_status",
    "resting_heart_rate",
    "body_battery",
    "stress_score",
    "training_readiness",
    "recovery_time_hours",
    "steps",
    "calories",
]

FIELD_MAPPINGS = {
    "sleep_score": [
        "sleep.dailySleepDTO.sleepScores.overall.value",
        "sleep.sleepScores.overall.value",
    ],
    "sleep_duration_minutes": [
        "sleep.dailySleepDTO.sleepTimeSeconds",
        "sleep.sleepTimeSeconds",
    ],
    "hrv_status": [
        "hrv.hrvSummary.status",
    ],
    "resting_heart_rate": [
        "stats.restingHeartRate",
        "stats.data[].heartRate.restingValue",
        "stats[].heartRate.restingValue",
    ],
    "body_battery": [
        "stats.bodyBatteryMostRecentValue",
        "stats.data[].bodyBattery.latestValue",
        "stats[].bodyBattery.latestValue",
        "body_battery[].bodyBatteryValuesArray[][]",
    ],
    "stress_score": [
        "stats.averageStressLevel",
        "stats.data[].stress.avgLevel",
        "stats[].stress.avgLevel",
    ],
    "training_readiness": [
        "training_readiness[].score",
    ],
    "recovery_time_hours": [
        "training_readiness[].recoveryTime",
    ],
    "steps": [
        "stats.totalSteps",
        "stats.data[].movement.steps.value",
        "stats[].movement.steps.value",
    ],
    "calories": [
        "stats.totalKilocalories",
        "stats.data[].calories.burnedTotal",
        "stats[].calories.burnedTotal",
    ],
}


def parse_args() -> argparse.Namespace:
    load_dotenv_local()
    parser = argparse.ArgumentParser(description="Import Garmin data for TrainingOS.")
    parser.add_argument("--email", default=os.getenv("GARMIN_EMAIL"), help="Garmin email. Defaults to GARMIN_EMAIL.")
    parser.add_argument("--password", default=os.getenv("GARMIN_PASSWORD"), help="Garmin password. Defaults to GARMIN_PASSWORD env var.")
    parser.add_argument(
        "--tokenstore",
        default=os.getenv("GARMINTOKENS", str(DEFAULT_TOKENSTORE)),
        help="Local Garmin token cache directory. Defaults to tokens/garmin.",
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
        help="Optional Garmin Personal API key file. The official default and environment variable are also supported.",
    )
    parser.add_argument("--days", type=int, default=7, help="Number of recent days to import.")
    parser.add_argument(
        "--end-date",
        default=dt.date.today().isoformat(),
        help="Last date to import in YYYY-MM-DD format. Defaults to today.",
    )
    parser.add_argument(
        "--include-raw",
        action="store_true",
        help="Save raw Garmin responses under exports/. This may contain private health data.",
    )
    parser.add_argument(
        "--write-db",
        action="store_true",
        help="Write normalized recovery metrics into the local SQLite database.",
    )
    parser.add_argument(
        "--db",
        default=str(ROOT / "data" / "trainingos.sqlite"),
        help="SQLite database path used with --write-db.",
    )
    return parser.parse_args()


def date_range(end_date: str, days: int) -> list[dt.date]:
    end = dt.date.fromisoformat(end_date)
    return [end - dt.timedelta(days=offset) for offset in reversed(range(days))]


def fetch_day(client: Any, metric_date: dt.date) -> dict[str, Any]:
    date_text = metric_date.isoformat()
    return {
        "date": date_text,
        "source_tool": client_source_tool(client),
        "stats": call_first_available(
            client,
            [
                ("get_stats", (date_text,)),
                ("get_user_summary", (date_text,)),
            ],
        ),
        "sleep": call_first_available(
            client,
            [
                ("get_sleep_data", (date_text,)),
                ("get_sleep", (date_text,)),
            ],
        ),
        "hrv": call_first_available(
            client,
            [
                ("get_hrv_data", (date_text,)),
                ("get_hrv", (date_text,)),
            ],
        ),
        "body_battery": call_first_available(
            client,
            [
                ("get_body_battery", (date_text,)),
                ("get_body_battery_events", (date_text,)),
            ],
        ),
        "training_readiness": call_first_available(
            client,
            [
                ("get_training_readiness", (date_text,)),
                ("get_training_readiness_data", (date_text,)),
            ],
        ),
    }


def fill_training_readiness_from_legacy(raw_days: list[dict[str, Any]], legacy_client: Any) -> int:
    updated = 0
    for raw in raw_days:
        if raw.get("training_readiness", {}).get("ok"):
            continue
        result = call_first_available(
            legacy_client,
            [
                ("get_training_readiness", (raw["date"],)),
                ("get_training_readiness_data", (raw["date"],)),
            ],
        )
        if not result.get("ok"):
            continue
        raw["training_readiness"] = result
        raw.setdefault("field_sources", {})["training_readiness"] = client_source_tool(
            legacy_client
        )
        updated += 1
    return updated


def deep_find_number(payload: Any, names: set[str]) -> float | int | None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            normalized_key = key.lower().replace("_", "").replace("-", "")
            if normalized_key in names and isinstance(value, (int, float)):
                return value
        for value in payload.values():
            found = deep_find_number(value, names)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = deep_find_number(item, names)
            if found is not None:
                return found
    return None


def deep_find_string(payload: Any, names: set[str]) -> str | None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            normalized_key = key.lower().replace("_", "").replace("-", "")
            if normalized_key in names and isinstance(value, str):
                return value
        for value in payload.values():
            found = deep_find_string(value, names)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = deep_find_string(item, names)
            if found is not None:
                return found
    return None


def body_battery_last_value(payload: Any) -> int | None:
    if not isinstance(payload, list):
        return None
    candidates: list[int] = []
    for day in payload:
        if not isinstance(day, dict):
            continue
        values = day.get("bodyBatteryValuesArray")
        if not isinstance(values, list):
            continue
        for item in values:
            if (
                isinstance(item, list)
                and len(item) >= 2
                and isinstance(item[1], int)
            ):
                candidates.append(item[1])
    return candidates[-1] if candidates else None


def value_at_path(payload: Any, path: str) -> Any:
    current = payload
    for part in path.split("."):
        if part.endswith("[]"):
            key = part[:-2]
            if isinstance(current, dict):
                current = current.get(key)
            if isinstance(current, list):
                current = current[0] if current else None
            else:
                return None
        else:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
    return current


def number_at_path(payload: Any, path: str) -> float | int | None:
    value = value_at_path(payload, path)
    if isinstance(value, (int, float)):
        return value
    return None


def string_at_path(payload: Any, path: str) -> str | None:
    value = value_at_path(payload, path)
    if isinstance(value, str):
        return value
    return None


def first_number(payload: Any, paths: list[str]) -> float | int | None:
    for path in paths:
        value = number_at_path(payload, path)
        if value is not None:
            return value
    return None


def first_string(payload: Any, paths: list[str]) -> str | None:
    for path in paths:
        value = string_at_path(payload, path)
        if value is not None:
            return value
    return None


def unwrap(result: dict[str, Any]) -> Any:
    if result.get("ok"):
        return result.get("data")
    return None


def minutes_from_seconds(value: Any) -> int | None:
    return round(value / 60) if isinstance(value, (int, float)) else None


def source_tool_for_day(raw: dict[str, Any]) -> str:
    field_sources = raw.get("field_sources") or {}
    source_tool = raw.get("source_tool", "python-garminconnect")
    return "+".join(dict.fromkeys([source_tool, *field_sources.values()]))


def normalize_health_details(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Normalize richer Garmin fields into stable, category-specific records."""
    payload = {
        "stats": unwrap(raw["stats"]),
        "sleep": unwrap(raw["sleep"]),
        "hrv": unwrap(raw["hrv"]),
        "training_readiness": unwrap(raw["training_readiness"]),
    }
    base = {
        "provider": "garmin",
        "source_tool": source_tool_for_day(raw),
        "metric_date": raw["date"],
    }

    def number(*paths: str) -> float | int | None:
        return first_number(payload, list(paths))

    def string(*paths: str) -> str | None:
        return first_string(payload, list(paths))

    def sleep_minutes(*names: str) -> int | None:
        paths = [f"sleep.{name}" for name in names]
        paths += [f"sleep.dailySleepDTO.{name}" for name in names]
        return minutes_from_seconds(first_number(payload, paths))

    return {
        "sleep": {
            **base,
            "deep_sleep_minutes": sleep_minutes("deepSleepSeconds"),
            "light_sleep_minutes": sleep_minutes("lightSleepSeconds"),
            "rem_sleep_minutes": sleep_minutes("remSleepSeconds"),
            "awake_minutes": sleep_minutes("awakeSleepSeconds", "awakeTimeSeconds"),
            "nap_minutes": sleep_minutes("napTimeSeconds"),
            "average_sleep_stress": number("sleep.avgSleepStress", "sleep.dailySleepDTO.avgSleepStress"),
            "average_sleep_heart_rate": number("sleep.avgHeartRate", "sleep.dailySleepDTO.avgHeartRate"),
            "average_spo2": number("sleep.averageSpO2Value", "sleep.dailySleepDTO.averageSpO2Value"),
            "minimum_spo2": number("sleep.lowestSpO2Value", "sleep.dailySleepDTO.lowestSpO2Value"),
            "maximum_spo2": number("sleep.highestSpO2Value", "sleep.dailySleepDTO.highestSpO2Value"),
            "average_respiration": number("sleep.averageRespirationValue", "sleep.dailySleepDTO.averageRespirationValue"),
            "minimum_respiration": number("sleep.lowestRespirationValue", "sleep.dailySleepDTO.lowestRespirationValue"),
            "maximum_respiration": number("sleep.highestRespirationValue", "sleep.dailySleepDTO.highestRespirationValue"),
            "sleep_need_minutes": number("sleep.sleepNeed.actual", "sleep.dailySleepDTO.sleepNeed.actual"),
        },
        "hrv": {
            **base,
            "status": string("hrv.hrvSummary.status"),
            "weekly_average_ms": number("hrv.hrvSummary.weeklyAvg"),
            "last_night_average_ms": number("hrv.hrvSummary.lastNightAvg"),
            "last_night_5min_high_ms": number("hrv.hrvSummary.lastNight5MinHigh"),
            "baseline_low_upper_ms": number("hrv.hrvSummary.baseline.lowUpper"),
            "baseline_balanced_low_ms": number("hrv.hrvSummary.baseline.balancedLow"),
            "baseline_balanced_upper_ms": number("hrv.hrvSummary.baseline.balancedUpper"),
            "baseline_marker": number("hrv.hrvSummary.baseline.markerValue"),
        },
        "energy": {
            **base,
            "body_battery_min": number("stats.data[].bodyBattery.minValue", "stats[].bodyBattery.minValue"),
            "body_battery_max": number("stats.data[].bodyBattery.maxValue", "stats[].bodyBattery.maxValue"),
            "body_battery_charged": number("stats.data[].bodyBattery.chargedValue", "stats[].bodyBattery.chargedValue"),
            "body_battery_drained": number("stats.data[].bodyBattery.drainedValue", "stats[].bodyBattery.drainedValue"),
            "body_battery_latest": number("stats.data[].bodyBattery.latestValue", "stats[].bodyBattery.latestValue"),
            "resting_calories": number("stats.data[].calories.burnedResting", "stats[].calories.burnedResting"),
            "active_calories": number("stats.data[].calories.burnedActive", "stats[].calories.burnedActive"),
            "total_calories": number("stats.data[].calories.burnedTotal", "stats[].calories.burnedTotal"),
            "steps": number("stats.data[].movement.steps.value", "stats[].movement.steps.value"),
            "floors_ascended": number("stats.data[].movement.floorsAscended.value", "stats[].movement.floorsAscended.value"),
            "floors_descended": number("stats.data[].movement.floorsDescended.value", "stats[].movement.floorsDescended.value"),
            "moderate_intensity_minutes": number("stats.data[].intensityMinutes.moderate", "stats[].intensityMinutes.moderate"),
            "vigorous_intensity_minutes": number("stats.data[].intensityMinutes.vigorous", "stats[].intensityMinutes.vigorous"),
        },
        "vitals": {
            **base,
            "heart_rate_min": number("stats.data[].heartRate.minValue", "stats[].heartRate.minValue"),
            "heart_rate_max": number("stats.data[].heartRate.maxValue", "stats[].heartRate.maxValue"),
            "heart_rate_resting": number("stats.data[].heartRate.restingValue", "stats[].heartRate.restingValue"),
            "stress_average": number("stats.data[].stress.avgLevel", "stats[].stress.avgLevel"),
            "stress_maximum": number("stats.data[].stress.maxLevel", "stats[].stress.maxLevel"),
            "respiration_average": number("stats.data[].respiration.avgValue", "stats[].respiration.avgValue"),
            "respiration_minimum": number("stats.data[].respiration.minValue", "stats[].respiration.minValue"),
            "respiration_maximum": number("stats.data[].respiration.maxValue", "stats[].respiration.maxValue"),
            "respiration_latest": number("stats.data[].respiration.latestValue", "stats[].respiration.latestValue"),
            "pulse_ox_average": number("stats.data[].pulseOx.avgValue", "stats[].pulseOx.avgValue"),
            "pulse_ox_minimum": number("stats.data[].pulseOx.minValue", "stats[].pulseOx.minValue"),
            "pulse_ox_latest": number("stats.data[].pulseOx.latestValue", "stats[].pulseOx.latestValue"),
        },
        "readiness": {
            **base,
            "score": number("training_readiness[].score"),
            "level": string("training_readiness[].level"),
            "sleep_score_factor_percent": number("training_readiness[].sleepScoreFactorPercent"),
            "recovery_time_factor_percent": number("training_readiness[].recoveryTimeFactorPercent"),
            "hrv_factor_percent": number("training_readiness[].hrvFactorPercent"),
            "acute_load_factor_percent": number("training_readiness[].acuteLoadFactorPercent"),
            "stress_history_factor_percent": number("training_readiness[].stressHistoryFactorPercent"),
            "sleep_history_factor_percent": number("training_readiness[].sleepHistoryFactorPercent"),
            "feedback_short": string("training_readiness[].feedbackShort"),
        },
    }


def normalize_day(raw: dict[str, Any]) -> dict[str, Any]:
    stats = unwrap(raw["stats"])
    sleep = unwrap(raw["sleep"])
    hrv = unwrap(raw["hrv"])
    body_battery = unwrap(raw["body_battery"])
    training_readiness = unwrap(raw["training_readiness"])
    mapped_payload = {
        "stats": stats,
        "sleep": sleep,
        "hrv": hrv,
        "body_battery": body_battery,
        "training_readiness": training_readiness,
    }

    sleep_seconds = first_number(mapped_payload, FIELD_MAPPINGS["sleep_duration_minutes"])
    if sleep_seconds is None:
        sleep_seconds = deep_find_number(sleep, {"sleeptimeseconds", "sleepdurationseconds"})
    sleep_minutes = round(sleep_seconds / 60) if isinstance(sleep_seconds, (int, float)) else None
    recovery_time = first_number(mapped_payload, FIELD_MAPPINGS["recovery_time_hours"])
    recovery_time_hours = round(recovery_time / 60, 2) if isinstance(recovery_time, (int, float)) else None
    if recovery_time_hours is None:
        recovery_time_hours = deep_find_number(stats, {"recoverytimehours"})

    field_sources = raw.get("field_sources") or {}
    source_tool = source_tool_for_day(raw)
    return {
        "provider": "garmin",
        "source_tool": source_tool,
        "field_sources": field_sources,
        "metric_date": raw["date"],
        "sleep_score": first_number(mapped_payload, FIELD_MAPPINGS["sleep_score"])
        or deep_find_number(sleep, {"overallscore", "sleepscore", "score"}),
        "sleep_duration_minutes": sleep_minutes,
        "hrv_status": first_string(mapped_payload, FIELD_MAPPINGS["hrv_status"])
        or deep_find_string(hrv, {"hrvstatus", "status"}),
        "resting_heart_rate": first_number(mapped_payload, FIELD_MAPPINGS["resting_heart_rate"])
        or deep_find_number(stats, {"restingheartrate", "restinghr"}),
        "body_battery": first_number(mapped_payload, FIELD_MAPPINGS["body_battery"][:3])
        or body_battery_last_value(body_battery)
        or deep_find_number(body_battery, {"bodybattery", "charged", "level"}),
        "stress_score": first_number(mapped_payload, FIELD_MAPPINGS["stress_score"])
        or deep_find_number(stats, {"averagestresslevel", "stressscore"}),
        "training_readiness": first_number(mapped_payload, FIELD_MAPPINGS["training_readiness"])
        or deep_find_number(training_readiness, {"score", "trainingreadinessscore"}),
        "recovery_time_hours": recovery_time_hours,
        "steps": first_number(mapped_payload, FIELD_MAPPINGS["steps"])
        or deep_find_number(stats, {"totalsteps", "steps"}),
        "calories": first_number(mapped_payload, FIELD_MAPPINGS["calories"])
        or deep_find_number(stats, {"totalcalories", "calories"}),
        "raw_available": {
            "stats": raw["stats"].get("ok", False),
            "sleep": raw["sleep"].get("ok", False),
            "hrv": raw["hrv"].get("ok", False),
            "body_battery": raw["body_battery"].get("ok", False),
            "training_readiness": raw["training_readiness"].get("ok", False),
        },
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def collect_schema_paths(payload: Any, prefix: str = "", limit: int = 300) -> list[dict[str, str]]:
    paths: list[dict[str, str]] = []

    def walk(value: Any, path: str) -> None:
        if len(paths) >= limit:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                if isinstance(child, (dict, list)):
                    walk(child, child_path)
                else:
                    paths.append({"path": child_path, "type": type(child).__name__})
        elif isinstance(value, list):
            paths.append({"path": f"{path}[]", "type": "list", "length": str(len(value))})
            if value:
                walk(value[0], f"{path}[]")
        else:
            paths.append({"path": path, "type": type(value).__name__})

    walk(payload, prefix)
    return paths


def build_schema_summary(raw_days: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "description": "Field-path/type summary only. Values are intentionally omitted.",
        "days": len(raw_days),
        "dates": [day.get("date") for day in raw_days],
        "sections": {},
    }
    if not raw_days:
        return summary

    first_day = raw_days[0]
    for section_name in ["stats", "sleep", "hrv", "body_battery", "training_readiness"]:
        result = first_day.get(section_name, {})
        section_summary = {
            "ok": bool(result.get("ok")),
            "source_method": result.get("source_method"),
            "paths": [],
            "failures": result.get("failures"),
        }
        if result.get("ok"):
            section_summary["paths"] = collect_schema_paths(result.get("data"), section_name)
        summary["sections"][section_name] = section_summary
    return summary


def build_mapping_coverage(normalized: list[dict[str, Any]]) -> dict[str, Any]:
    coverage = {
        field: {
            "filled": sum(1 for day in normalized if day.get(field) is not None),
            "total": len(normalized),
            "candidate_paths": FIELD_MAPPINGS.get(field, []),
        }
        for field in NORMALIZED_FIELDS
    }
    return {
        "description": "Coverage report for Garmin raw-to-TrainingOS field mapping.",
        "records": len(normalized),
        "dates": [day.get("metric_date") for day in normalized],
        "fields": coverage,
    }


def main() -> int:
    args = parse_args()
    client = login_read(
        args.email,
        args.password,
        args.tokenstore,
        provider=args.read_provider,
        personal_api_key_file=args.personal_api_key_file,
    )
    raw_days = [fetch_day(client, day) for day in date_range(args.end_date, args.days)]
    readiness_fallback_count = 0
    tokenstore = Path(args.tokenstore).expanduser()
    if (
        client_source_tool(client) == "garmin-connect-personal-api-python"
        and any(not day["training_readiness"].get("ok") for day in raw_days)
        and has_tokens(tokenstore)
    ):
        try:
            legacy_client = login(args.email, args.password, tokenstore)
            readiness_fallback_count = fill_training_readiness_from_legacy(
                raw_days, legacy_client
            )
        except Exception:
            readiness_fallback_count = 0
    normalized = [normalize_day(day) for day in raw_days]
    health_details = [normalize_health_details(day) for day in raw_days]

    NORMALIZED_DIR.mkdir(parents=True, exist_ok=True)
    write_json(NORMALIZED_DIR / "daily_recovery_metrics.json", normalized)
    write_json(DAILY_HEALTH_DETAILS_PATH, health_details)
    write_json(NORMALIZED_DIR / "raw_schema_summary.json", build_schema_summary(raw_days))
    write_json(NORMALIZED_DIR / "mapping_coverage.json", build_mapping_coverage(normalized))
    write_json(NORMALIZED_DIR / "provider_capabilities.json", provider_metadata(client))

    if args.include_raw:
        write_json(RAW_DIR / f"daily_raw_{args.end_date}_{args.days}d.json", raw_days)

    if args.write_db:
        try:
            from scripts import trainingos_db
        except ImportError:
            import trainingos_db  # type: ignore

        trainingos_db.init_db(Path(args.db))
        with trainingos_db.connect(Path(args.db)) as connection:
            for metric, detail_by_category in zip(normalized, health_details):
                metric["raw_payload_path"] = str(NORMALIZED_DIR / "daily_recovery_metrics.json")
                trainingos_db.upsert_daily_recovery_metric(connection, metric)
                for category, detail in detail_by_category.items():
                    trainingos_db.upsert_daily_health_metric(connection, category, detail)

    print(f"Wrote {len(normalized)} normalized Garmin daily records.")
    print(f"Output: {NORMALIZED_DIR / 'daily_recovery_metrics.json'}")
    print(f"Health details: {DAILY_HEALTH_DETAILS_PATH}")
    print(f"Schema summary: {NORMALIZED_DIR / 'raw_schema_summary.json'}")
    print(f"Mapping coverage: {NORMALIZED_DIR / 'mapping_coverage.json'}")
    print(f"Provider capabilities: {NORMALIZED_DIR / 'provider_capabilities.json'}")
    print(f"Legacy training-readiness fallback records: {readiness_fallback_count}")
    if args.include_raw:
        print(f"Raw output: {RAW_DIR}")
    if args.write_db:
        print(f"SQLite upsert: {args.db}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
