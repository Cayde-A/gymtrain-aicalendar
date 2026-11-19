import tempfile
import unittest
from pathlib import Path

from scripts import trainingos_db, trainingos_weekly_review


class TrainingOSWeeklyReviewTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "trainingos.sqlite"
        trainingos_db.init_db(self.db_path)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_weekly_review_aggregates_training_recovery_pr_and_body_change(self):
        with trainingos_db.connect(self.db_path) as connection:
            trainingos_db.save_imported_workout(
                connection,
                {
                    "provider": "garmin",
                    "external_activity_id": "weekly-1",
                    "completed_at": "2026-10-02 09:00:00",
                    "session_type": "strength_training",
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
                {"metric_date": "2026-10-02", "provider": "garmin", "sleep_score": 80},
            )
            trainingos_db.upsert_daily_recovery_metric(
                connection,
                {"metric_date": "2026-10-03", "provider": "garmin", "sleep_score": 70},
            )
            trainingos_db.upsert_body_metric(
                connection, {"metric_date": "2026-09-29", "body_weight_kg": 80}
            )
            trainingos_db.upsert_body_metric(
                connection, {"metric_date": "2026-10-04", "body_weight_kg": 79.5}
            )
            report = trainingos_weekly_review.build_weekly_review(connection, "2026-10-04")
        self.assertEqual(report["period"]["start_date"], "2026-09-28")
        self.assertEqual(report["training"]["session_count"], 1)
        self.assertEqual(report["training"]["total_volume_kg"], 500)
        self.assertGreater(report["pr_count"], 0)
        self.assertEqual(report["recovery"]["days_present"], 2)
        self.assertEqual(report["recovery"]["averages"]["sleep_score"], 75)
        self.assertEqual(report["body_metrics"]["change_first_to_last"]["body_weight_kg"], -0.5)
        self.assertFalse(report["ai_api_called"])

    def test_markdown_handles_empty_week(self):
        with trainingos_db.connect(self.db_path) as connection:
            report = trainingos_weekly_review.build_weekly_review(connection, "2026-10-04")
        markdown = trainingos_weekly_review.render_markdown(report)
        self.assertIn("No completed exercise data", markdown)
        self.assertIn("Coverage: 0/7 days", markdown)
        self.assertIn("Insufficient records", markdown)


if __name__ == "__main__":
    unittest.main()
