import datetime as dt
import tempfile
import unittest
from pathlib import Path

from scripts import garmin_write_journal, trainingos_db


class GarminWriteJournalTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "trainingos.sqlite"
        garmin_write_journal.initialize(self.db_path)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_payload_hash_is_stable_across_key_order(self):
        first = garmin_write_journal.canonical_payload_hash({"b": 2, "a": 1})
        second = garmin_write_journal.canonical_payload_hash({"a": 1, "b": 2})
        self.assertEqual(first, second)

    def test_begin_operation_reuses_same_idempotency_key(self):
        with trainingos_db.connect(self.db_path) as connection:
            first = garmin_write_journal.begin_operation(
                connection, "key", "hash", "Workout", "2026-10-05"
            )
            second = garmin_write_journal.begin_operation(
                connection, "key", "hash", "Workout", "2026-10-05"
            )
            count = connection.execute("select count(*) from garmin_write_operations").fetchone()[0]
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(count, 1)

    def test_begin_operation_rejects_key_reuse_for_different_payload(self):
        with trainingos_db.connect(self.db_path) as connection:
            garmin_write_journal.begin_operation(connection, "key", "hash-a", "Workout", "2026-10-05")
            with self.assertRaises(ValueError):
                garmin_write_journal.begin_operation(connection, "key", "hash-b", "Workout", "2026-10-05")

    def test_update_operation_preserves_checkpoint_and_counts_attempts(self):
        with trainingos_db.connect(self.db_path) as connection:
            garmin_write_journal.begin_operation(connection, "key", "hash", "Workout", "2026-10-05")
            updated = garmin_write_journal.update_operation(
                connection,
                "key",
                status="pending",
                phase="uploaded",
                workout_id=123,
                increment_attempts=True,
            )
            failed = garmin_write_journal.update_operation(
                connection,
                "key",
                status="failed",
                error={"code": "provider_outage", "retryable": True},
            )
        self.assertEqual(updated["attempt_count"], 1)
        self.assertEqual(failed["phase"], "uploaded")
        self.assertEqual(failed["workout_id"], 123)

    def test_retry_time_uses_longer_cooldown_for_rate_limit(self):
        now = dt.datetime(2026, 10, 5, 0, 0, 0)
        rate_limit = garmin_write_journal.retry_time(
            {"code": "rate_limit", "retryable": True},
            now,
        )
        outage = garmin_write_journal.retry_time(
            {"code": "provider_outage", "retryable": True},
            now,
        )
        self.assertEqual(rate_limit, "2026-10-05T00:30:00")
        self.assertEqual(outage, "2026-10-05T00:05:00")


if __name__ == "__main__":
    unittest.main()
