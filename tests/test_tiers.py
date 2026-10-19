"""Tiering tests: an authoritative manifest must stop the pipeline before heuristics."""

from __future__ import annotations

import asyncio
import pathlib
import unittest

from provenance_mcp import tiers

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SIGNED = FIXTURES / "signed_chatgpt.png"
PLAIN = FIXTURES / "plain.png"


class TestTierOne(unittest.TestCase):
    def test_signed_image_is_authoritative(self):
        authoritative, text = tiers.tier1(str(SIGNED))
        self.assertTrue(authoritative)
        self.assertIn("AI_GENERATED", text)

    def test_plain_image_is_not(self):
        authoritative, text = tiers.tier1(str(PLAIN))
        self.assertFalse(authoritative)
        self.assertIn("No C2PA manifest", text)


class TestPipeline(unittest.TestCase):
    def test_stops_at_tier_one(self):
        out = asyncio.run(tiers.image_provenance(str(SIGNED)))
        self.assertIn("TIER 1", out)
        self.assertNotIn("TIER 2", out)  # heuristics never run when the signature speaks

    def test_falls_back_to_tier_two(self):
        out = asyncio.run(tiers.image_provenance(str(PLAIN)))
        self.assertIn("TIER 2", out)
        self.assertIn("NOT evidence", out)

    def test_missing_file(self):
        out = asyncio.run(tiers.image_provenance("/nonexistent/nope.png"))
        self.assertTrue(out.startswith("ERROR: file not found"))


if __name__ == "__main__":
    unittest.main()
