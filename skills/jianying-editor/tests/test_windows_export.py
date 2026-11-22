import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

skill = Path(os.environ.get("JY_SKILL_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(skill / "scripts"))

from jy_wrapper import JyProject


class WindowsExportTests(unittest.TestCase):
    def setUp(self):
        self.project = JyProject.__new__(JyProject)
        self.project.name = "Example"

    def test_delegates_export_options_and_returns_success(self):
        with patch("jy_wrapper.IS_MACOS", False), patch(
            "auto_exporter.auto_export", return_value=(0, {"ok": True})
        ) as export:
            result = self.project.export_video("output.mp4", "4K", "60")
        export.assert_called_once_with("Example", "output.mp4", "4K", "60")
        self.assertEqual(result, {"status": "success", "output": "output.mp4"})

    def test_preserves_export_failure(self):
        with patch("jy_wrapper.IS_MACOS", False), patch(
            "auto_exporter.auto_export",
            return_value=(1, {"ok": False, "reason": "Application unavailable"}),
        ):
            result = self.project.export_video("output.mp4")
        self.assertEqual(result, {"status": "failed", "error": "Application unavailable"})


if __name__ == "__main__":
    unittest.main()
