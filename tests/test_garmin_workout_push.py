import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import garmin_provider
from scripts import garmin_workout_push
from scripts import garmin_write_journal
from scripts import trainingos_db
from scripts import trainingos_garmin_payload


class FakeGarminClient:
    def __init__(self, workout_id=123, scheduled=False, fail_push=False, confirm_schedule=True):
        self.workout_id = workout_id
        self.scheduled = scheduled
        self.fail_push = fail_push
        self.confirm_schedule = confirm_schedule
        self.calls = []

    def get_workouts(self, start, limit):
        self.calls.append("get_workouts")
        return []

    def upload_strength_workout(self, workout):
        self.calls.append("upload")
        return {"workoutId": self.workout_id}

    def upload_workout(self, payload):
        self.calls.append("upload")
        return {"workoutId": self.workout_id}

    def schedule_workout(self, workout_id, schedule_date):
        self.calls.append("schedule")
        self.scheduled = True
        return {"workoutId": workout_id, "date": schedule_date}

    def get_scheduled_workouts(self, year, month):
        self.calls.append("get_scheduled")
        if not self.scheduled or not self.confirm_schedule:
            return {"items": []}
        return {
            "items": [
                {
                    "workoutScheduleId": 456,
                    "calendarDate": "2026-10-05",
                    "workout": {"workoutId": self.workout_id, "workoutName": "TrainingOS Test"},
                }
            ]
        }

    def unschedule_workout(self, schedule_id):
        self.calls.append("unschedule")
        self.scheduled = False
        return {"removed": schedule_id}

    def push_workout_to_device(self, workout_id):
        self.calls.append("push")
        if self.fail_push:
            raise TimeoutError("push timed out")
        return {"requested": workout_id}


class GarminWorkoutPushTestCase(unittest.TestCase):
    def payload(self):
        return trainingos_garmin_payload.build_strength_workout_payload(
            "TrainingOS Test",
            trainingos_garmin_payload.LEG_PRIORITY_AFTER_PUSH_PRESET,
        )

    def initialized_operation(self, db_path, key="write-key", phase="created", workout_id=None):
        garmin_write_journal.initialize(db_path)
        payload = self.payload()
        payload_hash = garmin_write_journal.canonical_payload_hash(payload)
        with trainingos_db.connect(db_path) as connection:
            garmin_write_journal.begin_operation(
                connection,
                key,
                payload_hash,
                payload["workoutName"],
                "2026-10-05",
            )
            if phase != "created":
                garmin_write_journal.update_operation(
                    connection,
                    key,
                    phase=phase,
                    workout_id=workout_id,
                )
        return payload

    def test_deep_find_workout_id_prefers_direct_id(self):
        payload = {"workoutId": 12345, "nested": {"id": 999}}
        self.assertEqual(garmin_workout_push.deep_find_workout_id(payload), 12345)

    def test_deep_find_workout_id_finds_nested_string_id(self):
        payload = {"data": [{"workout": {"workout_id": "67890"}}]}
        self.assertEqual(garmin_workout_push.deep_find_workout_id(payload), 67890)

    def test_find_scheduled_workouts_matches_same_date_and_name(self):
        scheduled = {
            "items": [
                {
                    "workoutScheduleId": 111,
                    "calendarDate": "2026-09-01",
                    "workout": {"workoutName": "TrainingOS Chest 2026-09-01"},
                },
                {
                    "id": 222,
                    "date": "2026-09-01",
                    "title": "TrainingOS Chest 2026-09-01",
                },
            ]
        }
        matches = garmin_workout_push.find_scheduled_workouts(
            scheduled,
            "2026-09-01",
            "TrainingOS Chest 2026-09-01",
        )
        self.assertEqual(
            matches,
            [
                {"workoutScheduleId": 111, "calendarDate": "2026-09-01", "workoutName": "TrainingOS Chest 2026-09-01"},
                {"workoutScheduleId": 222, "calendarDate": "2026-09-01", "workoutName": "TrainingOS Chest 2026-09-01"},
            ],
        )

    def test_build_strength_workout_payload_has_repeat_blocks(self):
        payload = trainingos_garmin_payload.build_strength_workout_payload(
            "TrainingOS Test",
            trainingos_garmin_payload.LEG_PRIORITY_AFTER_PUSH_PRESET,
        )
        steps = payload["workoutSegments"][0]["workoutSteps"]
        first_exercise = steps[0]["workoutSteps"][0]
        self.assertEqual(payload["sportType"]["sportTypeKey"], "strength_training")
        self.assertEqual(steps[0]["numberOfIterations"], 4)
        self.assertEqual(first_exercise["category"], "SQUAT")
        self.assertEqual(first_exercise["exerciseName"], "LEG_PRESS")
        self.assertIn("knees track toes", first_exercise["description"])

    def test_push_chest_conservative_preset_uses_chest_as_primary(self):
        payload = trainingos_garmin_payload.build_strength_workout_payload(
            "TrainingOS Chest Test",
            trainingos_garmin_payload.PUSH_CHEST_CONSERVATIVE_PRESET,
        )
        steps = payload["workoutSegments"][0]["workoutSteps"]
        categories = [step["workoutSteps"][0]["category"] for step in steps]
        self.assertEqual(categories[:3], ["BENCH_PRESS", "BENCH_PRESS", "FLYE"])
        self.assertEqual(categories[-1], "TRICEPS_EXTENSION")

    def test_pull_back_conservative_preset_uses_verified_garmin_exercises(self):
        from garminconnect.exercises import EXERCISES

        catalog_pairs = {(item["category"], item["exercise"]) for item in EXERCISES}
        payload = trainingos_garmin_payload.build_strength_workout_payload(
            "TrainingOS Pull Test",
            trainingos_garmin_payload.PULL_BACK_CONSERVATIVE_PRESET,
        )
        exercise_steps = [
            step["workoutSteps"][0]
            for step in payload["workoutSegments"][0]["workoutSteps"]
        ]
        self.assertEqual(exercise_steps[0]["exerciseName"], "LAT_PULLDOWN")
        for step in exercise_steps:
            self.assertIn((step["category"], step["exerciseName"]), catalog_pairs)

    def test_core_between_push_legs_preset_avoids_grip_and_hanging_work(self):
        payload = trainingos_garmin_payload.build_strength_workout_payload(
            "TrainingOS Core A Test",
            trainingos_garmin_payload.CORE_BETWEEN_PUSH_LEGS_PRESET,
        )
        exercises = [
            step["workoutSteps"][0]["exerciseName"]
            for step in payload["workoutSegments"][0]["workoutSteps"]
        ]
        self.assertIn("KNEELING_CABLE_CRUNCH", exercises)
        self.assertIn("WEIGHTED_DEAD_BUG", exercises)
        self.assertNotIn("HANGING_LEG_RAISE", exercises)

    def test_movement_cue_uses_custom_cue_and_limits_length(self):
        block = {
            "category": "BENCH_PRESS",
            "exerciseName": "BENCH_PRESS",
            "cue": "x" * 200,
        }
        cue = trainingos_garmin_payload.movement_cue(block)
        self.assertLessEqual(len(cue), trainingos_garmin_payload.CUE_MAX_LENGTH)
        self.assertTrue(cue.endswith("..."))

    def test_all_presets_include_step_descriptions(self):
        for preset in trainingos_garmin_payload.PRESETS.values():
            payload = trainingos_garmin_payload.build_strength_workout_payload(
                "TrainingOS Cue Test",
                preset["blocks"],
            )
            for step in payload["workoutSegments"][0]["workoutSteps"]:
                description = step["workoutSteps"][0].get("description")
                self.assertTrue(description)
                self.assertLessEqual(len(description), trainingos_garmin_payload.CUE_MAX_LENGTH)

    def test_main_writes_structured_failure_when_login_is_rate_limited(self):
        failure = garmin_provider.ProviderFailure(
            code=garmin_provider.ErrorCode.RATE_LIMIT,
            message="Too Many Requests",
            retryable=True,
            operation="login",
            status_code=429,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            payload_path = Path(tmpdir) / "workout.json"
            payload_path.write_text(
                json.dumps(
                    {
                        "workoutName": "TrainingOS Test",
                        "workoutSegments": [{"segmentOrder": 1, "workoutSteps": []}],
                    }
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(
                payload=str(payload_path),
                date="2026-10-05",
                name=None,
                email=None,
                password=None,
                tokenstore=str(Path(tmpdir) / "tokens"),
                skip_push=False,
                dry_run=False,
                replace_existing=False,
                db=str(Path(tmpdir) / "trainingos.sqlite"),
                idempotency_key="rate-limit-test",
                max_read_attempts=1,
                retry_base_seconds=0,
                result_dir=tmpdir,
                retry_ambiguous_push=False,
            )
            with (
                mock.patch.object(garmin_workout_push, "parse_args", return_value=args),
                mock.patch.object(
                    garmin_workout_push,
                    "login",
                    side_effect=garmin_provider.GarminProviderError(failure),
                ),
                mock.patch.object(garmin_workout_push, "RESULT_DIR", Path(tmpdir)),
            ):
                result = garmin_workout_push.main()

            self.assertEqual(result, 2)
            saved = json.loads(
                (Path(tmpdir) / "garmin_push_result_2026-10-05.json").read_text(encoding="utf-8")
            )
            self.assertEqual(saved["status"], "failed")
            self.assertEqual(saved["error"]["code"], "rate_limit")
            self.assertTrue(saved["error"]["retryable"])

    def test_perform_write_persists_all_checkpoints_and_confirms_schedule(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "trainingos.sqlite"
            payload = self.initialized_operation(db_path)
            client = FakeGarminClient()
            with trainingos_db.connect(db_path) as connection:
                result = garmin_workout_push.perform_garmin_write(
                    connection,
                    client,
                    payload,
                    "2026-10-05",
                    "write-key",
                    replace_existing=False,
                    skip_push=False,
                    retry_ambiguous_push=False,
                    max_read_attempts=1,
                    retry_base_seconds=0,
                )
                operation = garmin_write_journal.get_operation(connection, "write-key")
        self.assertEqual(result["status"], "confirmed")
        self.assertTrue(result["push_requested"])
        self.assertEqual(operation["status"], "confirmed")
        self.assertEqual(operation["phase"], "push_requested")
        self.assertEqual(operation["workout_id"], 123)
        self.assertEqual(operation["workout_schedule_id"], 456)

    def test_confirmed_operation_is_idempotent_on_repeat(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "trainingos.sqlite"
            payload = self.initialized_operation(db_path)
            first_client = FakeGarminClient()
            with trainingos_db.connect(db_path) as connection:
                garmin_workout_push.perform_garmin_write(
                    connection,
                    first_client,
                    payload,
                    "2026-10-05",
                    "write-key",
                    replace_existing=False,
                    skip_push=False,
                    retry_ambiguous_push=False,
                    max_read_attempts=1,
                    retry_base_seconds=0,
                )
            repeat_client = FakeGarminClient(scheduled=True)
            with trainingos_db.connect(db_path) as connection:
                result = garmin_workout_push.perform_garmin_write(
                    connection,
                    repeat_client,
                    payload,
                    "2026-10-05",
                    "write-key",
                    replace_existing=False,
                    skip_push=False,
                    retry_ambiguous_push=False,
                    max_read_attempts=1,
                    retry_base_seconds=0,
                )
        self.assertEqual(result["status"], "idempotent")
        self.assertNotIn("upload", repeat_client.calls)
        self.assertNotIn("schedule", repeat_client.calls)
        self.assertNotIn("push", repeat_client.calls)

    def test_uploaded_checkpoint_resumes_without_second_upload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "trainingos.sqlite"
            payload = self.initialized_operation(db_path, phase="uploaded", workout_id=123)
            client = FakeGarminClient()
            with trainingos_db.connect(db_path) as connection:
                result = garmin_workout_push.perform_garmin_write(
                    connection,
                    client,
                    payload,
                    "2026-10-05",
                    "write-key",
                    replace_existing=False,
                    skip_push=True,
                    retry_ambiguous_push=False,
                    max_read_attempts=1,
                    retry_base_seconds=0,
                )
        self.assertEqual(result["status"], "confirmed")
        self.assertNotIn("upload", client.calls)
        self.assertIn("schedule", client.calls)

    def test_schedule_must_be_confirmed_by_remote_read(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "trainingos.sqlite"
            payload = self.initialized_operation(db_path)
            client = FakeGarminClient(confirm_schedule=False)
            with trainingos_db.connect(db_path) as connection:
                with self.assertRaises(garmin_provider.GarminProviderError) as raised:
                    garmin_workout_push.perform_garmin_write(
                        connection,
                        client,
                        payload,
                        "2026-10-05",
                        "write-key",
                        replace_existing=False,
                        skip_push=True,
                        retry_ambiguous_push=False,
                        max_read_attempts=1,
                        retry_base_seconds=0,
                    )
        self.assertEqual(raised.exception.failure.code, garmin_provider.ErrorCode.CONFIRMATION_FAILED)

    def test_ambiguous_device_push_requires_explicit_retry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "trainingos.sqlite"
            payload = self.initialized_operation(db_path)
            failing_client = FakeGarminClient(fail_push=True)
            with trainingos_db.connect(db_path) as connection:
                with self.assertRaises(garmin_provider.GarminProviderError):
                    garmin_workout_push.perform_garmin_write(
                        connection,
                        failing_client,
                        payload,
                        "2026-10-05",
                        "write-key",
                        replace_existing=False,
                        skip_push=False,
                        retry_ambiguous_push=False,
                        max_read_attempts=1,
                        retry_base_seconds=0,
                    )
                operation = garmin_write_journal.get_operation(connection, "write-key")
            self.assertEqual(operation["phase"], "push_unknown")

            retry_client = FakeGarminClient(scheduled=True)
            with trainingos_db.connect(db_path) as connection:
                with self.assertRaises(garmin_provider.GarminProviderError) as raised:
                    garmin_workout_push.perform_garmin_write(
                        connection,
                        retry_client,
                        payload,
                        "2026-10-05",
                        "write-key",
                        replace_existing=False,
                        skip_push=False,
                        retry_ambiguous_push=False,
                        max_read_attempts=1,
                        retry_base_seconds=0,
                    )
            self.assertEqual(raised.exception.failure.code, garmin_provider.ErrorCode.AMBIGUOUS_WRITE)
            self.assertNotIn("push", retry_client.calls)

            confirmed_retry_client = FakeGarminClient(scheduled=True)
            with trainingos_db.connect(db_path) as connection:
                result = garmin_workout_push.perform_garmin_write(
                    connection,
                    confirmed_retry_client,
                    payload,
                    "2026-10-05",
                    "write-key",
                    replace_existing=False,
                    skip_push=False,
                    retry_ambiguous_push=True,
                    max_read_attempts=1,
                    retry_base_seconds=0,
                )
        self.assertEqual(result["status"], "confirmed")
        self.assertIn("push", confirmed_retry_client.calls)


if __name__ == "__main__":
    unittest.main()
