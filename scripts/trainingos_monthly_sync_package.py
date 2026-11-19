#!/usr/bin/env python3
"""Build and persist a privacy-minimized monthly Supabase sync package."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

try:
    from . import trainingos_db, trainingos_monthly_report
except ImportError:  # pragma: no cover - supports direct script execution.
    import trainingos_db  # type: ignore
    import trainingos_monthly_report  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "exports" / "sync"
TOP_LEVEL_KEYS = {
    "schema_version",
    "sync_month",
    "training_days",
    "session_count",
    "session_type_counts",
    "exercise_volume_summary",
    "best_sets",
    "pr_count",
    "estimated_1rm_trends",
    "recovery_summary",
}
FORBIDDEN_KEY_PARTS = (
    "token",
    "password",
    "credential",
    "raw_payload",
    "activity_id",
    "device_id",
    "garmin_user",
    "gps",
    "route",
    "note",
    "prompt",
    "completed_at",
    "set_log",
    "session_id",
    "athlete_id",
    "body_metric",
)


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def build_package(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "trainingos.supabase_monthly.v1",
        "sync_month": report["month"],
        "training_days": report["training"]["training_days"],
        "session_count": report["training"]["session_count"],
        "session_type_counts": report["training"]["session_type_counts"],
        "exercise_volume_summary": report["exercise_volume"],
        "best_sets": report["best_sets"],
        "pr_count": report["pr_count"],
        "estimated_1rm_trends": report["estimated_1rm_trends"],
        "recovery_summary": {
            "days_present": report["recovery"]["days_present"],
            "coverage_percent": report["recovery"]["coverage_percent"],
            "averages": report["recovery"]["averages"],
        },
    }


def sensitive_paths(value: Any, path: str = "$") -> list[str]:
    findings = []
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower()
            child_path = f"{path}.{key}"
            if any(part in normalized for part in FORBIDDEN_KEY_PARTS):
                findings.append(child_path)
            findings.extend(sensitive_paths(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(sensitive_paths(child, f"{path}[{index}]"))
    return findings


def validate_package(package: dict[str, Any]) -> None:
    keys = set(package)
    if keys != TOP_LEVEL_KEYS:
        raise ValueError(
            f"monthly sync package keys must match allowlist; missing={sorted(TOP_LEVEL_KEYS - keys)}, "
            f"extra={sorted(keys - TOP_LEVEL_KEYS)}"
        )
    trainingos_monthly_report.month_range(str(package["sync_month"]))
    findings = sensitive_paths(package)
    if findings:
        raise ValueError("sensitive fields are not allowed in monthly sync package: " + ", ".join(findings))


def persist_pending_package(
    connection: Any,
    package: dict[str, Any],
    digest: str,
) -> str:
    month = str(package["sync_month"])
    batch_id = f"monthly_sync_{month}"
    summary_id = f"cloud_summary_{month}"
    connection.execute(
        """
        insert into monthly_sync_batches (
          id, athlete_id, sync_month, status, summary_payload_hash, uploaded_at, error_message
        ) values (?, ?, ?, 'pending', ?, null, null)
        on conflict(athlete_id, sync_month) do update set
          status = 'pending', summary_payload_hash = excluded.summary_payload_hash,
          uploaded_at = null, error_message = null
        """,
        (batch_id, trainingos_db.DEFAULT_ATHLETE_ID, month, digest),
    )
    connection.execute(
        """
        insert into cloud_monthly_summaries (
          id, athlete_id, sync_batch_id, sync_month, training_days, session_count,
          session_type_counts_json, exercise_volume_summary_json, best_sets_json,
          pr_count, estimated_1rm_trends_json, recovery_summary_json
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(athlete_id, sync_month) do update set
          sync_batch_id = excluded.sync_batch_id,
          training_days = excluded.training_days,
          session_count = excluded.session_count,
          session_type_counts_json = excluded.session_type_counts_json,
          exercise_volume_summary_json = excluded.exercise_volume_summary_json,
          best_sets_json = excluded.best_sets_json,
          pr_count = excluded.pr_count,
          estimated_1rm_trends_json = excluded.estimated_1rm_trends_json,
          recovery_summary_json = excluded.recovery_summary_json
        """,
        (
            summary_id,
            trainingos_db.DEFAULT_ATHLETE_ID,
            batch_id,
            month,
            package["training_days"],
            package["session_count"],
            json.dumps(package["session_type_counts"], sort_keys=True),
            json.dumps(package["exercise_volume_summary"], sort_keys=True),
            json.dumps(package["best_sets"], sort_keys=True),
            package["pr_count"],
            json.dumps(package["estimated_1rm_trends"], sort_keys=True),
            json.dumps(package["recovery_summary"], sort_keys=True),
        ),
    )
    return batch_id


def create_package(connection: Any, month: str) -> tuple[dict[str, Any], str, str]:
    report = trainingos_monthly_report.build_monthly_report(connection, month)
    package = build_package(report)
    validate_package(package)
    digest = payload_hash(package)
    batch_id = persist_pending_package(connection, package, digest)
    return package, digest, batch_id


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a minimized monthly Supabase sync package.")
    parser.add_argument("--db", default=str(trainingos_db.DEFAULT_DB_PATH))
    parser.add_argument("--month", required=True, help="Month in YYYY-MM format.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db)
    trainingos_db.init_db(db_path)
    with trainingos_db.connect(db_path) as connection:
        package, digest, batch_id = create_package(connection, args.month)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"monthly_sync_{args.month}.json"
    output_path.write_text(json.dumps(package, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "pending_upload",
                "batch_id": batch_id,
                "payload_sha256": digest,
                "path": str(output_path),
                "sensitive_field_findings": [],
                "uploaded": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
