#!/usr/bin/env python3
"""Upload, schedule, and optionally push a TrainingOS strength workout to Garmin."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

try:
    from .garmin_import import write_json
    from . import garmin_write_journal, trainingos_db
    from .garmin_provider import (
        ErrorCode,
        GarminProviderError,
        ProviderFailure,
        classify_error,
        default_tokenstore,
        execute,
        execute_with_retry,
        load_dotenv_local,
        login,
    )
except ImportError:
    from garmin_import import write_json  # type: ignore
    import garmin_write_journal  # type: ignore
    import trainingos_db  # type: ignore
    from garmin_provider import (  # type: ignore
        ErrorCode,
        GarminProviderError,
        ProviderFailure,
        classify_error,
        default_tokenstore,
        execute,
        execute_with_retry,
        load_dotenv_local,
        login,
    )


ROOT = Path(__file__).resolve().parents[1]
RESULT_DIR = ROOT / "exports" / "garmin" / "normalized"


def parse_args() -> argparse.Namespace:
    load_dotenv_local()
    parser = argparse.ArgumentParser(description="Push a TrainingOS workout to Garmin.")
    parser.add_argument("--payload", required=True, help="Workout payload JSON path.")
    parser.add_argument("--date", required=True, help="Schedule date in YYYY-MM-DD format.")
    parser.add_argument("--name", help="Override workout name before upload.")
    parser.add_argument("--email", help="Garmin email. Defaults to GARMIN_EMAIL.")
    parser.add_argument("--password", help="Garmin password. Defaults to GARMIN_PASSWORD.")
    parser.add_argument(
        "--tokenstore",
        default=str(default_tokenstore()),
        help="Local Garmin token cache directory. Defaults to tokens/garmin.",
    )
    parser.add_argument("--skip-push", action="store_true", help="Schedule only; do not push to watch.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and write payload without Garmin API calls.")
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Unschedule same-date, same-name Garmin workouts before scheduling the new one.",
    )
    parser.add_argument("--db", default=str(trainingos_db.DEFAULT_DB_PATH), help="Local idempotency journal database.")
    parser.add_argument("--idempotency-key", help="Stable key supplied by the caller. Defaults to payload-derived key.")
    parser.add_argument("--max-read-attempts", type=int, default=3, help="Maximum attempts for retryable Garmin reads.")
    parser.add_argument("--retry-base-seconds", type=float, default=1.0, help="Initial read retry delay.")
    parser.add_argument("--result-dir", default=str(RESULT_DIR), help="Directory for the machine-readable result.")
    parser.add_argument(
        "--retry-ambiguous-push",
        action="store_true",
        help="Explicitly retry a device push whose previous outcome could not be confirmed.",
    )
    return parser.parse_args()


def load_payload(path: Path, name: str | None = None) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Workout payload must be a JSON object.")
    if name:
        payload["workoutName"] = name
    if not payload.get("workoutName"):
        raise ValueError("Workout payload is missing workoutName.")
    if not payload.get("workoutSegments"):
        raise ValueError("Workout payload is missing workoutSegments.")
    return payload


def deep_find_workout_id(value: Any) -> int | None:
    if isinstance(value, dict):
        for key in ("workoutId", "workout_id", "id"):
            candidate = value.get(key)
            if isinstance(candidate, int):
                return candidate
            if isinstance(candidate, str) and candidate.isdigit():
                return int(candidate)
        for child in value.values():
            found = deep_find_workout_id(child)
            if found is not None:
                return found
    if isinstance(value, list):
        for child in value:
            found = deep_find_workout_id(child)
            if found is not None:
                return found
    return None


def walk_dicts(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        items = [value]
        for child in value.values():
            items.extend(walk_dicts(child))
        return items
    if isinstance(value, list):
        items = []
        for child in value:
            items.extend(walk_dicts(child))
        return items
    return []


def first_text(value: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate:
            return candidate
    return None


def find_scheduled_workouts(
    scheduled_payload: Any,
    schedule_date: str,
    workout_name: str,
) -> list[dict[str, Any]]:
    matches = []
    for item in walk_dicts(scheduled_payload):
        date_text = first_text(item, ("calendarDate", "date", "scheduledDate"))
        if date_text != schedule_date:
            continue
        name = first_text(item, ("workoutName", "name", "messageName", "title"))
        if name is None and isinstance(item.get("workout"), dict):
            name = first_text(item["workout"], ("workoutName", "name", "messageName", "title"))
        if name != workout_name:
            continue
        schedule_id = (
            item.get("workoutScheduleId")
            or item.get("scheduledWorkoutId")
            or item.get("scheduleId")
            or item.get("id")
        )
        if isinstance(schedule_id, str) and schedule_id.isdigit():
            schedule_id = int(schedule_id)
        if isinstance(schedule_id, int):
            match = {"workoutScheduleId": schedule_id, "calendarDate": date_text, "workoutName": name}
            workout_id = find_named_workout_id(item)
            if workout_id is not None:
                match["workoutId"] = workout_id
            matches.append(match)
    return matches


def find_named_workout_id(value: Any) -> int | None:
    if isinstance(value, dict):
        for key in ("workoutId", "workout_id"):
            candidate = value.get(key)
            if isinstance(candidate, int):
                return candidate
            if isinstance(candidate, str) and candidate.isdigit():
                return int(candidate)
        for child in value.values():
            found = find_named_workout_id(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_named_workout_id(child)
            if found is not None:
                return found
    return None


def read_scheduled_workouts(
    client: Any,
    schedule_date: str,
    max_attempts: int,
    base_delay_seconds: float,
) -> Any:
    date_value = dt.date.fromisoformat(schedule_date)
    return execute_with_retry(
        "get_scheduled_workouts",
        client.get_scheduled_workouts,
        date_value.year,
        date_value.month,
        max_attempts=max_attempts,
        base_delay_seconds=base_delay_seconds,
    )


def unschedule_matching_workouts(
    client: Any,
    schedule_date: str,
    workout_name: str,
    max_attempts: int = 3,
    base_delay_seconds: float = 1.0,
) -> list[dict[str, Any]]:
    scheduled_payload = read_scheduled_workouts(client, schedule_date, max_attempts, base_delay_seconds)
    matches = find_scheduled_workouts(scheduled_payload, schedule_date, workout_name)
    unscheduled = []
    for match in matches:
        response = execute(
            "unschedule_workout",
            client.unschedule_workout,
            match["workoutScheduleId"],
        )
        unscheduled.append({**match, "response": response})
    return unscheduled


def idempotency_marker(idempotency_key: str) -> str:
    return f"[trainingos:{idempotency_key[:16]}]"


def payload_with_marker(payload: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
    marked = copy.deepcopy(payload)
    marker = idempotency_marker(idempotency_key)
    description = str(marked.get("description") or "").strip()
    if marker not in description:
        marked["description"] = f"{description} {marker}".strip()
    return marked


def find_uploaded_workout_id(
    client: Any,
    workout_name: str,
    idempotency_key: str,
    max_attempts: int,
    base_delay_seconds: float,
) -> int | None:
    workouts = execute_with_retry(
        "get_workouts",
        client.get_workouts,
        0,
        100,
        max_attempts=max_attempts,
        base_delay_seconds=base_delay_seconds,
    )
    marker = idempotency_marker(idempotency_key)
    matches = []
    for item in workouts if isinstance(workouts, list) else []:
        if not isinstance(item, dict):
            continue
        name = first_text(item, ("workoutName", "name", "title"))
        description = first_text(item, ("description", "workoutDescription")) or ""
        workout_id = find_named_workout_id(item) or deep_find_workout_id(item)
        if name == workout_name and marker in description and workout_id is not None:
            matches.append(workout_id)
    return max(matches) if matches else None


def confirm_schedule(
    client: Any,
    schedule_date: str,
    workout_name: str,
    workout_id: int,
    max_attempts: int,
    base_delay_seconds: float,
) -> dict[str, Any] | None:
    scheduled = read_scheduled_workouts(client, schedule_date, max_attempts, base_delay_seconds)
    matches = find_scheduled_workouts(scheduled, schedule_date, workout_name)
    exact = [item for item in matches if item.get("workoutId") == workout_id]
    if exact:
        return exact[0]
    # Some Garmin responses omit workoutId; date and unique TrainingOS name still confirm the schedule.
    return matches[0] if matches else None


def upload_workout(client: Any, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        from garminconnect.workout import StrengthWorkout
    except ImportError:
        StrengthWorkout = None  # type: ignore[assignment]

    if StrengthWorkout is not None:
        try:
            workout = StrengthWorkout(**payload)
        except Exception:
            workout = None
        if workout is not None:
            return client.upload_strength_workout(workout)
    return client.upload_workout(payload)


def perform_garmin_write(
    connection: Any,
    client: Any,
    payload: dict[str, Any],
    schedule_date: str,
    idempotency_key: str,
    *,
    replace_existing: bool,
    skip_push: bool,
    retry_ambiguous_push: bool,
    max_read_attempts: int,
    retry_base_seconds: float,
) -> dict[str, Any]:
    operation = garmin_write_journal.get_operation(connection, idempotency_key)
    if operation is None:
        raise ValueError("Garmin write operation was not initialized.")
    garmin_write_journal.update_operation(connection, idempotency_key, increment_attempts=True)
    operation = garmin_write_journal.get_operation(connection, idempotency_key) or operation
    workout_name = str(payload["workoutName"])
    phase = str(operation["phase"])
    workout_id = operation.get("workout_id")
    unscheduled: list[dict[str, Any]] = []

    if phase == "push_unknown" and not retry_ambiguous_push:
        raise GarminProviderError(
            ProviderFailure(
                code=ErrorCode.AMBIGUOUS_WRITE,
                message="Previous device push outcome is unknown; explicit retry confirmation is required.",
                retryable=False,
                operation="push_workout_to_device",
            )
        )
    if phase == "push_unknown":
        phase = "scheduled"
        garmin_write_journal.update_operation(
            connection,
            idempotency_key,
            status="pending",
            phase="scheduled",
            error={},
        )

    if operation["status"] == "confirmed" and workout_id is not None:
        confirmed = confirm_schedule(
            client,
            schedule_date,
            workout_name,
            int(workout_id),
            max_read_attempts,
            retry_base_seconds,
        )
        if confirmed:
            return {
                "status": "idempotent",
                "phase": phase,
                "workout_id": int(workout_id),
                "schedule_confirmation": confirmed,
                "idempotency_key": idempotency_key,
            }
        phase = "uploaded"
        garmin_write_journal.update_operation(
            connection,
            idempotency_key,
            status="pending",
            phase=phase,
            error={},
        )

    marked_payload = payload_with_marker(payload, idempotency_key)
    if phase == "created":
        recovered_id = find_uploaded_workout_id(
            client,
            workout_name,
            idempotency_key,
            max_read_attempts,
            retry_base_seconds,
        )
        if recovered_id is not None:
            workout_id = recovered_id
        else:
            if replace_existing:
                unscheduled = unschedule_matching_workouts(
                    client,
                    schedule_date,
                    workout_name,
                    max_read_attempts,
                    retry_base_seconds,
                )
            try:
                uploaded = execute("upload_workout", upload_workout, client, marked_payload)
                workout_id = deep_find_workout_id(uploaded)
            except GarminProviderError as exc:
                if not exc.failure.retryable:
                    raise
                workout_id = find_uploaded_workout_id(
                    client,
                    workout_name,
                    idempotency_key,
                    max_read_attempts,
                    retry_base_seconds,
                )
                if workout_id is None:
                    raise
            if workout_id is None:
                raise ValueError("Garmin upload response did not contain a workout id")
        phase = "uploaded"
        garmin_write_journal.update_operation(
            connection,
            idempotency_key,
            status="pending",
            phase=phase,
            workout_id=int(workout_id),
            error={},
        )

    if workout_id is None:
        raise ValueError("Garmin write journal is missing workout_id after upload phase")

    if phase == "uploaded":
        try:
            scheduled_response = execute("schedule_workout", client.schedule_workout, int(workout_id), schedule_date)
        except GarminProviderError as exc:
            if not exc.failure.retryable:
                raise
            confirmed = confirm_schedule(
                client,
                schedule_date,
                workout_name,
                int(workout_id),
                max_read_attempts,
                retry_base_seconds,
            )
            if not confirmed:
                raise
            scheduled_response = {"recovered_after_error": True, "confirmation": confirmed}
        phase = "scheduled"
        garmin_write_journal.update_operation(
            connection,
            idempotency_key,
            status="pending",
            phase=phase,
            result={"scheduled": scheduled_response},
            error={},
        )

    confirmation = confirm_schedule(
        client,
        schedule_date,
        workout_name,
        int(workout_id),
        max_read_attempts,
        retry_base_seconds,
    )
    if confirmation is None:
        raise GarminProviderError(
            ProviderFailure(
                code=ErrorCode.CONFIRMATION_FAILED,
                message="Garmin schedule write could not be confirmed by a calendar read.",
                retryable=True,
                operation="confirm_schedule",
            )
        )
    schedule_id = confirmation.get("workoutScheduleId")
    garmin_write_journal.update_operation(
        connection,
        idempotency_key,
        status="pending",
        phase="scheduled",
        workout_schedule_id=int(schedule_id) if isinstance(schedule_id, int) else None,
        error={},
    )

    pushed = None
    if not skip_push and phase == "scheduled":
        try:
            pushed = execute("push_workout_to_device", client.push_workout_to_device, int(workout_id))
        except GarminProviderError as exc:
            if exc.failure.code == ErrorCode.PROVIDER_OUTAGE:
                garmin_write_journal.update_operation(
                    connection,
                    idempotency_key,
                    status="failed",
                    phase="push_unknown",
                    error=exc.to_dict(),
                )
            raise
        phase = "push_requested"
        garmin_write_journal.update_operation(
            connection,
            idempotency_key,
            status="pending",
            phase=phase,
            result={"pushed": pushed, "schedule_confirmation": confirmation},
            error={},
        )

    result = {
        "status": "confirmed",
        "phase": phase,
        "workout_id": int(workout_id),
        "workout_schedule_id": schedule_id,
        "schedule_confirmation": confirmation,
        "push_requested": pushed is not None,
        "unscheduled": unscheduled,
        "idempotency_key": idempotency_key,
    }
    garmin_write_journal.update_operation(
        connection,
        idempotency_key,
        status="confirmed",
        phase=phase,
        result=result,
        error={},
    )
    return result


def main() -> int:
    args = parse_args()
    schedule_date = dt.date.fromisoformat(args.date).isoformat()
    payload = load_payload(Path(args.payload), args.name)
    result_path = Path(args.result_dir) / f"garmin_push_result_{schedule_date}.json"
    payload_hash = garmin_write_journal.canonical_payload_hash(payload)
    idempotency_key = args.idempotency_key or garmin_write_journal.default_idempotency_key(
        schedule_date,
        str(payload["workoutName"]),
        payload_hash,
    )
    if args.dry_run:
        write_json(
            result_path,
            {
                "status": "dry_run",
                "scheduled_date": schedule_date,
                "workout_name": payload["workoutName"],
                "payload_hash": payload_hash,
                "idempotency_key": idempotency_key,
                "payload": payload,
            },
        )
        print(f"Dry run OK: {payload['workoutName']} for {schedule_date}")
        print(f"Result: {result_path}")
        return 0

    db_path = Path(args.db)
    garmin_write_journal.initialize(db_path)
    operation_initialized = False
    try:
        with trainingos_db.connect(db_path) as connection:
            garmin_write_journal.begin_operation(
                connection,
                idempotency_key,
                payload_hash,
                str(payload["workoutName"]),
                schedule_date,
            )
            operation_initialized = True
            client = login(args.email, args.password, args.tokenstore)
            result = perform_garmin_write(
                connection,
                client,
                payload,
                schedule_date,
                idempotency_key,
                replace_existing=args.replace_existing,
                skip_push=args.skip_push,
                retry_ambiguous_push=args.retry_ambiguous_push,
                max_read_attempts=args.max_read_attempts,
                retry_base_seconds=args.retry_base_seconds,
            )
    except GarminProviderError as exc:
        with trainingos_db.connect(db_path) as connection:
            if operation_initialized and garmin_write_journal.get_operation(connection, idempotency_key):
                current = garmin_write_journal.get_operation(connection, idempotency_key) or {}
                phase = "push_unknown" if current.get("phase") == "push_unknown" else current.get("phase")
                garmin_write_journal.update_operation(
                    connection,
                    idempotency_key,
                    status="failed",
                    phase=phase,
                    next_retry_at=garmin_write_journal.retry_time(exc.to_dict()),
                    error=exc.to_dict(),
                )
        write_json(
            result_path,
            {
                "status": "failed",
                "scheduled_date": schedule_date,
                "workout_name": payload["workoutName"],
                "idempotency_key": idempotency_key,
                "error": exc.to_dict(),
            },
        )
        print(f"Garmin push failed: {exc.failure.code}")
        print(f"Retryable: {str(exc.failure.retryable).lower()}")
        print(f"Result: {result_path}")
        return 2
    except Exception as exc:
        failure = classify_error(exc, "validate_upload_response")
        with trainingos_db.connect(db_path) as connection:
            if operation_initialized and garmin_write_journal.get_operation(connection, idempotency_key):
                garmin_write_journal.update_operation(
                    connection,
                    idempotency_key,
                    status="failed",
                    next_retry_at=garmin_write_journal.retry_time(failure.to_dict()),
                    error=failure.to_dict(),
                )
        write_json(
            result_path,
            {
                "status": "failed",
                "scheduled_date": schedule_date,
                "workout_name": payload["workoutName"],
                "idempotency_key": idempotency_key,
                "error": failure.to_dict(),
            },
        )
        print(f"Garmin push failed: {failure.code}")
        print(f"Retryable: {str(failure.retryable).lower()}")
        print(f"Result: {result_path}")
        return 2
    write_json(result_path, {**result, "scheduled_date": schedule_date, "workout_name": payload["workoutName"]})
    print(f"Workout: {payload['workoutName']}")
    print(f"Workout id: {result['workout_id']}")
    print(f"Scheduled date: {schedule_date}")
    print(f"Status: {result['status']}")
    print(f"Idempotency key: {idempotency_key}")
    print(f"Result: {result_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
