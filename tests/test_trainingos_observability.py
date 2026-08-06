import tempfile
import unittest
from pathlib import Path

from scripts import trainingos_observability


class TrainingOSObservabilityTestCase(unittest.TestCase):
    def test_record_event_redacts_sensitive_details(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            event_log = Path(tmpdir) / "events.jsonl"
            trainingos_observability.record_event(
                "login",
                details={"email": "user@example.com", "count": 1, "token_path": "secret"},
                event_log=event_log,
            )
            events = trainingos_observability.read_events(event_log=event_log)
        self.assertEqual(events[0]["event"], "login")
        self.assertEqual(events[0]["details"]["email"], "[redacted]")
        self.assertEqual(events[0]["details"]["token_path"], "[redacted]")
        self.assertEqual(events[0]["details"]["count"], 1)

    def test_read_events_returns_latest_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            event_log = Path(tmpdir) / "events.jsonl"
            for index in range(5):
                trainingos_observability.record_event(f"event_{index}", event_log=event_log)
            events = trainingos_observability.read_events(limit=2, event_log=event_log)
        self.assertEqual([event["event"] for event in events], ["event_3", "event_4"])

    def test_clear_events_empties_log(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            event_log = Path(tmpdir) / "events.jsonl"
            trainingos_observability.record_event("event", event_log=event_log)
            trainingos_observability.clear_events(event_log)
            events = trainingos_observability.read_events(event_log=event_log)
        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
