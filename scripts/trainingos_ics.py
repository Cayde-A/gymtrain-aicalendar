#!/usr/bin/env python3
"""Generate the TrainingOS V4 dynamic calendar framework as RFC 5545 ICS."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "TrainingOS_V4_Framework.ics"
TIMEZONE = "Australia/Sydney"


@dataclass(frozen=True)
class CycleEvent:
    key: str
    day_offset: int
    title: str
    primary_target: str
    avoided_overlap: str
    focus: str
    fallback: str
    duration_minutes: int = 90


CYCLE = (
    CycleEvent(
        "push_chest",
        0,
        "TrainingOS V4 - Push / Chest",
        "Chest",
        "Keep shoulder and triceps accessory volume limited.",
        "PR-aware chest work; load and set count finalized from morning recovery.",
        "If recovery is poor: reduce volume or use technique work; do not force a PR.",
    ),
    CycleEvent(
        "core_a",
        1,
        "TrainingOS V4 - Core A",
        "Core",
        "Avoid grip-heavy, hanging, and high-volume hip-flexor work before legs.",
        "Medium/high-intensity trunk flexion and anti-extension with controlled fatigue.",
        "If bracing is fatigued: use low-load control work or recovery only.",
        60,
    ),
    CycleEvent(
        "legs",
        2,
        "TrainingOS V4 - Legs",
        "Legs",
        "No upper-body loading; protect the prior pressing chain.",
        "One lower-body priority with PR-aware progression and an RPE cap.",
        "If recovery is poor: remove one accessory block and cap all work at RPE 7.",
    ),
    CycleEvent(
        "core_b",
        3,
        "TrainingOS V4 - Core B",
        "Core",
        "Avoid hanging, grip-heavy, and lower-back-fatiguing work before pull.",
        "Medium/high-intensity trunk work that preserves grip and spinal erectors.",
        "If legs or lower back remain fatigued: use supported control work or rest.",
        60,
    ),
    CycleEvent(
        "pull_back",
        4,
        "TrainingOS V4 - Pull / Back",
        "Back",
        "Biceps are secondary; avoid turning the session into an arm-priority day.",
        "Back-priority vertical and horizontal pulling with conservative arm volume.",
        "If recovery is poor: reduce one row/curl block and keep two reps in reserve.",
    ),
    CycleEvent(
        "recovery_sync",
        5,
        "TrainingOS V4 - Recovery / Sync",
        "Recovery",
        "No primary resistance-training target.",
        "Sync Garmin data, correct the prior sessions, and review the next cycle.",
        "If data quality is incomplete: keep the next plan as draft and do not auto-push.",
        30,
    ),
)


def escape_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold_line(line: str, limit: int = 75) -> list[str]:
    """Fold ASCII content lines to the RFC 5545 75-octet recommendation."""
    if len(line.encode("utf-8")) <= limit:
        return [line]
    parts: list[str] = []
    remaining = line
    first = True
    while remaining:
        available = limit if first else limit - 1
        chunk = remaining[:available]
        parts.append(chunk if first else " " + chunk)
        remaining = remaining[len(chunk) :]
        first = False
    return parts


def event_description(event: CycleEvent) -> str:
    return "\n".join(
        [
            f"Primary target: {event.primary_target}",
            f"Overlap rule: {event.avoided_overlap}",
            f"Focus: {event.focus}",
            "Morning inputs: sleep, HRV, Body Battery, readiness, recent PR state.",
            "Load: dynamic; do not copy a fixed weight from the calendar.",
            "Record: sets, reps, weight, RPE, pain, and technique notes in Garmin/TrainingOS.",
            f"Fallback: {event.fallback}",
        ]
    )


def calendar_lines(
    start_date: dt.date,
    cycles: int,
    start_time: dt.time = dt.time(11, 0),
    location: str = "Gunyama Park Aquatic and Recreation Centre",
) -> list[str]:
    if cycles < 1:
        raise ValueError("cycles must be at least 1")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//TrainingOS//V4 Dynamic Framework//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:TrainingOS V4 Dynamic Framework",
        f"X-WR-TIMEZONE:{TIMEZONE}",
        "BEGIN:VTIMEZONE",
        f"TZID:{TIMEZONE}",
        "BEGIN:DAYLIGHT",
        "TZOFFSETFROM:+1000",
        "TZOFFSETTO:+1100",
        "TZNAME:AEDT",
        "DTSTART:19701004T020000",
        "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=1SU",
        "END:DAYLIGHT",
        "BEGIN:STANDARD",
        "TZOFFSETFROM:+1100",
        "TZOFFSETTO:+1000",
        "TZNAME:AEST",
        "DTSTART:19700405T030000",
        "RRULE:FREQ=YEARLY;BYMONTH=4;BYDAY=1SU",
        "END:STANDARD",
        "END:VTIMEZONE",
    ]
    stamp = start_date.strftime("%Y%m%d") + "T000000Z"
    for event in CYCLE:
        event_date = start_date + dt.timedelta(days=event.day_offset)
        start = dt.datetime.combine(event_date, start_time)
        end = start + dt.timedelta(minutes=event.duration_minutes)
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:trainingos-v4-{event.key}-{start_date.isoformat()}@trainingos.local",
                f"DTSTAMP:{stamp}",
                f"DTSTART;TZID={TIMEZONE}:{start.strftime('%Y%m%dT%H%M%S')}",
                f"DTEND;TZID={TIMEZONE}:{end.strftime('%Y%m%dT%H%M%S')}",
                f"RRULE:FREQ=DAILY;INTERVAL=6;COUNT={cycles}",
                f"SUMMARY:{escape_text(event.title)}",
                f"LOCATION:{escape_text(location)}",
                f"DESCRIPTION:{escape_text(event_description(event))}",
                "BEGIN:VALARM",
                "TRIGGER:-PT45M",
                "ACTION:DISPLAY",
                f"DESCRIPTION:{escape_text(event.title)}",
                "END:VALARM",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return lines


def render_calendar(start_date: dt.date, cycles: int) -> str:
    folded = [folded_line for line in calendar_lines(start_date, cycles) for folded_line in fold_line(line)]
    return "\r\n".join(folded) + "\r\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the TrainingOS V4 ICS framework.")
    parser.add_argument("--start-date", required=True, help="First chest day in YYYY-MM-DD format.")
    parser.add_argument("--cycles", type=int, default=8, help="Number of six-day cycles.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output .ics path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    start_date = dt.date.fromisoformat(args.start_date)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(render_calendar(start_date, args.cycles).encode("utf-8"))
    print(f"Generated {len(CYCLE)} recurring events across {args.cycles} six-day cycles.")
    print(f"Output: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
