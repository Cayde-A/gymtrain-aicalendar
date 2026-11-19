#!/usr/bin/env python3
"""Build Garmin strength workout payloads from TrainingOS plan blocks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "exports" / "garmin" / "normalized"
STRENGTH_SPORT_TYPE = {
    "sportTypeId": 5,
    "sportTypeKey": "strength_training",
    "displayOrder": 5,
}
INTERVAL_STEP_TYPE = {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3}
REST_STEP_TYPE = {"stepTypeId": 5, "stepTypeKey": "rest", "displayOrder": 5}
REPEAT_STEP_TYPE = {"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6}
REPS_CONDITION = {
    "conditionTypeId": 10,
    "conditionTypeKey": "reps",
    "displayOrder": 10,
    "displayable": True,
}
TIME_CONDITION = {
    "conditionTypeId": 2,
    "conditionTypeKey": "time",
    "displayOrder": 2,
    "displayable": True,
}
ITERATIONS_CONDITION = {
    "conditionTypeId": 7,
    "conditionTypeKey": "iterations",
    "displayOrder": 7,
    "displayable": False,
}
NO_TARGET = {
    "workoutTargetTypeId": 1,
    "workoutTargetTypeKey": "no.target",
    "displayOrder": 1,
}
CUE_MAX_LENGTH = 120

EXERCISE_CUES = {
    "BENCH_PRESS": "Shoulder blades set, feet planted, controlled touch, press without bouncing.",
    "INCLINE_DUMBBELL_BENCH_PRESS": "Keep ribs down, elbows slightly tucked, pause briefly at bottom, no shoulder shrug.",
    "CABLE_CROSSOVER": "Soft elbows, chest tall, squeeze across midline, stop before shoulder rolls forward.",
    "ROPE_PRESSDOWN": "Elbows pinned, shoulders quiet, full lockout, control the return.",
    "LEG_PRESS": "Feet stable, knees track toes, lower under control, avoid hip lift at depth.",
    "ROMANIAN_DEADLIFT": "Hips back, neutral spine, soft knees, feel hamstrings, stop before back rounds.",
    "GOBLET_SQUAT": "Brace first, knees track toes, stay tall, pause if depth control fades.",
    "STANDING_CALF_RAISE": "Full stretch, rise through big toe, pause at top, no bouncing.",
    "PLANK": "Ribs down, glutes tight, breathe shallow, stop if low back takes over.",
    "KNEELING_CABLE_CRUNCH": "Hips still, curl ribs toward pelvis, exhale hard, avoid pulling with arms.",
    "WEIGHTED_DEAD_BUG": "Low back quiet, slow opposite reach, exhale on extension, keep control.",
    "SIDE_PLANK": "Stack ribs over hips, push floor away, keep neck relaxed, stop before form breaks.",
    "WEIGHTED_CRUNCH": "Small controlled curl, ribs toward pelvis, no neck pull, slow lower.",
    "RUSSIAN_TWIST": "Brace, rotate ribs not arms, keep range controlled, avoid low-back swing.",
    "MCGILL_CURL_UP": "Neutral spine, one knee bent, small lift, hold tension without neck strain.",
    "LAT_PULLDOWN": "Chest tall, pull elbows toward ribs, avoid shrugging, control the full return.",
    "SEATED_CABLE_ROW": "Brace torso, lead with elbows, pause without leaning back, control the reach.",
    "FACE_PULL": "Pull toward eye level, rotate thumbs back, keep ribs down, use a controlled load.",
    "CABLE_BICEPS_CURL": "Elbows stay near sides, curl without shoulder swing, control the lowering phase.",
}


LEG_PRIORITY_AFTER_PUSH_PRESET = [
    {
        "label": "Leg Press",
        "category": "SQUAT",
        "exerciseName": "LEG_PRESS",
        "sets": 4,
        "reps": 10,
        "rest_seconds": 90,
    },
    {
        "label": "Romanian Deadlift",
        "category": "DEADLIFT",
        "exerciseName": "ROMANIAN_DEADLIFT",
        "sets": 3,
        "reps": 8,
        "rest_seconds": 90,
    },
    {
        "label": "Goblet Squat",
        "category": "SQUAT",
        "exerciseName": "GOBLET_SQUAT",
        "sets": 3,
        "reps": 12,
        "rest_seconds": 75,
    },
    {
        "label": "Standing Calf Raise",
        "category": "CALF_RAISE",
        "exerciseName": "STANDING_CALF_RAISE",
        "sets": 2,
        "reps": 15,
        "rest_seconds": 60,
    },
    {
        "label": "Plank",
        "category": "PLANK",
        "exerciseName": "PLANK",
        "sets": 2,
        "reps": 1,
        "rest_seconds": 60,
    },
]

PULL_LOWER_RECOVERY_PRESET = LEG_PRIORITY_AFTER_PUSH_PRESET

PUSH_CHEST_CONSERVATIVE_PRESET = [
    {
        "label": "Bench Press",
        "category": "BENCH_PRESS",
        "exerciseName": "BENCH_PRESS",
        "sets": 3,
        "reps": 8,
        "rest_seconds": 120,
    },
    {
        "label": "Incline Dumbbell Bench Press",
        "category": "BENCH_PRESS",
        "exerciseName": "INCLINE_DUMBBELL_BENCH_PRESS",
        "sets": 3,
        "reps": 8,
        "rest_seconds": 90,
    },
    {
        "label": "Cable Crossover",
        "category": "FLYE",
        "exerciseName": "CABLE_CROSSOVER",
        "sets": 2,
        "reps": 12,
        "rest_seconds": 60,
    },
    {
        "label": "Rope Press-down",
        "category": "TRICEPS_EXTENSION",
        "exerciseName": "ROPE_PRESSDOWN",
        "sets": 2,
        "reps": 12,
        "rest_seconds": 60,
    },
]

PULL_BACK_CONSERVATIVE_PRESET = [
    {
        "label": "Lat Pull-down",
        "category": "PULL_UP",
        "exerciseName": "LAT_PULLDOWN",
        "sets": 4,
        "reps": 8,
        "rest_seconds": 90,
    },
    {
        "label": "Seated Cable Row",
        "category": "ROW",
        "exerciseName": "SEATED_CABLE_ROW",
        "sets": 3,
        "reps": 10,
        "rest_seconds": 90,
    },
    {
        "label": "Face Pull",
        "category": "ROW",
        "exerciseName": "FACE_PULL",
        "sets": 3,
        "reps": 12,
        "rest_seconds": 60,
    },
    {
        "label": "Cable Biceps Curl",
        "category": "CURL",
        "exerciseName": "CABLE_BICEPS_CURL",
        "sets": 2,
        "reps": 12,
        "rest_seconds": 60,
    },
]

CORE_BETWEEN_PUSH_LEGS_PRESET = [
    {
        "label": "Kneeling Cable Crunch",
        "category": "CRUNCH",
        "exerciseName": "KNEELING_CABLE_CRUNCH",
        "sets": 3,
        "reps": 12,
        "rest_seconds": 60,
    },
    {
        "label": "Weighted Dead Bug",
        "category": "HIP_STABILITY",
        "exerciseName": "WEIGHTED_DEAD_BUG",
        "sets": 3,
        "reps": 10,
        "rest_seconds": 45,
    },
    {
        "label": "Side Plank",
        "category": "PLANK",
        "exerciseName": "SIDE_PLANK",
        "sets": 2,
        "reps": 1,
        "rest_seconds": 45,
    },
]

CORE_BETWEEN_LEGS_PULL_PRESET = [
    {
        "label": "Weighted Crunch",
        "category": "CRUNCH",
        "exerciseName": "WEIGHTED_CRUNCH",
        "sets": 3,
        "reps": 12,
        "rest_seconds": 60,
    },
    {
        "label": "Russian Twist",
        "category": "CORE",
        "exerciseName": "RUSSIAN_TWIST",
        "sets": 3,
        "reps": 16,
        "rest_seconds": 45,
    },
    {
        "label": "McGill Curl-up",
        "category": "CRUNCH",
        "exerciseName": "MCGILL_CURL_UP",
        "sets": 2,
        "reps": 10,
        "rest_seconds": 45,
    },
]

PRESETS = {
    "legs_after_push": {
        "default_name": "TrainingOS Legs",
        "blocks": LEG_PRIORITY_AFTER_PUSH_PRESET,
    },
    "push_chest_conservative": {
        "default_name": "TrainingOS Chest",
        "blocks": PUSH_CHEST_CONSERVATIVE_PRESET,
    },
    "pull_back_conservative": {
        "default_name": "TrainingOS Pull",
        "blocks": PULL_BACK_CONSERVATIVE_PRESET,
    },
    "core_between_push_legs": {
        "default_name": "TrainingOS Core A",
        "blocks": CORE_BETWEEN_PUSH_LEGS_PRESET,
    },
    "core_between_legs_pull": {
        "default_name": "TrainingOS Core B",
        "blocks": CORE_BETWEEN_LEGS_PULL_PRESET,
    },
}


def strength_block(block: dict[str, Any], step_order: int) -> dict[str, Any]:
    cue = movement_cue(block)
    exercise_step = {
        "type": "ExecutableStepDTO",
        "stepOrder": step_order + 1,
        "stepType": INTERVAL_STEP_TYPE,
        "endCondition": REPS_CONDITION,
        "endConditionValue": float(block["reps"]),
        "targetType": NO_TARGET,
        "category": block["category"],
        "exerciseName": block["exerciseName"],
        "description": cue,
    }
    rest_step = {
        "type": "ExecutableStepDTO",
        "stepOrder": step_order + 2,
        "stepType": REST_STEP_TYPE,
        "endCondition": TIME_CONDITION,
        "endConditionValue": float(block["rest_seconds"]),
        "targetType": NO_TARGET,
    }
    return {
        "type": "RepeatGroupDTO",
        "stepOrder": step_order,
        "stepType": REPEAT_STEP_TYPE,
        "numberOfIterations": int(block["sets"]),
        "workoutSteps": [exercise_step, rest_step],
        "endCondition": ITERATIONS_CONDITION,
        "endConditionValue": float(block["sets"]),
        "smartRepeat": False,
    }


def movement_cue(block: dict[str, Any]) -> str:
    cue = str(block.get("cue") or EXERCISE_CUES.get(str(block["exerciseName"]), "")).strip()
    if len(cue) > CUE_MAX_LENGTH:
        return cue[: CUE_MAX_LENGTH - 3].rstrip() + "..."
    return cue


def build_strength_workout_payload(name: str, blocks: list[dict[str, Any]]) -> dict[str, Any]:
    workout_steps = []
    step_order = 1
    estimated_duration = 0
    for block in blocks:
        workout_steps.append(strength_block(block, step_order))
        estimated_duration += int(block["sets"]) * (45 + int(block["rest_seconds"]))
        step_order += 3
    return {
        "workoutName": name,
        "sportType": STRENGTH_SPORT_TYPE,
        "estimatedDurationInSecs": estimated_duration,
        "description": "TrainingOS generated recovery-aware strength plan.",
        "workoutSegments": [
            {
                "segmentOrder": 1,
                "sportType": STRENGTH_SPORT_TYPE,
                "workoutSteps": workout_steps,
            }
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a Garmin strength workout payload.")
    parser.add_argument("--date", required=True, help="Target training date in YYYY-MM-DD format.")
    parser.add_argument("--name", help="Workout name. Defaults to TrainingOS Legs <date>.")
    parser.add_argument(
        "--preset",
        choices=sorted(PRESETS),
        default="legs_after_push",
        help="TrainingOS preset to export.",
    )
    parser.add_argument("--output", help="Output JSON path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    preset = PRESETS[args.preset]
    name = args.name or f"{preset['default_name']} {args.date}"
    payload = build_strength_workout_payload(name, preset["blocks"])
    output = Path(args.output) if args.output else DEFAULT_OUTPUT_DIR / f"garmin_strength_workout_payload_{args.date}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Workout payload: {payload['workoutName']}")
    print(f"Output: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
