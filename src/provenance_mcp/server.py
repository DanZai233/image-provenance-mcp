"""MCP surface.

Two tools are ours, the rest are the vendored pixel analyzers:

  image_provenance   tier 1 (C2PA) then tier 2 (heuristics) — start here
  c2pa_inspect       tier 1 only
  full_forensic_report, noise_map, error_level_analysis, frequency_analysis,
  spectral_decay_analysis, color_analysis, metadata_check   (tier 2)
"""

from __future__ import annotations

import os

from provenance_mcp.app import mcp
from provenance_mcp import c2pa_core, tiers

__all__ = ["mcp", "main"]


@mcp.tool()
async def image_provenance(image_path: str) -> str:
    """One-stop provenance check for an image: signed provenance first, heuristics only after.

    Use this whenever someone asks "is this image AI-made / edited / real?".
    Tier 1 reads C2PA Content Credentials: when the file carries a manifest the
    answer is authoritative (who made it, with which tool, and whether the pixels
    still match the signature). Only when no manifest exists does it fall back to
    pixel heuristics, and it labels them as non-evidence.
    """
    if not os.path.exists(image_path):
        return f"ERROR: file not found: {image_path}"
    try:
        return await tiers.image_provenance(image_path)
    except Exception as exc:
        return f"ERROR: provenance check failed for {image_path}: {exc.__class__.__name__}: {exc}"


@mcp.tool()
def c2pa_inspect(image_path: str) -> str:
    """Read Content Credentials (C2PA) only, and report the signed provenance.

    Faster than image_provenance when you already know the file carries a manifest,
    or when you want to see NO_C2PA without paying for pixel analysis. Verdicts:
    AI_GENERATED / EDITED / CAPTURED / INVALID_HASH / NO_C2PA.
    """
    if not os.path.exists(image_path):
        return f"ERROR: file not found: {image_path}"
    try:
        return c2pa_core.render(c2pa_core.analyse(image_path))
    except Exception as exc:
        return f"ERROR: could not parse C2PA from {image_path}: {exc.__class__.__name__}: {exc}"


def _register_pixel_tools() -> None:
    """Import the analyzers for their registration side effect; tolerate absence."""
    try:
        from provenance_mcp.pixel import (  # noqa: F401
            color,
            ela,
            frequency,
            full_report,
            metadata,
            noise_map,
            spectral_decay,
        )
    except ImportError:
        # numpy/scipy/PIL missing — C2PA tools still work.
        pass


_register_pixel_tools()


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
