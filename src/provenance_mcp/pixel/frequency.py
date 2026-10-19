"""FFT frequency analysis tool for detecting AI image artifacts."""

import numpy as np

from mcp.types import ImageContent, TextContent

from provenance_mcp.pixel._app import mcp
from provenance_mcp.pixel.helpers import _load_image, _image_to_base64, _normalize_array_to_image


@mcp.tool()
async def frequency_analysis(image_path: str) -> list[TextContent | ImageContent]:
    """Perform FFT frequency analysis on an image.

    Analyzes the frequency spectrum for artifacts common in AI-generated images,
    including grid patterns, spectral peaks, and unusual energy distribution.

    Args:
        image_path: Absolute path to the image file.
    """
    img = _load_image(image_path)
    gray = np.array(img.convert("L"), dtype=np.float64)

    f_transform = np.fft.fft2(gray)
    f_shift = np.fft.fftshift(f_transform)
    magnitude = np.log1p(np.abs(f_shift))

    spectrum_img = _normalize_array_to_image(magnitude)

    h, w = magnitude.shape
    cy, cx = h // 2, w // 2
    radius_low = min(h, w) // 8
    radius_mid = min(h, w) // 4

    y_coords, x_coords = np.ogrid[:h, :w]
    dist = np.sqrt((y_coords - cy) ** 2 + (x_coords - cx) ** 2)

    low_freq_energy = float(np.mean(magnitude[dist <= radius_low]))
    mid_freq_energy = float(np.mean(magnitude[(dist > radius_low) & (dist <= radius_mid)]))
    high_freq_energy = float(np.mean(magnitude[dist > radius_mid]))
    total_energy = float(np.mean(magnitude))

    masked_mag = magnitude.copy()
    masked_mag[dist <= radius_low] = 0
    peak_threshold = np.mean(masked_mag) + 3 * np.std(masked_mag)
    num_peaks = int(np.sum(masked_mag > peak_threshold))
    peak_ratio = num_peaks / max(masked_mag.size, 1)

    hf_ratio = high_freq_energy / max(total_energy, 0.001)

    report = f"""## Frequency Analysis (FFT)

**Image:** {image_path}

### Energy Distribution
| Band | Mean Energy |
|------|-------------|
| Low frequency (center) | {low_freq_energy:.4f} |
| Mid frequency | {mid_freq_energy:.4f} |
| High frequency (edges) | {high_freq_energy:.4f} |
| Total | {total_energy:.4f} |

### High-frequency ratio: {hf_ratio:.4f}
### Spectral peak ratio: {peak_ratio:.6f} ({num_peaks} peaks detected)

### Interpretation
"""
    if hf_ratio < 0.3:
        report += "- **[FLAG:FFT_SMOOTH]** Low high-frequency content — overly smooth, common in AI-generated images.\n"
    elif hf_ratio > 0.7:
        report += "- High high-frequency content — significant detail/texture, more typical of real photographs.\n"
    else:
        report += "- Moderate frequency distribution — within normal range.\n"

    if peak_ratio > 0.001:
        report += f"- **[FLAG:FFT_PERIODIC]** Periodic artifacts detected ({num_peaks} spectral peaks) — can indicate GAN or processing artifacts.\n"
    else:
        report += "- No significant periodic artifacts in the frequency domain.\n"

    return [
        TextContent(type="text", text=report),
        ImageContent(type="image", data=_image_to_base64(spectrum_img), mimeType="image/png"),
    ]
