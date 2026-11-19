#!/usr/bin/env python3
"""Generate a trigger-gated structured post-workout review with the Responses API."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

try:
    from . import trainingos_db, trainingos_observability
except ImportError:  # pragma: no cover - supports direct script execution.
    import trainingos_db  # type: ignore
    import trainingos_observability  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "exports" / "ai"
RESPONSES_URL = "https://api.openai.com/v1/responses"
PRIMARY_GROUPS = ["legs", "chest", "back", "shoulders", "arms", "core", "recovery"]
INTERSTITIAL_CORE = ["none", "core_between_push_legs", "core_between_legs_pull"]


REVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "analysis_summary",
        "performance_direction",
        "risk_flags",
        "data_quality_issues",
        "initial_next_day_plan",
        "next_morning_adjustment_rules",
    ],
    "properties": {
        "analysis_summary": {"type": "string"},
        "performance_direction": {
            "type": "string",
            "enum": ["increase", "keep", "reduce", "deload"],
        },
        "risk_flags": {"type": "array", "items": {"type": "string"}},
        "data_quality_issues": {"type": "array", "items": {"type": "string"}},
        "initial_next_day_plan": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "status",
                "session_type",
                "primary_large_muscle_group",
                "interstitial_core",
                "focus",
                "avoided_overlap",
                "rounds",
            ],
            "properties": {
                "status": {"type": "string", "enum": ["initial_draft"]},
                "session_type": {"type": "string"},
                "primary_large_muscle_group": {"type": "string", "enum": PRIMARY_GROUPS},
                "interstitial_core": {"type": "string", "enum": INTERSTITIAL_CORE},
                "focus": {"type": "array", "items": {"type": "string"}},
                "avoided_overlap": {"type": "array", "items": {"type": "string"}},
                "rounds": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["exercise", "sets", "reps", "load_guidance", "rpe_cap"],
                        "properties": {
                            "exercise": {"type": "string"},
                            "sets": {"type": "integer", "minimum": 0, "maximum": 12},
                            "reps": {"type": "string"},
                            "load_guidance": {"type": "string"},
                            "rpe_cap": {"type": ["number", "null"]},
                        },
                    },
                },
            },
        },
        "next_morning_adjustment_rules": {"type": "array", "items": {"type": "string"}},
    },
}


def build_request(packet: dict[str, Any], model: str) -> dict[str, Any]:
    return {
        "model": model,
        "store": False,
        "max_output_tokens": 1800,
        "reasoning": {"effort": "low"},
        "instructions": (
            "You are TrainingOS Coach Agent. Use only the supplied packet. Keep analysis compact. "
            "Return an initial draft only; deterministic local validation will finalize it after recovery sync."
        ),
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(packet, ensure_ascii=False, sort_keys=True),
                    }
                ],
            }
        ],
        "text": {
            "verbosity": "low",
            "format": {
                "type": "json_schema",
                "name": "trainingos_post_workout_review",
                "description": "TrainingOS post-workout review and initial next-day draft",
                "strict": True,
                "schema": REVIEW_SCHEMA,
            },
        },
        "metadata": {"workflow": "trainingos_post_workout_review"},
    }


def extract_output_text(response: dict[str, Any]) -> str:
    for output in response.get("output") or []:
        if output.get("type") != "message":
            continue
        for content in output.get("content") or []:
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                return str(content["text"])
    raise ValueError("Responses API result does not contain output_text")


def validate_review_output(review: dict[str, Any]) -> list[str]:
    issues = []
    required = set(REVIEW_SCHEMA["required"])
    missing = sorted(required - set(review))
    if missing:
        issues.append("missing_fields:" + ",".join(missing))
    extra = sorted(set(review) - required)
    if extra:
        issues.append("unexpected_fields:" + ",".join(extra))
    if review.get("performance_direction") not in {"increase", "keep", "reduce", "deload"}:
        issues.append("invalid_performance_direction")
    if not isinstance(review.get("analysis_summary"), str):
        issues.append("analysis_summary_not_string")
    plan = review.get("initial_next_day_plan")
    if not isinstance(plan, dict):
        issues.append("initial_next_day_plan_not_object")
        return issues
    if plan.get("status") != "initial_draft":
        issues.append("plan_status_must_be_initial_draft")
    if plan.get("primary_large_muscle_group") not in PRIMARY_GROUPS:
        issues.append("invalid_primary_large_muscle_group")
    if plan.get("interstitial_core") not in INTERSTITIAL_CORE:
        issues.append("invalid_interstitial_core")
    plan_required = set(REVIEW_SCHEMA["properties"]["initial_next_day_plan"]["required"])
    if set(plan) != plan_required:
        issues.append("initial_next_day_plan_fields_mismatch")
    if not isinstance(plan.get("session_type"), str):
        issues.append("session_type_not_string")
    for field in ("focus", "avoided_overlap"):
        if not isinstance(plan.get(field), list) or not all(
            isinstance(item, str) for item in plan.get(field, [])
        ):
            issues.append(f"{field}_not_string_array")
    if not isinstance(plan.get("rounds"), list):
        issues.append("rounds_not_array")
    else:
        round_fields = {"exercise", "sets", "reps", "load_guidance", "rpe_cap"}
        for index, round_item in enumerate(plan["rounds"]):
            if not isinstance(round_item, dict) or set(round_item) != round_fields:
                issues.append(f"round_{index}_fields_mismatch")
                continue
            if not isinstance(round_item["exercise"], str):
                issues.append(f"round_{index}_exercise_not_string")
            if (
                not isinstance(round_item["sets"], int)
                or isinstance(round_item["sets"], bool)
                or not 0 <= round_item["sets"] <= 12
            ):
                issues.append(f"round_{index}_sets_invalid")
            if not isinstance(round_item["reps"], str):
                issues.append(f"round_{index}_reps_not_string")
            if not isinstance(round_item["load_guidance"], str):
                issues.append(f"round_{index}_load_guidance_not_string")
            if round_item["rpe_cap"] is not None and (
                not isinstance(round_item["rpe_cap"], (int, float))
                or isinstance(round_item["rpe_cap"], bool)
            ):
                issues.append(f"round_{index}_rpe_cap_invalid")
    for field in ("risk_flags", "data_quality_issues", "next_morning_adjustment_rules"):
        if not isinstance(review.get(field), list) or not all(
            isinstance(item, str) for item in review.get(field, [])
        ):
            issues.append(f"{field}_not_string_array")
    return issues


Requester = Callable[[dict[str, Any], str], tuple[int, dict[str, Any]]]


def request_openai(payload: dict[str, Any], api_key: str) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        RESPONSES_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            body = response.read().decode("utf-8")
            return int(response.status), json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {"error": {"message": body[:500]}}
        return int(exc.code), parsed


def existing_structured_review(connection: Any, training_date: str) -> dict[str, Any] | None:
    for review in trainingos_db.get_ai_reviews_for_day(connection, training_date):
        try:
            target = json.loads(review.get("next_target_json") or "{}")
        except json.JSONDecodeError:
            continue
        raw = target.get("raw_json")
        if isinstance(raw, dict) and not validate_review_output(raw):
            return review
    return None


def run_review(
    connection: Any,
    training_date: str,
    model: str,
    user_confirmed: bool,
    api_key: str | None,
    requester: Requester = request_openai,
    force: bool = False,
) -> tuple[int, dict[str, Any]]:
    anchor = trainingos_db.training_anchor_state(connection, training_date)
    if not anchor["ready"]:
        return 3, {
            "status": anchor["status"],
            "training_anchor": anchor,
            "message": "TrainingOS will wait for the first completed workout before analysis.",
            "api_called": False,
        }
    existing = existing_structured_review(connection, training_date)
    if existing and not force:
        return 0, {
            "status": "existing_review_reused",
            "review_id": existing["id"],
            "training_date": training_date,
            "api_called": False,
        }
    packet = trainingos_db.build_day_ai_review_packet(connection, training_date)
    decision = trainingos_db.evaluate_api_trigger(
        connection,
        "post_workout_ai",
        user_confirmed=user_confirmed,
    )
    trainingos_db.record_api_trigger_decision(
        connection,
        decision,
        context={"training_date": training_date, "adapter": "openai_responses"},
    )
    if not decision["allowed"]:
        return 3, {"status": decision["status"], "trigger": decision, "api_called": False}
    if not api_key:
        return 3, {"status": "needs_api_key", "key_env": "OPENAI_API_KEY", "api_called": False}
    request_payload = build_request(packet, model)
    status, response = requester(request_payload, api_key)
    if status not in {200, 201}:
        error = response.get("error") or {}
        return 4, {
            "status": "openai_api_failed",
            "http_status": status,
            "error_type": error.get("type"),
            "error_code": error.get("code"),
            "api_called": True,
        }
    try:
        output_text = extract_output_text(response)
        review = json.loads(output_text)
    except (ValueError, json.JSONDecodeError) as exc:
        return 4, {"status": "invalid_structured_output", "message": str(exc), "api_called": True}
    issues = validate_review_output(review)
    if issues:
        return 4, {"status": "invalid_structured_output", "issues": issues, "api_called": True}
    review_id = trainingos_db.save_day_ai_review_response(
        connection,
        training_date,
        json.dumps(review, ensure_ascii=False),
    )
    trainingos_observability.record_event(
        "structured_ai_review_completed",
        details={"training_date": training_date, "review_id": review_id, "model": model},
    )
    usage = response.get("usage") or {}
    return 0, {
        "status": "review_saved",
        "review_id": review_id,
        "training_date": training_date,
        "model": model,
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "api_called": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a structured TrainingOS post-workout review.")
    parser.add_argument("--date", required=True, help="Completed training date.")
    parser.add_argument("--db", default=str(trainingos_db.DEFAULT_DB_PATH))
    parser.add_argument("--model", default=os.environ.get("TRAININGOS_OPENAI_MODEL", "gpt-5-mini"))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--call", action="store_true", help="Call the API after all gates pass.")
    parser.add_argument("--force", action="store_true", help="Ignore an existing structured review.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db)
    trainingos_db.init_db(db_path)
    with trainingos_db.connect(db_path) as connection:
        anchor = trainingos_db.training_anchor_state(connection, args.date)
        if not anchor["ready"]:
            print(
                json.dumps(
                    {
                        "status": anchor["status"],
                        "training_anchor": anchor,
                        "message": "TrainingOS will wait for the first completed workout before analysis.",
                        "api_called": False,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 3
        packet = trainingos_db.build_day_ai_review_packet(connection, args.date)
        request_payload = build_request(packet, args.model)
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        request_path = output_dir / f"openai_review_request_{args.date}.json"
        request_path.write_text(
            json.dumps(request_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        if not args.call:
            print(
                json.dumps(
                    {"status": "dry_run", "request_path": str(request_path), "api_called": False},
                    indent=2,
                )
            )
            return 0
        exit_code, result = run_review(
            connection,
            args.date,
            args.model,
            args.confirm,
            os.environ.get("OPENAI_API_KEY"),
            force=args.force,
        )
    result["request_path"] = str(request_path)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
