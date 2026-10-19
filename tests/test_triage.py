"""Tests for the forensic-triage helper shipped as part of the agent skill."""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPT = os.path.join(ROOT, "skills", "image-forensic-triage", "scripts", "triage.py")
FIXTURES = os.path.join(HERE, "fixtures")

try:
    from PIL import Image, ImageDraw

    HAVE_PIL = True
except ImportError:  # pragma: no cover
    HAVE_PIL = False

try:
    import numpy as np

    HAVE_NUMPY = True
except ImportError:  # pragma: no cover
    HAVE_NUMPY = False


def load_triage():
    spec = importlib.util.spec_from_file_location("triage_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(HAVE_PIL and HAVE_NUMPY, "needs pillow + numpy")
class AnnotationDetectorTest(unittest.TestCase):
    def setUp(self):
        self.triage = load_triage()

    def test_finds_a_drawn_rectangle(self):
        im = Image.new("RGB", (400, 300), (18, 22, 30))
        draw = ImageDraw.Draw(im)
        draw.rectangle([100, 60, 300, 180], outline=(187, 24, 7), width=5)
        found = self.triage.annotation_layers(im)
        self.assertTrue(found, "the drawn rectangle should be reported")
        colours = [tuple(c["colour"]) for c in found]
        self.assertTrue(
            any(abs(c[0] - 187) < 12 and c[1] < 40 and c[2] < 30 for c in colours),
            f"red annotation not among {colours}",
        )

    def test_ignores_a_plain_gradient(self):
        im = Image.new("RGB", (400, 300))
        for x in range(400):
            for y in range(0, 300, 3):
                im.putpixel((x, y), (30 + x // 4, 40 + y // 4, 60))
        self.assertEqual(self.triage.annotation_layers(im), [])

    def test_ignores_a_large_coloured_subject(self):
        # a filled saturated block is subject matter, not an outline
        im = Image.new("RGB", (400, 300), (200, 210, 220))
        ImageDraw.Draw(im).rectangle([20, 20, 380, 280], fill=(120, 198, 251))
        self.assertEqual(self.triage.annotation_layers(im), [])


@unittest.skipUnless(HAVE_PIL, "needs pillow")
class ProbeTest(unittest.TestCase):
    def setUp(self):
        self.triage = load_triage()

    def test_signed_fixture_reaches_grade_a(self):
        row = self.triage.probe(os.path.join(FIXTURES, "signed_chatgpt.png"))
        self.assertTrue(row["c2pa"]["has_manifest"])
        self.assertEqual(row["c2pa"]["verdict"], "AI_GENERATED")
        self.assertTrue(row["c2pa"]["hash_ok"])
        self.assertEqual(row["grade_hint"]["grade"], "A")

    def test_unsigned_file_is_not_grade_a(self):
        row = self.triage.probe(os.path.join(FIXTURES, "plain.png"))
        self.assertFalse(row["c2pa"]["has_manifest"])
        self.assertNotEqual(row["grade_hint"]["grade"], "A")

    def test_missing_file_is_reported_not_raised(self):
        row = self.triage.probe(os.path.join(FIXTURES, "does-not-exist.png"))
        self.assertIn("error", row)

    def test_cli_writes_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            json_path = os.path.join(tmp, "ledger.json")
            md_path = os.path.join(tmp, "ledger.md")
            code = self.triage.main([
                os.path.join(FIXTURES, "plain.png"),
                "--json", json_path,
                "--md", md_path,
            ])
            self.assertEqual(code, 0)
            with open(json_path, encoding="utf-8") as fh:
                ledger = json.load(fh)
            self.assertEqual(len(ledger), 1)
            with open(md_path, encoding="utf-8") as fh:
                self.assertIn("Image triage ledger", fh.read())


if __name__ == "__main__":
    unittest.main()
