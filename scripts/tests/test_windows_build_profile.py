"""The shipping Flutter build must actually compile its advertised input option."""
import contextlib
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import build


class WindowsBuildProfileTests(unittest.TestCase):
    def features(self, arguments, windows=True):
        with patch.object(build, "windows", windows), patch.object(build, "osx", False):
            with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                try:
                    args = build.make_parser().parse_args(arguments)
                except SystemExit as error:
                    self.fail(f"Build argument is not supported: {arguments}: {error}")
                return build.get_features(args)

    def test_invalid_platform_never_deletes_existing_binary(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            existing = Path(directory) / "customer-build.exe"
            existing.write_bytes(b"keep existing build")
            with patch.object(build, "windows", False), patch.object(build, "osx", False), \
                 patch.object(build, "exe_path", str(existing)), \
                 patch.object(sys, "argv", ["build.py", "--flutter", "--windows-input-plus"]):
                with self.assertRaises(ValueError):
                    build.main()
            self.assertEqual(existing.read_bytes(), b"keep existing build")

    def test_standard_flutter_is_unchanged(self):
        self.assertEqual(self.features(["--flutter"]), ["flutter"])

    def test_explicit_input_capability_included(self):
        self.assertIn("windows-user-input-plus", self.features(["--flutter", "--windows-input-plus"]))

    def test_input_capability_requires_windows(self):
        with self.assertRaises(ValueError):
            self.features(["--flutter", "--windows-input-plus"], windows=False)

    def test_input_capability_requires_flutter(self):
        with self.assertRaises(ValueError):
            self.features(["--windows-input-plus"])

    def test_no_driver_or_hardware_bridge_enabled_implicitly(self):
        features = self.features(["--flutter", "--windows-input-plus"])
        self.assertNotIn("vynx-play", features)
        self.assertNotIn("vynx-input-bridge", features)


if __name__ == "__main__":
    unittest.main()
