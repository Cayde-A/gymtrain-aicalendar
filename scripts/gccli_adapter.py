#!/usr/bin/env python3
"""Read-only gccli transport adapter and workout payload dry-run checks.

gccli is an optional Garmin transport. This module deliberately returns raw
provider JSON; TrainingOS normalizers and planning rules remain authoritative.
Remote workout writes stay in the existing audited push path until live parity
and idempotency checks have passed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

try:
    from .garmin_provider import ErrorCode, GarminProviderError, ProviderFailure
except ImportError:  # pragma: no cover - supports direct script execution.
    from garmin_provider import ErrorCode, GarminProviderError, ProviderFailure  # type: ignore


SOURCE_TOOL = "gccli"
READ_CAPABILITIES = (
    "activities",
    "activity_sets",
    "daily_summary",
    "sleep",
    "hrv",
    "body_battery",
    "training_readiness",
    "exercise_catalog",
)
WRITE_CAPABILITIES = ("workout_upload", "workout_schedule")

CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def default_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=False)


def _failure_from_process(
    process: subprocess.CompletedProcess[str], operation: str
) -> ProviderFailure:
    message = (process.stderr or process.stdout or "gccli command failed").strip()
    text = message.lower()
    if "no account specified" in text or any(
        term in text
        for term in ("not authenticated", "authentication", "unauthorized", "token expired")
    ):
        code, retryable = ErrorCode.AUTHENTICATION, False
    elif "429" in text or "rate limit" in text or "too many requests" in text:
        code, retryable = ErrorCode.RATE_LIMIT, True
    elif "not found" in text and "gccli" in text:
        code, retryable = ErrorCode.CAPABILITY_UNAVAILABLE, False
    elif any(term in text for term in ("invalid json", "decode", "unmarshal", "schema")):
        code, retryable = ErrorCode.SCHEMA, False
    elif process.returncode in {126, 127}:
        code, retryable = ErrorCode.CAPABILITY_UNAVAILABLE, False
    elif any(term in text for term in ("timeout", "connection", "temporarily unavailable", "502", "503")):
        code, retryable = ErrorCode.PROVIDER_OUTAGE, True
    else:
        code, retryable = ErrorCode.UNKNOWN, False
    return ProviderFailure(
        code=code,
        message=message[:500],
        retryable=retryable,
        operation=operation,
    )


def validate_workout_payload(payload: Any) -> dict[str, Any]:
    """Validate the gccli upload contract without making a remote write."""
    errors: list[str] = []
    if not isinstance(payload, dict):
        errors.append("payload must be a JSON object")
        return {"ok": False, "errors": errors, "remote_write": False}

    if not isinstance(payload.get("workoutName"), str) or not payload["workoutName"].strip():
        errors.append("workoutName must be a non-empty string")
    sport_type = payload.get("sportType")
    if not isinstance(sport_type, dict) or not sport_type.get("sportTypeKey"):
        errors.append("sportType.sportTypeKey is required")
    segments = payload.get("workoutSegments")
    if not isinstance(segments, list) or not segments:
        errors.append("workoutSegments must contain at least one segment")
    else:
        for segment_index, segment in enumerate(segments, start=1):
            steps = segment.get("workoutSteps") if isinstance(segment, dict) else None
            if not isinstance(steps, list) or not steps:
                errors.append(f"workoutSegments[{segment_index}] must contain workoutSteps")
                continue
            for step_index, step in enumerate(steps, start=1):
                if not isinstance(step, dict) or not step.get("type"):
                    errors.append(
                        f"workoutSegments[{segment_index}].workoutSteps[{step_index}] requires type"
                    )
    return {
        "ok": not errors,
        "errors": errors,
        "remote_write": False,
        "workout_name": payload.get("workoutName"),
        "segment_count": len(segments) if isinstance(segments, list) else 0,
    }


@dataclass
class GccliAdapter:
    binary: str = "gccli"
    account: str | None = None
    runner: CommandRunner = default_runner

    def installed(self) -> bool:
        return shutil.which(self.binary) is not None

    def _command(self, arguments: Sequence[str], *, json_output: bool = True) -> list[str]:
        command = [self.binary]
        if json_output:
            command.append("--json")
        if self.account:
            command.extend(["--account", self.account])
        command.extend(arguments)
        return command

    def run_json(self, operation: str, arguments: Sequence[str]) -> Any:
        if not self.installed():
            raise GarminProviderError(
                ProviderFailure(
                    code=ErrorCode.CAPABILITY_UNAVAILABLE,
                    message=f"{self.binary} is not installed",
                    retryable=False,
                    operation=operation,
                )
            )
        try:
            process = self.runner(self._command(arguments))
        except OSError as exc:
            raise GarminProviderError(
                ProviderFailure(
                    code=ErrorCode.CAPABILITY_UNAVAILABLE,
                    message=str(exc)[:500],
                    retryable=False,
                    operation=operation,
                )
            ) from exc
        if process.returncode != 0:
            raise GarminProviderError(_failure_from_process(process, operation))
        try:
            return json.loads(process.stdout)
        except json.JSONDecodeError as exc:
            raise GarminProviderError(
                ProviderFailure(
                    code=ErrorCode.SCHEMA,
                    message=f"gccli returned invalid JSON: {exc}",
                    retryable=False,
                    operation=operation,
                )
            ) from exc

    def version(self) -> str:
        if not self.installed():
            raise GarminProviderError(
                ProviderFailure(
                    code=ErrorCode.CAPABILITY_UNAVAILABLE,
                    message=f"{self.binary} is not installed",
                    retryable=False,
                    operation="version",
                )
            )
        process = self.runner([self.binary, "--version"])
        if process.returncode != 0:
            raise GarminProviderError(_failure_from_process(process, "version"))
        return process.stdout.strip()

    def auth_status(self) -> Any:
        return self.run_json("auth_status", ["auth", "status"])

    def activities(self, limit: int = 2, activity_type: str | None = None) -> Any:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        command = ["activities", "list", "--limit", str(limit)]
        if activity_type:
            command.extend(["--type", activity_type])
        return self.run_json("activities", command)

    def activity_summary(self, activity_id: int | str) -> Any:
        return self.run_json("activity_summary", ["activity", "summary", str(activity_id)])

    def activity_details(self, activity_id: int | str) -> Any:
        return self.run_json("activity_details", ["activity", "details", str(activity_id)])

    def activity_sets(self, activity_id: int | str) -> Any:
        return self.run_json(
            "activity_sets",
            ["activity", "exercise-sets", "show", str(activity_id)],
        )

    def recovery_day(self, date_text: str) -> dict[str, Any]:
        commands = {
            "stats": ["health", "summary", date_text],
            "sleep": ["health", "sleep", date_text],
            "hrv": ["health", "hrv", date_text],
            "body_battery": ["health", "body-battery", "view", date_text],
            "training_readiness": ["health", "training-readiness", date_text],
        }
        result: dict[str, Any] = {"date": date_text}
        for name, command in commands.items():
            result[name] = {
                "ok": True,
                "source_method": "gccli " + " ".join(command[:-1]),
                "data": self.run_json(name, command),
            }
        return result

    def exercise_catalog(self, category: str | None = None) -> Any:
        command = ["exercises", "list"]
        if category:
            command.extend(["--category", category])
        return self.run_json("exercise_catalog", command)

    def metadata(self) -> dict[str, Any]:
        return {
            "source_tool": SOURCE_TOOL,
            "version": self.version(),
            "capabilities": {
                **{name: True for name in READ_CAPABILITIES},
                # Writes remain disabled in TrainingOS until live parity passes.
                **{name: False for name in WRITE_CAPABILITIES},
            },
        }

    def dry_run_workout_file(self, path: str | Path) -> dict[str, Any]:
        payload_path = Path(path)
        try:
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {"ok": False, "errors": [str(exc)], "remote_write": False}
        result = validate_workout_payload(payload)
        result["proposed_command"] = self._command(
            ["workouts", "upload", str(payload_path.resolve())]
        )
        return result
