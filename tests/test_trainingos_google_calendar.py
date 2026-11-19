import datetime as dt
import re
import tempfile
import unittest
from pathlib import Path

from scripts import trainingos_db, trainingos_google_calendar, trainingos_ics


class FakeCalendarRequester:
    def __init__(self):
        self.events = {}
        self.calls = []

    def __call__(self, method, url, payload):
        self.calls.append((method, url, payload))
        event_id = url.rsplit("/", 1)[-1]
        if method == "GET":
            return (200, self.events[event_id]) if event_id in self.events else (404, {})
        if method == "POST":
            self.events[str(payload["id"])] = dict(payload)
            return 201, dict(payload)
        if method == "PATCH":
            self.events[event_id].update(payload)
            return 200, dict(self.events[event_id])
        raise AssertionError(f"unexpected method: {method}")


class TrainingOSGoogleCalendarTestCase(unittest.TestCase):
    def test_google_payloads_share_the_ics_model_and_recurrence(self):
        start = dt.date(2026, 10, 5)
        payloads = trainingos_google_calendar.framework_payloads(start, cycles=8)
        self.assertEqual(len(payloads), len(trainingos_ics.CYCLE))
        self.assertEqual(payloads[0]["summary"], trainingos_ics.CYCLE[0].title)
        self.assertEqual(payloads[0]["recurrence"], ["RRULE:FREQ=DAILY;INTERVAL=6;COUNT=8"])
        self.assertEqual(payloads[0]["start"]["timeZone"], "Australia/Sydney")
        self.assertTrue(payloads[0]["start"]["dateTime"].endswith("+11:00"))
        self.assertEqual(payloads[0]["reminders"]["overrides"][0]["minutes"], 45)
        self.assertEqual(payloads[0]["visibility"], "private")
        self.assertRegex(payloads[0]["id"], re.compile(r"^[a-v0-9]{5,1024}$"))

    def test_event_id_is_stable_and_changes_with_framework_start(self):
        first = trainingos_google_calendar.event_id("push_chest", "2026-10-05")
        repeated = trainingos_google_calendar.event_id("push_chest", "2026-10-05")
        next_cycle = trainingos_google_calendar.event_id("push_chest", "2026-12-01")
        self.assertEqual(first, repeated)
        self.assertNotEqual(first, next_cycle)

    def test_sync_creates_then_updates_without_duplicate_local_rows(self):
        requester = FakeCalendarRequester()
        client = trainingos_google_calendar.GoogleCalendarClient(
            "test-token", requester=requester
        )
        payloads = trainingos_google_calendar.framework_payloads(dt.date(2026, 10, 5))
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "trainingos.sqlite"
            trainingos_db.init_db(db_path)
            with trainingos_db.connect(db_path) as connection:
                first = trainingos_google_calendar.sync_framework(connection, client, payloads)
                second = trainingos_google_calendar.sync_framework(connection, client, payloads)
                local_count = connection.execute("select count(*) from calendar_events").fetchone()[0]
        self.assertEqual(first["created_count"], 6)
        self.assertEqual(first["updated_count"], 0)
        self.assertEqual(second["created_count"], 0)
        self.assertEqual(second["updated_count"], 6)
        self.assertEqual(local_count, 6)
        self.assertEqual(len(requester.events), 6)

    def test_insert_error_is_structured(self):
        def requester(method, url, payload):
            if method == "GET":
                return 404, {}
            return 403, {"error": {"message": "forbidden"}}

        client = trainingos_google_calendar.GoogleCalendarClient("test-token", requester=requester)
        payload = trainingos_google_calendar.framework_payloads(dt.date(2026, 10, 5))[0]
        with self.assertRaises(trainingos_google_calendar.CalendarApiError) as context:
            client.sync_event(payload)
        self.assertEqual(context.exception.status, 403)

    def test_completed_summary_excludes_private_notes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "trainingos.sqlite"
            trainingos_db.init_db(db_path)
            with trainingos_db.connect(db_path) as connection:
                session_id = trainingos_db.save_imported_workout(
                    connection,
                    {
                        "provider": "garmin",
                        "external_activity_id": "calendar-complete",
                        "completed_at": "2026-10-05 09:00:00",
                        "session_type": "strength_training",
                        "activity_name": "Chest",
                        "pain_notes": "private pain text",
                        "sets": [
                            {
                                "exercise_name": "Bench Press",
                                "set_order": 1,
                                "set_type": "working",
                                "weight_kg": 100,
                                "reps": 5,
                                "rpe": 8,
                                "notes": "private technique text",
                            }
                        ],
                    },
                )
                trainingos_db.save_ai_review_response(
                    connection,
                    session_id,
                    '{"analysis_summary":"private review text","performance_direction":"increase"}',
                )
                patch = trainingos_google_calendar.completed_session_patch(connection, session_id)
        serialized = str(patch)
        self.assertIn("Bench Press: 1 sets; best 100 kg x 5", patch["description"])
        self.assertIn("Review decision: increase", patch["description"])
        self.assertNotIn("private pain", serialized)
        self.assertNotIn("private technique", serialized)
        self.assertNotIn("private review", serialized)
        self.assertNotIn(session_id, serialized)

    def test_completed_patch_preserves_existing_private_properties(self):
        requester = FakeCalendarRequester()
        requester.events["event1"] = {
            "id": "event1",
            "extendedProperties": {"private": {"trainingosKey": "v4:key"}},
        }
        client = trainingos_google_calendar.GoogleCalendarClient("test-token", requester=requester)
        updated = client.patch_completed_event(
            "event1",
            {
                "description": "Completed",
                "extendedProperties": {"private": {"trainingosCompleted": "true"}},
            },
        )
        private = updated["extendedProperties"]["private"]
        self.assertEqual(private["trainingosKey"], "v4:key")
        self.assertEqual(private["trainingosCompleted"], "true")


if __name__ == "__main__":
    unittest.main()
