"""Metadata/EXIF inspection tool for AI generation signatures."""

import json

from PIL.ExifTags import TAGS

from mcp.types import TextContent

from provenance_mcp.pixel._app import mcp
from provenance_mcp.pixel.helpers import _load_image, _resolution_flags, AI_SIGNATURES


@mcp.tool()
async def metadata_check(image_path: str) -> list[TextContent]:
    """Check image metadata/EXIF for AI generation signatures and resolution fingerprints.

    Looks for known AI tool signatures, unusual metadata patterns,
    missing camera information, and AI-typical output resolutions.

    Args:
        image_path: Absolute path to the image file.
    """
    img = _load_image(image_path)
    w, h = img.size

    metadata = {}
    flags = []

    metadata["format"] = img.format or "Unknown"
    metadata["mode"] = img.mode
    metadata["size"] = f"{w}x{h}"

    # EXIF data
    exif_data = {}
    try:
        raw_exif = img._getexif()
        if raw_exif:
            for tag_id, value in raw_exif.items():
                tag_name = TAGS.get(tag_id, str(tag_id))
                try:
                    exif_data[tag_name] = str(value)
                except Exception:
                    exif_data[tag_name] = "<unreadable>"
    except Exception:
        pass

    info_data = {}
    for key, value in img.info.items():
        try:
            info_data[str(key)] = str(value)
        except Exception:
            pass

    # Scan for AI signatures
    all_meta_text = json.dumps({**exif_data, **info_data}).lower()
    found_signatures = []
    for sig in AI_SIGNATURES:
        if sig in all_meta_text:
            found_signatures.append(sig)

    camera_fields = ["Make", "Model", "LensModel", "FocalLength", "ExposureTime", "FNumber", "ISOSpeedRatings"]
    present_camera_fields = [f for f in camera_fields if f in exif_data]
    missing_camera_fields = [f for f in camera_fields if f not in exif_data]

    software = exif_data.get("Software", info_data.get("Software", ""))

    # Build flags
    if found_signatures:
        flags.append(f"[FLAG:META_AI_SIG] AI SIGNATURES FOUND: {', '.join(found_signatures)}")
    if not exif_data and not info_data:
        flags.append("[FLAG:META_NO_DATA] NO METADATA — stripped of all metadata (common for AI images AND social media)")
    elif not present_camera_fields:
        flags.append("[FLAG:META_NO_CAMERA] NO CAMERA DATA — no camera make/model/lens/exposure info (common for AI images AND social media re-uploads)")
    elif len(missing_camera_fields) > 4:
        flags.append(f"SPARSE CAMERA DATA — missing: {', '.join(missing_camera_fields)}")
    if software:
        for sig in AI_SIGNATURES:
            if sig in software.lower():
                flags.append(f"[FLAG:META_AI_SIG] SOFTWARE FIELD contains AI signature: {software}")
                break

    if "parameters" in info_data:
        flags.append("[FLAG:META_SD_PARAMS] STABLE DIFFUSION PARAMETERS chunk detected in PNG metadata")
    if "prompt" in all_meta_text or "negative_prompt" in all_meta_text:
        flags.append("[FLAG:META_PROMPT] PROMPT/NEGATIVE_PROMPT found in metadata — likely AI-generated")
    if "steps" in info_data and "sampler" in all_meta_text:
        flags.append("[FLAG:META_SD_PARAMS] Generation parameters (steps, sampler) found — likely AI-generated")

    # Resolution fingerprinting
    res_flags = _resolution_flags(w, h)
    flags.extend(res_flags)

    report = f"""## Metadata Analysis

**Image:** {image_path}
**Format:** {metadata['format']} | **Mode:** {metadata['mode']} | **Size:** {metadata['size']}

### Flags
"""
    if flags:
        for flag in flags:
            report += f"- **{flag}**\n"
    else:
        report += "- No AI-generation flags detected.\n"

    if exif_data:
        report += "\n### EXIF Data\n| Tag | Value |\n|-----|-------|\n"
        for tag, value in sorted(exif_data.items()):
            report += f"| {tag} | {str(value)[:200]} |\n"

    if info_data:
        report += "\n### Image Info / Text Chunks\n| Key | Value |\n|-----|-------|\n"
        for key, value in sorted(info_data.items()):
            report += f"| {key} | {str(value)[:200]} |\n"

    if present_camera_fields:
        report += f"\n### Camera fields present: {', '.join(present_camera_fields)}"
    if missing_camera_fields:
        report += f"\n### Camera fields missing: {', '.join(missing_camera_fields)}"

    return [TextContent(type="text", text=report)]
