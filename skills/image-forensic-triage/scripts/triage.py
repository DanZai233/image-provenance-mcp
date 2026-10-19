#!/usr/bin/env python3
"""Batch triage ledger for image evidence.

Runs the cheap, decisive checks first and prints them in the order a human should trust
them: C2PA → file structure → annotation layers. Pixel heuristics are deliberately NOT run
here; they belong to the optional [pixel] tier and are never evidence (see SKILL.md).

Usage:
    triage.py FILE [FILE ...] [--json out.json] [--md out.md]

Exit codes: 0 all files probed, 1 at least one file unreadable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter

try:  # numpy is only needed for the block-noise probe
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

from PIL import Image


# --------------------------------------------------------------------------- helpers

def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def exif_summary(im: Image.Image) -> dict:
    tags = im.getexif()
    out = {"count": len(tags)}
    for key, label in (
        (271, "make"),          # Make
        (272, "model"),         # Model
        (305, "software"),      # Software
        (306, "datetime"),      # DateTime
        (36867, "datetime_original"),
    ):
        value = tags.get(key)
        if value:
            out[label] = str(value).strip("\x00").strip()
    return out


def c2pa_probe(path: str) -> dict:
    """Tier 1. Imported lazily so this script still runs without the package installed."""
    try:
        from provenance_mcp import c2pa_core
    except ImportError:
        return {"available": False, "note": "provenance_mcp not installed"}
    try:
        rep = c2pa_core.analyse(path)
    except Exception as exc:  # noqa: BLE001 - a broken carrier must not abort the batch
        return {"available": True, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "available": True,
        "has_manifest": rep.get("has_manifest", False),
        "carrier": rep.get("carrier"),
        "verdict": rep.get("verdict"),
        "verdict_reason": rep.get("verdict_reason"),
        "claim_generator": rep.get("claim_generator"),
        "hash_ok": (rep.get("hash") or {}).get("ok"),
        "hash_method": (rep.get("hash") or {}).get("method"),
        "actions": [
            {"action": a.get("action"), "when": a.get("when"), "agent": a.get("agent")}
            for a in rep.get("actions", [])
        ],
    }


def annotation_layers(im: Image.Image) -> list[dict]:
    """Find solid single-colour overlays: the fingerprint of a drawn-on annotation.

    A vector rectangle survives JPEG as one tight colour cluster with straight, long runs.
    Colours are quantised to 16 levels per channel so JPEG ringing does not shatter the
    cluster into hundreds of near-identical values.
    """
    if np is None:
        return []
    small = im.convert("RGB")
    if max(small.size) > 2000:
        small = small.resize((small.width // 2, small.height // 2), Image.NEAREST)
    arr = np.asarray(small)
    h, w = arr.shape[:2]
    total = h * w

    q = (arr // 16).astype(np.int32)
    codes = q[..., 0] * 256 + q[..., 1] * 16 + q[..., 2]
    vals, counts = np.unique(codes, return_counts=True)
    order = np.argsort(counts)[::-1][:40]

    found = []
    for idx in order:
        code, count = int(vals[idx]), int(counts[idx])
        if count < 200:
            continue
        mask = codes == code
        mean = tuple(int(v) for v in arr[mask].mean(axis=0))
        if min(mean) > 235:                     # white page background
            continue
        if max(mean) - min(mean) < 45:          # greys/blacks: paper, chassis, text
            continue
        if max(mean) < 120:                     # deep shading bands inside UI art
            continue
        ys, xs = np.nonzero(mask)
        bbox = int(ys.max() - ys.min() + 1) * int(xs.max() - xs.min() + 1)
        if bbox < total * 0.01:                 # too small to be an annotation
            continue
        fill = count / bbox
        if fill > 0.35:                         # solid filled shape = subject, not an outline
            continue
        longest = max(int(mask.sum(axis=1).max()), int(mask.sum(axis=0).max()))
        if longest < 0.15 * max(h, w):
            continue
        # Annotations are "foreign" colours: red on a blue screen, yellow on paper. If a
        # comparable colour covers much of the frame it is subject matter, not an overlay.
        near = np.abs(arr.astype(np.int16) - np.array(mean, dtype=np.int16)).sum(axis=2) < 72
        own_share = count / total
        if near.mean() > max(0.02, 2.5 * own_share):
            continue
        found.append({
            "colour": list(mean),
            "pixels": count,
            "fill": round(fill, 3),
            "bbox": [int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)],
            "longest_run": longest,
        })
    return found[:3]


def block_noise(im: Image.Image, block: int = 8) -> dict:
    """8x8 high-frequency energy: an outlier block is a *candidate* paste boundary."""
    if np is None:
        return {"available": False}
    grey = np.asarray(im.convert("L").resize(
        (max(1, im.width // 2), max(1, im.height // 2)), Image.BILINEAR
    )).astype(np.float32)
    # cheap unsharp: subtract a box-blurred copy
    k = 3
    pad = np.pad(grey, k, mode="edge")
    smooth = sum(
        pad[dy:dy + grey.shape[0], dx:dx + grey.shape[1]]
        for dy in range(2 * k + 1) for dx in range(2 * k + 1)
    ) / ((2 * k + 1) ** 2)
    high = grey - smooth

    h, w = high.shape
    bh, bw = h // block, w // block
    if bh == 0 or bw == 0:
        return {"available": False}
    grid = high[: bh * block, : bw * block].reshape(bh, block, bw, block).transpose(0, 2, 1, 3)
    stds = grid.std(axis=(2, 3))
    med = float(np.median(stds))
    peak = float(stds.max())
    y, x = np.unravel_index(int(stds.argmax()), stds.shape)
    return {
        "available": True,
        "median": round(med, 2),
        "peak": round(peak, 2),
        "ratio": round(peak / med, 2) if med else None,
        "peak_block": [int(y) * block, int(x) * block],
    }


def grade_hint(info: dict) -> tuple[str, str]:
    """Best grade the *file* can support, plus the reason. Never a conclusion."""
    c2pa = info["c2pa"]
    if c2pa.get("has_manifest"):
        if c2pa.get("hash_ok") is True:
            return "A", "signed, pixel hash verified"
        if c2pa.get("hash_ok") is False:
            return "A", "signed, pixel hash MISMATCH — edited after signing"
        return "A", "manifest present, hash not resolved"
    if info["width"] * info["height"] < 64 * 64:
        return "D", "too small to analyse"
    stripped = info["exif"]["count"] == 0
    small = max(info["width"], info["height"]) < 1600
    dpi96 = info.get("dpi") == 96
    if info["annotations"]:
        return "C", "vector annotation present — not the camera original"
    if stripped and (small or dpi96):
        why = []
        if small:
            why.append(f"{info['width']}×{info['height']} is small for a camera original")
        if dpi96:
            why.append("96 dpi re-export marker")
        return "C", "EXIF stripped; " + "; ".join(why)
    if not stripped:
        return "B", "EXIF present — structure can still be checked"
    return "C", "no EXIF; cannot exclude re-encoding"


# --------------------------------------------------------------------------- main probe

def probe(path: str) -> dict:
    base = {
        "file": os.path.abspath(path),
        "name": os.path.basename(path),
    }
    try:
        base["bytes"] = os.path.getsize(path)
        base["sha256"] = sha256(path)
    except OSError as exc:
        base["error"] = f"{type(exc).__name__}: {exc}"
        return base
    try:
        with Image.open(path) as im:
            im.load()
            base.update({
                "format": im.format,
                "width": im.width,
                "height": im.height,
                "mode": im.mode,
                "dpi": (im.info.get("dpi") or (None,))[0],
                "exif": exif_summary(im),
                "annotations": annotation_layers(im),
                "block_noise": block_noise(im),
            })
    except Exception as exc:  # noqa: BLE001
        base["error"] = f"{type(exc).__name__}: {exc}"
        return base

    base["c2pa"] = c2pa_probe(path)
    grade, why = grade_hint(base)
    base["grade_hint"] = {"grade": grade, "why": why}
    return base


# --------------------------------------------------------------------------- rendering

def as_markdown(rows: list[dict]) -> str:
    out = ["# Image triage ledger", ""]
    out.append("| file | size | dims | C2PA | notes | grade |")
    out.append("|---|---|---|---|---|---|")
    for r in rows:
        if "error" in r:
            out.append(f"| `{r['name']}` | — | — | — | **unreadable**: {r['error']} | D |")
            continue
        c2pa = r["c2pa"]
        if c2pa.get("has_manifest"):
            manifest = f"{c2pa.get('verdict')} ({c2pa.get('claim_generator')})"
        else:
            manifest = "none"
        notes = []
        if r["annotations"]:
            notes.append(
                "annotation " + ", ".join(f"#{''.join(f'{c:02x}' for c in a['colour'])}"
                                          f"×{a['pixels']}" for a in r["annotations"])
            )
        if r["exif"]["count"] == 0:
            notes.append("EXIF stripped")
        else:
            notes.extend(f"{k}={v}" for k, v in r["exif"].items() if k not in {"count"})
        bn = r.get("block_noise") or {}
        if bn.get("ratio") and bn["ratio"] > 8:
            notes.append(f"block-noise outlier ×{bn['ratio']} (usually text edges)")
        out.append(
            f"| `{r['name']}` | {r['bytes'] / 1024:.0f} KB | {r['width']}×{r['height']} "
            f"| {manifest} | {'; '.join(notes) or '—'} | {r['grade_hint']['grade']} "
            f"({r['grade_hint']['why']}) |"
        )

    out += ["", "## Details", ""]
    for r in rows:
        if "error" in r:
            continue
        out.append(f"### {r['name']}")
        out.append(f"- sha256 `{r['sha256']}`")
        c2pa = r["c2pa"]
        if c2pa.get("has_manifest"):
            out.append(f"- C2PA: **{c2pa.get('verdict')}**, generator "
                       f"`{c2pa.get('claim_generator')}`, hash_ok={c2pa.get('hash_ok')}")
            for a in c2pa.get("actions", [])[:5]:
                out.append(f"  - {a['action']} · {a['when']} · {a['agent']}")
        else:
            out.append(f"- C2PA: none ({c2pa.get('verdict_reason') or c2pa.get('note') or '—'})")
        if not c2pa.get("available"):
            out.append(f"- tier 1 unavailable: {c2pa.get('note')}")
        out.append("")
    out.append("> Pixel heuristics are not run here on purpose. See SKILL.md — they are"
               " leads, and they misfire on re-encoded files.")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="C2PA-first batch triage ledger.")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--json", help="write the raw ledger here")
    ap.add_argument("--md", help="write the markdown report here (default: stdout)")
    args = ap.parse_args(argv)

    rows = [probe(p) for p in args.files]
    md = as_markdown(rows)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=2)
    if args.md:
        with open(args.md, "w", encoding="utf-8") as fh:
            fh.write(md + "\n")
        print(f"wrote {args.md} ({len(rows)} files)")
    else:
        print(md)

    return 1 if any("error" in r for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
