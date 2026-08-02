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
        self.assertIn("Generate an initial next-day plan draft", prompt)
        self.assertIn("initial_draft", prompt)
        self.assertIn("Return JSON only", prompt)
        self.assertIn("Garmin sleep, HRV, Body Battery", prompt)
        self.assertIn("Bench Press", prompt)

    def test_build_ai_review_packet_is_standardized_and_compact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "trainingos.sqlite"
            trainingos_db.init_db(db_path)
            with trainingos_db.connect(db_path) as connection:
                session_id = trainingos_db.save_imported_workout(
                    connection,
                    {
                        "provider": "garmin",
                        "external_activity_id": "packet",
                        "completed_at": "2026-08-02 11:00:00",
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
                packet = trainingos_db.build_ai_review_packet(connection, session_id)
        self.assertEqual(packet["task"], "post_workout_review_and_initial_next_day_draft")
        self.assertTrue(packet["constraints"]["return_json_only"])
        self.assertEqual(packet["metrics"]["set_count"], 1)
        self.assertAlmostEqual(packet["metrics"]["total_volume_kg"], 500)
        self.assertIn("initial_next_day_plan", packet["required_output_schema"])

    def test_save_ai_review_response_persists_structured_json(self):
        response = """
        {
          "analysis_summary": "Good session.",
          "performance_direction": "keep",
          "risk_flags": ["low_rpe_missing"],
          "data_quality_issues": [],
          "initial_next_day_plan": {"status": "initial_draft", "session_type": "pull"},
          "next_morning_adjustment_rules": ["reduce volume if readiness is low"]
        }
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "trainingos.sqlite"
            trainingos_db.init_db(db_path)
            with trainingos_db.connect(db_path) as connection:
                session_id = trainingos_db.save_imported_workout(
                    connection,
                    {
                        "provider": "garmin",
                        "external_activity_id": "ai",
                        "completed_at": "2026-08-02 12:00:00",
                        "session_type": "strength_training",
                        "sets": [],
                    },
                )
                review_id = trainingos_db.save_ai_review_response(connection, session_id, response)
                reviews = trainingos_db.get_ai_reviews_for_session(connection, session_id)
        self.assertTrue(review_id.startswith("ai_review_"))
        self.assertEqual(reviews[0]["decision"], "keep")
        self.assertEqual(reviews[0]["summary"], "Good session.")
        self.assertIn("initial_next_day_plan", reviews[0]["next_target_json"])

    def test_save_ai_review_response_preserves_unstructured_text(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "trainingos.sqlite"
            trainingos_db.init_db(db_path)
            with trainingos_db.connect(db_path) as connection:
                session_id = trainingos_db.save_imported_workout(
                    connection,
                    {
                        "provider": "garmin",
                        "external_activity_id": "text",
                        "completed_at": "2026-08-02 13:00:00",
                        "session_type": "strength_training",
                        "sets": [],
                    },
                )
                trainingos_db.save_ai_review_response(connection, session_id, "Plain analysis")
                reviews = trainingos_db.get_ai_reviews_for_session(connection, session_id)
        self.assertEqual(reviews[0]["decision"], "manual_review")
        self.assertEqual(reviews[0]["summary"], "Plain analysis")


if __name__ == "__main__":
    unittest.main()
