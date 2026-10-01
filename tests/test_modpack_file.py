import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from mcli import modrinth


class ModpackFileTests(unittest.TestCase):
    def test_rejects_archive_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pack = root / "bad.mrpack"
            index = {"dependencies": {"minecraft": "1.21.1"}, "files": [], "formatVersion": 1}
            with zipfile.ZipFile(pack, "w") as archive:
                archive.writestr("modrinth.index.json", json.dumps(index))
                archive.writestr("overrides/../../outside.txt", "bad")
            with patch.object(modrinth, "get_instance", return_value={"path": str(root / "instance"), "version": "1.21.1"}):
                with self.assertRaisesRegex(modrinth.ModrinthError, "Unsafe"):
                    modrinth.install_modpack_file(pack, "survival")
            self.assertFalse((root / "outside.txt").exists())

    def test_rejects_wrong_minecraft_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pack = root / "wrong.mrpack"
            with zipfile.ZipFile(pack, "w") as archive:
                archive.writestr("modrinth.index.json", json.dumps({"dependencies": {"minecraft": "1.20.1"}, "files": []}))
            with patch.object(modrinth, "get_instance", return_value={"path": str(root / "instance"), "version": "1.21.1"}):
                with self.assertRaisesRegex(modrinth.ModrinthError, "does not match"):
                    modrinth.install_modpack_file(pack, "survival")

    def test_explicit_mod_version_must_match_instance(self):
        with tempfile.TemporaryDirectory() as directory:
            obj = {"path": directory, "version": "1.21.1", "loader": "fabric"}
            version = {"id": "v1", "project_id": "project", "game_versions": ["1.20.1"], "loaders": ["fabric"], "files": [{"filename": "mod.jar"}]}
            with patch.object(modrinth, "get_instance", return_value=obj), patch.object(modrinth, "_get", return_value=version):
                with self.assertRaisesRegex(modrinth.ModrinthError, "incompatible"):
                    modrinth.install_mod("project", "survival", version_id="v1")


if __name__ == "__main__":
    unittest.main()
