import plistlib
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IOS_ROOT = ROOT / "apps" / "ios"
APP_ROOT = IOS_ROOT / "TrainingOSApp"


def localization_keys(path: Path) -> set[str]:
    return set(re.findall(r'^"([^"]+)"\s*=', path.read_text(encoding="utf-8"), re.MULTILINE))


class IOSSourceContractTestCase(unittest.TestCase):
    def test_customer_tab_contract_has_exactly_four_destinations(self):
        source = (
            IOS_ROOT
            / "TrainingOSCore"
            / "Sources"
            / "TrainingOSCore"
            / "Models.swift"
        ).read_text(encoding="utf-8")
        match = re.search(r"public enum CustomerTab.*?\{(.*?)\n\}", source, re.DOTALL)
        self.assertIsNotNone(match)
        cases = re.findall(r"^\s*case\s+(\w+)\s*$", match.group(1), re.MULTILINE)
        self.assertEqual(cases, ["today", "training", "nutrition", "progress"])
        self.assertNotIn("debug", cases)
        self.assertNotIn("settings", cases)

    def test_english_and_chinese_localization_keys_match(self):
        english = localization_keys(APP_ROOT / "Resources" / "en.lproj" / "Localizable.strings")
        chinese = localization_keys(APP_ROOT / "Resources" / "zh-Hans.lproj" / "Localizable.strings")
        self.assertEqual(english, chinese)
        self.assertIn("nutrition.photo", english)
        self.assertIn("anchor.waiting", english)

    def test_camera_permission_and_privacy_manifest_are_explicit(self):
        with (APP_ROOT / "Info.plist").open("rb") as handle:
            info = plistlib.load(handle)
        with (APP_ROOT / "Resources" / "PrivacyInfo.xcprivacy").open("rb") as handle:
            privacy = plistlib.load(handle)
        self.assertTrue(info["NSCameraUsageDescription"])
        self.assertFalse(privacy["NSPrivacyTracking"])
        self.assertEqual(privacy["NSPrivacyCollectedDataTypes"], [])

    def test_food_recognition_contract_requires_confirmation(self):
        source = (
            IOS_ROOT
            / "TrainingOSCore"
            / "Sources"
            / "TrainingOSCore"
            / "ServiceContracts.swift"
        ).read_text(encoding="utf-8")
        self.assertIn("requiresUserConfirmation", source)
        self.assertIn("requiresUserConfirmation: Bool = true", source)


if __name__ == "__main__":
    unittest.main()
