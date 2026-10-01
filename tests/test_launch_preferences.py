import os
import unittest
from unittest.mock import patch

from mcli.launcher import _launch_preferences


class LaunchPreferenceTests(unittest.TestCase):
    def test_valid_memory_and_resolution(self):
        with patch.dict(os.environ, {"MCLI_MEMORY_MB": "4096", "MCLI_RESOLUTION_WIDTH": "1280", "MCLI_RESOLUTION_HEIGHT": "720"}):
            self.assertEqual(_launch_preferences(), {"MCLI_MEMORY_MB": 4096, "MCLI_RESOLUTION_WIDTH": 1280, "MCLI_RESOLUTION_HEIGHT": 720})

    def test_rejects_invalid_memory(self):
        with patch.dict(os.environ, {"MCLI_MEMORY_MB": "-1"}):
            with self.assertRaisesRegex(RuntimeError, "MCLI_MEMORY_MB"):
                _launch_preferences()

    def test_game_directory_and_fullscreen_preferences(self):
        from pathlib import Path
        directory = str(Path.cwd().resolve())
        with patch.dict(os.environ, {"MCLI_GAME_DIR": directory, "MCLI_FULLSCREEN": "1"}):
            values = _launch_preferences()
        self.assertEqual(values["MCLI_GAME_DIR"], directory)
        self.assertTrue(values["MCLI_FULLSCREEN"])
        with patch.dict(os.environ, {"MCLI_GAME_DIR": "relative/path"}):
            with self.assertRaisesRegex(RuntimeError, "MCLI_GAME_DIR"):
                _launch_preferences()


if __name__ == "__main__":
    unittest.main()
