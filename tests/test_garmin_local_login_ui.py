import importlib.util
import stat
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "garmin_local_login_ui", ROOT / "scripts" / "garmin_local_login_ui.py"
)
garmin_local_login_ui = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(garmin_local_login_ui)


class GarminLocalLoginUiTests(unittest.TestCase):
    def test_write_personal_api_key_trims_and_protects_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "garmin" / "key"
            garmin_local_login_ui.write_personal_api_key("  test-key  ", path)

            self.assertEqual(path.read_text(encoding="utf-8"), "test-key\n")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_write_personal_api_key_rejects_empty_value(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "key"
            with self.assertRaises(ValueError):
                garmin_local_login_ui.write_personal_api_key("   ", path)
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
