"""Tiering tests: an authoritative manifest must stop the pipeline before heuristics."""

from __future__ import annotations

import asyncio
import unittest

from provenance_mcp import tiers

try:
    from .support import fixture
except ImportError:  # pragma: no cover - `unittest discover -s tests`
    from support import fixture


class TestTierOne(unittest.TestCase):
    def test_signed_image_is_authoritative(self):
        authoritative, text = tiers.tier1(fixture("signed"))
        self.assertTrue(authoritative)
        self.assertIn("AI_GENERATED", text)

    def test_plain_image_is_not(self):
        authoritative, text = tiers.tier1(fixture("plain"))
        self.assertFalse(authoritative)
        self.assertIn("No C2PA manifest", text)


class TestPipeline(unittest.TestCase):
    def test_stops_at_tier_one(self):
        out = asyncio.run(tiers.image_provenance(fixture("signed")))
        self.assertIn("TIER 1", out)
        self.assertNotIn("TIER 2", out)  # heuristics never run when the signature speaks

    def test_falls_back_to_tier_two(self):
        out = asyncio.run(tiers.image_provenance(fixture("plain")))
        self.assertIn("TIER 2", out)
        self.assertIn("NOT evidence", out)

    def test_missing_file(self):
        out = asyncio.run(tiers.image_provenance("/nonexistent/nope.png"))
        self.assertTrue(out.startswith("ERROR: file not found"))


if __name__ == "__main__":
    unittest.main()
