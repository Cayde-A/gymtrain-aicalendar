import json
import tempfile
import unittest
from pathlib import Path

from scripts import garmin_data_export_import, trainingos_db


DAY = {
    "summary": {"restingHeartRate": 55, "totalSteps": 9000, "averageStressLevel": 20},
    "sleep": {"sleepTimeSeconds": 27000, "sleepScore": 82},
    "hrv": {"hrvSummary": {"status": "BALANCED"}},
    "body_battery": [{"bodyBatteryValuesArray": [[1, 75]]}],
}
ACTIVITY = {
    "summary": {
        "activityId": 123,
        "activityName": "Strength",
        "activityType": {"typeKey": "strength_training"},
        "startTimeLocal": "2026-08-01 08:00:00",
        "duration": 1800,
    },
    "detail": {"calories": 180},
    "exercise_sets": {
        "exerciseSets": [
            {"exerciseName": "LEG_PRESS", "setOrder": 1, "repetitionCount": 10, "weight": 80000}
        ]
    },
}


class GarminDataExportImportTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.db = self.root / "trainingos.sqlite"

    def tearDown(self):
        self.tempdir.cleanup()

    def make_cache(self):
        daily = self.root / ".cache" / "daily"
        activities = self.root / ".cache" / "activities"
        daily.mkdir(parents=True)
        activities.mkdir(parents=True)
        (daily / "2026-08-01.json").write_text(json.dumps(DAY), encoding="utf-8")
        (activities / "123.json").write_text(json.dumps(ACTIVITY), encoding="utf-8")

    def test_cache_import_normalizes_weight_and_is_idempotent(self):
        self.make_cache()
        first = garmin_data_export_import.import_export(self.root, self.db)
        second = garmin_data_export_import.import_export(self.root, self.db)
        with trainingos_db.connect(self.db) as connection:
            sessions = connection.execute("select count(*) from completed_sessions").fetchone()[0]
            sets = connection.execute("select weight_kg, reps from set_logs").fetchall()
            recovery = connection.execute("select count(*) from daily_recovery_metrics").fetchone()[0]
            session_source = connection.execute(
                "select source_tool from completed_sessions"
            ).fetchone()[0]
            recovery_source = connection.execute(
                "select source_tool from daily_recovery_metrics"
            ).fetchone()[0]
        self.assertEqual(first["format"], "json_cache")
        self.assertEqual(second["stored_activity_records"], 1)
        self.assertEqual(sessions, 1)
        self.assertEqual(recovery, 1)
        self.assertEqual(tuple(sets[0]), (80.0, 10))
        self.assertEqual(session_source, "garmin-data-export")
        self.assertEqual(recovery_source, "garmin-data-export")

    def test_dry_run_does_not_create_database(self):
        self.make_cache()
        report = garmin_data_export_import.import_export(
            self.root, self.db, dry_run=True
        )
        self.assertEqual(report["status"], "preview")
        self.assertFalse(self.db.exists())
        self.assertEqual(report["activity_records"], 1)

    def test_compact_text_sections_are_parsed(self):
        compact_day = {
            "2026-08-01": {
                "Daily Summary": DAY["summary"],
                "Sleep": DAY["sleep"],
                "Heart Rate Variability": DAY["hrv"],
                "Body Battery": DAY["body_battery"],
            }
        }
        export = self.root / "garmin_export_2026-08-02_120000_compact_update.txt"
        export.write_text(
            "Garmin Connect Data Export -- Update\n\n"
            "Daily Health\n"
            "Schema: daily\n"
            + json.dumps(compact_day)
            + "\n\nActivities\n"
            "Schema: activities\n"
            + json.dumps([ACTIVITY])
            + "\n\nBody Composition\nNo data available.\n",
            encoding="utf-8",
        )
        report = garmin_data_export_import.import_export(export, self.db)
        self.assertEqual(report["format"], "compact_text")
        self.assertEqual(report["recovery_records"], 1)
        self.assertEqual(report["activity_records"], 1)

    def test_strength_filter_ignores_non_strength_activity(self):
        self.make_cache()
        walk = dict(ACTIVITY)
        walk["summary"] = dict(ACTIVITY["summary"])
        walk["summary"].update(
            {"activityId": 456, "activityName": "Walk", "activityType": {"typeKey": "walking"}}
        )
        (self.root / ".cache" / "activities" / "456.json").write_text(
            json.dumps(walk), encoding="utf-8"
        )
        report = garmin_data_export_import.import_export(self.root, self.db)
        self.assertEqual(report["activity_records"], 1)


if __name__ == "__main__":
    unittest.main()
