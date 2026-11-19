#!/usr/bin/env python3
"""Parse short local voice transcripts into editable strength-training sets."""

from __future__ import annotations

import re
from typing import Any


NUMBER = r"(?:\d+(?:\.\d+)?|[零〇一二两三四五六七八九十百点]+)"
REPEAT_PATTERN = re.compile(r"(?:再来一组|重复(?:一组)?|same(?: set)?|repeat(?: set)?)", re.I)
WEIGHT_PATTERN = re.compile(rf"(?P<value>{NUMBER})\s*(?:公斤|千克|kgs?|公斤重)", re.I)
REPS_PATTERN = re.compile(rf"(?P<value>{NUMBER})\s*(?:次|个|reps?|下)", re.I)
SETS_PATTERN = re.compile(rf"(?P<value>{NUMBER})\s*(?:组|sets?)", re.I)
RPE_PATTERN = re.compile(rf"(?:r\s*p\s*e|难度)\s*(?P<value>{NUMBER})", re.I)
ADJUST_PATTERN = re.compile(
    rf"(?P<direction>加|增加|升|减|减少|降|plus|minus)\s*(?P<value>{NUMBER})\s*(?:公斤|千克|kg|kgs)?",
    re.I,
)


def chinese_number(value: str) -> float:
    if re.fullmatch(r"\d+(?:\.\d+)?", value):
        return float(value)
    digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if "点" in value:
        whole, fraction = value.split("点", 1)
        fraction_value = "".join(str(digits[item]) for item in fraction)
        return chinese_number(whole or "零") + float(f"0.{fraction_value}")
    total = 0
    current = 0
    for character in value:
        if character in digits:
            current = digits[character]
        elif character == "十":
            total += (current or 1) * 10
            current = 0
        elif character == "百":
            total += (current or 1) * 100
            current = 0
        else:
            raise ValueError(f"Unsupported Chinese number: {value}")
    return float(total + current)


def matched_number(pattern: re.Pattern[str], text: str) -> float | None:
    match = pattern.search(text)
    return chinese_number(match.group("value")) if match else None


def clean_exercise(text: str) -> str:
    cleaned = text
    for pattern in (WEIGHT_PATTERN, REPS_PATTERN, SETS_PATTERN, RPE_PATTERN, ADJUST_PATTERN, REPEAT_PATTERN):
        cleaned = pattern.sub(" ", cleaned)
    cleaned = re.sub(r"[，,。；;：:]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -")
    return cleaned


def parse_voice_entry(
    transcript: str,
    previous_set: dict[str, Any] | None = None,
    next_order: int = 1,
) -> dict[str, Any]:
    """Return structured sets while preserving the transcript only in caller memory."""
    text = transcript.strip()
    if not text:
        return {"status": "invalid", "issues": ["empty_transcript"], "sets": []}

    repeating = bool(REPEAT_PATTERN.search(text))
    if repeating and previous_set is None:
        return {"status": "invalid", "issues": ["repeat_without_previous_set"], "sets": []}

    measurement_text = ADJUST_PATTERN.sub(" ", text)
    weight = matched_number(WEIGHT_PATTERN, measurement_text)
    reps_value = matched_number(REPS_PATTERN, measurement_text)
    rpe = matched_number(RPE_PATTERN, measurement_text)
    set_count_value = matched_number(SETS_PATTERN, measurement_text)
    set_count = int(set_count_value or 1)
    exercise = clean_exercise(text)

    if previous_set is not None:
        if repeating or not exercise:
            exercise = str(previous_set.get("exercise_name") or "").strip()
        if repeating and weight is None:
            previous_weight = previous_set.get("weight_kg")
            weight = float(previous_weight) if previous_weight is not None else None
        if repeating and reps_value is None:
            previous_reps = previous_set.get("reps")
            reps_value = float(previous_reps) if previous_reps is not None else None
        if repeating and rpe is None:
            previous_rpe = previous_set.get("rpe")
            rpe = float(previous_rpe) if previous_rpe is not None else None

    adjustment = ADJUST_PATTERN.search(text)
    if adjustment:
        if weight is None and previous_set is not None and previous_set.get("weight_kg") is not None:
            weight = float(previous_set["weight_kg"])
        if weight is not None:
            amount = chinese_number(adjustment.group("value"))
            direction = adjustment.group("direction").lower()
            weight += -amount if direction in {"减", "减少", "降", "minus"} else amount

    issues = []
    if not exercise:
        issues.append("missing_exercise")
    if weight is None:
        issues.append("missing_weight")
    elif not 0 <= weight <= 1000:
        issues.append("weight_out_of_range")
    if reps_value is None:
        issues.append("missing_reps")
    elif reps_value != int(reps_value) or not 0 <= reps_value <= 100:
        issues.append("reps_out_of_range")
    if rpe is not None and not 0 <= rpe <= 10:
        issues.append("rpe_out_of_range")
    if not 1 <= set_count <= 12:
        issues.append("set_count_out_of_range")
    if issues:
        return {"status": "invalid", "issues": issues, "sets": []}

    parsed_sets = []
    for offset in range(set_count):
        parsed_sets.append(
            {
                "exercise_name": exercise,
                "set_order": next_order + offset,
                "set_type": "working",
                "weight_kg": weight,
                "reps": int(reps_value),
                "rpe": rpe,
                "notes": None,
            }
        )
    return {"status": "parsed", "issues": [], "sets": parsed_sets}
