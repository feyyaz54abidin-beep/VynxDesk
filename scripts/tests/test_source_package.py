"""Exercise exact-revision archives with real temporary Git repositories."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / "package_source.py"


class SourcePackageTests(unittest.TestCase):
    def setUp(self):
        if not SCRIPT.is_file():
            self.fail("Missing tracked-source exporter; worktree tar can include credentials")
        spec = importlib.util.spec_from_file_location("package_source", SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        self.git("init", "--quiet")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        (self.root / "README.md").write_text("source\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-qm", "fixture")
        self.output = Path(self.temp.name) / "source.zip"

    def git(self, *args, root=None):
        return subprocess.check_output(["git", "-C", str(root or self.root), *args], text=True).strip()

    def test_only_tracked_files_and_provenance_are_archived(self):
        (self.root / ".env").write_text("TEST_SECRET=never-export", encoding="utf-8")
        (self.root / "signing.pfx").write_bytes(b"dummy-private-key")
        self.module.create_archive(self.root, self.output)
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(set(archive.namelist()), {"README.md", "VYNXDESK_SOURCE.json"})
            self.assertEqual(json.loads(archive.read("VYNXDESK_SOURCE.json"))["commit"], self.git("rev-parse", "HEAD"))

    def test_dirty_tracked_worktree_rejected(self):
        (self.root / "README.md").write_text("not committed", encoding="utf-8")
        with self.assertRaises(self.module.SourcePackageError):
            self.module.create_archive(self.root, self.output)
        self.assertFalse(self.output.exists())

    def test_dirty_index_rejected(self):
        (self.root / "README.md").write_text("staged", encoding="utf-8")
        self.git("add", "README.md")
        with self.assertRaises(self.module.SourcePackageError):
            self.module.create_archive(self.root, self.output)

    def test_existing_output_not_overwritten_without_force(self):
        self.output.write_bytes(b"keep")
        with self.assertRaises(self.module.SourcePackageError):
            self.module.create_archive(self.root, self.output)
        self.assertEqual(self.output.read_bytes(), b"keep")

    def test_force_and_deterministic_output(self):
        self.module.create_archive(self.root, self.output)
        first = self.output.read_bytes()
        self.module.create_archive(self.root, self.output, force=True)
        self.assertEqual(self.output.read_bytes(), first)

    def test_tar_gz_is_supported_and_reproducible(self):
        output = self.output.with_suffix(".tar.gz")
        self.module.create_archive(self.root, output)
        first = output.read_bytes()
        self.module.create_archive(self.root, output, force=True)
        self.assertEqual(output.read_bytes(), first)
        with tarfile.open(output) as archive:
            self.assertEqual(archive.extractfile("README.md").read(), b"source\n")

    def test_tracked_private_key_rejected(self):
        (self.root / "id_ed25519").write_text("FAKE KEY", encoding="utf-8")
        self.git("add", "id_ed25519")
        self.git("commit", "-qm", "unsafe fixture")
        with self.assertRaises(self.module.SourcePackageError):
            self.module.create_archive(self.root, self.output)

    def add_submodule(self):
        child = Path(self.temp.name) / "child"
        child.mkdir()
        self.git("init", "--quiet", root=child)
        self.git("config", "user.name", "Fixture", root=child)
        self.git("config", "user.email", "fixture@example.invalid", root=child)
        (child / "shared.rs").write_text("// shared source\n", encoding="utf-8")
        self.git("add", ".", root=child)
        self.git("commit", "-qm", "child fixture", root=child)
        self.git("-c", "protocol.file.allow=always", "submodule", "add", "--quiet", str(child), "libs/shared")
        self.git("commit", "-qm", "pin child")
        return self.root / "libs/shared"

    def test_pinned_submodule_source_is_included(self):
        child = self.add_submodule()
        (child / ".env").write_text("TEST_SECRET=skip", encoding="utf-8")
        self.module.create_archive(self.root, self.output)
        with zipfile.ZipFile(self.output) as archive:
            self.assertIn("libs/shared/shared.rs", archive.namelist())
            self.assertNotIn("libs/shared/.env", archive.namelist())
            metadata = json.loads(archive.read("VYNXDESK_SOURCE.json"))
            self.assertEqual(metadata["submodules"]["libs/shared"], self.git("rev-parse", "HEAD", root=child))

    def test_missing_submodule_rejected(self):
        self.add_submodule()
        self.git("submodule", "deinit", "-f", "--", "libs/shared")
        with self.assertRaises(self.module.SourcePackageError):
            self.module.create_archive(self.root, self.output)

    def test_dirty_submodule_rejected(self):
        child = self.add_submodule()
        (child / "shared.rs").write_text("// changed\n", encoding="utf-8")
        with self.assertRaises(self.module.SourcePackageError):
            self.module.create_archive(self.root, self.output)

    def test_invalid_archive_extension_rejected(self):
        with self.assertRaises(self.module.SourcePackageError):
            self.module.create_archive(self.root, self.output.with_suffix(".exe"))


if __name__ == "__main__":
    unittest.main()
