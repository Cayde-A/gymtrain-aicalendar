#!/usr/bin/env python3
"""Seed and maintain the Gunyama candidate exercise catalog."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

try:
    from . import trainingos_db
except ImportError:  # pragma: no cover - supports direct script execution.
    import trainingos_db  # type: ignore


OFFICIAL_SOURCE = (
    "https://cityofsydneyleisure.com.au/visit/"
    "gunyama-park-aquatic-and-recreation-centre"
)

CATALOG = (
    ("Bench Press", "chest", "barbell/free weights", "BENCH_PRESS", "BENCH_PRESS"),
    ("Incline Dumbbell Bench Press", "chest", "dumbbells/bench", "BENCH_PRESS", "INCLINE_DUMBBELL_BENCH_PRESS"),
    ("Cable Crossover", "chest", "cable station", "FLYE", "CABLE_CROSSOVER"),
    ("Rope Press-down", "triceps", "cable station", "TRICEPS_EXTENSION", "ROPE_PRESSDOWN"),
    ("Leg Press", "quadriceps", "strength machine", "SQUAT", "LEG_PRESS"),
    ("Romanian Deadlift", "hamstrings", "barbell/free weights", "DEADLIFT", "ROMANIAN_DEADLIFT"),
    ("Goblet Squat", "quadriceps", "dumbbell/free weights", "SQUAT", "GOBLET_SQUAT"),
    ("Standing Calf Raise", "calves", "strength machine/free weights", "CALF_RAISE", "STANDING_CALF_RAISE"),
    ("Lat Pull-down", "back", "cable/strength machine", "PULL_UP", "LAT_PULLDOWN"),
    ("Seated Cable Row", "back", "cable/strength machine", "ROW", "SEATED_CABLE_ROW"),
    ("Face Pull", "rear delts", "cable station", "ROW", "FACE_PULL"),
    ("Cable Biceps Curl", "biceps", "cable station", "CURL", "CABLE_BICEPS_CURL"),
    ("Kneeling Cable Crunch", "core", "cable station", "CRUNCH", "KNEELING_CABLE_CRUNCH"),
    ("Weighted Dead Bug", "core", "free weights/floor", "HIP_STABILITY", "WEIGHTED_DEAD_BUG"),
    ("Plank", "core", "floor", "PLANK", "PLANK"),
    ("Side Plank", "core", "floor", "PLANK", "SIDE_PLANK"),
    ("Weighted Crunch", "core", "free weights/floor", "CRUNCH", "WEIGHTED_CRUNCH"),
    ("Russian Twist", "core", "free weights/floor", "CORE", "RUSSIAN_TWIST"),
    ("McGill Curl-up", "core", "floor", "CRUNCH", "MCGILL_CURL_UP"),
)

VALID_STATUSES = {"candidate", "user_verified", "unavailable"}


def garmin_pairs() -> set[tuple[str, str]]:
    try:
        from garminconnect.exercises import EXERCISES
    except ImportError as exc:
        raise RuntimeError("garminconnect is required to verify the Garmin exercise catalog") from exc
    return {
        (str(item.get("category")), str(item.get("exercise")))
        for item in EXERCISES
        if isinstance(item, dict)
    }


def validate_catalog() -> list[str]:
    available = garmin_pairs()
    return [
        f"{category}/{exercise}"
        for _, _, _, category, exercise in CATALOG
        if (category, exercise) not in available
    ]


def seed_catalog(connection: Any) -> int:
    missing = validate_catalog()
    if missing:
        raise ValueError("Garmin catalog mappings are unavailable: " + ", ".join(missing))
    saved = 0
    for name, muscle, equipment, category, exercise in CATALOG:
        row = connection.execute(
            "select id from exercise_catalog where lower(name) = lower(?) limit 1", (name,)
        ).fetchone()
        exercise_id = str(row["id"]) if row else trainingos_db.new_id("exercise")
        connection.execute(
            """
            insert into exercise_catalog (
              id, name, category, primary_muscle, equipment, location,
              garmin_category, garmin_exercise_name, venue_availability_status,
              verification_level, verification_source, is_active
            )
            values (?, ?, 'strength', ?, ?, 'Gunyama Park Aquatic and Recreation Centre',
                    ?, ?, 'candidate', 'venue_category_only', ?, 1)
            on conflict(id) do update set
              name = excluded.name,
              category = excluded.category,
              primary_muscle = excluded.primary_muscle,
              equipment = excluded.equipment,
              location = excluded.location,
              garmin_category = excluded.garmin_category,
              garmin_exercise_name = excluded.garmin_exercise_name,
              verification_source = excluded.verification_source,
              is_active = 1
            """,
            (exercise_id, name, muscle, equipment, category, exercise, OFFICIAL_SOURCE),
        )
        saved += 1
    return saved


def set_availability(
    connection: Any, name: str, status: str, verified_on: str | None = None
) -> bool:
    if status not in VALID_STATUSES:
        raise ValueError(f"unsupported status: {status}")
    verification_level = "user_verified" if status in {"user_verified", "unavailable"} else "venue_category_only"
    result = connection.execute(
        """
        update exercise_catalog
        set venue_availability_status = ?,
            verification_level = ?,
            last_verified_on = ?
        where lower(name) = lower(?) and location = 'Gunyama Park Aquatic and Recreation Centre'
        """,
        (status, verification_level, verified_on or dt.date.today().isoformat(), name),
    )
    return result.rowcount == 1


def catalog_summary(connection: Any) -> dict[str, Any]:
    rows = connection.execute(
        """
        select venue_availability_status, count(*) as count
        from exercise_catalog
        where location = 'Gunyama Park Aquatic and Recreation Centre'
        group by venue_availability_status
        """
    ).fetchall()
    return {
        "location": "Gunyama Park Aquatic and Recreation Centre",
        "counts": {str(row["venue_availability_status"]): int(row["count"]) for row in rows},
        "specific_inventory_officially_published": False,
        "garmin_mappings_verified": not validate_catalog(),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed or confirm Gunyama exercise availability.")
    parser.add_argument("--db", default=str(trainingos_db.DEFAULT_DB_PATH))
    parser.add_argument("--confirm", help="Exercise name observed at the venue.")
    parser.add_argument("--unavailable", help="Exercise name confirmed unavailable at the venue.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db)
    trainingos_db.init_db(db_path)
    with trainingos_db.connect(db_path) as connection:
        saved = seed_catalog(connection)
        if args.confirm and not set_availability(connection, args.confirm, "user_verified"):
            raise SystemExit(f"Unknown Gunyama exercise: {args.confirm}")
        if args.unavailable and not set_availability(connection, args.unavailable, "unavailable"):
            raise SystemExit(f"Unknown Gunyama exercise: {args.unavailable}")
        summary = catalog_summary(connection)
    print(json.dumps({"seeded": saved, **summary}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
