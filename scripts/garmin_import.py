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
import getpass
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "exports" / "garmin" / "raw"
NORMALIZED_DIR = ROOT / "exports" / "garmin" / "normalized"
DEFAULT_TOKENSTORE = ROOT / "tokens" / "garmin"
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
    ],
    "sleep_duration_minutes": [
        "sleep.dailySleepDTO.sleepTimeSeconds",
    ],
    "hrv_status": [
        "hrv.hrvSummary.status",
    ],
    "resting_heart_rate": [
        "stats.restingHeartRate",
    ],
    "body_battery": [
        "stats.bodyBatteryMostRecentValue",
        "body_battery[].bodyBatteryValuesArray[][]",
    ],
    "stress_score": [
        "stats.averageStressLevel",
    ],
    "training_readiness": [
        "training_readiness[].score",
    ],
    "recovery_time_hours": [
        "training_readiness[].recoveryTime",
    ],
    "steps": [
        "stats.totalSteps",
    ],
    "calories": [
        "stats.totalKilocalories",
    ],
}


def load_dotenv_local() -> None:
    env_path = ROOT / ".env.local"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


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
    return parser.parse_args()


def import_garmin_client() -> Any:
    try:
        from garminconnect import Garmin  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency: garminconnect. Install with:\n"
            "  python3 -m pip install -r requirements.txt"
        ) from exc
    return Garmin


def has_tokens(tokenstore: Path) -> bool:
    return (tokenstore / "oauth1_token.json").exists() and (tokenstore / "oauth2_token.json").exists()


def login(email: str | None, password: str | None, tokenstore: str) -> Any:
    Garmin = import_garmin_client()
    tokenstore_path = Path(tokenstore).expanduser()
    if has_tokens(tokenstore_path):
        client = Garmin()
        client.login(str(tokenstore_path))
        return client

    if not email:
        email = input("Garmin email: ").strip()
    if not password:
        password = getpass.getpass("Garmin password: ")
    client = Garmin(email, password)
    client.login()
    tokenstore_path.mkdir(parents=True, exist_ok=True)
    client.garth.dump(str(tokenstore_path))
    return client


def date_range(end_date: str, days: int) -> list[dt.date]:
    end = dt.date.fromisoformat(end_date)
    return [end - dt.timedelta(days=offset) for offset in reversed(range(days))]


def call_first_available(client: Any, candidates: list[tuple[str, tuple[Any, ...]]]) -> dict[str, Any]:
    failures: dict[str, str] = {}
    for method_name, args in candidates:
        method: Callable[..., Any] | None = getattr(client, method_name, None)
        if not callable(method):
            failures[method_name] = "method not available"
            continue
        try:
            return {
                "source_method": method_name,
                "ok": True,
                "data": method(*args),
            }
        except Exception as exc:  # noqa: BLE001 - keep exploration resilient.
            failures[method_name] = f"{type(exc).__name__}: {exc}"
    return {"ok": False, "failures": failures}


def fetch_day(client: Any, metric_date: dt.date) -> dict[str, Any]:
    date_text = metric_date.isoformat()
    return {
        "date": date_text,
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
    sleep_minutes = round(sleep_seconds / 60) if isinstance(sleep_seconds, (int, float)) else None
    recovery_time = first_number(mapped_payload, FIELD_MAPPINGS["recovery_time_hours"])
    recovery_time_hours = round(recovery_time / 3600, 2) if isinstance(recovery_time, (int, float)) else None

    return {
        "provider": "garmin",
        "source_tool": "python-garminconnect",
        "metric_date": raw["date"],
        "sleep_score": first_number(mapped_payload, FIELD_MAPPINGS["sleep_score"])
        or deep_find_number(sleep, {"overallscore", "sleepscore", "score"}),
        "sleep_duration_minutes": sleep_minutes,
        "hrv_status": first_string(mapped_payload, FIELD_MAPPINGS["hrv_status"])
        or deep_find_string(hrv, {"hrvstatus", "status"}),
        "resting_heart_rate": first_number(mapped_payload, FIELD_MAPPINGS["resting_heart_rate"])
        or deep_find_number(stats, {"restingheartrate", "restinghr"}),
        "body_battery": first_number(mapped_payload, FIELD_MAPPINGS["body_battery"][:1])
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
    client = login(args.email, args.password, args.tokenstore)
    raw_days = [fetch_day(client, day) for day in date_range(args.end_date, args.days)]
    normalized = [normalize_day(day) for day in raw_days]

    NORMALIZED_DIR.mkdir(parents=True, exist_ok=True)
    write_json(NORMALIZED_DIR / "daily_recovery_metrics.json", normalized)
    write_json(NORMALIZED_DIR / "raw_schema_summary.json", build_schema_summary(raw_days))
    write_json(NORMALIZED_DIR / "mapping_coverage.json", build_mapping_coverage(normalized))

    if args.include_raw:
        write_json(RAW_DIR / f"daily_raw_{args.end_date}_{args.days}d.json", raw_days)

    print(f"Wrote {len(normalized)} normalized Garmin daily records.")
    print(f"Output: {NORMALIZED_DIR / 'daily_recovery_metrics.json'}")
    print(f"Schema summary: {NORMALIZED_DIR / 'raw_schema_summary.json'}")
    print(f"Mapping coverage: {NORMALIZED_DIR / 'mapping_coverage.json'}")
    if args.include_raw:
        print(f"Raw output: {RAW_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
