import io
import unittest
import zipfile
from unittest import mock

from scripts import garmin_fit_activity


class GarminFitActivityTestCase(unittest.TestCase):
    def test_normalize_fit_sets_maps_profile_names_and_rest(self):
        result = garmin_fit_activity.normalize_fit_set_messages(
            [
                {
                    "set_type": "active",
                    "repetitions": 10,
                    "weight": 40.0,
                    "category": ["pull_up", "pull_up"],
                    "category_subtype": [13, 13],
                },
                {"set_type": "rest"},
            ],
            {"pull_up_exercise_name": {13: "lat_pulldown"}},
        )
        self.assertEqual(result[0]["exerciseName"], "LAT_PULLDOWN")
        self.assertEqual(result[0]["weight"], 40)
        self.assertEqual(result[0]["repetitionCount"], 10)
        self.assertEqual(result[1]["exerciseName"], "Rest")
        self.assertEqual(result[1]["setType"], "rest")

    def test_decode_activity_zip_rejects_non_zip_and_multiple_fit_files(self):
        with self.assertRaisesRegex(ValueError, "not a ZIP"):
            garmin_fit_activity.decode_activity_zip(b"not-a-zip")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("one.fit", b"one")
            archive.writestr("two.fit", b"two")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            garmin_fit_activity.decode_activity_zip(buffer.getvalue())

    def test_decode_activity_zip_returns_normalized_sets(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("activity.fit", b"fit-data")
        messages = {
            "set_mesgs": [
                {
                    "set_type": "active",
                    "repetitions": 8,
                    "weight": 85.0,
                    "category": "bench_press",
                    "category_subtype": 0,
                }
            ]
        }
        with mock.patch.object(
            garmin_fit_activity, "decode_fit_bytes", return_value=(messages, [])
        ):
            result = garmin_fit_activity.decode_activity_zip(buffer.getvalue())
        self.assertEqual(result["fit_message_count"], 1)
        self.assertEqual(result["exerciseSets"][0]["weight"], 85)


if __name__ == "__main__":
    unittest.main()
