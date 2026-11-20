from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from scripts.deployment import receive_learn_v2 as receiver


SHA = "a" * 40


def archive(name="learn_web/dist/index.html"):
    files = {name: b"app"}
    manifest = {"id": "learn-v2-" + SHA[:12], "commit": SHA,
                "inputs": {path: sha256(data).hexdigest() for path, data in files.items()}}
    files["RELEASE.json"] = json.dumps(manifest).encode()
    stream = BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as tar:
        for path, data in files.items():
            member = tarfile.TarInfo(path)
            member.size = len(data)
            tar.addfile(member, BytesIO(data))
    return stream.getvalue()


class ReleaseTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def test_receives_expected_commit(self):
        data = archive()
        folder = receiver.prepare(BytesIO(data), self.root, SHA, sha256(data).hexdigest())
        self.assertEqual((folder / "learn_web/dist/index.html").read_bytes(), b"app")

    def test_rejects_wrong_archive_or_commit_and_unsafe_paths(self):
        for name, commit, checksum in [("a", SHA, "0" * 64), ("a", "b" * 40, None),
                                       ("../outside", SHA, None)]:
            with self.subTest(name=name, commit=commit), tempfile.TemporaryDirectory() as folder:
                data = archive(name)
                with self.assertRaises(ValueError):
                    receiver.prepare(BytesIO(data), Path(folder), commit, checksum or sha256(data).hexdigest())

    def test_failed_health_restores_original_populated_directory(self):
        current, alternate = self.root / "src", self.root / "previous"
        for path in [current, alternate]:
            path.mkdir()
            (path / "version").write_text(path.name)
        with patch.object(receiver, "stop"), patch.object(receiver, "start", side_effect=[RuntimeError, None]):
            with self.assertRaises(RuntimeError):
                receiver.switch(current, alternate)
        self.assertEqual((current / "version").read_text(), "src")
        self.assertEqual((alternate / "version").read_text(), "previous")

    def test_runtime_gate_ignores_bytecode_but_detects_migration(self):
        for name in receiver.GUARDED:
            path = self.root / name
            if path.suffix:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            else:
                path.mkdir()
        before = receiver.guarded_files(self.root)
        cache = self.root / "migrations/__pycache__"
        cache.mkdir()
        (cache / "env.pyc").touch()
        self.assertEqual(receiver.guarded_files(self.root), before)
        (self.root / "migrations/new.py").touch()
        self.assertNotEqual(receiver.guarded_files(self.root), before)
