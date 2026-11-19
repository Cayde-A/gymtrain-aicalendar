import tempfile
import unittest
from pathlib import Path

from scripts import trainingos_db, trainingos_monthly_report


class TrainingOSMonthlyReportTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "trainingos.sqlite"
        trainingos_db.init_db(self.db_path)

    def tearDown(self):
        self.tempdir.cleanup()

    def save_bench(self, activity_id, date, weight):
        with trainingos_db.connect(self.db_path) as connection:
            trainingos_db.save_imported_workout(
                connection,
                {
                    "provider": "garmin",
                    "external_activity_id": activity_id,
                    "completed_at": f"{date} 09:00:00",
                    "session_type": "strength_training",
                    "sets": [
                        {
                            "exercise_name": "Bench Press",
                            "set_order": 1,
                            "set_type": "working",
                            "weight_kg": weight,
                            "reps": 5,
                            "rpe": 8,
                        }
                    ],
                },
            )

    def test_monthly_report_tracks_best_set_and_estimated_1rm_change(self):
        self.save_bench("month-1", "2026-10-02", 90)
        self.save_bench("month-2", "2026-10-20", 100)
        with trainingos_db.connect(self.db_path) as connection:
            trainingos_db.upsert_daily_recovery_metric(
                connection, {"metric_date": "2026-10-02", "provider": "garmin", "sleep_score": 80}
            )
            trainingos_db.upsert_daily_recovery_metric(
                connection, {"metric_date": "2026-10-03", "provider": "garmin", "sleep_score": 70}
            )
            trainingos_db.upsert_body_metric(
                connection, {"metric_date": "2026-10-01", "body_weight_kg": 80}
            )
            trainingos_db.upsert_body_metric(
                connection, {"metric_date": "2026-10-31", "body_weight_kg": 79}
            )
            report = trainingos_monthly_report.build_monthly_report(connection, "2026-10")
        self.assertEqual(report["period"]["calendar_days"], 31)
        self.assertEqual(report["training"]["session_count"], 2)
        self.assertEqual(report["training"]["total_volume_kg"], 950)
        self.assertEqual(report["best_sets"][0]["weight_kg"], 100)
        self.assertEqual(report["estimated_1rm_trends"][0]["observed_sessions"], 2)
        self.assertGreater(report["estimated_1rm_trends"][0]["change_kg"], 0)
        self.assertEqual(report["recovery"]["averages"]["sleep_score"], 75)
        self.assertEqual(report["body_metrics"]["change_first_to_last"]["body_weight_kg"], -1)
        self.assertFalse(report["ai_api_called"])

    def test_empty_month_markdown_is_explicit(self):
        with trainingos_db.connect(self.db_path) as connection:
            report = trainingos_monthly_report.build_monthly_report(connection, "2026-02")
        markdown = trainingos_monthly_report.render_markdown(report)
        self.assertEqual(report["period"]["calendar_days"], 28)
        self.assertIn("No completed exercise data", markdown)
        self.assertIn("Coverage: 0/28 days", markdown)
        self.assertIn("Insufficient records", markdown)


if __name__ == "__main__":
    unittest.main()
