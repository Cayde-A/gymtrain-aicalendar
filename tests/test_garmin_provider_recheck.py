import unittest

from scripts import garmin_provider, garmin_provider_recheck


def status(state, code=None):
    result = {"status": state, "probes": []}
    if code:
        result["error"] = {"code": code}
    return result


class GarminProviderRecheckTestCase(unittest.TestCase):
    def test_both_healthy_continue_primary(self):
        result = garmin_provider_recheck.recommendation(
            status("healthy"), status("healthy")
        )
        self.assertEqual(result["action"], "continue_primary")

    def test_gccli_can_be_read_fallback(self):
        result = garmin_provider_recheck.recommendation(
            status("failed", garmin_provider.ErrorCode.PROVIDER_OUTAGE),
            status("healthy"),
        )
        self.assertEqual(result["action"], "use_gccli_read_fallback")

    def test_official_provider_can_use_legacy_fallback(self):
        result = garmin_provider_recheck.recommendation(
            status("authentication_required"),
            status("healthy"),
            fallback_action="use_legacy_read_fallback",
        )
        self.assertEqual(result["action"], "use_legacy_read_fallback")

    def test_rate_limit_never_recommends_reauthentication(self):
        result = garmin_provider_recheck.recommendation(
            status("failed", garmin_provider.ErrorCode.RATE_LIMIT),
            status("healthy"),
        )
        self.assertEqual(result["action"], "wait_without_reauthentication")

    def test_authentication_requests_user_login(self):
        result = garmin_provider_recheck.recommendation(
            status("authentication_required", garmin_provider.ErrorCode.AUTHENTICATION),
            status("authentication_required"),
        )
        self.assertEqual(result["action"], "user_login_required")

    def test_schema_failure_rechecks_same_source(self):
        result = garmin_provider_recheck.recommendation(
            status("failed", garmin_provider.ErrorCode.SCHEMA),
            status("failed", garmin_provider.ErrorCode.UNKNOWN),
        )
        self.assertEqual(result["action"], "inspect_same_source_release_and_schema")

    def test_safe_probe_omits_values(self):
        result = garmin_provider_recheck.safe_probe(
            "summary", lambda: {"sleepScore": 90, "steps": 10000}
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["top_level_fields"], 2)
        self.assertNotIn("sleepScore", result)
        self.assertNotIn("steps", result)


if __name__ == "__main__":
    unittest.main()
