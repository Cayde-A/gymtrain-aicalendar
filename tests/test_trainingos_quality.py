import argparse
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from scripts import trainingos_db, trainingos_quality


class TrainingOSQualityTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "trainingos.sqlite"
        trainingos_db.init_db(self.db_path)

    def tearDown(self):
        self.tempdir.cleanup()

    def save_session(self, sets):
        with trainingos_db.connect(self.db_path) as connection:
            return trainingos_db.save_imported_workout(
                connection,
                {
                    "provider": "garmin",
                    "external_activity_id": "quality-session",
                    "completed_at": "2026-10-04 09:00:00",
                    "session_type": "strength_training",
                    "activity_name": "Strength",
                    "sets": sets,
                },
            )

    def report(self, recovery_date=None):
        with trainingos_db.connect(self.db_path) as connection:
            return trainingos_quality.build_quality_report(connection, "2026-10-04", recovery_date)

    def issue_codes(self, report):
        return {issue["code"] for issue in report["training"]["issues"]}

    def test_valid_training_day_is_analysis_ready(self):
        self.save_session(
            [{"exercise_name": "Bench Press", "set_order": 1, "set_type": "working", "weight_kg": 100, "reps": 5}]
        )
        report = self.report()
        self.assertTrue(report["analysis_ready"])
        self.assertEqual(report["training"]["active_set_count"], 1)

    def test_missing_reps_blocks_analysis(self):
        self.save_session(
            [{"exercise_name": "Bench Press", "set_order": 1, "set_type": "ACTIVE", "weight_kg": 100, "reps": None}]
        )
        report = self.report()
        self.assertFalse(report["analysis_ready"])
        self.assertIn("missing_reps", self.issue_codes(report))

    def test_abnormal_weight_blocks_analysis(self):
        self.save_session(
            [{"exercise_name": "Leg Press", "set_order": 1, "set_type": "working", "weight_kg": 108000, "reps": 10}]
        )
        report = self.report()
        self.assertFalse(report["analysis_ready"])
        self.assertIn("abnormal_weight", self.issue_codes(report))

    def test_unknown_exercise_blocks_analysis(self):
        self.save_session(
            [{"exercise_name": "Unknown Exercise", "set_order": 1, "set_type": "working", "weight_kg": 20, "reps": 10}]
        )
        report = self.report()
        self.assertFalse(report["analysis_ready"])
        self.assertIn("unknown_exercise", self.issue_codes(report))

    def test_missing_weight_is_warning_for_possible_bodyweight_set(self):
        self.save_session(
            [{"exercise_name": "Plank", "set_order": 1, "set_type": "working", "weight_kg": None, "reps": 1}]
        )
        report = self.report()
        self.assertTrue(report["analysis_ready"])
        self.assertIn("missing_weight", self.issue_codes(report))

    def test_rest_sets_do_not_require_reps(self):
        self.save_session(
            [
                {"exercise_name": "Bench Press", "set_order": 1, "set_type": "working", "weight_kg": 100, "reps": 5},
                {"exercise_name": "Bench Press", "set_order": 2, "set_type": "REST", "weight_kg": None, "reps": None},
            ]
        )
        report = self.report()
        self.assertTrue(report["analysis_ready"])
        self.assertEqual(report["training"]["active_set_count"], 1)

    def test_recovery_is_required_for_finalization(self):
        self.save_session(
            [{"exercise_name": "Bench Press", "set_order": 1, "set_type": "working", "weight_kg": 100, "reps": 5}]
        )
        report = self.report("2026-10-05")
        self.assertTrue(report["analysis_ready"])
        self.assertFalse(report["finalization_ready"])
        self.assertEqual(report["recovery"]["issues"][0]["code"], "recovery_missing")

    def test_complete_recovery_allows_finalization(self):
        self.save_session(
            [{"exercise_name": "Bench Press", "set_order": 1, "set_type": "working", "weight_kg": 100, "reps": 5}]
        )
        with trainingos_db.connect(self.db_path) as connection:
            trainingos_db.upsert_daily_recovery_metric(
                connection,
                {
                    "metric_date": "2026-10-05",
                    "provider": "garmin",
                    "sleep_score": 82,
                    "training_readiness": 71,
                    "body_battery": 68,
                },
            )
        report = self.report("2026-10-05")
        self.assertTrue(report["finalization_ready"])
        self.assertIn("training_readiness", report["recovery"]["available_fields"])

    def test_out_of_range_recovery_blocks_finalization(self):
        self.save_session(
            [{"exercise_name": "Bench Press", "set_order": 1, "set_type": "working", "weight_kg": 100, "reps": 5}]
        )
        with trainingos_db.connect(self.db_path) as connection:
            trainingos_db.upsert_daily_recovery_metric(
                connection,
                {"metric_date": "2026-10-05", "provider": "garmin", "body_battery": 1000},
            )
        report = self.report("2026-10-05")
        self.assertFalse(report["finalization_ready"])
        self.assertEqual(report["recovery"]["issues"][0]["code"], "recovery_value_out_of_range")

    def test_cli_returns_blocking_exit_code_and_writes_report(self):
        output_path = Path(self.tempdir.name) / "quality.json"
        args = argparse.Namespace(
            date="2026-10-04",
            recovery_date=None,
            db=str(self.db_path),
            output=str(output_path),
        )
        with mock.patch.object(trainingos_quality, "parse_args", return_value=args), redirect_stdout(io.StringIO()):
            result = trainingos_quality.main()
        self.assertEqual(result, 2)
        self.assertTrue(output_path.exists())
        self.assertIn('"training_day_missing"', output_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
