import json
import tempfile
import unittest
from pathlib import Path

from scripts import trainingos_db, trainingos_openai_review


def valid_review():
    return {
        "analysis_summary": "Performance reviewed.",
        "performance_direction": "keep",
        "risk_flags": [],
        "data_quality_issues": [],
        "initial_next_day_plan": {
            "status": "initial_draft",
            "session_type": "legs",
            "primary_large_muscle_group": "legs",
            "interstitial_core": "none",
            "focus": ["controlled volume"],
            "avoided_overlap": ["chest"],
            "rounds": [
                {
                    "exercise": "Leg Press",
                    "sets": 4,
                    "reps": "10",
                    "load_guidance": "Use current working load",
                    "rpe_cap": 8,
                }
            ],
        },
        "next_morning_adjustment_rules": ["Use recovery data"],
    }


def response_for(review):
    return {
        "id": "resp_test",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": json.dumps(review)}],
            }
        ],
        "usage": {"input_tokens": 100, "output_tokens": 50},
    }


class TrainingOSOpenAIReviewTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "trainingos.sqlite"
        trainingos_db.init_db(self.db_path)
        with trainingos_db.connect(self.db_path) as connection:
            trainingos_db.save_imported_workout(
                connection,
                {
                    "provider": "garmin",
                    "external_activity_id": "ai-adapter",
                    "completed_at": "2026-10-04 09:00:00",
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

    def tearDown(self):
        self.tempdir.cleanup()

    def test_request_uses_strict_schema_and_disables_storage(self):
        with trainingos_db.connect(self.db_path) as connection:
            packet = trainingos_db.build_day_ai_review_packet(connection, "2026-10-04")
        request = trainingos_openai_review.build_request(packet, "gpt-5-mini")
        self.assertFalse(request["store"])
        self.assertEqual(request["reasoning"]["effort"], "low")
        self.assertEqual(request["text"]["format"]["type"], "json_schema")
        self.assertTrue(request["text"]["format"]["strict"])
        self.assertFalse(request["text"]["format"]["schema"]["additionalProperties"])

    def test_review_without_training_anchor_never_calls_api(self):
        empty_db = Path(self.tempdir.name) / "empty.sqlite"
        trainingos_db.init_db(empty_db)
        calls = []

        def requester(payload, api_key):
            calls.append(payload)
            return 200, response_for(valid_review())

        with trainingos_db.connect(empty_db) as connection:
            code, result = trainingos_openai_review.run_review(
                connection, "2026-10-04", "gpt-5-mini", True, "test-key", requester
            )
        self.assertEqual(code, 3)
        self.assertEqual(result["status"], "waiting_for_first_training")
        self.assertFalse(result["api_called"])
        self.assertEqual(calls, [])

    def test_default_manual_policy_blocks_api_call(self):
        calls = []

        def requester(payload, api_key):
            calls.append(payload)
            return 200, response_for(valid_review())

        with trainingos_db.connect(self.db_path) as connection:
            code, result = trainingos_openai_review.run_review(
                connection, "2026-10-04", "gpt-5-mini", True, "test-key", requester
            )
        self.assertEqual(code, 3)
        self.assertEqual(result["status"], "manual")
        self.assertEqual(calls, [])

    def test_confirmed_call_saves_review_then_reuses_it(self):
        calls = []

        def requester(payload, api_key):
            calls.append((payload, api_key))
            return 200, response_for(valid_review())

        with trainingos_db.connect(self.db_path) as connection:
            trainingos_db.update_ai_trigger_policy(
                connection,
                {
                    "post_workout_ai_mode": "user_confirmed_api",
                    "next_morning_adjustment_mode": "user_confirmed_api",
                    "garmin_push_mode": "user_confirmed",
                    "max_ai_calls_per_day": 2,
                },
            )
            first_code, first = trainingos_openai_review.run_review(
                connection, "2026-10-04", "gpt-5-mini", True, "test-key", requester
            )
            second_code, second = trainingos_openai_review.run_review(
                connection, "2026-10-04", "gpt-5-mini", True, "test-key", requester
            )
            reviews = trainingos_db.get_ai_reviews_for_day(connection, "2026-10-04")
        self.assertEqual(first_code, 0)
        self.assertEqual(first["status"], "review_saved")
        self.assertEqual(first["input_tokens"], 100)
        self.assertEqual(second_code, 0)
        self.assertEqual(second["status"], "existing_review_reused")
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(reviews), 1)

    def test_invalid_structured_output_is_not_saved(self):
        invalid = valid_review()
        invalid["initial_next_day_plan"]["status"] = "final"

        def requester(payload, api_key):
            return 200, response_for(invalid)

        with trainingos_db.connect(self.db_path) as connection:
            trainingos_db.update_ai_trigger_policy(
                connection,
                {
                    "post_workout_ai_mode": "user_confirmed_api",
                    "next_morning_adjustment_mode": "user_confirmed_api",
                    "garmin_push_mode": "user_confirmed",
                    "max_ai_calls_per_day": 2,
                },
            )
            code, result = trainingos_openai_review.run_review(
                connection, "2026-10-04", "gpt-5-mini", True, "test-key", requester
            )
            reviews = trainingos_db.get_ai_reviews_for_day(connection, "2026-10-04")
        self.assertEqual(code, 4)
        self.assertEqual(result["status"], "invalid_structured_output")
        self.assertIn("plan_status_must_be_initial_draft", result["issues"])
        self.assertEqual(reviews, [])

    def test_allowed_trigger_without_api_key_never_calls_requester(self):
        calls = []

        def requester(payload, api_key):
            calls.append((payload, api_key))
            return 200, response_for(valid_review())

        with trainingos_db.connect(self.db_path) as connection:
            trainingos_db.update_ai_trigger_policy(
                connection,
                {
                    "post_workout_ai_mode": "user_confirmed_api",
                    "next_morning_adjustment_mode": "user_confirmed_api",
                    "garmin_push_mode": "user_confirmed",
                    "max_ai_calls_per_day": 2,
                },
            )
            code, result = trainingos_openai_review.run_review(
                connection, "2026-10-04", "gpt-5-mini", True, None, requester
            )
        self.assertEqual(code, 3)
        self.assertEqual(result["status"], "needs_api_key")
        self.assertEqual(calls, [])

    def test_boolean_round_values_are_rejected(self):
        invalid = valid_review()
        invalid["initial_next_day_plan"]["rounds"][0]["sets"] = True
        invalid["initial_next_day_plan"]["rounds"][0]["rpe_cap"] = False
        issues = trainingos_openai_review.validate_review_output(invalid)
        self.assertIn("round_0_sets_invalid", issues)
        self.assertIn("round_0_rpe_cap_invalid", issues)


if __name__ == "__main__":
    unittest.main()
