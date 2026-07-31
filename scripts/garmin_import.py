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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import Garmin data for TrainingOS.")
    parser.add_argument("--email", default=os.getenv("GARMIN_EMAIL"), help="Garmin email. Defaults to GARMIN_EMAIL.")
    parser.add_argument("--password", default=os.getenv("GARMIN_PASSWORD"), help="Garmin password. Defaults to GARMIN_PASSWORD env var.")
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


def login(email: str | None, password: str | None) -> Any:
    Garmin = import_garmin_client()
    if not email:
        email = input("Garmin email: ").strip()
    if not password:
        password = getpass.getpass("Garmin password: ")
    client = Garmin(email, password)
    client.login()
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

    sleep_score = deep_find_number(sleep, {"overallscore", "sleepscore", "score"})
    sleep_minutes = deep_find_number(
        sleep,
        {"sleepduration", "sleepdurationseconds", "totalsleeptimeinseconds", "durationinseconds"},
    )
    if isinstance(sleep_minutes, (int, float)) and sleep_minutes > 24 * 60:
        sleep_minutes = round(sleep_minutes / 60)

    return {
        "provider": "garmin",
        "source_tool": "python-garminconnect",
        "metric_date": raw["date"],
        "sleep_score": sleep_score,
        "sleep_duration_minutes": sleep_minutes,
        "hrv_status": deep_find_string(hrv, {"hrvstatus", "status"}),
        "resting_heart_rate": deep_find_number(stats, {"restingheartrate", "restinghr"}),
        "body_battery": deep_find_number(body_battery, {"bodybattery", "charged", "level"}),
        "stress_score": deep_find_number(stats, {"averagestresslevel", "stressscore"}),
        "training_readiness": deep_find_number(training_readiness, {"score", "trainingreadinessscore"}),
        "recovery_time_hours": deep_find_number(stats, {"recoverytime", "recoverytimehours"}),
        "steps": deep_find_number(stats, {"totalsteps", "steps"}),
        "calories": deep_find_number(stats, {"totalcalories", "calories"}),
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


def main() -> int:
    args = parse_args()
    client = login(args.email, args.password)
    raw_days = [fetch_day(client, day) for day in date_range(args.end_date, args.days)]
    normalized = [normalize_day(day) for day in raw_days]

    NORMALIZED_DIR.mkdir(parents=True, exist_ok=True)
    write_json(NORMALIZED_DIR / "daily_recovery_metrics.json", normalized)

    if args.include_raw:
        write_json(RAW_DIR / f"daily_raw_{args.end_date}_{args.days}d.json", raw_days)

    print(f"Wrote {len(normalized)} normalized Garmin daily records.")
    print(f"Output: {NORMALIZED_DIR / 'daily_recovery_metrics.json'}")
    if args.include_raw:
        print(f"Raw output: {RAW_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

