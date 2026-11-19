import argparse
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts import garmin_activity_import, gccli_adapter, gccli_parity, trainingos_db


class FakeAdapter:
    def auth_status(self):
        return {"authenticated": True}

    def activities(self, limit=2, activity_type=None):
        activities = [
            {
                "activityId": index,
                "activityName": f"Session {index}",
                "activityType": {"typeKey": "strength_training"},
                "startTimeLocal": f"2026-10-0{index} 08:00:00",
            }
            for index in range(1, 3)
        ]
        activities.append(
            {
                "activityId": 99,
                "activityName": "Walk",
                "activityType": {"typeKey": "walking"},
                "startTimeLocal": "2026-10-03 08:00:00",
            }
        )
        return activities

    def activity_details(self, activity_id):
        return {"duration": 1800, "calories": 200}

    def activity_sets(self, activity_id):
        return {"exerciseSets": [{"exerciseName": "LEG_PRESS", "repetitionCount": 10, "weight": 80000}]}

    def recovery_day(self, date_text):
        return {
            "date": date_text,
            "stats": {"ok": True, "data": {"restingHeartRate": 55, "totalSteps": 8000}},
            "sleep": {"ok": True, "data": {"sleepTimeSeconds": 27000, "sleepScore": 80}},
            "hrv": {"ok": True, "data": {"status": "BALANCED"}},
            "body_battery": {"ok": True, "data": {"bodyBattery": 70}},
            "training_readiness": {"ok": True, "data": {"score": 75, "recoveryTime": 36000}},
        }

    def dry_run_workout_file(self, path):
        return {"ok": True, "remote_write": False, "errors": []}

    def version(self):
        return "gccli test"


class GccliParityTestCase(unittest.TestCase):
    def test_normalized_gccli_activity_reimport_is_idempotent(self):
        adapter = FakeAdapter()
        summary = adapter.activities(limit=1)[0]
        activity_id = summary["activityId"]
        normalized = garmin_activity_import.normalize_activity(
            {
                "summary": summary,
                "details": adapter.activity_details(activity_id),
                "exercise_sets": adapter.activity_sets(activity_id),
            }
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "trainingos.sqlite"
            trainingos_db.init_db(db_path)
            with trainingos_db.connect(db_path) as connection:
                first_id = trainingos_db.save_imported_workout(connection, normalized)
                second_id = trainingos_db.save_imported_workout(connection, normalized)
                session_count = connection.execute(
                    "select count(*) from completed_sessions"
                ).fetchone()[0]
                set_count = connection.execute("select count(*) from set_logs").fetchone()[0]
        self.assertEqual(first_id, second_id)
        self.assertEqual(session_count, 1)
        self.assertEqual(set_count, 1)

    def test_run_reports_counts_without_personal_values(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            workout = root / "workout.json"
            workout.write_text("{}", encoding="utf-8")
            args = argparse.Namespace(
                account=None,
                activities=2,
                days=7,
                end_date="2026-10-07",
                workout=str(workout),
                current_recovery=str(root / "missing-recovery.json"),
                current_activities=str(root / "missing-activities.json"),
                output=str(root / "report.json"),
            )
            code, report = gccli_parity.run(args, adapter=FakeAdapter())
        self.assertEqual(code, 0)
        self.assertEqual(report["activity_quality"]["completed_sessions"], 2)
        self.assertEqual(report["activity_quality"]["missing_reps"], 0)
        self.assertEqual(report["recovery_parity"]["candidate_records"], 7)
        self.assertFalse(report["contains_personal_values"])
        self.assertFalse(report["workout_dry_run"]["remote_write"])

    def test_run_returns_auth_block_without_reading_data(self):
        class BlockedAdapter(FakeAdapter):
            def auth_status(self):
                process = subprocess.CompletedProcess(
                    [], 1, stdout="", stderr="no account specified; run gccli auth login"
                )
                raise gccli_adapter.GarminProviderError(
                    gccli_adapter._failure_from_process(process, "auth_status")
                )

        args = argparse.Namespace(
            account=None,
            activities=2,
            days=7,
            end_date="2026-10-07",
            workout="unused.json",
            current_recovery="unused.json",
            current_activities="unused.json",
            output="unused.json",
        )
        code, report = gccli_parity.run(args, adapter=BlockedAdapter())
        self.assertEqual(code, 2)
        self.assertEqual(report["error"]["code"], "authentication")


if __name__ == "__main__":
    unittest.main()
