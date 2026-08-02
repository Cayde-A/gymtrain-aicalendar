#!/usr/bin/env python3
"""Local-only debug event log for TrainingOS."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVENT_LOG = ROOT / "data" / "debug_events.jsonl"


def now_text() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def redact_details(details: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    blocked_fragments = ("password", "token", "secret", "email")
    for key, value in details.items():
        normalized_key = key.lower()
        if any(fragment in normalized_key for fragment in blocked_fragments):
            redacted[key] = "[redacted]"
        else:
            redacted[key] = value
    return redacted


def record_event(
    event: str,
    status: str = "ok",
    details: dict[str, Any] | None = None,
    event_log: Path = DEFAULT_EVENT_LOG,
) -> dict[str, Any]:
    payload = {
        "time": now_text(),
        "event": event,
        "status": status,
        "details": redact_details(details or {}),
    }
    event_log.parent.mkdir(parents=True, exist_ok=True)
    with event_log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    return payload


def read_events(limit: int = 100, event_log: Path = DEFAULT_EVENT_LOG) -> list[dict[str, Any]]:
    if not event_log.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in event_log.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            rows.append(
                {
                    "time": "",
                    "event": "debug_log_parse_error",
                    "status": "warning",
                    "details": {"line": line[:200]},
                }
            )
    return rows[-limit:]


def clear_events(event_log: Path = DEFAULT_EVENT_LOG) -> None:
    event_log.parent.mkdir(parents=True, exist_ok=True)
    event_log.write_text("", encoding="utf-8")
