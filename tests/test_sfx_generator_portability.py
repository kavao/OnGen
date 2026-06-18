import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_PATH = ROOT / "tools" / "sound" / "sfx_generator.py"


class CanonicalCliTests(unittest.TestCase):
    def test_canonical_cli_list_presets_succeeds(self) -> None:
        result = subprocess.run(
            [sys.executable, str(CANONICAL_PATH), "--list-presets"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("jump", result.stdout)


class PortabilityTests(unittest.TestCase):
    def test_single_file_copy_runs_in_isolated_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            shutil.copy2(CANONICAL_PATH, tmp / "sfx_generator.py")
            result = subprocess.run(
                [sys.executable, str(tmp / "sfx_generator.py"), "--list-presets"],
                cwd=tmp,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("coin", result.stdout)

    def test_single_file_copy_runs_lint_and_analyze(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            shutil.copy2(CANONICAL_PATH, tmp / "sfx_generator.py")
            result = subprocess.run(
                [
                    sys.executable,
                    str(tmp / "sfx_generator.py"),
                    "--input",
                    "O4 L4 T120 C",
                    "--lint",
                    "--analyze",
                    "--report-json",
                    str(tmp / "report.json"),
                    "-o",
                    str(tmp / "sample"),
                ],
                cwd=tmp,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("OnGen Audio Lint Report", result.stdout)
            self.assertTrue((tmp / "report.json").exists())


if __name__ == "__main__":
    unittest.main()
