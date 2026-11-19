import json
import tempfile
import unittest
from pathlib import Path

from scripts import trainingos_db, trainingos_monthly_sync_package


class TrainingOSMonthlySyncPackageTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "trainingos.sqlite"
        trainingos_db.init_db(self.db_path)

    def tearDown(self):
        self.tempdir.cleanup()

    def seed_private_data(self):
        with trainingos_db.connect(self.db_path) as connection:
            trainingos_db.save_imported_workout(
                connection,
                {
                    "provider": "garmin",
                    "external_activity_id": "private-activity-id",
                    "completed_at": "2026-10-04 09:00:00",
                    "session_type": "strength_training",
                    "pain_notes": "private pain note",
                    "sets": [
                        {
                            "exercise_name": "Bench Press",
                            "set_order": 1,
                            "set_type": "working",
                            "weight_kg": 100,
                            "reps": 5,
                            "rpe": 8,
                            "notes": "private set note",
                        }
                    ],
                },
            )
            trainingos_db.upsert_body_metric(
                connection,
                {"metric_date": "2026-10-04", "body_weight_kg": 80, "notes": "private body note"},
            )

    def test_package_uses_exact_allowlist_and_excludes_private_fields(self):
        self.seed_private_data()
        with trainingos_db.connect(self.db_path) as connection:
            package, digest, batch_id = trainingos_monthly_sync_package.create_package(
                connection, "2026-10"
            )
            batch = connection.execute(
                "select * from monthly_sync_batches where id = ?", (batch_id,)
            ).fetchone()
        serialized = json.dumps(package, sort_keys=True)
        self.assertEqual(set(package), trainingos_monthly_sync_package.TOP_LEVEL_KEYS)
        self.assertEqual(trainingos_monthly_sync_package.sensitive_paths(package), [])
        self.assertNotIn("private", serialized)
        self.assertNotIn("body_weight", serialized)
        self.assertNotIn("activity_id", serialized)
        self.assertEqual(batch["status"], "pending")
        self.assertEqual(batch["summary_payload_hash"], digest)

    def test_repeated_package_is_stable_and_idempotent(self):
        self.seed_private_data()
        with trainingos_db.connect(self.db_path) as connection:
            first_package, first_hash, first_batch = trainingos_monthly_sync_package.create_package(
                connection, "2026-10"
            )
            second_package, second_hash, second_batch = trainingos_monthly_sync_package.create_package(
                connection, "2026-10"
            )
            batch_count = connection.execute("select count(*) from monthly_sync_batches").fetchone()[0]
            summary_count = connection.execute("select count(*) from cloud_monthly_summaries").fetchone()[0]
        self.assertEqual(first_package, second_package)
        self.assertEqual(first_hash, second_hash)
        self.assertEqual(first_batch, second_batch)
        self.assertEqual(batch_count, 1)
        self.assertEqual(summary_count, 1)

    def test_privacy_scanner_rejects_forbidden_nested_key(self):
        package = {key: None for key in trainingos_monthly_sync_package.TOP_LEVEL_KEYS}
        package["sync_month"] = "2026-10"
        package["recovery_summary"] = {"private_notes": "must not upload"}
        with self.assertRaisesRegex(ValueError, "sensitive fields"):
            trainingos_monthly_sync_package.validate_package(package)


if __name__ == "__main__":
    unittest.main()
