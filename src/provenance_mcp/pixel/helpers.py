"""Shared constants and utility functions for image forensics tools."""

import base64
import io
import os
import time
from pathlib import Path

import numpy as np
from PIL import Image

# Known AI generator signatures in metadata
AI_SIGNATURES = [
    "stable diffusion", "dall-e", "dalle", "midjourney", "comfyui",
    "automatic1111", "invoke ai", "novelai", "adobe firefly", "firefly",
    "dreamstudio", "leonardo.ai", "playground ai", "bing image creator",
    "copilot", "imagen", "ideogram", "flux", "sdxl", "kandinsky",
    "deepfloyd", "waifu diffusion", "openjourney", "deliberate",
    "realistic vision", "dreamshaper", "ai generated", "txt2img",
    "img2img", "synthid",
]

# Common AI model output resolutions
AI_RESOLUTIONS = {
    (512, 512), (768, 768), (1024, 1024), (1536, 1024), (1024, 1536),
    (1440, 896), (896, 1440), (1152, 896), (896, 1152),
    (1024, 768), (768, 1024), (512, 768), (768, 512),
}

VIS_DIR = Path(os.environ.get("PROVENANCE_TMP", "/tmp/image-provenance"))


def _load_image(image_path: str) -> Image.Image:
    """Load and validate an image from a file path."""
    path = Path(image_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")
    # Read the bytes and close the handle: PIL would otherwise keep the file open
    # for the lifetime of the decoded image, which leaks a descriptor per call.
    with open(path, "rb") as fh:
        return Image.open(io.BytesIO(fh.read()))


def _image_to_base64(img: Image.Image, fmt: str = "PNG") -> str:
    """Convert a PIL Image to a base64 string."""
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _normalize_array_to_image(arr: np.ndarray) -> Image.Image:
    """Normalize a numpy array to 0-255 and convert to PIL Image."""
    arr = arr.astype(np.float64)
    if arr.max() - arr.min() > 0:
        arr = (arr - arr.min()) / (arr.max() - arr.min()) * 255
    return Image.fromarray(arr.astype(np.uint8))


def _save_visualization(img: Image.Image, name: str) -> str:
    """Save a visualization image to /tmp and return the path."""
    VIS_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time() * 1000)
    path = VIS_DIR / f"{name}_{ts}.png"
    img.save(path, format="PNG")
    return str(path)


def _radially_averaged_psd(gray: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Compute radially averaged power spectral density."""
    f_transform = np.fft.fft2(gray)
    f_shift = np.fft.fftshift(f_transform)
    power = np.abs(f_shift) ** 2

    center = np.array(power.shape) // 2
    y, x = np.ogrid[-center[0]:power.shape[0] - center[0],
                     -center[1]:power.shape[1] - center[1]]
    radius = np.sqrt(x * x + y * y).astype(int)

    radial_sum = np.bincount(radius.ravel(), power.ravel())
    radial_count = np.bincount(radius.ravel())
    radial_count[radial_count == 0] = 1
    radial_profile = radial_sum / radial_count

    frequencies = np.arange(len(radial_profile)) / len(radial_profile)
    return frequencies, radial_profile


def _resolution_flags(w: int, h: int) -> list[str]:
    """Check if dimensions match known AI output patterns."""
    flags = []
    if (w, h) in AI_RESOLUTIONS:
        flags.append(f"[FLAG:RES_AI_MATCH] EXACT AI RESOLUTION — {w}x{h} is a common AI model output size (also used by social media resizing)")
    if w == h:
        flags.append(f"SQUARE ASPECT RATIO — {w}x{h} (common for both AI and social media)")
    if w % 64 == 0 and h % 64 == 0:
        flags.append(f"[FLAG:RES_DIV64] DIMENSIONS DIVISIBLE BY 64 — {w}x{h} aligns with diffusion model latent space")
    return flags
