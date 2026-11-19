import datetime as dt
import tempfile
import unittest
from pathlib import Path

from scripts import trainingos_ics


class TrainingOSIcsTestCase(unittest.TestCase):
    def test_calendar_has_six_ordered_cycle_events(self):
        content = trainingos_ics.render_calendar(dt.date(2026, 10, 5), 8)
        self.assertEqual(content.count("BEGIN:VEVENT"), 6)
        self.assertEqual(content.count("RRULE:FREQ=DAILY;INTERVAL=6;COUNT=8"), 6)
        titles = [
            "Push / Chest",
            "Core A",
            "Legs",
            "Core B",
            "Pull / Back",
            "Recovery / Sync",
        ]
        positions = [content.index(title) for title in titles]
        self.assertEqual(positions, sorted(positions))

    def test_calendar_uses_sydney_timezone_and_crlf(self):
        content = trainingos_ics.render_calendar(dt.date(2026, 10, 5), 1)
        self.assertIn("TZID:Australia/Sydney\r\n", content)
        self.assertIn("DTSTART;TZID=Australia/Sydney:20261005T110000", content)
        self.assertTrue(content.endswith("END:VCALENDAR\r\n"))
        self.assertNotIn("\n", content.replace("\r\n", ""))

    def test_calendar_keeps_load_dynamic_and_primary_target_explicit(self):
        content = trainingos_ics.render_calendar(dt.date(2026, 10, 5), 1)
        self.assertNotIn(" kg", content)
        self.assertEqual(content.count("Primary target:"), 6)
        self.assertIn("Chest", content)
        self.assertIn("Legs", content)
        self.assertIn("Back", content)

    def test_content_lines_are_folded_to_75_octets(self):
        content = trainingos_ics.render_calendar(dt.date(2026, 10, 5), 1)
        self.assertTrue(all(len(line.encode("utf-8")) <= 75 for line in content.split("\r\n")))

    def test_render_is_deterministic(self):
        first = trainingos_ics.render_calendar(dt.date(2026, 10, 5), 8)
        second = trainingos_ics.render_calendar(dt.date(2026, 10, 5), 8)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
