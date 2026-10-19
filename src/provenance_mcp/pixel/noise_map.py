"""Noise map extraction tool for AI image detection."""

import numpy as np
from scipy.ndimage import gaussian_filter

from mcp.types import ImageContent, TextContent

from provenance_mcp.pixel._app import mcp
from provenance_mcp.pixel.helpers import _load_image, _image_to_base64, _normalize_array_to_image


@mcp.tool()
async def noise_map(image_path: str, blur_sigma: float = 3.0) -> list[TextContent | ImageContent]:
    """Extract the noise pattern from an image to help detect AI generation.

    Subtracts a Gaussian-blurred version from the original to isolate noise.
    AI-generated images tend to have unnaturally uniform or structured noise.

    Args:
        image_path: Absolute path to the image file.
        blur_sigma: Gaussian blur sigma (higher = more smoothing). Default 3.0.
    """
    img = _load_image(image_path)
    img_rgb = img.convert("RGB")
    arr = np.array(img_rgb, dtype=np.float64)

    blurred = gaussian_filter(arr, sigma=(blur_sigma, blur_sigma, 0))
    noise = arr - blurred

    channel_names = ["Red", "Green", "Blue"]
    stats = {}
    for i, name in enumerate(channel_names):
        ch = noise[:, :, i]
        stats[name] = {
            "mean": float(np.mean(ch)),
            "std": float(np.std(ch)),
            "min": float(np.min(ch)),
            "max": float(np.max(ch)),
        }

    block_size = 64
    h, w = noise.shape[:2]
    local_stds = []
    for y in range(0, h - block_size, block_size):
        for x in range(0, w - block_size, block_size):
            block = noise[y:y + block_size, x:x + block_size]
            local_stds.append(np.std(block))
    uniformity_score = float(np.std(local_stds)) if local_stds else 0.0

    noise_vis = np.abs(noise)
    noise_gray = np.mean(noise_vis, axis=2) if noise_vis.ndim == 3 else noise_vis
    noise_img = _normalize_array_to_image(noise_gray)

    report = f"""## Noise Map Analysis

**Image:** {image_path}
**Blur sigma:** {blur_sigma}

### Per-Channel Statistics
| Channel | Mean | Std Dev | Min | Max |
|---------|------|---------|-----|-----|
"""
    for name, s in stats.items():
        report += f"| {name} | {s['mean']:.4f} | {s['std']:.4f} | {s['min']:.4f} | {s['max']:.4f} |\n"

    report += f"""
### Uniformity Score: {uniformity_score:.4f}
- **Low (<2.0):** Suspiciously uniform — common in AI-generated images
- **High (>5.0):** Natural variation — more likely a real photo

### Interpretation
"""
    if uniformity_score < 2.0:
        report += "**[FLAG:NOISE_UNIFORM]** The noise pattern is unusually uniform, a common indicator of AI-generated images."
    elif uniformity_score < 5.0:
        report += "**[FLAG:NOISE_MODERATE]** The noise pattern shows moderate uniformity. Could be either real or AI-generated."
    else:
        report += "The noise pattern shows natural variation, consistent with a real photograph."

    return [
        TextContent(type="text", text=report),
        ImageContent(type="image", data=_image_to_base64(noise_img), mimeType="image/png"),
    ]
