import unittest

from scripts import trainingos_voice_input


class TrainingOSVoiceInputTestCase(unittest.TestCase):
    def test_parses_chinese_strength_set(self):
        result = trainingos_voice_input.parse_voice_entry("杠铃卧推 八十公斤 八次 RPE八")
        self.assertEqual(result["status"], "parsed")
        self.assertEqual(result["sets"][0]["exercise_name"], "杠铃卧推")
        self.assertEqual(result["sets"][0]["weight_kg"], 80)
        self.assertEqual(result["sets"][0]["reps"], 8)
        self.assertEqual(result["sets"][0]["rpe"], 8)

    def test_expands_multiple_sets(self):
        result = trainingos_voice_input.parse_voice_entry("Leg Press 120 kg 10 reps 3 sets", next_order=2)
        self.assertEqual([item["set_order"] for item in result["sets"]], [2, 3, 4])
        self.assertEqual(result["sets"][2]["weight_kg"], 120)

    def test_repeat_can_reduce_previous_weight(self):
        previous = {
            "exercise_name": "Bench Press",
            "weight_kg": 100,
            "reps": 5,
            "rpe": 8,
        }
        result = trainingos_voice_input.parse_voice_entry("再来一组 减十公斤", previous, 2)
        self.assertEqual(result["status"], "parsed")
        self.assertEqual(result["sets"][0]["exercise_name"], "Bench Press")
        self.assertEqual(result["sets"][0]["weight_kg"], 90)
        self.assertEqual(result["sets"][0]["reps"], 5)

    def test_missing_required_fields_is_not_accepted(self):
        result = trainingos_voice_input.parse_voice_entry("卧推 RPE八")
        self.assertEqual(result["status"], "invalid")
        self.assertEqual(result["issues"], ["missing_weight", "missing_reps"])

    def test_repeat_requires_previous_set(self):
        result = trainingos_voice_input.parse_voice_entry("再来一组")
        self.assertEqual(result["issues"], ["repeat_without_previous_set"])


if __name__ == "__main__":
    unittest.main()
