#!/usr/bin/env python3
"""Observable TrainingOS import-to-Garmin orchestration state machine."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

try:
    from . import (
        gunyama_exercise_catalog,
        trainingos_db,
        trainingos_garmin_payload,
        trainingos_observability,
        trainingos_program_cycle,
        trainingos_quality,
    )
except ImportError:  # pragma: no cover - supports direct script execution.
    import gunyama_exercise_catalog  # type: ignore
    import trainingos_db  # type: ignore
    import trainingos_garmin_payload  # type: ignore
    import trainingos_observability  # type: ignore
    import trainingos_program_cycle  # type: ignore
    import trainingos_quality  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "exports" / "pipeline"
GARMIN_RESULT_DIR = ROOT / "exports" / "garmin" / "normalized"
DEFAULT_VENUE = "Gunyama Park Aquatic and Recreation Centre"
VENUE_SUBSTITUTIONS = {
    "Leg Press": ["Goblet Squat"],
    "Cable Crossover": ["Incline Dumbbell Bench Press"],
    "Lat Pull-down": ["Seated Cable Row"],
    "Seated Cable Row": ["Lat Pull-down"],
    "Kneeling Cable Crunch": ["Weighted Crunch", "Weighted Dead Bug"],
}
PRESET_PRIMARY_GROUP = {
    "legs_after_push": "legs",
    "push_chest_conservative": "chest",
    "pull_back_conservative": "back",
    "core_between_push_legs": "core",
    "core_between_legs_pull": "core",
}
PRIMARY_GROUP_PRESET = {
    "legs": "legs_after_push",
    "chest": "push_chest_conservative",
    "back": "pull_back_conservative",
}
EXERCISE_GROUP_KEYWORDS = {
    "chest": ("bench", "chest press", "fly", "crossover"),
    "shoulders": ("shoulder press", "lateral raise", "front raise", "overhead press"),
    "legs": ("leg press", "squat", "lunge", "calf", "romanian deadlift", "leg curl", "leg extension"),
    "back": ("row", "pull-up", "pull up", "pulldown", "pull-down", "lat ", "face pull"),
    "arms": ("biceps", "curl", "triceps", "pressdown", "press-down"),
    "core": ("plank", "crunch", "dead bug", "deadbug", "russian twist", "curl-up"),
}


@dataclass(frozen=True)
class PipelineOptions:
    training_date: str
    target_date: str
    db_path: Path
    output_dir: Path = DEFAULT_OUTPUT_DIR
    sync_garmin: bool = False
    activity_days: int = 3
    anchor_lookback_days: int = 180
    recovery_days: int = 3
    ai_response_path: Path | None = None
    preset_override: str | None = None
    confirm_push: bool = False
    push: bool = False
    dry_run_push: bool = False
    venue: str = DEFAULT_VENUE
    confirm_candidate_equipment: bool = False


class CandidateEquipmentConfirmationRequired(ValueError):
    def __init__(self, exercises: list[str], substitutions: dict[str, list[str]]):
        super().__init__("Candidate venue equipment requires user confirmation: " + ", ".join(exercises))
        self.exercises = exercises
        self.substitutions = substitutions


CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=str(ROOT), text=True, capture_output=True, check=False)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_key(options: PipelineOptions) -> str:
    source = f"{trainingos_db.DEFAULT_ATHLETE_ID}|{options.training_date}|{options.target_date}"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def save_pipeline_run(
    connection: Any,
    options: PipelineOptions,
    report: dict[str, Any],
    review_id: str | None = None,
    plan: dict[str, Any] | None = None,
    payload_path: Path | None = None,
    push_result_path: Path | None = None,
) -> str:
    key = run_key(options)
    run_id = f"pipeline_{key[:24]}"
    connection.execute(
        """
        insert into pipeline_runs (
          id, athlete_id, source_training_date, target_date, status, review_id,
          plan_json, quality_report_json, garmin_payload_path, push_result_path,
          error_json, idempotency_key
        )
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(idempotency_key) do update set
          status = excluded.status,
          review_id = excluded.review_id,
          plan_json = excluded.plan_json,
          quality_report_json = excluded.quality_report_json,
          garmin_payload_path = excluded.garmin_payload_path,
          push_result_path = excluded.push_result_path,
          error_json = excluded.error_json,
          updated_at = current_timestamp
        """,
        (
            run_id,
            trainingos_db.DEFAULT_ATHLETE_ID,
            options.training_date,
            options.target_date,
            report["status"],
            review_id,
            json.dumps(plan, ensure_ascii=False, sort_keys=True) if plan else None,
            json.dumps(report.get("quality"), ensure_ascii=False, sort_keys=True),
            str(payload_path) if payload_path else None,
            str(push_result_path) if push_result_path else None,
            json.dumps(report.get("error"), ensure_ascii=False, sort_keys=True) if report.get("error") else None,
            key,
        ),
    )
    return run_id


def sync_commands(options: PipelineOptions) -> list[list[str]]:
    python = sys.executable
    return [
        [
            python,
            str(ROOT / "scripts" / "garmin_import.py"),
            "--days",
            str(options.recovery_days),
            "--end-date",
            options.target_date,
            "--write-db",
            "--db",
            str(options.db_path),
        ],
        [
            python,
            str(ROOT / "scripts" / "garmin_activity_import.py"),
            "--days",
            str(options.activity_days),
            "--end-date",
            options.training_date,
            "--strength-only",
            "--db",
            str(options.db_path),
        ],
    ]


def run_sync(options: PipelineOptions, runner: CommandRunner) -> list[dict[str, Any]]:
    results = []
    for command in sync_commands(options):
        completed = runner(command)
        results.append({"script": Path(command[1]).name, "returncode": completed.returncode})
        if completed.returncode != 0:
            break
    return results


def anchor_lookup_command(options: PipelineOptions) -> list[str]:
    return [
        sys.executable,
        str(ROOT / "scripts" / "garmin_activity_import.py"),
        "--days",
        str(options.anchor_lookback_days),
        "--end-date",
        options.training_date,
        "--strength-only",
        "--limit",
        "5",
        "--db",
        str(options.db_path),
    ]


def matching_review_id(connection: Any, training_date: str, response_text: str) -> str | None:
    parsed = trainingos_db.extract_json_object(response_text)
    if parsed is None:
        return None
    for review in trainingos_db.get_ai_reviews_for_day(connection, training_date):
        try:
            target = json.loads(review.get("next_target_json") or "{}")
        except json.JSONDecodeError:
            continue
        if target.get("raw_json") == parsed:
            return str(review["id"])
    return None


def latest_day_review(connection: Any, training_date: str) -> dict[str, Any] | None:
    reviews = trainingos_db.get_ai_reviews_for_day(connection, training_date)
    return reviews[0] if reviews else None


def get_review(connection: Any, review_id: str) -> dict[str, Any] | None:
    row = connection.execute("select * from ai_reviews where id = ?", (review_id,)).fetchone()
    return dict(row) if row else None


def initial_plan_from_review(review: dict[str, Any]) -> dict[str, Any] | None:
    try:
        target = json.loads(review.get("next_target_json") or "{}")
    except json.JSONDecodeError:
        return None
    initial = target.get("initial_next_day_plan")
    return initial if isinstance(initial, dict) else None


def review_data_quality_issues(review: dict[str, Any]) -> list[str]:
    try:
        target = json.loads(review.get("next_target_json") or "{}")
    except json.JSONDecodeError:
        return ["review_next_target_json_invalid"]
    raw = target.get("raw_json")
    if not isinstance(raw, dict):
        return ["review_response_unstructured"]
    issues = raw.get("data_quality_issues") or []
    if not isinstance(issues, list):
        return ["review_data_quality_issues_invalid"]
    return [str(issue) for issue in issues if str(issue).strip()]


def infer_trained_groups(sessions: list[dict[str, Any]]) -> list[str]:
    scores = {group: 0 for group in EXERCISE_GROUP_KEYWORDS}
    for session in sessions:
        for set_log in session.get("sets", []):
            if trainingos_quality.is_rest_set(set_log):
                continue
            name = str(set_log.get("exercise_name") or "").lower()
            for group, keywords in EXERCISE_GROUP_KEYWORDS.items():
                if any(keyword in name for keyword in keywords):
                    scores[group] += 1
    return [group for group, score in scores.items() if score > 0]


def choose_preset(initial_plan: dict[str, Any], override: str | None = None) -> str:
    if override:
        return override
    primary = str(initial_plan.get("primary_large_muscle_group") or "").lower()
    if primary == "core":
        interstitial = str(initial_plan.get("interstitial_core") or "")
        if interstitial in {"core_between_push_legs", "core_between_legs_pull"}:
            return interstitial
        raise ValueError("Core plan must name a supported interstitial_core preset.")
    preset = PRIMARY_GROUP_PRESET.get(primary)
    if preset is None:
        raise ValueError(f"No Garmin preset is available for primary group: {primary or 'missing'}")
    return preset


def derive_recovery_adjustment(metric: dict[str, Any]) -> str:
    sleep_score = metric.get("sleep_score")
    body_battery = metric.get("body_battery")
    readiness = metric.get("training_readiness")
    recovery_hours = metric.get("recovery_time_hours")
    hrv_status = str(metric.get("hrv_status") or "").lower()

    if any(
        condition
        for condition in (
            isinstance(sleep_score, (int, float)) and sleep_score < 50,
            isinstance(body_battery, (int, float)) and body_battery < 25,
            isinstance(readiness, (int, float)) and readiness < 30,
        )
    ):
        return "deload"
    if any(
        condition
        for condition in (
            isinstance(sleep_score, (int, float)) and sleep_score < 65,
            isinstance(body_battery, (int, float)) and body_battery < 45,
            isinstance(readiness, (int, float)) and readiness < 50,
            isinstance(recovery_hours, (int, float)) and recovery_hours > 48,
            hrv_status in {"low", "poor", "unbalanced", "strained"},
        )
    ):
        return "reduce_volume"
    return "keep"


def adjusted_blocks(preset: str, adjustment: str) -> list[dict[str, Any]]:
    blocks = copy.deepcopy(trainingos_garmin_payload.PRESETS[preset]["blocks"])
    if adjustment == "reduce_volume":
        for block in blocks:
            block["sets"] = max(1, int(block["sets"]) - 1)
    elif adjustment == "deload":
        for block in blocks:
            block["sets"] = max(1, (int(block["sets"]) + 1) // 2)
    return blocks


def apply_cycle_volume(
    preset: str,
    blocks: list[dict[str, Any]],
    volume_multiplier: float,
) -> list[dict[str, Any]]:
    original_by_label = {
        str(item["label"]): int(item["sets"])
        for item in trainingos_garmin_payload.PRESETS[preset]["blocks"]
    }
    for block in blocks:
        original_sets = original_by_label.get(str(block.get("label")), int(block["sets"]))
        cycle_sets = max(1, int(original_sets * volume_multiplier + 0.5))
        block["sets"] = min(int(block["sets"]), cycle_sets)
    return blocks


def validate_overlap(previous_groups: list[str], preset: str) -> list[str]:
    issues = []
    target_group = PRESET_PRIMARY_GROUP[preset]
    if ({"chest", "shoulders"} & set(previous_groups)) and preset not in {
        "legs_after_push",
        "core_between_push_legs",
    }:
        issues.append("after_chest_or_shoulders_target_legs_or_core_between_push_legs")
    if target_group in previous_groups and target_group != "core":
        issues.append("primary_muscle_group_repeats_previous_day")
    return issues


def validate_venue_availability(
    connection: Any,
    blocks: list[dict[str, Any]],
    venue: str,
    confirm_candidates: bool,
) -> dict[str, Any]:
    if not venue:
        return {"status": "not_applicable", "venue": None}

    rows = connection.execute(
        """
        select name, venue_availability_status
        from exercise_catalog
        where location = ? and is_active = 1
        """,
        (venue,),
    ).fetchall()
    availability = {
        str(row["name"]).casefold(): str(row["venue_availability_status"] or "candidate")
        for row in rows
    }
    labels = [str(block.get("label") or block.get("exerciseName") or "").strip() for block in blocks]
    unavailable = [label for label in labels if availability.get(label.casefold()) == "unavailable"]
    candidates = [
        label
        for label in labels
        if availability.get(label.casefold(), "candidate") not in {"user_verified", "unavailable"}
    ]
    suggested_substitutions = {
        label: [
            alternative
            for alternative in VENUE_SUBSTITUTIONS.get(label, [])
            if availability.get(alternative.casefold(), "candidate") != "unavailable"
        ]
        for label in [*unavailable, *candidates]
        if VENUE_SUBSTITUTIONS.get(label)
    }
    if unavailable:
        raise ValueError(
            "Plan contains exercises marked unavailable at "
            f"{venue}: {', '.join(unavailable)}. Select and confirm a substitution first."
        )
    if candidates and not confirm_candidates:
        raise CandidateEquipmentConfirmationRequired(candidates, suggested_substitutions)
    return {
        "status": "confirmed_for_run" if candidates else "verified",
        "venue": venue,
        "candidate_exercises": candidates,
        "verified_exercises": [label for label in labels if label not in candidates],
        "suggested_substitutions": suggested_substitutions,
    }


def build_final_plan(
    connection: Any,
    options: PipelineOptions,
    initial_plan: dict[str, Any],
    quality: dict[str, Any],
) -> dict[str, Any]:
    if not quality["finalization_ready"]:
        raise ValueError("Training and target-date recovery data must pass quality checks before finalization.")
    preset = choose_preset(initial_plan, options.preset_override)
    sessions = trainingos_db.get_sessions_for_day(connection, options.training_date)
    previous_groups = infer_trained_groups(sessions)
    overlap_issues = validate_overlap(previous_groups, preset)
    if overlap_issues:
        raise ValueError("Plan violates overlap constraints: " + ", ".join(overlap_issues))
    metric = trainingos_quality.get_recovery_metric(connection, options.target_date)
    if metric is None:
        raise ValueError("Recovery metric disappeared during finalization.")
    adjustment = derive_recovery_adjustment(metric)
    blocks = adjusted_blocks(preset, adjustment)
    cycle = trainingos_program_cycle.cycle_context(connection, options.target_date)
    blocks = apply_cycle_volume(preset, blocks, float(cycle["volume_multiplier"]))
    venue_validation = validate_venue_availability(
        connection,
        blocks,
        options.venue,
        options.confirm_candidate_equipment,
    )
    primary_group = PRESET_PRIMARY_GROUP[preset]
    primary_exercise = str(blocks[0]["label"])
    progression = trainingos_program_cycle.progression_decision(
        connection,
        primary_exercise,
        options.target_date,
        cycle,
        adjustment,
    )
    return {
        "version": "trainingos.final_plan.v1",
        "status": "final",
        "source_training_date": options.training_date,
        "target_date": options.target_date,
        "recovery_date": options.target_date,
        "preset": preset,
        "primary_large_muscle_group": primary_group,
        "previous_trained_groups": previous_groups,
        "avoided_overlap": initial_plan.get("avoided_overlap") or [],
        "recovery_adjustment": adjustment,
        "program_cycle": cycle,
        "primary_exercise_progression": {
            "exercise": primary_exercise,
            "top_set_reps": cycle["top_set_reps"],
            **progression,
        },
        "venue_validation": venue_validation,
        "rounds": blocks,
    }


def push_command(options: PipelineOptions, payload_path: Path, dry_run: bool) -> list[str]:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "garmin_workout_push.py"),
        "--payload",
        str(payload_path),
        "--date",
        options.target_date,
        "--replace-existing",
        "--db",
        str(options.db_path),
        "--idempotency-key",
        f"pipeline-{run_key(options)}",
    ]
    if dry_run:
        command.append("--dry-run")
    return command


def finish(
    connection: Any,
    options: PipelineOptions,
    report: dict[str, Any],
    exit_code: int,
    report_path: Path,
    review_id: str | None = None,
    plan: dict[str, Any] | None = None,
    payload_path: Path | None = None,
    push_result_path: Path | None = None,
) -> tuple[int, dict[str, Any]]:
    report["pipeline_run_id"] = save_pipeline_run(
        connection,
        options,
        report,
        review_id=review_id,
        plan=plan,
        payload_path=payload_path,
        push_result_path=push_result_path,
    )
    write_json(report_path, report)
    trainingos_observability.record_event(
        "pipeline_completed",
        details={
            "pipeline_run_id": report["pipeline_run_id"],
            "training_date": options.training_date,
            "target_date": options.target_date,
            "status": report["status"],
        },
    )
    return exit_code, report


def run_pipeline(options: PipelineOptions, runner: CommandRunner = run_command) -> tuple[int, dict[str, Any]]:
    dt.date.fromisoformat(options.training_date)
    dt.date.fromisoformat(options.target_date)
    if options.target_date <= options.training_date:
        raise ValueError("target_date must be later than training_date")

    options.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = options.output_dir / f"pipeline_{options.training_date}_to_{options.target_date}.json"
    packet_path = options.output_dir / f"ai_review_packet_{options.training_date}.json"
    payload_path = options.output_dir / f"garmin_workout_{options.target_date}.json"
    report: dict[str, Any] = {
        "version": "trainingos.pipeline.v1",
        "training_date": options.training_date,
        "target_date": options.target_date,
        "status": "started",
        "sync": [],
        "training_anchor": None,
        "quality": None,
        "review": None,
        "plan": None,
        "trigger": None,
        "push": None,
    }

    trainingos_db.init_db(options.db_path)
    if options.sync_garmin:
        report["sync"] = run_sync(options, runner)
        if not report["sync"] or report["sync"][-1]["returncode"] != 0:
            report["status"] = "sync_failed"
            report["error"] = {"code": "garmin_sync_failed", "retryable": True}
            with trainingos_db.connect(options.db_path) as connection:
                return finish(connection, options, report, 4, report_path)
        with trainingos_db.connect(options.db_path) as connection:
            initial_anchor = trainingos_db.training_anchor_state(connection, options.training_date)
        if not initial_anchor["ready"] and options.anchor_lookback_days > options.activity_days:
            completed = runner(anchor_lookup_command(options))
            report["sync"].append(
                {
                    "script": "garmin_activity_import.py",
                    "phase": "anchor_lookup",
                    "lookback_days": options.anchor_lookback_days,
                    "returncode": completed.returncode,
                }
            )
            if completed.returncode != 0:
                report["status"] = "sync_failed"
                report["error"] = {"code": "garmin_anchor_lookup_failed", "retryable": True}
                with trainingos_db.connect(options.db_path) as connection:
                    return finish(connection, options, report, 4, report_path)

    with trainingos_db.connect(options.db_path) as connection:
        if options.venue == DEFAULT_VENUE:
            gunyama_exercise_catalog.seed_catalog(connection)
        anchor = trainingos_db.training_anchor_state(connection, options.training_date)
        report["training_anchor"] = anchor
        if not anchor["ready"]:
            report["status"] = anchor["status"]
            report["error"] = {
                "code": "training_anchor_unavailable",
                "message": (
                    "No completed training history is available. Recovery synchronization may continue, "
                    "but TrainingOS will wait for the first completed workout before analysis."
                    if anchor["status"] == "waiting_for_first_training"
                    else "A completed activity exists but has no active sets. Sync or correct the first workout before analysis."
                ),
                "retryable": True,
            }
            return finish(connection, options, report, 3, report_path)
        quality = trainingos_quality.build_quality_report(
            connection,
            options.training_date,
            options.target_date,
        )
        report["quality"] = quality
        if not quality["analysis_ready"]:
            report["status"] = "quality_blocked"
            return finish(connection, options, report, 2, report_path)

        packet = trainingos_db.build_day_ai_review_packet(connection, options.training_date)
        write_json(packet_path, packet)
        report["review"] = {"packet_path": str(packet_path)}

        review_id = None
        if options.ai_response_path:
            response_text = options.ai_response_path.read_text(encoding="utf-8")
            review_id = matching_review_id(connection, options.training_date, response_text)
            if review_id is None:
                review_id = trainingos_db.save_day_ai_review_response(
                    connection,
                    options.training_date,
                    response_text,
                )
        review = get_review(connection, review_id) if review_id else latest_day_review(connection, options.training_date)
        if review is None:
            report["status"] = "needs_ai_review"
            return finish(connection, options, report, 3, report_path)
        review_id = str(review["id"])
        initial_plan = initial_plan_from_review(review)
        review_issues = review_data_quality_issues(review)
        report["review"].update(
            {
                "review_id": review_id,
                "structured_plan": bool(initial_plan),
                "data_quality_issues": review_issues,
            }
        )
        if review_issues:
            report["status"] = "review_quality_blocked"
            report["error"] = {
                "code": "ai_review_data_quality_issues",
                "issues": review_issues,
                "retryable": False,
            }
            return finish(connection, options, report, 2, report_path, review_id=review_id)
        if initial_plan is None:
            report["status"] = "review_missing_plan"
            return finish(connection, options, report, 2, report_path, review_id=review_id)
        if not quality["finalization_ready"]:
            report["status"] = "needs_recovery_sync"
            return finish(connection, options, report, 3, report_path, review_id=review_id)

        try:
            plan = build_final_plan(connection, options, initial_plan, quality)
        except CandidateEquipmentConfirmationRequired as exc:
            report["status"] = "needs_venue_confirmation"
            report["error"] = {
                "code": "venue_equipment_confirmation_required",
                "venue": options.venue,
                "exercises": exc.exercises,
                "suggested_substitutions": exc.substitutions,
                "retryable": False,
            }
            return finish(connection, options, report, 3, report_path, review_id=review_id)
        except ValueError as exc:
            report["status"] = "plan_blocked"
            report["error"] = {"code": "plan_validation_failed", "message": str(exc), "retryable": False}
            return finish(connection, options, report, 2, report_path, review_id=review_id)

        preset = trainingos_garmin_payload.PRESETS[plan["preset"]]
        workout_name = f"{preset['default_name']} {options.target_date}"
        payload = trainingos_garmin_payload.build_strength_workout_payload(workout_name, plan["rounds"])
        payload["description"] = (
            f"TrainingOS final plan; recovery adjustment={plan['recovery_adjustment']}; "
            f"cycle week={plan['program_cycle']['week']} {plan['program_cycle']['phase']}; "
            f"progression={plan['primary_exercise_progression']['action']}; source={options.training_date}."
        )
        write_json(payload_path, payload)
        report["plan"] = {**plan, "payload_path": str(payload_path), "workout_name": workout_name}

        decision = trainingos_db.evaluate_api_trigger(
            connection,
            "garmin_push",
            user_confirmed=options.confirm_push,
        )
        trainingos_db.record_api_trigger_decision(
            connection,
            decision,
            context={"training_date": options.training_date, "target_date": options.target_date},
        )
        report["trigger"] = decision

        if options.dry_run_push:
            completed = runner(push_command(options, payload_path, dry_run=True))
            report["push"] = {"mode": "dry_run", "returncode": completed.returncode}
            report["status"] = "dry_run_complete" if completed.returncode == 0 else "push_failed"
            exit_code = 0 if completed.returncode == 0 else 4
            return finish(
                connection,
                options,
                report,
                exit_code,
                report_path,
                review_id=review_id,
                plan=plan,
                payload_path=payload_path,
            )

        automatic_push = decision["allowed"] and decision["mode"] == "auto_after_final_plan"
        should_push = options.push or automatic_push
        if should_push and not decision["allowed"]:
            report["status"] = "needs_push_confirmation"
            return finish(
                connection,
                options,
                report,
                3,
                report_path,
                review_id=review_id,
                plan=plan,
                payload_path=payload_path,
            )
        if not should_push:
            report["status"] = "final_plan_ready"
            return finish(
                connection,
                options,
                report,
                0,
                report_path,
                review_id=review_id,
                plan=plan,
                payload_path=payload_path,
            )

        completed = runner(push_command(options, payload_path, dry_run=False))
        push_result_path = GARMIN_RESULT_DIR / f"garmin_push_result_{options.target_date}.json"
        report["push"] = {
            "mode": "live",
            "returncode": completed.returncode,
            "result_path": str(push_result_path),
        }
        report["status"] = "pushed" if completed.returncode == 0 else "push_failed"
        exit_code = 0 if completed.returncode == 0 else 4
        return finish(
            connection,
            options,
            report,
            exit_code,
            report_path,
            review_id=review_id,
            plan=plan,
            payload_path=payload_path,
            push_result_path=push_result_path,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the observable TrainingOS daily workflow.")
    parser.add_argument("--date", required=True, help="Completed training date in YYYY-MM-DD format.")
    parser.add_argument("--target-date", required=True, help="Next plan date in YYYY-MM-DD format.")
    parser.add_argument("--db", default=str(trainingos_db.DEFAULT_DB_PATH), help="SQLite database path.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Local pipeline artifact directory.")
    parser.add_argument("--sync-garmin", action="store_true", help="Import Garmin recovery and strength data first.")
    parser.add_argument("--activity-days", type=int, default=3)
    parser.add_argument(
        "--anchor-lookback-days",
        type=int,
        default=180,
        help="One-time extended Strength history lookup when no local training anchor exists.",
    )
    parser.add_argument("--recovery-days", type=int, default=3)
    parser.add_argument("--ai-response", help="JSON AI review response to save before finalization.")
    parser.add_argument("--preset", choices=sorted(trainingos_garmin_payload.PRESETS), help="Override reviewed preset.")
    parser.add_argument("--confirm-push", action="store_true", help="Confirm this push for user-confirmed policy mode.")
    parser.add_argument("--push", action="store_true", help="Request a live Garmin write if the trigger gate allows it.")
    parser.add_argument("--dry-run-push", action="store_true", help="Validate the Garmin payload without a live write.")
    parser.add_argument("--venue", default=DEFAULT_VENUE, help="Venue used for equipment validation; empty disables it.")
    parser.add_argument(
        "--confirm-candidate-equipment",
        action="store_true",
        help="Confirm candidate equipment for this run without changing the catalog.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    options = PipelineOptions(
        training_date=args.date,
        target_date=args.target_date,
        db_path=Path(args.db),
        output_dir=Path(args.output_dir),
        sync_garmin=args.sync_garmin,
        activity_days=args.activity_days,
        anchor_lookback_days=args.anchor_lookback_days,
        recovery_days=args.recovery_days,
        ai_response_path=Path(args.ai_response) if args.ai_response else None,
        preset_override=args.preset,
        confirm_push=args.confirm_push,
        push=args.push,
        dry_run_push=args.dry_run_push,
        venue=args.venue,
        confirm_candidate_equipment=args.confirm_candidate_equipment,
    )
    exit_code, report = run_pipeline(options)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
