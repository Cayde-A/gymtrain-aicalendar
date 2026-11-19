import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import garmin_provider


class DummyResponseError(Exception):
    def __init__(self, message, status_code):
        super().__init__(message)
        self.status_code = status_code


class DummyClient:
    def get_stats(self):
        return {}

    def upload_workout(self):
        return {}


class DummyOfficialClient:
    def __init__(self):
        self.activity_calls = []

    def get_daily_summaries(self, start_date, end_date):
        return {"data": [{"calendarDate": start_date}]}

    def search_activities(self, **kwargs):
        self.activity_calls.append(kwargs)
        return [{"activityId": 123}]

    def get_activity(self, activity_id):
        return {"activityId": activity_id}

    def get_activity_workouts(self, activity_id):
        return {"activityId": activity_id, "workouts": []}

    def download_activity(self, activity_id):
        return b"zip"


class GarminProviderTestCase(unittest.TestCase):
    def test_has_tokens_accepts_oauth_pair(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tokenstore = Path(tmpdir)
            (tokenstore / "oauth1_token.json").touch()
            (tokenstore / "oauth2_token.json").touch()
            self.assertTrue(garmin_provider.has_tokens(tokenstore))

    def test_has_tokens_rejects_partial_oauth_pair(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tokenstore = Path(tmpdir)
            (tokenstore / "oauth1_token.json").touch()
            self.assertFalse(garmin_provider.has_tokens(tokenstore))

    def test_default_tokenstore_prefers_environment(self):
        with mock.patch.dict(os.environ, {"GARMINTOKENS": "~/custom-garmin"}):
            self.assertEqual(
                garmin_provider.default_tokenstore(),
                Path("~/custom-garmin").expanduser(),
            )

    def test_detect_capabilities_reports_method_groups(self):
        capabilities = garmin_provider.detect_capabilities(DummyClient())
        self.assertTrue(capabilities["daily_summary"])
        self.assertTrue(capabilities["workout_upload"])
        self.assertFalse(capabilities["activities"])
        self.assertFalse(capabilities["workout_device_push"])

    def test_personal_adapter_reports_read_capabilities_without_write(self):
        client = garmin_provider.GarminPersonalReadClient(DummyOfficialClient())
        capabilities = garmin_provider.detect_capabilities(client)
        self.assertTrue(capabilities["daily_summary"])
        self.assertTrue(capabilities["activities"])
        self.assertTrue(capabilities["activity_sets"])
        self.assertTrue(capabilities["activity_download"])
        self.assertFalse(capabilities["training_readiness"])
        self.assertFalse(capabilities["workout_upload"])
        metadata = garmin_provider.provider_metadata(client)
        self.assertEqual(metadata["source_tool"], garmin_provider.PERSONAL_SOURCE_TOOL)
        self.assertTrue(metadata["read_only"])

    def test_personal_adapter_paginates_activity_search(self):
        official = DummyOfficialClient()
        client = garmin_provider.GarminPersonalReadClient(official)
        activities = client.get_activities_by_date("2026-11-01", "2026-11-02")
        self.assertEqual(activities, [{"activityId": 123}])
        self.assertEqual(official.activity_calls[0]["start"], 0)
        self.assertEqual(official.activity_calls[0]["limit"], 100)

    def test_login_read_auto_prefers_personal_api_key(self):
        personal_client = object()
        with mock.patch.object(garmin_provider, "has_personal_api_key", return_value=True), mock.patch.object(
            garmin_provider, "login_personal_read", return_value=personal_client
        ) as personal_login, mock.patch.object(garmin_provider, "login") as legacy_login:
            result = garmin_provider.login_read(None, None, "tokens", provider="auto")
        self.assertIs(result, personal_client)
        personal_login.assert_called_once_with(None)
        legacy_login.assert_not_called()

    def test_login_read_auto_falls_back_to_legacy_without_key(self):
        legacy_client = object()
        with mock.patch.object(garmin_provider, "has_personal_api_key", return_value=False), mock.patch.object(
            garmin_provider, "login", return_value=legacy_client
        ) as legacy_login:
            result = garmin_provider.login_read(None, None, "tokens", provider="auto")
        self.assertIs(result, legacy_client)
        legacy_login.assert_called_once_with(None, None, "tokens")

    def test_classify_error_marks_rate_limit_retryable(self):
        failure = garmin_provider.classify_error(
            DummyResponseError("Too Many Requests", 429),
            "get_stats",
        )
        self.assertEqual(failure.code, garmin_provider.ErrorCode.RATE_LIMIT)
        self.assertTrue(failure.retryable)
        self.assertEqual(failure.status_code, 429)
        self.assertEqual(failure.operation, "get_stats")

    def test_classify_error_marks_authentication_non_retryable(self):
        failure = garmin_provider.classify_error(
            DummyResponseError("Unauthorized", 401),
            "login",
        )
        self.assertEqual(failure.code, garmin_provider.ErrorCode.AUTHENTICATION)
        self.assertFalse(failure.retryable)

    def test_execute_raises_structured_provider_error(self):
        def fail():
            raise TimeoutError("provider timed out")

        with self.assertRaises(garmin_provider.GarminProviderError) as raised:
            garmin_provider.execute("fetch_sleep", fail)
        self.assertEqual(
            raised.exception.failure.code,
            garmin_provider.ErrorCode.PROVIDER_OUTAGE,
        )
        self.assertTrue(raised.exception.failure.retryable)

    def test_execute_with_retry_retries_outage_with_exponential_backoff(self):
        calls = []
        sleeps = []

        def flaky():
            calls.append(True)
            if len(calls) < 3:
                raise TimeoutError("temporary outage")
            return "ok"

        result = garmin_provider.execute_with_retry(
            "fetch",
            flaky,
            max_attempts=3,
            base_delay_seconds=0.5,
            sleeper=sleeps.append,
        )
        self.assertEqual(result, "ok")
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleeps, [0.5, 1.0])

    def test_execute_with_retry_does_not_retry_rate_limit(self):
        calls = []

        def limited():
            calls.append(True)
            raise DummyResponseError("Too Many Requests", 429)

        with self.assertRaises(garmin_provider.GarminProviderError) as raised:
            garmin_provider.execute_with_retry(
                "login",
                limited,
                max_attempts=3,
                sleeper=lambda _: None,
            )
        self.assertEqual(len(calls), 1)
        self.assertEqual(raised.exception.failure.attempts, 1)
        self.assertEqual(raised.exception.failure.code, garmin_provider.ErrorCode.RATE_LIMIT)

    def test_execute_with_retry_reports_final_attempt_count(self):
        with self.assertRaises(garmin_provider.GarminProviderError) as raised:
            garmin_provider.execute_with_retry(
                "fetch",
                lambda: (_ for _ in ()).throw(TimeoutError("outage")),
                max_attempts=2,
                sleeper=lambda _: None,
            )
        self.assertEqual(raised.exception.failure.attempts, 2)


if __name__ == "__main__":
    unittest.main()
