"""Two tiers of evidence, in the only order that makes sense.

Tier 1 — C2PA Content Credentials. Signed, verifiable, authoritative. When a
manifest exists we stop here: there is nothing a noise histogram can add.

Tier 2 — pixel heuristics (vendored image-forensics). Only used when tier 1 has
nothing to say, and always labelled as a guess.
"""

from __future__ import annotations

import os

from provenance_mcp import c2pa_core

RULE = "=" * 72

NO_MANIFEST = (
    "No C2PA manifest in this file. That is not evidence of anything by itself:\n"
    "most cameras, most messengers and every screenshot strip it."
)

TIER2_WARNING = (
    "TIER 2 — PIXEL HEURISTICS  (NOT evidence: these mis-fire on\n"
    "         re-encoded / screenshot / social-media images)"
)


def tier1(path: str) -> tuple[bool, str]:
    """Return (authoritative, text). authoritative is True when a manifest exists."""
    rep = c2pa_core.analyse(path)
    text = c2pa_core.render(rep)
    return bool(rep.get("has_manifest")), text


async def tier2(path: str) -> str:
    """Pixel heuristics. Imported lazily so a C2PA-only install stays dependency-free."""
    try:
        from provenance_mcp.pixel.full_report import full_forensic_report
    except ImportError as exc:  # numpy / scipy / pillow not installed
        return (
            "Tier 2 unavailable: pixel analyzers need the optional extras.\n"
            f"  pip install 'image-provenance-mcp[pixel]'\n  ({exc})"
        )
    parts = await full_forensic_report(path)
    return "\n".join(getattr(p, "text", "") for p in parts)


async def image_provenance(path: str) -> str:
    """The whole pipeline as one string: tier 1 first, tier 2 only if needed."""
    if not os.path.exists(path):
        return f"ERROR: file not found: {path}"

    authoritative, tier1_text = tier1(path)
    if authoritative:
        return "\n".join([
            RULE,
            "TIER 1 — C2PA SIGNED PROVENANCE  (authoritative, stop here)",
            RULE,
            tier1_text,
        ])

    return "\n".join([
        RULE,
        "TIER 1 — C2PA: nothing signed in this file",
        RULE,
        NO_MANIFEST,
        "",
        tier1_text,
        "",
        RULE,
        TIER2_WARNING,
        RULE,
        await tier2(path),
    ])
