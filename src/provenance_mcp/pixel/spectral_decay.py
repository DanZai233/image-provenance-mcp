"""Power spectral density decay analysis tool (CVPR 2025 research)."""

import numpy as np
from PIL import Image

from mcp.types import ImageContent, TextContent

from provenance_mcp.pixel._app import mcp
from provenance_mcp.pixel.helpers import _load_image, _image_to_base64, _radially_averaged_psd


@mcp.tool()
async def spectral_decay_analysis(image_path: str) -> list[TextContent | ImageContent]:
    """Analyze the power spectral density decay curve of an image.

    Natural images follow a characteristic 1/f^beta power law. AI-generated
    images (especially from diffusion models) often show different decay slopes
    and anomalies in specific frequency bands. Based on CVPR 2025 research.

    Args:
        image_path: Absolute path to the image file.
    """
    img = _load_image(image_path)
    gray = np.array(img.convert("L"), dtype=np.float64)

    frequencies, psd = _radially_averaged_psd(gray)

    # Skip DC and near-DC components
    start_idx = max(5, len(frequencies) // 50)
    freq_trimmed = frequencies[start_idx:]
    psd_trimmed = psd[start_idx:]

    # Log-log fit for beta slope
    valid = (freq_trimmed > 0) & (psd_trimmed > 0)
    log_freq = np.log10(freq_trimmed[valid])
    log_psd = np.log10(psd_trimmed[valid])

    beta_slope, intercept = np.polyfit(log_freq, log_psd, 1)
    predicted = beta_slope * log_freq + intercept
    residuals = log_psd - predicted
    fit_residual_std = float(np.std(residuals))

    # Analyze thirds of the spectrum for anomalies
    n = len(log_freq)
    third = n // 3
    low_residual = float(np.mean(np.abs(residuals[:third])))
    mid_residual = float(np.mean(np.abs(residuals[third:2 * third])))
    high_residual = float(np.mean(np.abs(residuals[2 * third:])))

    # Create PSD visualization
    psd_vis = np.zeros((256, 256), dtype=np.float64)
    for i in range(min(256, len(log_psd))):
        idx = int(i * len(log_psd) / 256)
        val = (log_psd[idx] - log_psd.min()) / (log_psd.max() - log_psd.min() + 1e-10)
        col_height = int(val * 255)
        psd_vis[255 - col_height:, i] = 255
    psd_img = Image.fromarray(psd_vis.astype(np.uint8))

    report = f"""## Spectral Decay Analysis (Power Spectral Density)

**Image:** {image_path}

### Power Law Fit: PSD ~ 1/f^beta
| Metric | Value |
|--------|-------|
| Beta slope | {beta_slope:.4f} |
| Fit residual std | {fit_residual_std:.4f} |
| Low-freq residual | {low_residual:.4f} |
| Mid-freq residual | {mid_residual:.4f} |
| High-freq residual | {high_residual:.4f} |

### Reference ranges
- **Natural photos:** beta typically -1.5 to -4.0, low residuals (<0.4)
- **AI-generated:** beta often outside this range OR high residuals (>0.4)

### Interpretation
"""
    beta_abs = abs(beta_slope)
    if beta_abs < 1.5 or beta_abs > 4.0:
        report += f"- **[FLAG:PSD_SLOPE_ANOMALY]** Anomalous spectral decay (beta={beta_slope:.2f}) — outside typical natural image range.\n"
    else:
        report += f"- Normal spectral decay (beta={beta_slope:.2f}) — within natural image range.\n"

    if fit_residual_std > 0.4:
        report += f"- **[FLAG:PSD_FIT_POOR]** Irregular spectral fit (residual std={fit_residual_std:.2f}) — spectral irregularities detected.\n"
    else:
        report += f"- Good spectral fit (residual std={fit_residual_std:.2f}) — follows natural power law.\n"

    if high_residual > mid_residual * 2.0:
        report += "- **[FLAG:PSD_HF_ANOMALY]** High-frequency spectral anomaly detected.\n"

    return [
        TextContent(type="text", text=report),
        ImageContent(type="image", data=_image_to_base64(psd_img), mimeType="image/png"),
    ]
