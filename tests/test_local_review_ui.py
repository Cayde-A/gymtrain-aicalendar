import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from scripts import local_review_ui, trainingos_db


class LocalReviewUiBodyMetricsTestCase(unittest.TestCase):
    def test_dashboard_exposes_manual_garmin_sync_button(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            app = local_review_ui.ReviewServer(Path(tmpdir) / "trainingos.sqlite")
            rendered = app.dashboard_page()

        self.assertIn('action="/garmin/sync"', rendered)
        self.assertIn("立即读取 Garmin", rendered)

    def test_manual_garmin_sync_updates_dashboard(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "trainingos.sqlite"
            app = local_review_ui.ReviewServer(db_path)
            commands = []

            def runner(command, **kwargs):
                commands.append(command)
                with trainingos_db.connect(db_path) as connection:
                    trainingos_db.upsert_daily_recovery_metric(
                        connection,
                        {
                            "metric_date": "2026-11-19",
                            "provider": "garmin",
                            "sleep_duration_minutes": 420,
                            "hrv_status": "BALANCED",
                            "body_battery": 55,
                        },
                    )
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            rendered = app.sync_garmin_today(runner=runner, today="2026-11-19")

        self.assertIn("Garmin 今日状态同步成功", rendered)
        self.assertIn("7 小时 0 分", rendered)
        self.assertIn(">55<", rendered)
        self.assertIn("--read-provider", commands[0])
        self.assertIn("personal", commands[0])
        self.assertIn("--write-db", commands[0])

    def test_dashboard_displays_available_recovery_fields_without_sleep_score(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "trainingos.sqlite"
            app = local_review_ui.ReviewServer(db_path)
            with trainingos_db.connect(db_path) as connection:
                trainingos_db.upsert_daily_recovery_metric(
                    connection,
                    {
                        "metric_date": "2026-11-19",
                        "provider": "garmin",
                        "sleep_duration_minutes": 322,
                        "hrv_status": "BALANCED",
                        "body_battery": 14,
                    },
                )

            rendered = app.dashboard_page()

        self.assertIn("5 小时 22 分", rendered)
        self.assertIn("BALANCED", rendered)
        self.assertIn(">14<", rendered)

    def test_dashboard_renders_categorized_health_visualizations(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "trainingos.sqlite"
            app = local_review_ui.ReviewServer(db_path)
            with trainingos_db.connect(db_path) as connection:
                trainingos_db.upsert_daily_recovery_metric(
                    connection,
                    {"metric_date": "2026-11-19", "sleep_score": 72, "body_battery": 55, "training_readiness": 64},
                )
                trainingos_db.upsert_daily_health_metric(
                    connection,
                    "sleep",
                    {"metric_date": "2026-11-19", "deep_sleep_minutes": 60, "light_sleep_minutes": 180, "rem_sleep_minutes": 70, "awake_minutes": 20},
                )
                trainingos_db.upsert_daily_health_metric(
                    connection,
                    "hrv",
                    {"metric_date": "2026-11-19", "last_night_average_ms": 49},
                )

            rendered = app.dashboard_page()

        self.assertIn("14 天恢复趋势", rendered)
        self.assertIn("查看趋势数据", rendered)
        self.assertIn("睡眠构成", rendered)
        self.assertIn("深睡 60 分", rendered)
        self.assertIn("夜间 HRV 均值 ms", rendered)
        self.assertIn(">49.0<", rendered)

    def test_pwa_manifest_and_service_worker_do_not_cache_private_pages(self):
        manifest = local_review_ui.PWA_MANIFEST
        self.assertEqual(manifest["name"], "TrainingOS")
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual(manifest["start_url"], "/")
        self.assertEqual(manifest["icons"][0]["type"], "image/svg+xml")
        self.assertTrue(local_review_ui.APP_ICON_PATH.exists())
        worker = local_review_ui.SERVICE_WORKER
        self.assertIn("fetch(event.request).catch", worker)
        self.assertIn("'/offline'", worker)
        self.assertNotIn("'/body'", worker)
        self.assertNotIn("'/session'", worker)
        self.assertNotIn("'/day'", worker)
        self.assertNotIn("cache.put", worker)

    def test_pages_register_service_worker_and_manifest(self):
        rendered = local_review_ui.page("Test", "<h1>Test</h1>")
        self.assertIn('rel="manifest" href="/manifest.webmanifest"', rendered)
        self.assertIn("serviceWorker.register('/service-worker.js')", rendered)

    def test_dashboard_is_the_operational_home_page(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            app = local_review_ui.ReviewServer(Path(tmpdir) / "trainingos.sqlite")
            rendered = app.dashboard_page()
        self.assertIn("TrainingOS 总览", rendered)
        self.assertIn("近 30 天训练日", rendered)
        self.assertIn('href="/training"', rendered)
        self.assertIn("暂无训练记录", rendered)

    def test_body_metrics_page_saves_to_local_database(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "trainingos.sqlite"
            app = local_review_ui.ReviewServer(db_path)
            html = app.save_body_metrics(
                {
                    "metric_date": ["2026-10-04"],
                    "body_weight_kg": ["80.2"],
                    "body_fat_percent": ["15.1"],
                    "waist_cm": ["84"],
                    "notes": ["morning"],
                }
            )
            with trainingos_db.connect(db_path) as connection:
                records = trainingos_db.get_recent_body_metrics(connection)
        self.assertIn("身体指标已保存在本机 SQLite", html)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["body_weight_kg"], 80.2)

    def test_body_metrics_page_shows_validation_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            app = local_review_ui.ReviewServer(Path(tmpdir) / "trainingos.sqlite")
            html = app.save_body_metrics(
                {"metric_date": ["2026-10-04"], "body_weight_kg": ["999"]}
            )
        self.assertIn("body_weight_kg must be between 20 and 400", html)

    def test_voice_parse_prefills_manual_entry_without_saving(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "trainingos.sqlite"
            app = local_review_ui.ReviewServer(db_path)
            rendered = app.parse_manual_voice(
                {
                    "activity_name": ["Chest"],
                    "completed_at": ["2026-10-04T09:00"],
                    "set_count": ["6"],
                    "voice_transcript": ["Bench Press 80 kg 8 reps RPE 8"],
                }
            )
            with trainingos_db.connect(db_path) as connection:
                sessions = trainingos_db.get_recent_sessions(connection)
        self.assertIn('value="Bench Press"', rendered)
        self.assertIn('value="80.0"', rendered)
        self.assertIn('value="8"', rendered)
        self.assertEqual(sessions, [])

    def test_manual_entry_saves_normalized_local_session(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "trainingos.sqlite"
            app = local_review_ui.ReviewServer(db_path)
            rendered = app.save_manual_entry(
                {
                    "activity_name": ["Legs"],
                    "completed_at": ["2026-10-04T09:00"],
                    "overall_rpe": ["8"],
                    "fatigue_rating": ["6"],
                    "set_count": ["1"],
                    "exercise_name_0": ["Leg Press"],
                    "set_order_0": ["1"],
                    "weight_kg_0": ["120"],
                    "reps_0": ["10"],
                    "rpe_0": ["8"],
                }
            )
            with trainingos_db.connect(db_path) as connection:
                sessions = trainingos_db.get_recent_sessions(connection)
                saved = trainingos_db.get_session_for_review(connection, sessions[0]["id"])
        self.assertIn("已保存校正", rendered)
        self.assertEqual(saved["provider"], "local")
        self.assertEqual(saved["source_tool"], "local_manual_entry")
        self.assertEqual(saved["sets"][0]["weight_kg"], 120)
        self.assertEqual(saved["sets"][0]["reps"], 10)

    def test_session_page_exposes_voice_correction_without_direct_save(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "trainingos.sqlite"
            app = local_review_ui.ReviewServer(db_path)
            with trainingos_db.connect(db_path) as connection:
                session_id = trainingos_db.save_imported_workout(
                    connection,
                    {
                        "provider": "garmin",
                        "external_activity_id": "voice-correction",
                        "completed_at": "2026-10-04 09:00:00",
                        "activity_name": "Strength",
                        "sets": [
                            {
                                "exercise_name": "Bench Press",
                                "set_order": 1,
                                "set_type": "working",
                                "weight_kg": 80,
                                "reps": 8,
                            }
                        ],
                    },
                )
            rendered = app.parse_session_voice(
                {
                    "session_id": [session_id],
                    "target_set": ["1"],
                    "voice_transcript": ["Bench Press 82.5 kg 8 reps RPE 8"],
                }
            )
            with trainingos_db.connect(db_path) as connection:
                unchanged = trainingos_db.get_session_for_review(connection, session_id)
        self.assertIn('value="82.5"', rendered)
        self.assertEqual(unchanged["sets"][0]["weight_kg"], 80)


if __name__ == "__main__":
    unittest.main()
