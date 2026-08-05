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
        self.assertEqual(packet["trigger_policy"]["post_workout_ai_mode"], "manual_copy_paste")
        self.assertFalse(packet["trigger_policy"]["auto_api_enabled"])

    def test_ai_trigger_policy_defaults_are_conservative(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "trainingos.sqlite"
            trainingos_db.init_db(db_path)
            with trainingos_db.connect(db_path) as connection:
                policy = trainingos_db.get_ai_trigger_policy(connection)
        self.assertEqual(policy["post_workout_ai_mode"], "manual_copy_paste")
        self.assertEqual(policy["next_morning_adjustment_mode"], "user_confirmed_api")
        self.assertEqual(policy["garmin_push_mode"], "user_confirmed")
        self.assertFalse(policy["auto_api_enabled"])
        self.assertEqual(policy["max_ai_calls_per_day"], 2)

    def test_update_ai_trigger_policy_persists_and_is_included_in_packet(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "trainingos.sqlite"
            trainingos_db.init_db(db_path)
            with trainingos_db.connect(db_path) as connection:
                trainingos_db.update_ai_trigger_policy(
                    connection,
                    {
                        "post_workout_ai_mode": "user_confirmed_api",
                        "next_morning_adjustment_mode": "auto_api_after_recovery_sync",
                        "garmin_push_mode": "manual_only",
                        "auto_api_enabled": True,
                        "max_ai_calls_per_day": 5,
                    },
                )
                session_id = trainingos_db.save_imported_workout(
                    connection,
                    {
                        "provider": "garmin",
                        "external_activity_id": "policy-packet",
                        "completed_at": "2026-08-02 11:30:00",
                        "session_type": "strength_training",
                        "sets": [],
                    },
                )
                packet = trainingos_db.build_ai_review_packet(connection, session_id)
        self.assertEqual(packet["trigger_policy"]["post_workout_ai_mode"], "user_confirmed_api")
        self.assertEqual(packet["trigger_policy"]["next_morning_adjustment_mode"], "auto_api_after_recovery_sync")
        self.assertEqual(packet["trigger_policy"]["garmin_push_mode"], "manual_only")
        self.assertTrue(packet["trigger_policy"]["auto_api_enabled"])
        self.assertEqual(packet["trigger_policy"]["max_ai_calls_per_day"], 5)

    def test_evaluate_api_trigger_blocks_manual_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "trainingos.sqlite"
            trainingos_db.init_db(db_path)
            with trainingos_db.connect(db_path) as connection:
                decision = trainingos_db.evaluate_api_trigger(connection, "post_workout_ai")
                log_id = trainingos_db.record_api_trigger_decision(connection, decision)
                logs = trainingos_db.get_recent_api_trigger_logs(connection)
        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["status"], "manual")
        self.assertEqual(decision["reason"], "manual_mode_selected")
        self.assertTrue(log_id.startswith("api_trigger_"))
        self.assertEqual(logs[0]["trigger_name"], "post_workout_ai")

    def test_evaluate_api_trigger_allows_user_confirmed_mode_only_after_confirmation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "trainingos.sqlite"
            trainingos_db.init_db(db_path)
            with trainingos_db.connect(db_path) as connection:
                trainingos_db.update_ai_trigger_policy(
                    connection,
                    {
                        "post_workout_ai_mode": "user_confirmed_api",
                        "next_morning_adjustment_mode": "user_confirmed_api",
                        "garmin_push_mode": "user_confirmed",
                        "auto_api_enabled": False,
                        "max_ai_calls_per_day": 2,
                    },
                )
                before_confirmation = trainingos_db.evaluate_api_trigger(connection, "post_workout_ai")
                after_confirmation = trainingos_db.evaluate_api_trigger(
                    connection,
                    "post_workout_ai",
                    user_confirmed=True,
                )
        self.assertFalse(before_confirmation["allowed"])
        self.assertEqual(before_confirmation["status"], "needs_confirmation")
        self.assertTrue(after_confirmation["allowed"])
        self.assertEqual(after_confirmation["status"], "allowed")

    def test_evaluate_api_trigger_enforces_daily_ai_call_cap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "trainingos.sqlite"
            trainingos_db.init_db(db_path)
            with trainingos_db.connect(db_path) as connection:
                trainingos_db.update_ai_trigger_policy(
                    connection,
                    {
                        "post_workout_ai_mode": "user_confirmed_api",
                        "next_morning_adjustment_mode": "user_confirmed_api",
                        "garmin_push_mode": "user_confirmed",
                        "auto_api_enabled": False,
                        "max_ai_calls_per_day": 1,
                    },
                )
                first_decision = trainingos_db.evaluate_api_trigger(
                    connection,
                    "post_workout_ai",
                    user_confirmed=True,
                )
                trainingos_db.record_api_trigger_decision(connection, first_decision)
                capped_decision = trainingos_db.evaluate_api_trigger(
                    connection,
                    "next_morning_adjustment",
                    user_confirmed=True,
                )
        self.assertTrue(first_decision["allowed"])
        self.assertFalse(capped_decision["allowed"])
        self.assertEqual(capped_decision["reason"], "daily_ai_call_cap_reached")

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

    def test_same_day_sessions_are_grouped_for_ai_review(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "trainingos.sqlite"
            trainingos_db.init_db(db_path)
            with trainingos_db.connect(db_path) as connection:
                trainingos_db.save_imported_workout(
                    connection,
                    {
                        "provider": "garmin",
                        "external_activity_id": "same-day-a",
                        "completed_at": "2026-08-02 09:00:00",
                        "session_type": "strength_training",
                        "activity_name": "Strength A",
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
                trainingos_db.save_imported_workout(
                    connection,
                    {
                        "provider": "garmin",
                        "external_activity_id": "same-day-b",
                        "completed_at": "2026-08-02 09:20:00",
                        "session_type": "strength_training",
                        "activity_name": "Strength B",
                        "sets": [
                            {
                                "exercise_name": "Row",
                                "set_order": 1,
                                "set_type": "working",
                                "weight_kg": 80,
                                "reps": 8,
                            }
                        ],
                    },
                )
                days = trainingos_db.get_recent_training_days(connection)
                packet = trainingos_db.build_day_ai_review_packet(connection, "2026-08-02")
                prompt = trainingos_db.build_day_post_workout_analysis_prompt(connection, "2026-08-02")
        self.assertEqual(days[0]["training_date"], "2026-08-02")
        self.assertEqual(days[0]["session_count"], 2)
        self.assertEqual(packet["constraints"]["treat_same_day_sessions_as_one_workout"], True)
        self.assertEqual(packet["metrics"]["session_count"], 2)
        self.assertEqual(packet["metrics"]["set_count"], 2)
        self.assertIn("Strength A", str(packet))
        self.assertIn("Strength B", str(packet))
        self.assertIn("Treat all sessions in the same training_date as one workout", prompt)

    def test_save_day_ai_review_response_persists_day_review(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "trainingos.sqlite"
            trainingos_db.init_db(db_path)
            with trainingos_db.connect(db_path) as connection:
                review_id = trainingos_db.save_day_ai_review_response(
                    connection,
                    "2026-08-02",
                    '{"analysis_summary":"Day review","performance_direction":"increase","risk_flags":[]}',
                )
                reviews = trainingos_db.get_ai_reviews_for_day(connection, "2026-08-02")
        self.assertTrue(review_id.startswith("ai_review_"))
        self.assertEqual(reviews[0]["decision"], "increase")
        self.assertEqual(reviews[0]["summary"], "Day review")


if __name__ == "__main__":
    unittest.main()
