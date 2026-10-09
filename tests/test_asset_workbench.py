"""Synthetic asset-workbench tests: no game content or keys."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from tools.asset_workbench import scan, modernize

class AssetWorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.input = self.root / "assets"
        self.input.mkdir()

    def test_scan_guesses_and_opaque(self):
        (self.input / "flower").mkdir()
        img = self.input / "flower" / "petal.png"
        Image.new("RGBA", (6, 5), (12, 34, 56, 128)).save(img)
        (self.input / "encrypted.nca").write_bytes(b"test-only")
        report = scan(self.input, include_hashes=True)
        self.assertEqual(report["file_counts"]["encrypted_or_opaque_container"], 1)
        self.assertEqual(report["file_counts"]["readable_image"], 1)
        plant = next(x for x in report["files"] if x["path"].endswith("petal.png"))
        self.assertIn("possible_plant", plant["candidate_subject_tags"])
        self.assertFalse(plant["content_inspected"])
        self.assertEqual(len(plant["sha256"]), 64)
        self.assertEqual(report["pc_port"]["status"], "planning_only")

    def test_upscale_preserves_original(self):
        img = self.input / "plant.jpg"
        Image.new("RGB", (4, 7), (10, 20, 30)).save(img)
        original = img.read_bytes()
        output = self.root / "modern"
        result = modernize(self.input, output, scale=2)
        self.assertEqual(len(result["converted"]), 1)
        with Image.open(output / "plant.jpg.png") as converted:
            self.assertEqual(converted.size, (8, 14))
        self.assertEqual(img.read_bytes(), original)
        self.assertFalse(result["pc_port_created"])

    def test_output_inside_input_refused(self):
        with self.assertRaisesRegex(ValueError, "must not be inside"):
            modernize(self.input, self.input / "outputs", scale=2)

    def test_corrupt_image_skipped(self):
        (self.input / "bad.png").write_bytes(b"not PNG")
        result = modernize(self.input, self.root / "new", scale=2)
        self.assertEqual(len(result["converted"]), 0)
        self.assertEqual(result["skipped"][0]["reason"], "unreadable_image")

    def test_output_not_overwritten(self):
        Image.new("RGB", (2, 2), (1, 2, 3)).save(self.input / "a.png")
        out = self.root / "results"
        modernize(self.input, out, scale=2)
        before = (out / "a.png.png").read_bytes()
        Image.new("RGB", (3, 3), (7, 8, 9)).save(self.input / "a.png")
        second = modernize(self.input, out, scale=2)
        self.assertEqual(second["skipped"][0]["reason"], "output_exists")
        self.assertEqual((out / "a.png.png").read_bytes(), before)

    def test_cli(self):
        Image.new("RGB", (3, 2), (5, 6, 7)).save(self.input / "tree.png")
        report = self.root / "inventory.json"
        r = subprocess.run([sys.executable, "tools/asset_workbench.py", "scan",
                            str(self.input), "--report", str(report)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(report.read_text())["file_counts"]["readable_image"], 1)
        out = self.root / "outputs"
        r = subprocess.run([sys.executable, "tools/asset_workbench.py", "modernize",
                            str(self.input), str(out), "--scale", "3"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        with Image.open(out / "tree.png.png") as converted:
            self.assertEqual(converted.size, (9, 6))

    def test_symlinks_skipped(self):
        Image.new("RGB", (2, 2)).save(self.input / "true.png")
        (self.input / "shortcut.png").symlink_to(self.input / "true.png")
        self.assertEqual(len(scan(self.input)["files"]), 1)

    def test_pixel_guard(self):
        Image.new("RGB", (5, 6)).save(self.input / "big.png")
        result = modernize(self.input, self.root / "resize", scale=4, max_pixels=100)
        self.assertEqual(result["skipped"][0]["reason"], "pixel_limit")

if __name__ == "__main__":
    unittest.main()
