"""Color channel correlation, saturation, and entropy analysis tool (CVPR 2025 research)."""

import numpy as np
from scipy.stats import entropy as scipy_entropy

from mcp.types import TextContent

from provenance_mcp.pixel._app import mcp
from provenance_mcp.pixel.helpers import _load_image


@mcp.tool()
async def color_analysis(image_path: str) -> list[TextContent]:
    """Analyze color channel correlations, saturation, and entropy for AI detection.

    Based on CVPR 2025 "Secret Lies in Color" — AI-generated images show unusual
    RGB channel correlations, gradient patterns, and saturation distributions
    compared to natural photographs.

    Args:
        image_path: Absolute path to the image file.
    """
    img = _load_image(image_path)
    arr = np.array(img.convert("RGB"), dtype=np.float64)

    r, g, b = arr[:, :, 0].flatten(), arr[:, :, 1].flatten(), arr[:, :, 2].flatten()

    # 1. RGB channel cross-correlation
    corr_rg = float(np.corrcoef(r, g)[0, 1])
    corr_rb = float(np.corrcoef(r, b)[0, 1])
    corr_gb = float(np.corrcoef(g, b)[0, 1])
    mean_corr = (corr_rg + corr_rb + corr_gb) / 3

    # 2. Gradient correlation between channels
    grad_corrs = []
    for i in range(3):
        for j in range(i + 1, 3):
            ch_i = arr[:, :, i]
            ch_j = arr[:, :, j]
            gy_i, gx_i = np.gradient(ch_i)
            gy_j, gx_j = np.gradient(ch_j)
            mag_i = np.sqrt(gx_i ** 2 + gy_i ** 2).flatten()
            mag_j = np.sqrt(gx_j ** 2 + gy_j ** 2).flatten()
            gc = float(np.corrcoef(mag_i, mag_j)[0, 1])
            grad_corrs.append(gc)
    mean_grad_corr = float(np.mean(grad_corrs))

    # 3. Per-channel entropy
    entropies = {}
    for i, name in enumerate(["R", "G", "B"]):
        ch = arr[:, :, i].flatten().astype(np.uint8)
        hist, _ = np.histogram(ch, bins=256, range=(0, 256))
        hist = hist / hist.sum()
        entropies[name] = float(scipy_entropy(hist, base=2))
    entropy_spread = max(entropies.values()) - min(entropies.values())

    # 4. HSV saturation analysis
    arr_norm = arr / 255.0
    max_rgb = np.max(arr_norm, axis=2)
    min_rgb = np.min(arr_norm, axis=2)
    saturation = np.divide(max_rgb - min_rgb, max_rgb,
                           where=max_rgb != 0, out=np.zeros_like(max_rgb))
    mean_sat = float(np.mean(saturation))
    std_sat = float(np.std(saturation))
    high_sat_ratio = float(np.sum(saturation > 0.7) / saturation.size)

    # Detect near-grayscale images (B&W, desaturated, monochrome filters)
    is_near_grayscale = mean_sat < 0.08 or mean_corr > 0.97

    report = f"""## Color Analysis

**Image:** {image_path}
**Near-grayscale detected:** {"Yes (color metrics less reliable)" if is_near_grayscale else "No"}

### RGB Channel Correlation
| Pair | Correlation |
|------|-------------|
| R-G | {corr_rg:.4f} |
| R-B | {corr_rb:.4f} |
| G-B | {corr_gb:.4f} |
| **Mean** | **{mean_corr:.4f}** |

### Gradient Correlation (between channel edge maps)
| Metric | Value |
|--------|-------|
| Mean gradient correlation | {mean_grad_corr:.4f} |

### Per-Channel Entropy (bits)
| Channel | Entropy |
|---------|---------|
| R | {entropies['R']:.4f} |
| G | {entropies['G']:.4f} |
| B | {entropies['B']:.4f} |
| **Spread** | **{entropy_spread:.4f}** |

### Saturation Distribution
| Metric | Value |
|--------|-------|
| Mean saturation | {mean_sat:.4f} |
| Std saturation | {std_sat:.4f} |
| High-saturation ratio (>0.7) | {high_sat_ratio:.4f} |

### Interpretation
"""
    if is_near_grayscale:
        report += "- **Near-grayscale image detected** — channel correlation and gradient metrics are expected to be high. These are NOT flagged as suspicious for this image.\n"
    else:
        # Channel correlation flags (only meaningful for color images)
        if mean_corr > 0.95:
            report += "- **[FLAG:COLOR_HIGH_CORR]** Extremely high channel correlation — channels are nearly identical, unusual for a color image.\n"
        elif mean_corr > 0.85:
            report += "- Moderately high channel correlation — within range for many natural scenes.\n"
        else:
            report += "- Normal channel correlation — typical of natural color photographs.\n"

        # Gradient correlation
        if mean_grad_corr > 0.99:
            report += "- **[FLAG:COLOR_GRAD_CORR]** Very high gradient correlation — edge patterns almost identical across channels.\n"
        elif mean_grad_corr < 0.7:
            report += "- Low gradient correlation — channels have independent edge structures, more natural.\n"
        else:
            report += "- Normal gradient correlation — within expected range.\n"

    # Entropy spread (meaningful regardless of grayscale)
    if entropy_spread < 0.03 and not is_near_grayscale:
        report += "- **[FLAG:COLOR_ENTROPY]** Very similar channel entropies — AI models often produce channels with near-identical information content.\n"
    elif entropy_spread < 0.1:
        report += f"- Channel entropy spread: {entropy_spread:.2f} — slightly low but within range.\n"
    else:
        report += f"- Channel entropy spread: {entropy_spread:.2f} — normal variation between channels.\n"

    # Saturation (meaningful regardless)
    if mean_sat > 0.5:
        report += f"- **[FLAG:COLOR_HIGH_SAT]** High mean saturation ({mean_sat:.2f}) — AI images tend to be more vivid/saturated.\n"
    elif mean_sat < 0.08:
        report += f"- Very low saturation ({mean_sat:.2f}) — grayscale or heavily desaturated image.\n"
    elif mean_sat < 0.15:
        report += f"- Low saturation ({mean_sat:.2f}) — muted colors.\n"
    else:
        report += f"- Normal saturation ({mean_sat:.2f}).\n"

    if high_sat_ratio > 0.15:
        report += f"- **[FLAG:COLOR_VIVID]** {high_sat_ratio * 100:.1f}% of pixels highly saturated (>0.7) — unusually vivid, common in AI outputs.\n"

    return [TextContent(type="text", text=report)]
