import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from mcli import curseforge
from mcli.modrinth import ModrinthError


class CurseForgePackTests(unittest.TestCase):
    def test_rejects_override_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "pack.zip"
            manifest = {"minecraft": {"version": "1.21.1", "modLoaders": [{"id": "fabric-0.16.0"}]}, "overrides": "overrides", "files": []}
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("manifest.json", json.dumps(manifest))
                archive.writestr("overrides/../../outside.txt", "bad")
            with patch.object(curseforge, "get_instance", return_value={"path": str(root / "instance"), "version": "1.21.1", "loader": "fabric"}):
                with self.assertRaises(ModrinthError):
                    curseforge.install_modpack_file(archive_path, "survival")
            self.assertFalse((root / "outside.txt").exists())


if __name__ == "__main__":
    unittest.main()
