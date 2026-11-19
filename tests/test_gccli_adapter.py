import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import garmin_provider, gccli_adapter


class FakeRunner:
    def __init__(self, responses):
        self.responses = list(responses)
        self.commands = []

    def __call__(self, command):
        self.commands.append(command)
        return self.responses.pop(0)


def completed(stdout="{}", stderr="", returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)


class GccliAdapterTestCase(unittest.TestCase):
    def adapter(self, responses, account=None):
        runner = FakeRunner(responses)
        adapter = gccli_adapter.GccliAdapter(account=account, runner=runner)
        return adapter, runner

    def test_activities_uses_json_and_limit(self):
        adapter, runner = self.adapter([completed('[{"activityId": 42}]')])
        with mock.patch.object(adapter, "installed", return_value=True):
            result = adapter.activities(2)
        self.assertEqual(result[0]["activityId"], 42)
        self.assertEqual(
            runner.commands[0],
            ["gccli", "--json", "activities", "list", "--limit", "2"],
        )

    def test_activities_can_filter_strength(self):
        adapter, runner = self.adapter([completed("[]")])
        with mock.patch.object(adapter, "installed", return_value=True):
            adapter.activities(2, activity_type="strength_training")
        self.assertEqual(runner.commands[0][-2:], ["--type", "strength_training"])

    def test_account_is_passed_as_global_flag(self):
        adapter, runner = self.adapter([completed("[]")], account="tester@example.com")
        with mock.patch.object(adapter, "installed", return_value=True):
            adapter.activities()
        self.assertEqual(runner.commands[0][1:4], ["--json", "--account", "tester@example.com"])

    def test_authentication_failure_is_structured(self):
        adapter, _ = self.adapter(
            [completed(stderr="no account specified; run gccli auth login", returncode=1)]
        )
        with mock.patch.object(adapter, "installed", return_value=True):
            with self.assertRaises(garmin_provider.GarminProviderError) as raised:
                adapter.auth_status()
        self.assertEqual(raised.exception.failure.code, garmin_provider.ErrorCode.AUTHENTICATION)
        self.assertFalse(raised.exception.failure.retryable)

    def test_invalid_json_is_schema_failure(self):
        adapter, _ = self.adapter([completed("not-json")])
        with mock.patch.object(adapter, "installed", return_value=True):
            with self.assertRaises(garmin_provider.GarminProviderError) as raised:
                adapter.activities()
        self.assertEqual(raised.exception.failure.code, garmin_provider.ErrorCode.SCHEMA)

    def test_recovery_day_preserves_current_import_envelope(self):
        adapter, runner = self.adapter(
            [completed(json.dumps({"value": index})) for index in range(5)]
        )
        with mock.patch.object(adapter, "installed", return_value=True):
            result = adapter.recovery_day("2026-10-04")
        self.assertEqual(result["date"], "2026-10-04")
        self.assertEqual(result["stats"]["data"]["value"], 0)
        self.assertEqual(result["training_readiness"]["data"]["value"], 4)
        self.assertEqual(len(runner.commands), 5)
        self.assertEqual(
            runner.commands[-1],
            ["gccli", "--json", "health", "training-readiness", "2026-10-04"],
        )

    def test_exercise_catalog_category_command(self):
        adapter, runner = self.adapter([completed("[]")])
        with mock.patch.object(adapter, "installed", return_value=True):
            adapter.exercise_catalog("BENCH_PRESS")
        self.assertEqual(
            runner.commands[0],
            ["gccli", "--json", "exercises", "list", "--category", "BENCH_PRESS"],
        )

    def test_dry_run_validates_without_calling_runner(self):
        payload = {
            "workoutName": "TrainingOS test",
            "sportType": {"sportTypeKey": "strength_training"},
            "workoutSegments": [
                {"workoutSteps": [{"type": "ExecutableStepDTO", "stepOrder": 1}]}
            ],
        }
        adapter, runner = self.adapter([])
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "workout.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = adapter.dry_run_workout_file(path)
        self.assertTrue(result["ok"])
        self.assertFalse(result["remote_write"])
        self.assertEqual(runner.commands, [])
        self.assertEqual(result["proposed_command"][:3], ["gccli", "--json", "workouts"])

    def test_dry_run_rejects_incomplete_payload(self):
        result = gccli_adapter.validate_workout_payload({"workoutName": ""})
        self.assertFalse(result["ok"])
        self.assertGreaterEqual(len(result["errors"]), 3)


if __name__ == "__main__":
    unittest.main()
