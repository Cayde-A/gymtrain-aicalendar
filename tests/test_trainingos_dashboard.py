import tempfile
import unittest
from pathlib import Path

from scripts import trainingos_dashboard, trainingos_db, trainingos_program_cycle


class TrainingOSDashboardTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "trainingos.sqlite"
        trainingos_db.init_db(self.db_path)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_snapshot_combines_training_recovery_body_cycle_and_pr(self):
        with trainingos_db.connect(self.db_path) as connection:
            trainingos_db.save_imported_workout(
                connection,
                {
                    "provider": "garmin",
                    "external_activity_id": "dashboard-1",
                    "completed_at": "2026-10-03 09:00:00",
                    "session_type": "strength_training",
                    "activity_name": "Chest",
                    "sets": [
                        {
                            "exercise_name": "Bench Press",
                            "set_order": 1,
                            "set_type": "working",
                            "weight_kg": 100,
                            "reps": 5,
                            "rpe": 8,
                        }
                    ],
                },
            )
            trainingos_db.upsert_daily_recovery_metric(
                connection,
                {
                    "metric_date": "2026-10-04",
                    "provider": "garmin",
                    "sleep_score": 80,
                    "sleep_duration_minutes": 442,
                    "hrv_status": "BALANCED",
                    "body_battery": 70,
                },
            )
            trainingos_db.upsert_daily_health_metric(
                connection,
                "sleep",
                {
                    "metric_date": "2026-10-04",
                    "deep_sleep_minutes": 70,
                    "light_sleep_minutes": 220,
                    "rem_sleep_minutes": 90,
                },
            )
            trainingos_db.upsert_body_metric(
                connection, {"metric_date": "2026-10-04", "body_weight_kg": 80}
            )
            trainingos_program_cycle.create_cycle(connection, "2026-09-14")
            snapshot = trainingos_dashboard.dashboard_snapshot(connection, "2026-10-04")
        self.assertEqual(snapshot["training"]["training_days"], 1)
        self.assertEqual(snapshot["training"]["session_count"], 1)
        self.assertEqual(snapshot["training"]["volume_kg"], 500)
        self.assertGreater(snapshot["training"]["pr_record_count"], 0)
        self.assertEqual(snapshot["latest_recovery"]["sleep_score"], 80)
        self.assertEqual(snapshot["latest_recovery"]["sleep_duration_minutes"], 442)
        self.assertEqual(snapshot["latest_recovery"]["hrv_status"], "BALANCED")
        self.assertEqual(len(snapshot["recovery_trends"]), 1)
        self.assertEqual(snapshot["health_details"]["sleep"]["deep_sleep_minutes"], 70)
        self.assertEqual(snapshot["body_metrics"]["values"]["body_weight_kg"], 80)
        self.assertEqual(snapshot["program_cycle"]["week"], 3)
        self.assertEqual(snapshot["estimated_1rm_prs"][0]["exercise"], "Bench Press")
        self.assertEqual(snapshot["training_anchor"]["status"], "ready")
        self.assertEqual(snapshot["training_anchor"]["anchor_training_date"], "2026-10-03")

    def test_empty_snapshot_does_not_create_program_cycle(self):
        with trainingos_db.connect(self.db_path) as connection:
            snapshot = trainingos_dashboard.dashboard_snapshot(connection, "2026-10-04")
            cycle_count = connection.execute("select count(*) from training_blocks").fetchone()[0]
        self.assertEqual(snapshot["training"]["session_count"], 0)
        self.assertIsNone(snapshot["latest_recovery"])
        self.assertIsNone(snapshot["program_cycle"])
        self.assertEqual(snapshot["recovery_trends"], [])
        self.assertIsNone(snapshot["health_details"]["sleep"])
        self.assertEqual(cycle_count, 0)
        self.assertEqual(snapshot["training_anchor"]["status"], "waiting_for_first_training")


if __name__ == "__main__":
    unittest.main()
