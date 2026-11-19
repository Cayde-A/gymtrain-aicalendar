import tempfile
import unittest
from pathlib import Path

from scripts import trainingos_db, trainingos_monthly_sync_package, trainingos_supabase_sync


class TrainingOSSupabaseSyncTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "trainingos.sqlite"
        trainingos_db.init_db(self.db_path)
        with trainingos_db.connect(self.db_path) as connection:
            trainingos_db.save_imported_workout(
                connection,
                {
                    "provider": "garmin",
                    "external_activity_id": "private-id",
                    "completed_at": "2026-10-04 09:00:00",
                    "pain_notes": "private note",
                    "sets": [
                        {
                            "exercise_name": "Bench Press",
                            "set_order": 1,
                            "set_type": "working",
                            "weight_kg": 100,
                            "reps": 5,
                        }
                    ],
                },
            )

    def tearDown(self):
        self.tempdir.cleanup()

    def package(self, connection):
        package, _, _ = trainingos_monthly_sync_package.create_package(connection, "2026-10")
        return package

    def test_confirmation_gate_prevents_network_calls(self):
        calls = []

        def requester(method, url, headers, payload):
            calls.append((method, url))
            return 500, None

        with trainingos_db.connect(self.db_path) as connection:
            code, result = trainingos_supabase_sync.run_upload(
                connection,
                self.package(connection),
                "https://project.supabase.co",
                "publishable",
                "access-token",
                False,
                requester,
            )
        self.assertEqual(code, 3)
        self.assertEqual(result["status"], "needs_confirmation")
        self.assertEqual(calls, [])

    def test_missing_auth_prevents_network_calls(self):
        calls = []

        def requester(method, url, headers, payload):
            calls.append((method, url))
            return 500, None

        with trainingos_db.connect(self.db_path) as connection:
            code, result = trainingos_supabase_sync.run_upload(
                connection, self.package(connection), None, None, None, True, requester
            )
        self.assertEqual(code, 3)
        self.assertEqual(result["status"], "needs_supabase_auth")
        self.assertEqual(len(result["missing"]), 3)
        self.assertEqual(calls, [])

    def test_authenticated_upsert_requires_hash_readback(self):
        calls = []

        def requester(method, url, headers, payload):
            calls.append((method, url, headers, payload))
            if url.endswith("/auth/v1/user"):
                return 200, {"id": "00000000-0000-0000-0000-000000000001"}
            if method == "POST":
                return 201, [{"sync_month": "2026-10", "payload_sha256": payload["payload_sha256"]}]
            digest = calls[-2][3]["payload_sha256"]
            return 200, [{"sync_month": "2026-10", "payload_sha256": digest}]

        with trainingos_db.connect(self.db_path) as connection:
            package = self.package(connection)
            code, result = trainingos_supabase_sync.run_upload(
                connection,
                package,
                "https://project.supabase.co",
                "publishable",
                "access-token",
                True,
                requester,
            )
            batch = connection.execute(
                "select * from monthly_sync_batches where sync_month = '2026-10'"
            ).fetchone()
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "uploaded")
        self.assertEqual(batch["status"], "uploaded")
        self.assertIsNotNone(batch["uploaded_at"])
        self.assertEqual(calls[1][2]["Prefer"], "resolution=merge-duplicates,return=representation")
        self.assertEqual(calls[1][3]["summary"], package)
        self.assertNotIn("private", str(calls[1][3]))
        self.assertEqual(calls[0][2]["apikey"], "publishable")
        self.assertEqual(calls[0][2]["Authorization"], "Bearer access-token")

    def test_hash_mismatch_marks_batch_failed_without_remote_body(self):
        def requester(method, url, headers, payload):
            if url.endswith("/auth/v1/user"):
                return 200, {"id": "00000000-0000-0000-0000-000000000001"}
            if method == "POST":
                return 201, []
            return 200, [{"sync_month": "2026-10", "payload_sha256": "wrong"}]

        with trainingos_db.connect(self.db_path) as connection:
            code, result = trainingos_supabase_sync.run_upload(
                connection,
                self.package(connection),
                "https://project.supabase.co",
                "publishable",
                "access-token",
                True,
                requester,
            )
            batch = connection.execute(
                "select * from monthly_sync_batches where sync_month = '2026-10'"
            ).fetchone()
        self.assertEqual(code, 4)
        self.assertEqual(result["status"], "supabase_readback_failed")
        self.assertEqual(batch["status"], "failed")
        self.assertEqual(batch["error_message"], "readback_hash_mismatch")

    def test_project_url_rejects_credentials_and_paths(self):
        for value in (
            "http://project.supabase.co",
            "https://user:pass@project.supabase.co",
            "https://project.supabase.co/rest/v1",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                trainingos_supabase_sync.normalized_project_url(value)


if __name__ == "__main__":
    unittest.main()
