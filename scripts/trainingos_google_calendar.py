#!/usr/bin/env python3
"""Map the TrainingOS ICS model to idempotent Google Calendar API events."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

try:
    from . import trainingos_db, trainingos_ics
except ImportError:  # pragma: no cover - supports direct script execution.
    import trainingos_db  # type: ignore
    import trainingos_ics  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "exports" / "calendar"
API_BASE_URL = "https://www.googleapis.com/calendar/v3"


class CalendarApiError(RuntimeError):
    def __init__(self, status: int, message: str, response: dict[str, Any] | None = None):
        super().__init__(message)
        self.status = status
        self.response = response or {}


def event_id(event_key: str, framework_start: str) -> str:
    digest = hashlib.sha256(f"{event_key}|{framework_start}|v4".encode("utf-8")).hexdigest()[:32]
    return f"trainingos{digest}"


def google_event_payload(
    event: trainingos_ics.CycleEvent,
    framework_start: dt.date,
    cycles: int,
    start_time: dt.time = dt.time(11, 0),
    location: str = "Gunyama Park Aquatic and Recreation Centre",
) -> dict[str, Any]:
    if cycles < 1:
        raise ValueError("cycles must be at least 1")
    event_date = framework_start + dt.timedelta(days=event.day_offset)
    timezone = ZoneInfo(trainingos_ics.TIMEZONE)
    start = dt.datetime.combine(event_date, start_time, tzinfo=timezone)
    end = start + dt.timedelta(minutes=event.duration_minutes)
    key = f"v4:{framework_start.isoformat()}:{event.key}"
    return {
        "id": event_id(event.key, framework_start.isoformat()),
        "summary": event.title,
        "description": trainingos_ics.event_description(event),
        "location": location,
        "start": {"dateTime": start.isoformat(), "timeZone": trainingos_ics.TIMEZONE},
        "end": {"dateTime": end.isoformat(), "timeZone": trainingos_ics.TIMEZONE},
        "recurrence": [f"RRULE:FREQ=DAILY;INTERVAL=6;COUNT={cycles}"],
        "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 45}]},
        "visibility": "private",
        "extendedProperties": {
            "private": {
                "trainingosKey": key,
                "trainingosVersion": "v4",
                "primaryTarget": event.primary_target,
            }
        },
    }


def framework_payloads(
    start_date: dt.date,
    cycles: int = 8,
    start_time: dt.time = dt.time(11, 0),
    location: str = "Gunyama Park Aquatic and Recreation Centre",
) -> list[dict[str, Any]]:
    return [
        google_event_payload(event, start_date, cycles, start_time, location)
        for event in trainingos_ics.CYCLE
    ]


Requester = Callable[[str, str, dict[str, Any] | None], tuple[int, dict[str, Any]]]


class GoogleCalendarClient:
    def __init__(
        self,
        access_token: str,
        calendar_id: str = "primary",
        requester: Requester | None = None,
    ):
        if not access_token:
            raise ValueError("Google Calendar access token is required for live sync")
        self.access_token = access_token
        self.calendar_id = calendar_id
        self.requester = requester or self._request

    def event_url(self, event_id_value: str | None = None) -> str:
        calendar_id = urllib.parse.quote(self.calendar_id, safe="")
        base = f"{API_BASE_URL}/calendars/{calendar_id}/events"
        return f"{base}/{urllib.parse.quote(event_id_value, safe='')}" if event_id_value else base

    def _request(
        self,
        method: str,
        url: str,
        payload: dict[str, Any] | None,
    ) -> tuple[int, dict[str, Any]]:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8")
                return int(response.status), json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            try:
                parsed = json.loads(body) if body else {}
            except json.JSONDecodeError:
                parsed = {"message": body[:500]}
            return int(exc.code), parsed

    def sync_event(self, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        remote_id = str(payload["id"])
        status, existing = self.requester("GET", self.event_url(remote_id), None)
        if status == 404:
            create_status, created = self.requester("POST", self.event_url(), payload)
            if create_status not in {200, 201}:
                raise CalendarApiError(create_status, "Google Calendar event insert failed", created)
            return "created", created
        if status != 200:
            raise CalendarApiError(status, "Google Calendar event lookup failed", existing)
        patch_payload = {key: value for key, value in payload.items() if key != "id"}
        update_status, updated = self.requester("PATCH", self.event_url(remote_id), patch_payload)
        if update_status != 200:
            raise CalendarApiError(update_status, "Google Calendar event patch failed", updated)
        return "updated", updated

    def patch_completed_event(
        self,
        remote_event_id: str,
        patch_payload: dict[str, Any],
    ) -> dict[str, Any]:
        status, existing = self.requester("GET", self.event_url(remote_event_id), None)
        if status != 200:
            raise CalendarApiError(status, "Google Calendar completion target lookup failed", existing)
        existing_private = ((existing.get("extendedProperties") or {}).get("private") or {})
        completion_private = ((patch_payload.get("extendedProperties") or {}).get("private") or {})
        merged_patch = {
            **patch_payload,
            "extendedProperties": {"private": {**existing_private, **completion_private}},
        }
        update_status, updated = self.requester(
            "PATCH", self.event_url(remote_event_id), merged_patch
        )
        if update_status != 200:
            raise CalendarApiError(update_status, "Google Calendar completion patch failed", updated)
        return updated


def record_calendar_event(
    connection: Any,
    remote_event_id: str,
    status: str,
) -> None:
    local_id = f"calendar_{hashlib.sha256(remote_event_id.encode('utf-8')).hexdigest()[:24]}"
    connection.execute(
        """
        insert into calendar_events (
          id, provider, external_event_id, sync_status, last_synced_at
        ) values (?, 'google_calendar', ?, ?, current_timestamp)
        on conflict(provider, external_event_id) do update set
          sync_status = excluded.sync_status,
          last_synced_at = current_timestamp
        """,
        (local_id, remote_event_id, status),
    )


def sync_framework(
    connection: Any,
    client: GoogleCalendarClient,
    payloads: list[dict[str, Any]],
) -> dict[str, Any]:
    results = []
    for payload in payloads:
        action, remote = client.sync_event(payload)
        remote_id = str(remote.get("id") or payload["id"])
        record_calendar_event(connection, remote_id, "synced")
        results.append({"event_id": remote_id, "action": action, "status": "synced"})
    return {
        "status": "synced",
        "event_count": len(results),
        "created_count": sum(item["action"] == "created" for item in results),
        "updated_count": sum(item["action"] == "updated" for item in results),
        "events": results,
    }


def completed_session_patch(connection: Any, session_id: str) -> dict[str, Any]:
    session = trainingos_db.get_session_for_review(connection, session_id)
    if session is None:
        raise ValueError(f"Unknown session: {session_id}")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for set_log in session.get("sets", []):
        if str(set_log.get("set_type") or "").lower() == "rest":
            continue
        grouped.setdefault(str(set_log["exercise_name"]), []).append(set_log)
    exercise_lines = []
    for exercise_name, sets in grouped.items():
        logged = [item for item in sets if item.get("weight_kg") is not None and item.get("reps") is not None]
        if logged:
            best = max(logged, key=lambda item: float(item.get("estimated_1rm_kg") or 0))
            exercise_lines.append(
                f"{exercise_name}: {len(sets)} sets; best {float(best['weight_kg']):g} kg x {int(best['reps'])}"
            )
        else:
            exercise_lines.append(f"{exercise_name}: {len(sets)} sets")
    pr_count = len(trainingos_db.get_pr_records_for_session(connection, session_id))
    review_row = connection.execute(
        """
        select decision from ai_reviews
        where completed_session_id = ?
        order by created_at desc limit 1
        """,
        (session_id,),
    ).fetchone()
    lines = [
        "TrainingOS completed summary",
        f"Date: {str(session['completed_at'])[:10]}",
        f"Activity: {session.get('activity_name') or session.get('session_type')}",
        *exercise_lines,
        f"PR records: {pr_count}",
    ]
    if review_row:
        lines.append(f"Review decision: {review_row['decision']}")
    lines.append("Full set history and private notes remain in local TrainingOS.")
    session_marker = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:24]
    return {
        "description": "\n".join(lines),
        "extendedProperties": {
            "private": {
                "trainingosCompleted": "true",
                "trainingosSessionHash": session_marker,
            }
        },
    }


def parse_time(value: str) -> dt.time:
    return dt.time.fromisoformat(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run or sync the V4 framework to Google Calendar.")
    parser.add_argument("--start-date", help="Framework start date for schedule sync.")
    parser.add_argument("--cycles", type=int, default=8)
    parser.add_argument("--start-time", default="11:00")
    parser.add_argument("--location", default="Gunyama Park Aquatic and Recreation Centre")
    parser.add_argument("--calendar-id", default="primary")
    parser.add_argument("--db", default=str(trainingos_db.DEFAULT_DB_PATH))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--push", action="store_true", help="Perform live Calendar API writes.")
    parser.add_argument("--confirm", action="store_true", help="Explicitly confirm live Calendar writes.")
    parser.add_argument("--access-token-env", default="GOOGLE_CALENDAR_ACCESS_TOKEN")
    parser.add_argument("--completed-session", help="Local completed session ID to summarize.")
    parser.add_argument("--event-id", help="Google event ID receiving the completed summary.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.completed_session:
        if not args.event_id:
            raise SystemExit("--event-id is required with --completed-session")
        db_path = Path(args.db)
        trainingos_db.init_db(db_path)
        with trainingos_db.connect(db_path) as connection:
            patch_payload = completed_session_patch(connection, args.completed_session)
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        session_marker = hashlib.sha256(args.completed_session.encode("utf-8")).hexdigest()[:16]
        output_path = output_dir / f"google_calendar_completed_{session_marker}.json"
        output_path.write_text(
            json.dumps(patch_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        if not args.push:
            print(json.dumps({"status": "dry_run", "path": str(output_path)}, indent=2))
            return 0
        if not args.confirm:
            print(json.dumps({"status": "needs_confirmation"}, indent=2))
            return 3
        access_token = os.environ.get(args.access_token_env, "")
        if not access_token:
            print(json.dumps({"status": "needs_oauth", "token_env": args.access_token_env}, indent=2))
            return 3
        client = GoogleCalendarClient(access_token, args.calendar_id)
        try:
            client.patch_completed_event(args.event_id, patch_payload)
            with trainingos_db.connect(db_path) as connection:
                record_calendar_event(connection, args.event_id, "completed_synced")
        except CalendarApiError as exc:
            print(
                json.dumps(
                    {"status": "calendar_api_failed", "http_status": exc.status, "message": str(exc)},
                    indent=2,
                )
            )
            return 4
        print(json.dumps({"status": "completed_synced", "event_id": args.event_id}, indent=2))
        return 0

    if not args.start_date:
        raise SystemExit("--start-date is required unless --completed-session is used")
    start_date = dt.date.fromisoformat(args.start_date)
    payloads = framework_payloads(
        start_date,
        args.cycles,
        parse_time(args.start_time),
        args.location,
    )
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"google_calendar_v4_{start_date.isoformat()}.json"
    output_path.write_text(json.dumps(payloads, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if not args.push:
        print(json.dumps({"status": "dry_run", "event_count": len(payloads), "path": str(output_path)}, indent=2))
        return 0
    if not args.confirm:
        print(json.dumps({"status": "needs_confirmation", "event_count": len(payloads)}, indent=2))
        return 3
    access_token = os.environ.get(args.access_token_env, "")
    if not access_token:
        print(json.dumps({"status": "needs_oauth", "token_env": args.access_token_env}, indent=2))
        return 3
    db_path = Path(args.db)
    trainingos_db.init_db(db_path)
    client = GoogleCalendarClient(access_token, args.calendar_id)
    try:
        with trainingos_db.connect(db_path) as connection:
            result = sync_framework(connection, client, payloads)
    except CalendarApiError as exc:
        print(
            json.dumps(
                {"status": "calendar_api_failed", "http_status": exc.status, "message": str(exc)},
                indent=2,
            )
        )
        return 4
    result["path"] = str(output_path)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
