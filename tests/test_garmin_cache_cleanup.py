import datetime as dt
import json
import os
import tempfile
import unittest
from pathlib import Path

from scripts import garmin_cache_cleanup, trainingos_db


NOW = dt.datetime(2026, 10, 4, 0, 0, tzinfo=dt.timezone.utc)


class GarminCacheCleanupTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.raw = self.root / "raw"
        self.raw.mkdir()
        self.db = self.root / "trainingos.sqlite"
        trainingos_db.init_db(self.db)

    def tearDown(self):
        self.tempdir.cleanup()

    def age(self, path, days):
        timestamp = NOW.timestamp() - days * 86400
        os.utime(path, (timestamp, timestamp))

    def save_activity(self, activity_id="123"):
        with trainingos_db.connect(self.db) as connection:
            trainingos_db.save_imported_workout(
                connection,
                {
                    "provider": "garmin",
                    "external_activity_id": activity_id,
                    "completed_at": "2026-08-01 08:00:00",
                    "session_type": "strength_training",
                    "sets": [],
                },
            )

    def save_recovery(self, metric_date="2026-08-01"):
        with trainingos_db.connect(self.db) as connection:
            trainingos_db.upsert_daily_recovery_metric(
                connection,
                {"provider": "garmin", "metric_date": metric_date},
            )

    def test_preview_does_not_delete_verified_old_file(self):
        self.save_activity()
        path = self.raw / "activity_123_exercise_sets.json"
        path.write_text("{}", encoding="utf-8")
        self.age(path, 31)
        report = garmin_cache_cleanup.cleanup(
            self.raw, self.db, 30, apply=False, now=NOW
        )
        self.assertTrue(path.exists())
        self.assertEqual(report["eligible_files"], 1)
        self.assertEqual(report["deleted_files"], 0)
        self.assertEqual(report["status"], "preview")

    def test_apply_deletes_and_verifies_normalized_activity(self):
        self.save_activity()
        path = self.raw / "activity_123.json"
        path.write_text("{}", encoding="utf-8")
        self.age(path, 31)
        report = garmin_cache_cleanup.cleanup(
            self.raw, self.db, 30, apply=True, now=NOW
        )
        self.assertFalse(path.exists())
        self.assertEqual(report["deleted_files"], 1)
        self.assertTrue(report["deletion_verified"])

    def test_apply_deletes_daily_file_only_when_all_dates_are_normalized(self):
        self.save_recovery("2026-08-01")
        self.save_recovery("2026-08-02")
        path = self.raw / "daily_raw_2026-08-02_2d.json"
        path.write_text(
            json.dumps([{"date": "2026-08-01"}, {"date": "2026-08-02"}]),
            encoding="utf-8",
        )
        self.age(path, 31)
        report = garmin_cache_cleanup.cleanup(
            self.raw, self.db, 30, apply=True, now=NOW
        )
        self.assertFalse(path.exists())
        self.assertEqual(report["deleted_files"], 1)

    def test_unverified_recent_and_symlink_files_are_preserved(self):
        unknown = self.raw / "unknown.json"
        unknown.write_text("{}", encoding="utf-8")
        self.age(unknown, 31)
        recent = self.raw / "activity_999.json"
        recent.write_text("{}", encoding="utf-8")
        self.age(recent, 2)
        target = self.root / "outside.json"
        target.write_text("{}", encoding="utf-8")
        link = self.raw / "activity_123.json"
        link.symlink_to(target)
        report = garmin_cache_cleanup.cleanup(
            self.raw, self.db, 30, apply=True, now=NOW
        )
        self.assertTrue(unknown.exists())
        self.assertTrue(recent.exists())
        self.assertTrue(link.is_symlink())
        self.assertTrue(target.exists())
        self.assertEqual(report["unverified_files"], 1)
        self.assertEqual(report["recent_files"], 1)
        self.assertEqual(report["symlinks_skipped"], 1)

    def test_retention_days_reads_database_policy(self):
        with trainingos_db.connect(self.db) as connection:
            connection.execute(
                "update privacy_retention_policies set raw_cache_retention_days = 45"
            )
        self.assertEqual(garmin_cache_cleanup.retention_days(self.db), 45)


if __name__ == "__main__":
    unittest.main()
