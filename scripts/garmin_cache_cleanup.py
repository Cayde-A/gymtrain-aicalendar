#!/usr/bin/env python3
"""Conservative retention cleanup for local raw Garmin cache files."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from . import trainingos_db
except ImportError:  # pragma: no cover - supports direct script execution.
    import trainingos_db  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "exports" / "garmin" / "raw"
DEFAULT_REPORT = ROOT / "exports" / "garmin" / "normalized" / "cache_cleanup_report.json"
ACTIVITY_FILE = re.compile(r"^activity_(?P<activity_id>\d+)(?:_exercise_sets)?\.json$")


@dataclass(frozen=True)
class CacheCandidate:
    path: Path
    size_bytes: int
    reason: str


def retention_days(db_path: Path) -> int:
    if not db_path.exists():
        return 30
    with trainingos_db.connect(db_path) as connection:
        row = connection.execute(
            "select raw_cache_retention_days from privacy_retention_policies limit 1"
        ).fetchone()
    return max(1, int(row[0])) if row else 30


def normalized_state(db_path: Path) -> tuple[set[str], set[str]]:
    if not db_path.exists():
        return set(), set()
    try:
        with trainingos_db.connect(db_path) as connection:
            activity_ids = {
                str(row[0])
                for row in connection.execute(
                    "select external_activity_id from completed_sessions where provider = 'garmin'"
                )
                if row[0] is not None
            }
            recovery_dates = {
                str(row[0])
                for row in connection.execute(
                    "select metric_date from daily_recovery_metrics where provider = 'garmin'"
                )
                if row[0] is not None
            }
        return activity_ids, recovery_dates
    except sqlite3.DatabaseError:
        return set(), set()


def daily_dates(path: Path) -> set[str] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, list) or not payload:
        return None
    dates = {
        str(item["date"])
        for item in payload
        if isinstance(item, dict) and isinstance(item.get("date"), str)
    }
    return dates if len(dates) == len(payload) else None


def verification_reason(
    path: Path, activity_ids: set[str], recovery_dates: set[str]
) -> str | None:
    activity_match = ACTIVITY_FILE.match(path.name)
    if activity_match:
        activity_id = activity_match.group("activity_id")
        return "normalized_activity" if activity_id in activity_ids else None
    if path.name.startswith("daily_raw_") and path.suffix == ".json":
        dates = daily_dates(path)
        if dates and dates.issubset(recovery_dates):
            return "normalized_recovery"
    return None


def scan_cache(
    raw_root: Path,
    db_path: Path,
    keep_days: int,
    now: dt.datetime | None = None,
) -> tuple[list[CacheCandidate], dict[str, int]]:
    current = now or dt.datetime.now(dt.timezone.utc)
    cutoff = current.timestamp() - keep_days * 86400
    activity_ids, recovery_dates = normalized_state(db_path)
    candidates: list[CacheCandidate] = []
    counters = {
        "scanned_files": 0,
        "recent_files": 0,
        "unverified_files": 0,
        "symlinks_skipped": 0,
        "eligible_files": 0,
        "eligible_bytes": 0,
    }
    if not raw_root.exists():
        return candidates, counters
    for path in raw_root.rglob("*"):
        if path.is_symlink():
            counters["symlinks_skipped"] += 1
            continue
        if not path.is_file():
            continue
        counters["scanned_files"] += 1
        stat = path.stat()
        if stat.st_mtime > cutoff:
            counters["recent_files"] += 1
            continue
        reason = verification_reason(path, activity_ids, recovery_dates)
        if reason is None:
            counters["unverified_files"] += 1
            continue
        candidate = CacheCandidate(path=path, size_bytes=stat.st_size, reason=reason)
        candidates.append(candidate)
        counters["eligible_files"] += 1
        counters["eligible_bytes"] += stat.st_size
    return candidates, counters


def cleanup(
    raw_root: Path,
    db_path: Path,
    keep_days: int,
    *,
    apply: bool,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    candidates, counters = scan_cache(raw_root, db_path, keep_days, now)
    deleted = 0
    deleted_bytes = 0
    failed = 0
    if apply:
        for candidate in candidates:
            try:
                candidate.path.unlink()
                if candidate.path.exists() or candidate.path.is_symlink():
                    failed += 1
                    continue
                deleted += 1
                deleted_bytes += candidate.size_bytes
            except OSError:
                failed += 1
        for directory in sorted(
            (item for item in raw_root.rglob("*") if item.is_dir() and not item.is_symlink()),
            key=lambda item: len(item.parts),
            reverse=True,
        ):
            try:
                directory.rmdir()
            except OSError:
                pass
    return {
        "status": "completed" if apply and failed == 0 else "preview" if not apply else "partial_failure",
        "applied": apply,
        "retention_days": keep_days,
        **counters,
        "deleted_files": deleted,
        "deleted_bytes": deleted_bytes,
        "failed_deletions": failed,
        "deletion_verified": bool(apply and failed == 0 and deleted == len(candidates)),
        "contains_personal_values": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preview or clean verified raw Garmin cache files.")
    parser.add_argument("--db", default=str(trainingos_db.DEFAULT_DB_PATH), help="Local SQLite path.")
    parser.add_argument(
        "--retention-days",
        type=int,
        default=None,
        help="Override the SQLite retention policy for this run.",
    )
    parser.add_argument("--apply", action="store_true", help="Delete eligible files and verify removal.")
    parser.add_argument("--output", default=str(DEFAULT_REPORT), help="Aggregate JSON report path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db)
    keep_days = args.retention_days if args.retention_days is not None else retention_days(db_path)
    if keep_days < 1:
        raise SystemExit("retention-days must be at least 1")
    report = cleanup(RAW_ROOT, db_path, keep_days, apply=args.apply)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Report: {output}")
    return 0 if report["status"] != "partial_failure" else 3


if __name__ == "__main__":
    sys.exit(main())
