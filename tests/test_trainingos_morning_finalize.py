import unittest

from scripts import trainingos_morning_finalize


class TrainingOSMorningFinalizeTestCase(unittest.TestCase):
    def test_summary_exposes_final_adjustment_without_ai_call(self):
        summary = trainingos_morning_finalize.summarize(
            {
                "status": "final_plan_ready",
                "training_date": "2026-10-04",
                "target_date": "2026-10-05",
                "quality": {"finalization_ready": True},
                "review": {"review_id": "review-1"},
                "plan": {
                    "recovery_adjustment": "reduce_volume",
                    "program_cycle": {"week": 3, "phase": "intensification"},
                    "primary_exercise_progression": {"action": "keep"},
                    "venue_validation": {"status": "verified"},
                    "payload_path": "/tmp/workout.json",
                },
            }
        )
        self.assertEqual(summary["status"], "final_plan_ready")
        self.assertTrue(summary["quality_ready"])
        self.assertEqual(summary["recovery_adjustment"], "reduce_volume")
        self.assertEqual(summary["program_week"], 3)
        self.assertEqual(summary["progression_action"], "keep")
        self.assertFalse(summary["ai_api_called"])

    def test_summary_preserves_user_action_error(self):
        summary = trainingos_morning_finalize.summarize(
            {
                "status": "needs_venue_confirmation",
                "quality": {"finalization_ready": True},
                "error": {
                    "code": "venue_equipment_confirmation_required",
                    "exercises": ["Leg Press"],
                },
            }
        )
        self.assertEqual(summary["status"], "needs_venue_confirmation")
        self.assertEqual(summary["error"]["exercises"], ["Leg Press"])
        self.assertFalse(summary["ai_api_called"])


if __name__ == "__main__":
    unittest.main()
