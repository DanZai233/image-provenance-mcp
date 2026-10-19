"""Full forensic report — orchestrates all analysis tools and produces a verdict."""

import base64
import io

from PIL import Image

from mcp.types import TextContent

from provenance_mcp.pixel._app import mcp
from provenance_mcp.pixel.helpers import _load_image, _save_visualization
from provenance_mcp.pixel.noise_map import noise_map
from provenance_mcp.pixel.ela import error_level_analysis
from provenance_mcp.pixel.frequency import frequency_analysis
from provenance_mcp.pixel.spectral_decay import spectral_decay_analysis
from provenance_mcp.pixel.color import color_analysis
from provenance_mcp.pixel.metadata import metadata_check


@mcp.tool()
async def full_forensic_report(image_path: str) -> list[TextContent]:
    """Run all forensic analyses and produce a comprehensive report with overall verdict.

    Combines noise map, ELA, frequency analysis, spectral decay, color analysis,
    and metadata check. Saves visualization images to /tmp/image-forensics/ and
    returns text-only results to avoid output overflow.

    Args:
        image_path: Absolute path to the image file.
    """
    img = _load_image(image_path)
    w, h = img.size
    results = []
    total_checks = 0
    # Categorized flags: definitive (only AI), strong (rarely natural), weak (ambiguous with social media)
    definitive_flags = []
    strong_flags = []
    weak_flags = []

    results.append(TextContent(type="text", text=f"# Full Forensic Report\n**Image:** {image_path}\n**Size:** {w}x{h}\n---"))

    # ── 1. Noise Map ──
    try:
        noise_results = await noise_map(image_path)
        text = noise_results[0].text
        # Save visualization to file instead of returning base64
        if len(noise_results) > 1 and hasattr(noise_results[1], "data"):
            img_data = base64.b64decode(noise_results[1].data)
            vis_img = Image.open(io.BytesIO(img_data))
            vis_path = _save_visualization(vis_img, "noise_map")
            text += f"\n**Visualization saved to:** `{vis_path}`"
        results.append(TextContent(type="text", text=text))
        total_checks += 1
        if "[FLAG:NOISE_UNIFORM]" in text:
            strong_flags.append("Noise pattern is unusually uniform")
        elif "[FLAG:NOISE_MODERATE]" in text:
            weak_flags.append("Noise pattern shows moderate uniformity")
    except Exception as e:
        results.append(TextContent(type="text", text=f"\n### Noise Map: FAILED — {e}\n"))

    # ── 2. ELA ──
    try:
        ela_results = await error_level_analysis(image_path)
        text = ela_results[0].text
        if len(ela_results) > 1 and hasattr(ela_results[1], "data"):
            img_data = base64.b64decode(ela_results[1].data)
            vis_img = Image.open(io.BytesIO(img_data))
            vis_path = _save_visualization(vis_img, "ela")
            text += f"\n**Visualization saved to:** `{vis_path}`"
        results.append(TextContent(type="text", text=text))
        total_checks += 1
        if "[FLAG:ELA_UNIFORM]" in text:
            weak_flags.append("ELA: uniform compression history (also normal for single-source images)")
    except Exception as e:
        results.append(TextContent(type="text", text=f"\n### ELA: FAILED — {e}\n"))

    # ── 3. Frequency Analysis ──
    try:
        freq_results = await frequency_analysis(image_path)
        text = freq_results[0].text
        if len(freq_results) > 1 and hasattr(freq_results[1], "data"):
            img_data = base64.b64decode(freq_results[1].data)
            vis_img = Image.open(io.BytesIO(img_data))
            vis_path = _save_visualization(vis_img, "fft_spectrum")
            text += f"\n**Visualization saved to:** `{vis_path}`"
        results.append(TextContent(type="text", text=text))
        total_checks += 1
        if "[FLAG:FFT_SMOOTH]" in text:
            strong_flags.append("FFT: image is overly smooth (low high-frequency content)")
        if "[FLAG:FFT_PERIODIC]" in text:
            strong_flags.append("FFT: periodic artifacts detected (GAN signature)")
    except Exception as e:
        results.append(TextContent(type="text", text=f"\n### Frequency Analysis: FAILED — {e}\n"))

    # ── 4. Spectral Decay ──
    try:
        spectral_results = await spectral_decay_analysis(image_path)
        text = spectral_results[0].text
        if len(spectral_results) > 1 and hasattr(spectral_results[1], "data"):
            img_data = base64.b64decode(spectral_results[1].data)
            vis_img = Image.open(io.BytesIO(img_data))
            vis_path = _save_visualization(vis_img, "psd_curve")
            text += f"\n**Visualization saved to:** `{vis_path}`"
        results.append(TextContent(type="text", text=text))
        total_checks += 1
        if "[FLAG:PSD_SLOPE_ANOMALY]" in text:
            strong_flags.append("PSD: anomalous spectral decay slope")
        if "[FLAG:PSD_FIT_POOR]" in text:
            strong_flags.append("PSD: irregular spectral fit (poor 1/f adherence)")
        if "[FLAG:PSD_HF_ANOMALY]" in text:
            strong_flags.append("PSD: high-frequency spectral anomaly")
    except Exception as e:
        results.append(TextContent(type="text", text=f"\n### Spectral Decay: FAILED — {e}\n"))

    # ── 5. Color Analysis ──
    try:
        color_results = await color_analysis(image_path)
        text = color_results[0].text
        results.append(TextContent(type="text", text=text))
        total_checks += 1
        if "[FLAG:COLOR_HIGH_CORR]" in text:
            strong_flags.append("Color: extreme RGB channel correlation")
        if "[FLAG:COLOR_GRAD_CORR]" in text:
            strong_flags.append("Color: very high gradient correlation across channels")
        if "[FLAG:COLOR_ENTROPY]" in text:
            strong_flags.append("Color: near-identical channel entropies")
        if "[FLAG:COLOR_HIGH_SAT]" in text:
            strong_flags.append("Color: unusually high saturation")
        if "[FLAG:COLOR_VIVID]" in text:
            strong_flags.append("Color: high ratio of vivid pixels")
    except Exception as e:
        results.append(TextContent(type="text", text=f"\n### Color Analysis: FAILED — {e}\n"))

    # ── 6. Metadata ──
    try:
        meta_results = await metadata_check(image_path)
        text = meta_results[0].text
        results.append(TextContent(type="text", text=text))
        total_checks += 1
        if "[FLAG:META_AI_SIG]" in text:
            definitive_flags.append("AI tool signature found in metadata")
        if "[FLAG:META_PROMPT]" in text:
            definitive_flags.append("Generation prompt found in metadata")
        if "[FLAG:META_SD_PARAMS]" in text:
            definitive_flags.append("Stable Diffusion parameters found in metadata")
        if "[FLAG:META_NO_DATA]" in text:
            weak_flags.append("No metadata (common for AI AND social media)")
        if "[FLAG:META_NO_CAMERA]" in text:
            weak_flags.append("No camera data (common for AI AND social media)")
        if "[FLAG:RES_AI_MATCH]" in text:
            weak_flags.append("Resolution matches common AI output size (also used by social media)")
        if "[FLAG:RES_DIV64]" in text:
            weak_flags.append("Dimensions divisible by 64 (AI latent space, but also standard sizes)")
    except Exception as e:
        results.append(TextContent(type="text", text=f"\n### Metadata: FAILED — {e}\n"))

    # ── Verdict ──
    if definitive_flags:
        verdict = "AI-GENERATED — Definitive AI tool signatures found in the image."
    elif len(strong_flags) >= 3:
        verdict = "LIKELY AI-GENERATED — Multiple strong forensic indicators detected."
    elif len(strong_flags) >= 1:
        verdict = "POSSIBLY AI-GENERATED — Some forensic anomalies detected, but not conclusive."
    elif len(weak_flags) >= 3:
        verdict = "INCONCLUSIVE — Only weak/ambiguous indicators found. These are also common in social media images."
    elif len(weak_flags) >= 1:
        verdict = "LIKELY AUTHENTIC — Only minor ambiguous indicators, consistent with normal photo processing."
    else:
        verdict = "NO INDICATORS — No forensic signs of AI generation detected."

    def _format_flags(flags: list[str], label: str) -> str:
        if not flags:
            return f"**{label}:** None\n"
        text = f"**{label}:**\n"
        for f in flags:
            text += f"  - {f}\n"
        return text

    results.append(TextContent(type="text", text=f"""
---
## Overall Assessment ({total_checks} analyses)

{_format_flags(definitive_flags, "Definitive (AI tool fingerprints)")}
{_format_flags(strong_flags, "Strong indicators (forensic anomalies)")}
{_format_flags(weak_flags, "Weak/ambiguous (also caused by social media processing)")}
**Verdict:** {verdict}

*Note: Modern AI generators (Flux, DALL-E 3, Midjourney v6+) produce images that are nearly indistinguishable from real photos at the pixel level. Social media platforms (Facebook, Instagram) strip metadata and resize images to AI-typical dimensions, creating false positives. These heuristic analyses work best when metadata is intact or when images show older GAN artifacts. For ambiguous cases, visual inspection (teeth, hands, text, reflections) remains the most reliable method.*
"""))

    return results
