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


if __name__ == "__main__":
    unittest.main()
