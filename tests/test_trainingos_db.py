import tempfile
import unittest
from pathlib import Path

from scripts import trainingos_db


class TrainingOSDbTestCase(unittest.TestCase):
    def test_init_db_creates_core_tables(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "trainingos.sqlite"
            trainingos_db.init_db(db_path)
            with trainingos_db.connect(db_path) as connection:
                rows = connection.execute(
                    "select name from sqlite_master where type = 'table' and name = 'completed_sessions'"
                ).fetchall()
            self.assertEqual(len(rows), 1)

    def test_save_imported_workout_and_build_summary(self):
        workout = {
            "provider": "garmin",
            "external_activity_id": "123",
            "started_at": "2026-08-02 08:00:00",
            "completed_at": "2026-08-02 08:45:00",
            "session_type": "strength_training",
            "activity_name": "Strength",
            "duration_seconds": 2700,
            "average_heart_rate": 122,
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
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "trainingos.sqlite"
            trainingos_db.init_db(db_path)
            with trainingos_db.connect(db_path) as connection:
                session_id = trainingos_db.save_imported_workout(connection, workout)
                summary = trainingos_db.build_ai_review_summary(connection, session_id)
            self.assertEqual(summary["session"]["activity_name"], "Strength")
            self.assertEqual(summary["sets"][0]["exercise"], "Bench Press")
            self.assertAlmostEqual(summary["sets"][0]["estimated_1rm_kg"], 116.6666666667)

    def test_update_review_payload_replaces_sets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "trainingos.sqlite"
            trainingos_db.init_db(db_path)
            with trainingos_db.connect(db_path) as connection:
                session_id = trainingos_db.save_imported_workout(
                    connection,
                    {
                        "provider": "garmin",
                        "external_activity_id": "456",
                        "completed_at": "2026-08-02 09:00:00",
                        "session_type": "strength_training",
                        "sets": [],
                    },
                )
                trainingos_db.update_review_payload(
                    connection,
                    session_id,
                    {
                        "overall_rpe": 8.5,
                        "fatigue_rating": 7,
                        "pain_notes": "No pain",
                        "readiness_notes": "Normal",
                        "sets": [
                            {
                                "exercise_name": "Leg Press",
                                "set_order": 1,
                                "set_type": "working",
                                "weight_kg": 140,
                                "reps": 8,
                                "rpe": 8,
                            }
                        ],
                    },
                )
                session = trainingos_db.get_session_for_review(connection, session_id)
            self.assertEqual(session["overall_rpe"], 8.5)
            self.assertEqual(session["sets"][0]["exercise_name"], "Leg Press")

    def test_build_post_workout_analysis_prompt_includes_initial_plan_and_recovery_adjustment(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "trainingos.sqlite"
            trainingos_db.init_db(db_path)
            with trainingos_db.connect(db_path) as connection:
                session_id = trainingos_db.save_imported_workout(
                    connection,
                    {
                        "provider": "garmin",
                        "external_activity_id": "789",
                        "completed_at": "2026-08-02 10:00:00",
                        "session_type": "strength_training",
                        "activity_name": "Strength",
                        "sets": [
                            {
                                "exercise_name": "Bench Press",
                                "set_order": 1,
                                "set_type": "working",
                                "weight_kg": 100,
                                "reps": 5,
                            }
                        ],
                    },
                )
                prompt = trainingos_db.build_post_workout_analysis_prompt(connection, session_id)
        self.assertIn("generate an initial next-day training plan", prompt)
        self.assertIn("initial_draft", prompt)
        self.assertIn("Do not push a final Garmin workout", prompt)
        self.assertIn("Garmin sleep, HRV, Body Battery", prompt)
        self.assertIn("Bench Press", prompt)


if __name__ == "__main__":
    unittest.main()
