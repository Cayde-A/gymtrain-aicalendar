#!/usr/bin/env python3
"""Decode Garmin activity ZIP bytes into TrainingOS-compatible strength sets."""

from __future__ import annotations

import io
import zipfile
from typing import Any


MAX_FIT_BYTES = 20 * 1024 * 1024
MAX_ZIP_BYTES = 25 * 1024 * 1024


def first_scalar(value: Any) -> Any:
    if isinstance(value, list):
        return next((item for item in value if item is not None), None)
    return value


def exercise_identifier(category: Any, subtype: Any, profile_types: dict[str, Any]) -> str:
    category_value = first_scalar(category)
    subtype_value = first_scalar(subtype)
    category_name = str(category_value or "unknown").lower()
    type_name = f"{category_name}_exercise_name"
    mapped = profile_types.get(type_name, {}).get(subtype_value)
    return str(mapped or category_name or "unknown").upper()


def normalize_fit_set_messages(
    set_messages: list[dict[str, Any]],
    profile_types: dict[str, Any],
) -> list[dict[str, Any]]:
    sets = []
    active_order = 0
    for index, message in enumerate(set_messages, start=1):
        set_type = str(message.get("set_type") or "active").lower()
        if set_type == "rest":
            exercise_name = "Rest"
        else:
            active_order += 1
            exercise_name = exercise_identifier(
                message.get("category"), message.get("category_subtype"), profile_types
            )
        repetitions = message.get("repetitions")
        weight = message.get("weight")
        sets.append(
            {
                "exerciseName": exercise_name,
                "setNumber": index,
                "setType": set_type,
                "weight": weight if isinstance(weight, (int, float)) else None,
                "repetitionCount": (
                    int(repetitions) if isinstance(repetitions, (int, float)) else None
                ),
                "fitActiveOrder": active_order if set_type != "rest" else None,
            }
        )
    return sets


def decode_fit_bytes(fit_bytes: bytes) -> tuple[dict[str, Any], list[Any]]:
    try:
        from garmin_fit_sdk import Decoder, Stream
    except ImportError as exc:  # pragma: no cover - dependency error is environment-specific.
        raise RuntimeError("garmin-fit-sdk is required for FIT activity fallback") from exc
    decoder = Decoder(Stream.from_bytes_io(io.BytesIO(fit_bytes)))
    return decoder.read()


def decode_activity_zip(zip_bytes: bytes) -> dict[str, Any]:
    if not zip_bytes or len(zip_bytes) > MAX_ZIP_BYTES:
        raise ValueError("Garmin activity ZIP size is outside the allowed range")
    if not zipfile.is_zipfile(io.BytesIO(zip_bytes)):
        raise ValueError("Garmin activity download is not a ZIP file")
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        fit_members = [
            item
            for item in archive.infolist()
            if not item.is_dir() and item.filename.lower().endswith(".fit")
        ]
        if len(fit_members) != 1:
            raise ValueError("Garmin activity ZIP must contain exactly one FIT file")
        member = fit_members[0]
        if member.file_size <= 0 or member.file_size > MAX_FIT_BYTES:
            raise ValueError("Garmin FIT file size is outside the allowed range")
        fit_bytes = archive.read(member)
    messages, errors = decode_fit_bytes(fit_bytes)
    if errors:
        raise ValueError(f"Garmin FIT decode returned {len(errors)} error(s)")
    try:
        from garmin_fit_sdk.profile import Profile
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("garmin-fit-sdk profile is unavailable") from exc
    set_messages = messages.get("set_mesgs") or []
    if not isinstance(set_messages, list):
        set_messages = []
    return {
        "exerciseSets": normalize_fit_set_messages(set_messages, Profile.get("types", {})),
        "fit_message_count": len(set_messages),
    }
