"""Tests use only tiny generated files. No game content or hardware needed."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from tools.content_verify import ManifestError, load_manifest, verify

class ContentVerifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.src = self.home / "files"
        self.src.mkdir()

    def _make_manifest(self, records):
        path = self.home / "expected.json"
        path.write_text(json.dumps({"schema": "nxdt-content-hashes-v1",
                                   "files": records}), encoding="utf8")
        return path

    def _record(self, name, data, **extra):
        return {"path": name, "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data), **extra}

    def test_match_streams_full_file(self):
        data = b"hello world" * 16000
        (self.src / "one.bin").write_bytes(data)
        entry = self._record("one.bin", data, title_id="0100000000000001",
                             content_type="add_on_content")
        result = verify(self.src, load_manifest(self._make_manifest([entry])))
        self.assertTrue(result["all_matched"])
        self.assertEqual(result["counts"]["match"], 1)
        self.assertEqual(result["by_title"]["0100000000000001"]["match"], 1)
        self.assertEqual(result["files"][0]["actual_sha256"], entry["sha256"])

    def test_hash_mismatch(self):
        (self.src / "test.nca").write_bytes(b"correct size, wrong hash")
        data = b"totally different number!"
        self.assertEqual(len(data), len(b"correct size, wrong hash"))
        record = self._record("test.nca", data)
        result = verify(self.src, load_manifest(self._make_manifest([record])))
        self.assertEqual(result["counts"]["hash_mismatch"], 1)
        self.assertFalse(result["all_matched"])

    def test_size_mismatch(self):
        (self.src / "short.bin").write_bytes(b"a")
        result = verify(self.src, load_manifest(
            self._make_manifest([self._record("short.bin", b"abcdef")])
        ))
        self.assertEqual(result["counts"]["size_mismatch"], 1)

    def test_missing(self):
        result = verify(self.src, load_manifest(self._make_manifest([self._record("missing.bin", b"abc")])))
        self.assertEqual(result["counts"]["missing_or_unreadable"], 1)

    def test_symlink_rejected_even_when_hash_matches(self):
        secret = self.home / "elsewhere.bin"
        secret.write_bytes(b"private")
        (self.src / "link.bin").symlink_to(secret)
        result = verify(self.src, load_manifest(
            self._make_manifest([self._record("link.bin", b"private")])
        ))
        self.assertEqual(result["counts"]["unsafe_symlink_or_path"], 1)

    def test_traversal_and_duplicate_path_rejected(self):
        with self.assertRaises(ManifestError):
            load_manifest(self._make_manifest([self._record("../escape", b"")]))
        record = self._record("dup", b"x")
        with self.assertRaises(ManifestError):
            load_manifest(self._make_manifest([record, record]))

    def test_reject_invalid_sha_and_secrets(self):
        entry = {"path": "thing.bin", "sha256": "not-a-sha256", "ticket_key": "secret"}
        with self.assertRaises(ManifestError):
            load_manifest(self._make_manifest([entry]))
        valid = self._record("thing.bin", b"hey")
        valid["ticket_key"] = "secret"
        with self.assertRaisesRegex(ManifestError, "unknown fields"):
            load_manifest(self._make_manifest([valid]))

    def test_cli_exit_codes_and_outputs(self):
        data = b"known"
        (self.src / "known.bin").write_bytes(data)
        expected = self._make_manifest([self._record("known.bin", data)])
        target = self.home / "verification.json"
        cmd = [sys.executable, "tools/content_verify.py", str(self.src),
               "--manifest", str(expected), "--output", str(target)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(json.loads(target.read_text())["all_matched"])
        repeated = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(repeated.returncode, 2)
        self.assertIn("File exists", repeated.stderr)

    def test_cli_mismatch_exit_one_and_report_written(self):
        (self.src / "known.bin").write_bytes(b"actual")
        expected = self._make_manifest([self._record("known.bin", b"wrong!")])
        target = self.home / "verify.json"
        proc = subprocess.run(
            [sys.executable, "tools/content_verify.py", str(self.src),
             "--manifest", str(expected), "--output", str(target)],
            capture_output=True, text=True
        )
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertTrue(target.exists())
        self.assertFalse(json.loads(target.read_text())["all_matched"])

if __name__ == "__main__":
    unittest.main()
