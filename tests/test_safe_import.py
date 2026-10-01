import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcli import instance_import, instances


class SafeImportTests(unittest.TestCase):
    def test_data_only_import_omits_launcher_tokens_and_binaries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / ".minecraft"
            (source / "mods").mkdir(parents=True)
            (source / "versions").mkdir()
            (source / "assets").mkdir()
            (source / "mods" / "example.jar").write_bytes(b"mod")
            (source / "versions" / "game.jar").write_bytes(b"binary")
            (source / "launcher_profiles.json").write_text('{"token":"secret"}', encoding="utf-8")
            (source / "options.txt").write_text("gamma:1", encoding="utf-8")
            target = root / "javli"
            with patch.object(instances, "ROOT", target), patch.object(instances, "INSTANCES", target / "instances"), patch.object(instances, "INDEX", target / "instances.json"):
                obj, _ = instance_import.import_instance(source, "imported", version="1.21.1", data_only=True)
            game = Path(obj["path"]) / "minecraft"
            self.assertEqual((game / "mods" / "example.jar").read_bytes(), b"mod")
            self.assertEqual((game / "options.txt").read_text(encoding="utf-8"), "gamma:1")
            self.assertFalse((game / "launcher_profiles.json").exists())
            self.assertFalse((game / "versions").exists())
            self.assertTrue((source / "launcher_profiles.json").exists())


if __name__ == "__main__":
    unittest.main()
