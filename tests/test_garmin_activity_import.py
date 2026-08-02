import unittest

from scripts import garmin_activity_import


class GarminActivityImportTestCase(unittest.TestCase):
    def test_normalize_activity_extracts_summary_and_sets(self):
        payload = {
            "summary": {
                "activityId": 123,
                "activityName": "Strength",
                "activityType": {"typeKey": "strength_training"},
                "startTimeLocal": "2026-08-02 08:00:00",
                "duration": 2700,
                "averageHR": 121,
                "maxHR": 158,
                "calories": 320,
            },
            "details": {},
            "exercise_sets": {
                "exerciseSets": [
                    {
                        "exerciseName": "Bench Press",
                        "setNumber": 1,
                        "setType": "working",
                        "weight": 100,
                        "reps": 5,
                    }
                ]
            },
        }
        normalized = garmin_activity_import.normalize_activity(payload, "raw.json")
        self.assertEqual(normalized["external_activity_id"], "123")
        self.assertEqual(normalized["session_type"], "strength_training")
        self.assertEqual(normalized["average_heart_rate"], 121)
        self.assertEqual(normalized["sets"][0]["exercise_name"], "Bench Press")
        self.assertEqual(normalized["sets"][0]["reps"], 5)
        self.assertEqual(normalized["raw_payload_path"], "raw.json")

    def test_is_strength_activity_detects_strength_type(self):
        self.assertTrue(
            garmin_activity_import.is_strength_activity(
                {"activityName": "Gym", "activityType": {"typeKey": "strength_training"}}
            )
        )
        self.assertFalse(
            garmin_activity_import.is_strength_activity(
                {"activityName": "Run", "activityType": {"typeKey": "running"}}
            )
        )

    def test_extract_sets_returns_empty_when_unavailable(self):
        self.assertEqual(garmin_activity_import.extract_sets(None, "Strength"), [])


if __name__ == "__main__":
    unittest.main()
