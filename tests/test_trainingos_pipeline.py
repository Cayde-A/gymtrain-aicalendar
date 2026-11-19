import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts import (
    gunyama_exercise_catalog,
    trainingos_db,
    trainingos_pipeline,
    trainingos_program_cycle,
)


class FakeRunner:
    def __init__(self, returncodes=None):
        self.returncodes = list(returncodes or [])
        self.commands = []

    def __call__(self, command):
        self.commands.append(command)
        returncode = self.returncodes.pop(0) if self.returncodes else 0
        return subprocess.CompletedProcess(command, returncode, stdout="", stderr="")


class TrainingOSPipelineTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.db_path = self.root / "trainingos.sqlite"
        self.output_dir = self.root / "pipeline"
        trainingos_db.init_db(self.db_path)

    def tearDown(self):
        self.tempdir.cleanup()

    def save_chest_session(self, reps=8, weight=80):
        with trainingos_db.connect(self.db_path) as connection:
            trainingos_db.save_imported_workout(
                connection,
                {
                    "provider": "garmin",
                    "external_activity_id": "pipeline-chest",
                    "completed_at": "2026-10-04 09:00:00",
                    "session_type": "strength_training",
                    "activity_name": "Chest",
                    "sets": [
                        {
                            "exercise_name": "Bench Press",
                            "set_order": 1,
                            "set_type": "working",
                            "weight_kg": weight,
                            "reps": reps,
                        }
                    ],
                },
            )

    def save_recovery(self, readiness=75, body_battery=70, sleep_score=82):
        with trainingos_db.connect(self.db_path) as connection:
            trainingos_db.upsert_daily_recovery_metric(
                connection,
                {
                    "metric_date": "2026-10-05",
                    "provider": "garmin",
                    "training_readiness": readiness,
                    "body_battery": body_battery,
                    "sleep_score": sleep_score,
                },
            )

    def ai_response(self, primary="legs", interstitial="none", data_quality_issues=None):
        path = self.root / f"ai-{primary}-{interstitial}.json"
        path.write_text(
            json.dumps(
                {
                    "analysis_summary": "Reviewed.",
                    "performance_direction": "keep",
                    "risk_flags": [],
                    "data_quality_issues": data_quality_issues or [],
                    "initial_next_day_plan": {
                        "status": "initial_draft",
                        "session_type": primary,
                        "primary_large_muscle_group": primary,
                        "interstitial_core": interstitial,
                        "avoided_overlap": ["chest", "shoulders"],
                        "rounds": [],
                    },
                    "next_morning_adjustment_rules": ["use recovery data"],
                }
            ),
            encoding="utf-8",
        )
        return path

    def options(self, **overrides):
        values = {
            "training_date": "2026-10-04",
            "target_date": "2026-10-05",
            "db_path": self.db_path,
            "output_dir": self.output_dir,
            "confirm_candidate_equipment": True,
        }
        values.update(overrides)
        return trainingos_pipeline.PipelineOptions(**values)

    def test_pipeline_waits_for_first_completed_training_anchor(self):
        exit_code, report = trainingos_pipeline.run_pipeline(self.options(), FakeRunner())
        self.assertEqual(exit_code, 3)
        self.assertEqual(report["status"], "waiting_for_first_training")
        self.assertFalse(report["training_anchor"]["ready"])
        self.assertIsNone(report["quality"])

    def test_pipeline_waits_when_imported_activity_has_no_active_sets(self):
        with trainingos_db.connect(self.db_path) as connection:
            trainingos_db.save_imported_workout(
                connection,
                {
                    "provider": "garmin",
                    "external_activity_id": "empty-first-activity",
                    "completed_at": "2026-10-04 09:00:00",
                    "session_type": "strength_training",
                    "sets": [],
                },
            )
        exit_code, report = trainingos_pipeline.run_pipeline(self.options(), FakeRunner())
        self.assertEqual(exit_code, 3)
        self.assertEqual(report["status"], "first_training_needs_data")
        self.assertIsNone(report["quality"])

    def test_pipeline_exports_review_packet_when_review_is_missing(self):
        self.save_chest_session()
        self.save_recovery()
        exit_code, report = trainingos_pipeline.run_pipeline(self.options(), FakeRunner())
        self.assertEqual(exit_code, 3)
        self.assertEqual(report["status"], "needs_ai_review")
        self.assertTrue(Path(report["review"]["packet_path"]).exists())

    def test_pipeline_builds_final_plan_and_dry_runs_garmin_payload(self):
        self.save_chest_session()
        self.save_recovery()
        runner = FakeRunner()
        options = self.options(ai_response_path=self.ai_response(), dry_run_push=True)
        exit_code, report = trainingos_pipeline.run_pipeline(options, runner)
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], "dry_run_complete")
        self.assertEqual(report["plan"]["preset"], "legs_after_push")
        self.assertEqual(report["plan"]["recovery_adjustment"], "keep")
        self.assertIn("--dry-run", runner.commands[0])
        self.assertIn("--idempotency-key", runner.commands[0])
        self.assertIn(str(self.db_path), runner.commands[0])
        self.assertTrue(Path(report["plan"]["payload_path"]).exists())

    def test_pipeline_reduces_volume_when_recovery_is_moderate(self):
        self.save_chest_session()
        self.save_recovery(readiness=45)
        exit_code, report = trainingos_pipeline.run_pipeline(
            self.options(ai_response_path=self.ai_response()),
            FakeRunner(),
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], "final_plan_ready")
        self.assertEqual(report["plan"]["recovery_adjustment"], "reduce_volume")
        self.assertEqual(report["plan"]["rounds"][0]["sets"], 3)

    def test_pipeline_applies_scheduled_deload_week(self):
        self.save_chest_session()
        self.save_recovery()
        with trainingos_db.connect(self.db_path) as connection:
            trainingos_program_cycle.create_cycle(connection, "2026-09-14")
        exit_code, report = trainingos_pipeline.run_pipeline(
            self.options(ai_response_path=self.ai_response()),
            FakeRunner(),
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["plan"]["program_cycle"]["week"], 4)
        self.assertEqual(report["plan"]["program_cycle"]["phase"], "deload")
        self.assertEqual(report["plan"]["rounds"][0]["sets"], 2)
        self.assertEqual(report["plan"]["primary_exercise_progression"]["action"], "deload")

    def test_pipeline_requires_confirmation_for_candidate_venue_equipment(self):
        self.save_chest_session()
        self.save_recovery()
        exit_code, report = trainingos_pipeline.run_pipeline(
            self.options(
                ai_response_path=self.ai_response(),
                confirm_candidate_equipment=False,
            ),
            FakeRunner(),
        )
        self.assertEqual(exit_code, 3)
        self.assertEqual(report["status"], "needs_venue_confirmation")
        self.assertEqual(report["error"]["code"], "venue_equipment_confirmation_required")
        self.assertIn("Leg Press", report["error"]["exercises"])
        self.assertEqual(report["error"]["suggested_substitutions"]["Leg Press"], ["Goblet Squat"])

    def test_pipeline_blocks_exercise_marked_unavailable_at_venue(self):
        self.save_chest_session()
        self.save_recovery()
        with trainingos_db.connect(self.db_path) as connection:
            gunyama_exercise_catalog.seed_catalog(connection)
            gunyama_exercise_catalog.set_availability(connection, "Leg Press", "unavailable")
        exit_code, report = trainingos_pipeline.run_pipeline(
            self.options(ai_response_path=self.ai_response()),
            FakeRunner(),
        )
        self.assertEqual(exit_code, 2)
        self.assertEqual(report["status"], "plan_blocked")
        self.assertIn("marked unavailable", report["error"]["message"])
        self.assertIn("Leg Press", report["error"]["message"])

    def test_pipeline_blocks_back_plan_after_chest(self):
        self.save_chest_session()
        self.save_recovery()
        exit_code, report = trainingos_pipeline.run_pipeline(
            self.options(ai_response_path=self.ai_response(primary="back")),
            FakeRunner(),
        )
        self.assertEqual(exit_code, 2)
        self.assertEqual(report["status"], "plan_blocked")
        self.assertIn("after_chest_or_shoulders", report["error"]["message"])

    def test_pipeline_blocks_when_ai_reports_data_quality_issues(self):
        self.save_chest_session()
        self.save_recovery()
        response = self.ai_response(data_quality_issues=["exercise mapping uncertain"])
        exit_code, report = trainingos_pipeline.run_pipeline(
            self.options(ai_response_path=response),
            FakeRunner(),
        )
        self.assertEqual(exit_code, 2)
        self.assertEqual(report["status"], "review_quality_blocked")
        self.assertEqual(report["error"]["code"], "ai_review_data_quality_issues")

    def test_live_push_requires_trigger_confirmation(self):
        self.save_chest_session()
        self.save_recovery()
        response_path = self.ai_response()
        blocked_runner = FakeRunner()
        blocked_code, blocked = trainingos_pipeline.run_pipeline(
            self.options(ai_response_path=response_path, push=True),
            blocked_runner,
        )
        self.assertEqual(blocked_code, 3)
        self.assertEqual(blocked["status"], "needs_push_confirmation")
        self.assertEqual(blocked_runner.commands, [])

        allowed_runner = FakeRunner()
        allowed_code, allowed = trainingos_pipeline.run_pipeline(
            self.options(ai_response_path=response_path, push=True, confirm_push=True),
            allowed_runner,
        )
        self.assertEqual(allowed_code, 0)
        self.assertEqual(allowed["status"], "pushed")
        self.assertNotIn("--dry-run", allowed_runner.commands[0])

    def test_repeated_run_reuses_review_and_pipeline_record(self):
        self.save_chest_session()
        self.save_recovery()
        options = self.options(ai_response_path=self.ai_response())
        trainingos_pipeline.run_pipeline(options, FakeRunner())
        trainingos_pipeline.run_pipeline(options, FakeRunner())
        with trainingos_db.connect(self.db_path) as connection:
            review_count = connection.execute("select count(*) from ai_reviews").fetchone()[0]
            pipeline_count = connection.execute("select count(*) from pipeline_runs").fetchone()[0]
        self.assertEqual(review_count, 1)
        self.assertEqual(pipeline_count, 1)

    def test_sync_failure_stops_before_quality_and_records_retryable_error(self):
        runner = FakeRunner([4])
        exit_code, report = trainingos_pipeline.run_pipeline(
            self.options(sync_garmin=True),
            runner,
        )
        self.assertEqual(exit_code, 4)
        self.assertEqual(report["status"], "sync_failed")
        self.assertTrue(report["error"]["retryable"])
        self.assertEqual(len(runner.commands), 1)

    def test_sync_expands_history_once_when_local_anchor_is_missing(self):
        commands = []

        def runner(command):
            commands.append(command)
            if "--days" in command and command[command.index("--days") + 1] == "180":
                self.save_chest_session()
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        exit_code, report = trainingos_pipeline.run_pipeline(
            self.options(sync_garmin=True),
            runner,
        )
        self.assertEqual(exit_code, 3)
        self.assertEqual(report["status"], "needs_ai_review")
        self.assertEqual(len(commands), 3)
        self.assertEqual(report["sync"][-1]["phase"], "anchor_lookup")
        self.assertEqual(report["sync"][-1]["lookback_days"], 180)
        self.assertTrue(report["training_anchor"]["ready"])


if __name__ == "__main__":
    unittest.main()
