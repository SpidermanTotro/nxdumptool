"""Synthetic, rights-free XCI/HFS0 parser regression tests."""
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from tools.xci_inventory import InvalidImage, analyze, make_markdown

def hfs0(items):
    strings = b""
    entries = b""
    data = b""
    for name, content in items:
        name_at = len(strings)
        strings += name.encode("utf-8") + b"\x00"
        prefix = min(len(content), 0x200)
        entries += struct.pack(
            "<QQII8s32s", len(data), len(content), name_at, prefix, b"\x00" * 8,
            hashlib.sha256(content[:prefix]).digest() if prefix else b"\x00" * 32,
        )
        data += content
    header = b"HFS0" + struct.pack("<III", len(items), len(strings), 0) + entries + strings
    return header + data, len(header)

def fixture(path):
    secure, _ = hfs0([("00000000000000000000000000000000.cnmt.nca", b"A" * 0x200)])
    root, root_header_size = hfs0([("secure", secure), ("update", hfs0([])[0])])
    image = bytearray(0x10000)
    card = bytearray(0x200)
    card[0x100:0x104] = b"HEAD"
    struct.pack_into("<QQ", card, 0x130, 0x10000, root_header_size)
    card[0x140:0x160] = hashlib.sha256(root[:root_header_size]).digest()
    image[0x1000:0x1200] = card
    path.write_bytes(image + root)
    return path

class XCITests(unittest.TestCase):
    def test_reads_and_verifies_unencrypted_headers(self):
        with tempfile.TemporaryDirectory() as temp:
            path = fixture(Path(temp) / "tiny.xci")
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            result = analyze(path, as_of=date(2026, 10, 9))
            self.assertEqual(result["schema"], "nxdt-xci-inventory-v1")
            self.assertEqual(result["root_header_sha256"], "match")
            self.assertEqual(result["root"]["file_count"], 2)
            secure = next(p for p in result["partitions"] if p["name"] == "secure")
            self.assertEqual(secure["file_count"], 1)
            self.assertEqual(secure["entries"][0]["hashed_prefix_sha256"], "match")
            self.assertEqual(result["release_date_source"], "unknown")
            self.assertIsNone(result["age_days_as_of"])
            self.assertEqual(result["modernization_inventory"]["textures"]["status"], "not_inspected")
            self.assertEqual(before, hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertIn("NOT an asset scan", make_markdown(result))

    def test_release_age_is_only_user_supplied(self):
        with tempfile.TemporaryDirectory() as temp:
            result = analyze(fixture(Path(temp) / "a.xci"),
                             release_date=date(2026, 10, 1), as_of=date(2026, 10, 9))
            self.assertEqual(result["age_days_as_of"], 8)
            self.assertEqual(result["release_date_source"], "user_supplied")

    def test_bad_head_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            path = fixture(Path(temp) / "bad.xci")
            with path.open("r+b") as f:
                f.seek(0x1100)
                f.write(b"NOPE")
            with self.assertRaisesRegex(InvalidImage, "HEAD"):
                analyze(path)

    def test_truncated_partition_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            path = fixture(Path(temp) / "bad.xci")
            with path.open("r+b") as f:
                f.truncate(0x10016)
            with self.assertRaises(InvalidImage):
                analyze(path)

    def test_cli_writes_reports_without_touching_image(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = fixture(root / "test-image.xci")
            out = root / "reports"
            result = subprocess.run(
                [sys.executable, "tools/xci_inventory.py", str(image),
                 "--output-dir", str(out), "--as-of", "2026-10-09"],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((out / "test-image.inventory.md").exists())
            manifest = json.loads((out / "test-image.inventory.json").read_text())
            self.assertEqual(manifest["root_header_sha256"], "match")
            self.assertEqual(image.read_bytes()[0x1100:0x1104], b"HEAD")
            again = subprocess.run(
                [sys.executable, "tools/xci_inventory.py", str(image),
                 "--output-dir", str(out)],
                capture_output=True, text=True,
            )
            self.assertNotEqual(again.returncode, 0)
            self.assertIn("already exists", again.stderr)

if __name__ == "__main__":
    unittest.main()
