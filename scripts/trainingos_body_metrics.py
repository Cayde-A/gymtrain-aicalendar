#!/usr/bin/env python3
"""Record and inspect private local body metrics."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

try:
    from . import trainingos_db
except ImportError:  # pragma: no cover - supports direct script execution.
    import trainingos_db  # type: ignore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record or inspect local TrainingOS body metrics.")
    parser.add_argument("--db", default=str(trainingos_db.DEFAULT_DB_PATH))
    parser.add_argument("--date", default=dt.date.today().isoformat(), help="Metric date in YYYY-MM-DD format.")
    parser.add_argument("--weight-kg", type=float)
    parser.add_argument("--body-fat-percent", type=float)
    parser.add_argument("--waist-cm", type=float)
    parser.add_argument("--chest-cm", type=float)
    parser.add_argument("--hip-cm", type=float)
    parser.add_argument("--arm-cm", type=float)
    parser.add_argument("--leg-cm", type=float)
    parser.add_argument("--notes")
    parser.add_argument("--list", action="store_true", help="List recent local records instead of saving.")
    parser.add_argument("--limit", type=int, default=30)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dt.date.fromisoformat(args.date)
    db_path = Path(args.db)
    trainingos_db.init_db(db_path)
    with trainingos_db.connect(db_path) as connection:
        if args.list:
            result = {
                "storage": "local_sqlite_only",
                "records": trainingos_db.get_recent_body_metrics(connection, args.limit),
            }
        else:
            metric_id = trainingos_db.upsert_body_metric(
                connection,
                {
                    "metric_date": args.date,
                    "body_weight_kg": args.weight_kg,
                    "body_fat_percent": args.body_fat_percent,
                    "waist_cm": args.waist_cm,
                    "chest_cm": args.chest_cm,
                    "hip_cm": args.hip_cm,
                    "arm_cm": args.arm_cm,
                    "leg_cm": args.leg_cm,
                    "notes": args.notes,
                },
            )
            result = {
                "status": "saved",
                "id": metric_id,
                "storage": "local_sqlite_only",
                "context": trainingos_db.body_metrics_context(connection, args.date),
            }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
