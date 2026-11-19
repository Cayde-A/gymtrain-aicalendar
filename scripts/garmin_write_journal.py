#!/usr/bin/env python3
"""Persistent idempotency journal for TrainingOS Garmin writes."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from . import trainingos_db
except ImportError:  # pragma: no cover - supports direct script execution.
    import trainingos_db  # type: ignore


def canonical_payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def default_idempotency_key(schedule_date: str, workout_name: str, payload_hash: str) -> str:
    source = f"garmin-workout|{schedule_date}|{workout_name}|{payload_hash}"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def initialize(db_path: Path) -> None:
    trainingos_db.init_db(db_path)


def get_operation(connection: Any, idempotency_key: str) -> dict[str, Any] | None:
    row = connection.execute(
        "select * from garmin_write_operations where idempotency_key = ?",
        (idempotency_key,),
    ).fetchone()
    return dict(row) if row else None


def begin_operation(
    connection: Any,
    idempotency_key: str,
    payload_hash: str,
    workout_name: str,
    schedule_date: str,
) -> dict[str, Any]:
    existing = get_operation(connection, idempotency_key)
    if existing:
        expected = (payload_hash, workout_name, schedule_date)
        actual = (existing["payload_hash"], existing["workout_name"], existing["schedule_date"])
        if actual != expected:
            raise ValueError("Idempotency key is already bound to a different Garmin write.")
        return existing
    operation_id = f"garmin_write_{idempotency_key[:24]}"
    connection.execute(
        """
        insert into garmin_write_operations (
          id, athlete_id, idempotency_key, payload_hash, workout_name, schedule_date
        ) values (?, ?, ?, ?, ?, ?)
        """,
        (
            operation_id,
            trainingos_db.DEFAULT_ATHLETE_ID,
            idempotency_key,
            payload_hash,
            workout_name,
            schedule_date,
        ),
    )
    connection.commit()
    return get_operation(connection, idempotency_key) or {}


def update_operation(
    connection: Any,
    idempotency_key: str,
    *,
    status: str | None = None,
    phase: str | None = None,
    workout_id: int | None = None,
    workout_schedule_id: int | None = None,
    increment_attempts: bool = False,
    next_retry_at: str | None = None,
    error: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current = get_operation(connection, idempotency_key)
    if current is None:
        raise ValueError("Unknown Garmin write operation.")
    connection.execute(
        """
        update garmin_write_operations
        set status = ?,
            phase = ?,
            workout_id = ?,
            workout_schedule_id = ?,
            attempt_count = attempt_count + ?,
            next_retry_at = ?,
            last_error_json = ?,
            result_json = ?,
            updated_at = current_timestamp
        where idempotency_key = ?
        """,
        (
            status if status is not None else current["status"],
            phase if phase is not None else current["phase"],
            workout_id if workout_id is not None else current["workout_id"],
            workout_schedule_id if workout_schedule_id is not None else current["workout_schedule_id"],
            1 if increment_attempts else 0,
            next_retry_at,
            json.dumps(error, ensure_ascii=False, sort_keys=True) if error is not None else current["last_error_json"],
            json.dumps(result, ensure_ascii=False, sort_keys=True) if result is not None else current["result_json"],
            idempotency_key,
        ),
    )
    connection.commit()
    return get_operation(connection, idempotency_key) or {}


def retry_time(failure: dict[str, Any], now: dt.datetime | None = None) -> str | None:
    if not failure.get("retryable"):
        return None
    current = now or dt.datetime.now()
    delay_minutes = 30 if failure.get("code") == "rate_limit" else 5
    return (current + dt.timedelta(minutes=delay_minutes)).isoformat(timespec="seconds")
