"""Synthetic tests for metadata, local-only AI prompt and unsigned HFS0 rebuild."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.xci_inventory import hfs0
from tools.xci_project import (
    ask_local_ai, build_project, pack_plain_hfs0,
    safe_records, version_comparison,
)

class XCIProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_hfs0_roundtrip_and_input_unchanged(self):
        src = self.root / "readable"
        src.mkdir()
        one = src / "flower.txt"
        two = src / "terrain.bin"
        one.write_bytes(b"flower" * 60)
        two.write_bytes(bytes(range(200)) * 2)
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in src.iterdir()}
        out = self.root / "plain.hfs0"
        result = pack_plain_hfs0(src, out, prefix_length=0x200)
        self.assertFalse(result["xci_rebuilt"])
        self.assertEqual(result["file_count"], 2)
        with out.open("rb") as f:
            parsed = hfs0(f, 0, out.stat().st_size)
        self.assertEqual([e["name"] for e in parsed["entries"]], ["flower.txt", "terrain.bin"])
        self.assertEqual([e["hashed_prefix_sha256"] for e in parsed["entries"]], ["match", "match"])
        for e in parsed["entries"]:
            with out.open("rb") as f:
                f.seek(e["offset"])
                self.assertEqual(f.read(e["size_bytes"]), (src / e["name"]).read_bytes())
        self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in src.iterdir()})

    def test_unsafe_symlink_rejected(self):
        src = self.root / "input"
        src.mkdir()
        (src / "shortcut").symlink_to(self.root / "missing")
        with self.assertRaises(ValueError):
            pack_plain_hfs0(src, self.root / "out.hfs0")

    def test_destination_inside_source_rejected(self):
        src = self.root / "source"
        src.mkdir()
        with self.assertRaises(ValueError):
            pack_plain_hfs0(src, src / "file.hfs0")

    def test_does_not_overwrite_by_default(self):
        src = self.root / "plain"
        src.mkdir()
        (src / "a.bin").write_bytes(b"abc")
        dst = self.root / "output.hfs0"
        pack_plain_hfs0(src, dst)
        first = dst.read_bytes()
        with self.assertRaises(FileExistsError):
            pack_plain_hfs0(src, dst)
        self.assertEqual(dst.read_bytes(), first)

    def test_safe_filter_and_version_provenance(self):
        raw = {
            "gamecards": [
                {"title_id": "0100000000000001", "version": 100, "title_name": "Example",
                 "ticket_key": "DO_NOT_EXPORT", "contents": [
                     {"content_id": "deadbeef", "size_bytes": 512, "title_key": "hidden"}]},
                {"title_id": "0100000000000001", "version": 200},
                {"title_id": "0100000000000002", "version": "22"},
            ],
            "master_key": "not_allowed",
        }
        filtered = safe_records(raw)
        self.assertNotIn("DO_NOT_EXPORT", json.dumps(filtered))
        self.assertNotIn("not_allowed", json.dumps(filtered))
        self.assertNotIn("hidden", json.dumps(filtered))
        grouped = version_comparison(filtered)
        self.assertEqual(grouped[0]["observed_numeric_versions"], [100, 200])
        self.assertEqual(grouped[0]["highest_version_scope"], "only_supplied_local_metadata")
        self.assertEqual(grouped[0]["latest_available_online"], "unknown")

    def test_project_accepts_title_json_and_accessible_assets(self):
        path = self.root / "card.json"
        path.write_text(json.dumps({"applications": [
            {"title_id": "0100000000000001", "version": 100,
             "ticket_key": "never_publish"}]}), encoding="utf-8")
        source = self.root / "assets"
        source.mkdir()
        (source / "forest_tree.png").write_bytes(b"metadata-only-test")
        report = build_project(None, [path], source)
        self.assertEqual(report["title_reports"][0]["metadata_record_count"], 1)
        self.assertEqual(report["asset_inventory"]["file_counts"]["readable_image"], 1)
        self.assertIn("unknown", report["version_comparison"][0]["latest_available_online"])
        self.assertNotIn("never_publish", json.dumps(report))
        self.assertIn("encrypted NCA", " ".join(report["warnings"]))

    def test_local_ai_request_is_opt_in_and_limited(self):
        project = {"version_comparison": [], "asset_inventory": None, "xci": None,
                   "warnings": ["No metadata"], "next_steps": ["Verify data"]}
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, limit): return b'{"response":"Local model: unknown data."}'
        with patch("tools.xci_project.urllib.request.urlopen", return_value=Response()) as mock:
            self.assertEqual(ask_local_ai(project, "qwen3:8b"), "Local model: unknown data.")
            request = mock.call_args[0][0]
            self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/generate")
            self.assertNotIn(b"game content", request.data)

    def test_cli_project_and_pack(self):
        title = self.root / "metadata.json"
        title.write_text(json.dumps({"titles": [{"title_id": "0100000000000001", "version": 123}]}))
        dest = self.root / "project.json"
        res = subprocess.run([
            sys.executable, "tools/xci_project.py", "project",
            "--title-report", str(title), "--output", str(dest)],
            capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(json.loads(dest.read_text())["schema"], "nxdt-xci-rebuild-workbench-v1")
        src = self.root / "src"
        src.mkdir()
        (src / "test.bin").write_bytes(b"random synthetic")
        out = self.root / "raw.hfs0"
        res = subprocess.run([
            sys.executable, "tools/xci_project.py", "pack-hfs0", str(src), str(out)],
            capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue(out.read_bytes().startswith(b"HFS0"))
        self.assertFalse(json.loads(res.stdout)["xci_rebuilt"])

if __name__ == "__main__":
    unittest.main()
