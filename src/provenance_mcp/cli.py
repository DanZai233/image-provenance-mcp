"""Command line entry point: `image-provenance <image>` / `image-provenance c2pa <image>`."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from provenance_mcp import c2pa_core, tiers


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="image-provenance",
        description="C2PA-first image provenance. Read the signature before guessing from pixels.",
    )
    p.add_argument("image", nargs="?", help="path to the image")
    p.add_argument(
        "--mode",
        choices=("auto", "c2pa", "pixels"),
        default="auto",
        help="auto (default): C2PA then heuristics; c2pa: signature only; pixels: heuristics only",
    )
    p.add_argument("--json", action="store_true", help="dump the parsed C2PA record as JSON")
    p.add_argument("--mcp", action="store_true", help="run as a stdio MCP server instead")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.mcp:
        from provenance_mcp.server import main as serve

        serve()
        return 0

    if not args.image:
        build_parser().print_help()
        return 2

    if args.mode == "c2pa" or args.json:
        rep = c2pa_core.analyse(args.image)
        print(json.dumps(rep, indent=2, ensure_ascii=False, default=str) if args.json else c2pa_core.render(rep))
        return 0 if rep.get("has_manifest") else 1

    if args.mode == "pixels":
        print(asyncio.run(tiers.tier2(args.image)))
        return 0

    print(asyncio.run(tiers.image_provenance(args.image)))
    return 0 if tiers.tier1(args.image)[0] else 1


if __name__ == "__main__":
    sys.exit(main())
