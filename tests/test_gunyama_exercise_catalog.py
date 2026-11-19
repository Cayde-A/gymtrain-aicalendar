import tempfile
import unittest
from pathlib import Path

from scripts import gunyama_exercise_catalog, trainingos_db


class GunyamaExerciseCatalogTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "trainingos.sqlite"
        trainingos_db.init_db(self.db)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_all_mappings_exist_in_installed_garmin_catalog(self):
        self.assertEqual(gunyama_exercise_catalog.validate_catalog(), [])

    def test_seed_is_idempotent_and_specific_equipment_stays_candidate(self):
        with trainingos_db.connect(self.db) as connection:
            first = gunyama_exercise_catalog.seed_catalog(connection)
            second = gunyama_exercise_catalog.seed_catalog(connection)
            count = connection.execute(
                "select count(*) from exercise_catalog where location like 'Gunyama%'"
            ).fetchone()[0]
            statuses = {
                row[0]
                for row in connection.execute(
                    "select distinct venue_availability_status from exercise_catalog where location like 'Gunyama%'"
                )
            }
        self.assertEqual(first, len(gunyama_exercise_catalog.CATALOG))
        self.assertEqual(second, len(gunyama_exercise_catalog.CATALOG))
        self.assertEqual(count, len(gunyama_exercise_catalog.CATALOG))
        self.assertEqual(statuses, {"candidate"})

    def test_user_can_confirm_one_exercise_without_changing_others(self):
        with trainingos_db.connect(self.db) as connection:
            gunyama_exercise_catalog.seed_catalog(connection)
            changed = gunyama_exercise_catalog.set_availability(
                connection, "Leg Press", "user_verified", "2026-10-04"
            )
            leg_press = connection.execute(
                "select venue_availability_status, verification_level, last_verified_on from exercise_catalog where name = 'Leg Press'"
            ).fetchone()
            candidate_count = connection.execute(
                "select count(*) from exercise_catalog where venue_availability_status = 'candidate'"
            ).fetchone()[0]
        self.assertTrue(changed)
        self.assertEqual(tuple(leg_press), ("user_verified", "user_verified", "2026-10-04"))
        self.assertEqual(candidate_count, len(gunyama_exercise_catalog.CATALOG) - 1)

    def test_init_db_migrates_legacy_exercise_catalog(self):
        legacy_db = Path(self.tempdir.name) / "legacy.sqlite"
        with trainingos_db.connect(legacy_db) as connection:
            connection.execute(
                "create table exercise_catalog (id text primary key, name text not null, category text not null)"
            )
        trainingos_db.init_db(legacy_db)
        with trainingos_db.connect(legacy_db) as connection:
            columns = {
                row["name"] for row in connection.execute("pragma table_info(exercise_catalog)")
            }
        self.assertIn("garmin_category", columns)
        self.assertIn("venue_availability_status", columns)


if __name__ == "__main__":
    unittest.main()
