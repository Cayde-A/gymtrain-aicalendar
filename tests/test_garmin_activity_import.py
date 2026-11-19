import unittest

from scripts import garmin_activity_import, garmin_provider


class DummyOfficialActivityClient:
    source_tool = garmin_provider.PERSONAL_SOURCE_TOOL

    def get_activity(self, activity_id):
        return {
            "activityId": activity_id,
            "summarizedExerciseSets": [
                {
                    "setNumber": 1,
                    "weight": 85000,
                    "repetitionCount": 8,
                    "exercises": [{"category": "BENCH_PRESS"}],
                }
            ],
        }

    def get_activity_exercise_sets(self, activity_id):
        return {"workouts": []}


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
                        "exercises": [{"category": "BENCH_PRESS", "name": None}],
                        "setNumber": 1,
                        "setType": "working",
                        "weight": 100000,
                        "repetitionCount": 5,
                    }
                ]
            },
        }
        normalized = garmin_activity_import.normalize_activity(payload, "raw.json")
        self.assertEqual(normalized["external_activity_id"], "123")
        self.assertEqual(normalized["session_type"], "strength_training")
        self.assertEqual(normalized["average_heart_rate"], 121)
        self.assertEqual(normalized["sets"][0]["exercise_name"], "BENCH_PRESS")
        self.assertEqual(normalized["sets"][0]["weight_kg"], 100)
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

    def test_normalize_set_log_uses_central_mapping(self):
        normalized = garmin_activity_import.normalize_set_log(
            {
                "setNumber": 2,
                "setType": "ACTIVE",
                "weight": 108000,
                "repetitionCount": 10,
                "exercises": [{"category": "SIT_UP"}],
            },
            "Strength",
            1,
        )
        self.assertEqual(normalized["exercise_name"], "SIT_UP")
        self.assertEqual(normalized["set_order"], 2)
        self.assertEqual(normalized["set_type"], "ACTIVE")
        self.assertEqual(normalized["weight_kg"], 108)
        self.assertEqual(normalized["reps"], 10)

    def test_normalize_weight_keeps_small_values_and_converts_grams(self):
        self.assertEqual(garmin_activity_import.normalize_weight_kg(108000), 108)
        self.assertEqual(garmin_activity_import.normalize_weight_kg(108), 108)
        self.assertIsNone(garmin_activity_import.normalize_weight_kg(None))

    def test_mapping_tables_include_known_garmin_fields(self):
        self.assertIn("repetitionCount", garmin_activity_import.SET_FIELD_MAPPINGS["reps"])
        self.assertIn("weight", garmin_activity_import.SET_FIELD_MAPPINGS["weight_kg"])
        self.assertIn("averageHR", garmin_activity_import.ACTIVITY_FIELD_MAPPINGS["average_heart_rate"])

    def test_fetch_payload_prefers_official_summarized_exercise_sets(self):
        payload = garmin_activity_import.fetch_activity_payload(
            DummyOfficialActivityClient(),
            {"activityId": 123, "activityName": "Strength"},
        )
        normalized = garmin_activity_import.normalize_activity(payload)
        self.assertEqual(payload["source_tool"], garmin_provider.PERSONAL_SOURCE_TOOL)
        self.assertEqual(normalized["source_tool"], garmin_provider.PERSONAL_SOURCE_TOOL)
        self.assertEqual(normalized["sets"][0]["weight_kg"], 85)
        self.assertEqual(normalized["sets"][0]["reps"], 8)


if __name__ == "__main__":
    unittest.main()
