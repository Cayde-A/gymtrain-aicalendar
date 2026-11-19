#!/usr/bin/env python3
"""Finalize an existing next-day draft after morning recovery synchronization."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from . import trainingos_db, trainingos_pipeline
except ImportError:  # pragma: no cover - supports direct script execution.
    import trainingos_db  # type: ignore
    import trainingos_pipeline  # type: ignore


def summarize(report: dict[str, Any]) -> dict[str, Any]:
    plan = report.get("plan") or {}
    return {
        "status": report.get("status"),
        "training_date": report.get("training_date"),
        "target_date": report.get("target_date"),
        "sync": report.get("sync") or [],
        "quality_ready": bool((report.get("quality") or {}).get("finalization_ready")),
        "review_id": (report.get("review") or {}).get("review_id"),
        "recovery_adjustment": plan.get("recovery_adjustment"),
        "program_week": (plan.get("program_cycle") or {}).get("week"),
        "program_phase": (plan.get("program_cycle") or {}).get("phase"),
        "progression_action": (plan.get("primary_exercise_progression") or {}).get("action"),
        "venue_status": (plan.get("venue_validation") or {}).get("status"),
        "payload_path": plan.get("payload_path"),
        "push": report.get("push"),
        "error": report.get("error"),
        "ai_api_called": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Finalize a saved TrainingOS draft using target-date recovery data."
    )
    parser.add_argument("--training-date", required=True, help="Completed training date.")
    parser.add_argument("--date", required=True, help="Target plan and recovery date.")
    parser.add_argument("--db", default=str(trainingos_db.DEFAULT_DB_PATH))
    parser.add_argument("--output-dir", default=str(trainingos_pipeline.DEFAULT_OUTPUT_DIR))
    parser.add_argument("--sync-garmin", action="store_true")
    parser.add_argument("--confirm-candidate-equipment", action="store_true")
    parser.add_argument("--dry-run-push", action="store_true")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--confirm-push", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    options = trainingos_pipeline.PipelineOptions(
        training_date=args.training_date,
        target_date=args.date,
        db_path=Path(args.db),
        output_dir=Path(args.output_dir),
        sync_garmin=args.sync_garmin,
        confirm_candidate_equipment=args.confirm_candidate_equipment,
        dry_run_push=args.dry_run_push,
        push=args.push,
        confirm_push=args.confirm_push,
    )
    exit_code, report = trainingos_pipeline.run_pipeline(options)
    print(json.dumps(summarize(report), indent=2, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
