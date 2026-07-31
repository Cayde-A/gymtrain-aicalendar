import datetime as dt
import json
import os
import tempfile
import unittest

from scripts import garmin_import


class DummyClient:
    def __init__(self, methods):
        self._methods = methods

    def __getattr__(self, item):
        if item in self._methods:
            return self._methods[item]
        raise AttributeError(item)


class GarminImportTestCase(unittest.TestCase):
    def test_date_range_returns_reversed_days(self):
        result = garmin_import.date_range("2026-07-31", 3)
        self.assertEqual(result, [dt.date(2026, 7, 29), dt.date(2026, 7, 30), dt.date(2026, 7, 31)])

    def test_call_first_available_uses_first_successful_method(self):
        client = DummyClient(
            {
                "one": lambda x: "fail",
                "two": lambda x: "ok",
            }
        )
        result = garmin_import.call_first_available(client, [("two", ("arg",))])
        self.assertTrue(result["ok"])
        self.assertEqual(result["source_method"], "two")
        self.assertEqual(result["data"], "ok")

    def test_call_first_available_falls_back_when_method_missing(self):
        client = DummyClient({})
        result = garmin_import.call_first_available(client, [("missing", ("arg",))])
        self.assertFalse(result["ok"])
        self.assertIn("missing", result["failures"])

    def test_call_first_available_falls_back_on_exception(self):
        def raise_error(arg):
            raise ValueError("boom")

        client = DummyClient({"broken": raise_error, "good": lambda arg: 123})
        result = garmin_import.call_first_available(client, [("broken", ("arg",)), ("good", ("arg",))])
        self.assertTrue(result["ok"])
        self.assertEqual(result["source_method"], "good")
        self.assertEqual(result["data"], 123)

    def test_deep_find_number_searches_nested_data(self):
        payload = {
            "outer": [{"RestingHeartRate": 55}, {"nested": {"sleep-duration-seconds": 450}}],
        }
        self.assertEqual(garmin_import.deep_find_number(payload, {"restingheartrate", "sleepdurationseconds"}), 55)

    def test_deep_find_string_searches_nested_data(self):
        payload = {"level": {"HRVStatus": "recovered"}, "other": ["ignore"]}
        self.assertEqual(garmin_import.deep_find_string(payload, {"hrvstatus", "status"}), "recovered")

    def test_normalize_day_extracts_metrics_and_uses_unwrap(self):
        raw = {
            "date": "2026-07-31",
            "stats": {"ok": True, "data": {"restingHeartRate": 42, "totalSteps": 10000, "totalCalories": 2200, "trainingReadinessScore": 80, "recoveryTimeHours": 24, "averageStressLevel": 25}},
            "sleep": {"ok": True, "data": {"sleepScore": 90, "sleepDurationSeconds": 27000}},
            "hrv": {"ok": True, "data": {"status": "ready"}},
            "body_battery": {"ok": True, "data": {"bodyBattery": 85}},
            "training_readiness": {"ok": True, "data": {"score": 78}},
        }
        normalized = garmin_import.normalize_day(raw)
        self.assertEqual(normalized["metric_date"], "2026-07-31")
        self.assertEqual(normalized["resting_heart_rate"], 42)
        self.assertEqual(normalized["steps"], 10000)
        self.assertEqual(normalized["calories"], 2200)
        self.assertEqual(normalized["training_readiness"], 78)
        self.assertEqual(normalized["recovery_time_hours"], 24)
        self.assertEqual(normalized["sleep_score"], 90)
        self.assertEqual(normalized["sleep_duration_minutes"], 450)
        self.assertEqual(normalized["hrv_status"], "ready")
        self.assertEqual(normalized["body_battery"], 85)
        self.assertEqual(normalized["stress_score"], 25)
        self.assertEqual(normalized["raw_available"], {"stats": True, "sleep": True, "hrv": True, "body_battery": True, "training_readiness": True})

    def test_normalize_day_handles_missing_data(self):
        raw = {
            "date": "2026-07-31",
            "stats": {"ok": False, "failures": {"get_stats": "not available"}},
            "sleep": {"ok": False},
            "hrv": {"ok": False},
            "body_battery": {"ok": False},
            "training_readiness": {"ok": False},
        }
        normalized = garmin_import.normalize_day(raw)
        self.assertIsNone(normalized["sleep_score"])
        self.assertIsNone(normalized["sleep_duration_minutes"])
        self.assertIsNone(normalized["resting_heart_rate"])
        self.assertEqual(normalized["raw_available"], {"stats": False, "sleep": False, "hrv": False, "body_battery": False, "training_readiness": False})

    def test_write_json_saves_pretty_json(self):
        payload = {"a": 1, "nested": {"b": 2}}
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "output.json")
            garmin_import.write_json(garmin_import.Path(path), payload)
            with open(path, encoding="utf-8") as handle:
                content = json.load(handle)
            self.assertEqual(content, payload)


if __name__ == "__main__":
    unittest.main()
