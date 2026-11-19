import tempfile
import unittest
from pathlib import Path

from scripts import trainingos_db, trainingos_program_cycle


class TrainingOSProgramCycleTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "trainingos.sqlite"
        trainingos_db.init_db(self.db_path)

    def tearDown(self):
        self.tempdir.cleanup()

    def save_set(self, activity_id, completed_at, weight, rpe=8):
        with trainingos_db.connect(self.db_path) as connection:
            trainingos_db.save_imported_workout(
                connection,
                {
                    "provider": "garmin",
                    "external_activity_id": activity_id,
                    "completed_at": completed_at,
                    "session_type": "strength_training",
                    "sets": [
                        {
                            "exercise_name": "Bench Press",
                            "set_order": 1,
                            "set_type": "working",
                            "weight_kg": weight,
                            "reps": 5,
                            "rpe": rpe,
                        }
                    ],
                },
            )

    def test_cycle_creation_is_idempotent_and_has_eight_weeks(self):
        with trainingos_db.connect(self.db_path) as connection:
            first = trainingos_program_cycle.create_cycle(connection, "2026-10-05", "Build strength")
            second = trainingos_program_cycle.create_cycle(connection, "2026-10-05", "Build strength")
            block_count = connection.execute("select count(*) from training_blocks").fetchone()[0]
            week_count = connection.execute("select count(*) from workout_templates").fetchone()[0]
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(block_count, 1)
        self.assertEqual(week_count, 8)

    def test_cycle_context_selects_scheduled_deload_week(self):
        with trainingos_db.connect(self.db_path) as connection:
            trainingos_program_cycle.create_cycle(connection, "2026-10-05")
            context = trainingos_program_cycle.cycle_context(connection, "2026-10-26")
        self.assertEqual(context["week"], 4)
        self.assertEqual(context["phase"], "deload")
        self.assertFalse(context["pr_allowed"])
        self.assertEqual(context["volume_multiplier"], 0.55)

    def test_latest_pr_with_acceptable_rpe_increases_small(self):
        self.save_set("cycle-pr", "2026-10-05 09:00:00", 100, rpe=8)
        with trainingos_db.connect(self.db_path) as connection:
            cycle = trainingos_program_cycle.cycle_context(connection, "2026-10-06")
            decision = trainingos_program_cycle.progression_decision(
                connection, "Bench Press", "2026-10-06", cycle, "keep"
            )
        self.assertEqual(decision["action"], "increase_small")
        self.assertEqual(decision["load_change_percent"], 2.5)

    def test_two_consecutive_declines_reduce_five_percent(self):
        self.save_set("decline-1", "2026-10-01 09:00:00", 100)
        self.save_set("decline-2", "2026-10-08 09:00:00", 95)
        self.save_set("decline-3", "2026-10-15 09:00:00", 90)
        with trainingos_db.connect(self.db_path) as connection:
            cycle = trainingos_program_cycle.cycle_context(connection, "2026-10-16")
            decision = trainingos_program_cycle.progression_decision(
                connection, "Bench Press", "2026-10-16", cycle, "keep"
            )
        self.assertEqual(decision["action"], "reduce_5_percent")
        self.assertEqual(decision["reason"], "two_consecutive_declines")

    def test_recovery_reduction_takes_precedence_over_progression(self):
        self.save_set("cycle-recovery", "2026-10-05 09:00:00", 100, rpe=7)
        with trainingos_db.connect(self.db_path) as connection:
            cycle = trainingos_program_cycle.cycle_context(connection, "2026-10-06")
            decision = trainingos_program_cycle.progression_decision(
                connection, "Bench Press", "2026-10-06", cycle, "reduce_volume"
            )
        self.assertEqual(decision["action"], "keep")
        self.assertEqual(decision["reason"], "moderate_recovery_reduce_volume_first")


if __name__ == "__main__":
    unittest.main()
