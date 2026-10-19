"""Multi-scale Error Level Analysis (ELA) tool."""

import io

import numpy as np
from PIL import Image

from mcp.types import ImageContent, TextContent

from provenance_mcp.pixel._app import mcp
from provenance_mcp.pixel.helpers import _load_image, _image_to_base64


@mcp.tool()
async def error_level_analysis(image_path: str, quality: int = 90) -> list[TextContent | ImageContent]:
    """Perform multi-scale Error Level Analysis (ELA) on an image.

    Resaves at multiple JPEG quality levels and analyzes the error patterns.
    Includes consistency analysis across scales for better AI detection.

    Args:
        image_path: Absolute path to the image file.
        quality: Primary JPEG quality for visualization (1-100). Default 90.
    """
    img = _load_image(image_path)
    img_rgb = img.convert("RGB")
    original_arr = np.array(img_rgb, dtype=np.float64)

    # Primary ELA at requested quality
    buf = io.BytesIO()
    img_rgb.save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    resaved = Image.open(buf).convert("RGB")
    resaved_arr = np.array(resaved, dtype=np.float64)
    diff = np.abs(original_arr - resaved_arr)

    scale = 255.0 / max(diff.max(), 1.0)
    ela_arr = (diff * scale).clip(0, 255).astype(np.uint8)
    ela_img = Image.fromarray(ela_arr)

    mean_err = float(np.mean(diff))
    max_err = float(np.max(diff))
    std_err = float(np.std(diff))

    block_size = 64
    h, w = diff.shape[:2]
    block_means = []
    for y in range(0, h - block_size, block_size):
        for x in range(0, w - block_size, block_size):
            block = diff[y:y + block_size, x:x + block_size]
            block_means.append(np.mean(block))
    block_std = float(np.std(block_means)) if block_means else 0.0

    # Multi-scale ELA
    scale_errors = {}
    for q in [70, 80, 90, 95]:
        buf2 = io.BytesIO()
        img_rgb.save(buf2, format="JPEG", quality=q)
        buf2.seek(0)
        resaved2 = Image.open(buf2).convert("RGB")
        d = np.abs(original_arr - np.array(resaved2, dtype=np.float64))
        scale_errors[q] = float(np.mean(d))

    # Consistency: how linearly do errors decrease with quality?
    qs = sorted(scale_errors.keys())
    errs = [scale_errors[q] for q in qs]
    if len(errs) >= 2:
        coeffs = np.polyfit(qs, errs, 1)
        predicted = np.polyval(coeffs, qs)
        residuals = np.array(errs) - predicted
        consistency_score = float(np.std(residuals))
    else:
        consistency_score = 0.0

    report = f"""## Error Level Analysis (ELA)

**Image:** {image_path}
**Primary quality:** {quality}

### Error Statistics
| Metric | Value |
|--------|-------|
| Mean error | {mean_err:.4f} |
| Max error | {max_err:.4f} |
| Std deviation | {std_err:.4f} |
| Block variation | {block_std:.4f} |

### Multi-Scale ELA
| Quality | Mean Error |
|---------|-----------|
"""
    for q in qs:
        report += f"| {q} | {scale_errors[q]:.4f} |\n"

    report += f"""
### Cross-scale consistency: {consistency_score:.4f}
(Higher values indicate irregular compression behavior)

### Interpretation
"""
    if block_std < 1.5:
        report += "**[FLAG:ELA_UNIFORM]** Error levels are very uniform — same compression history everywhere, consistent with AI generation or a single-source image."
    elif block_std < 5.0:
        report += "Error levels show moderate variation. Some regions may have been edited or composited."
    else:
        report += "Error levels show significant variation — possible splicing, editing, or compositing."

    return [
        TextContent(type="text", text=report),
        ImageContent(type="image", data=_image_to_base64(ela_img), mimeType="image/png"),
    ]
