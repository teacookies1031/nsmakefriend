"""
Image processor for the Nintendo Switch drawing pipeline.

Takes a source image (PNG, JPG, or any Pillow-supported format) and converts
it to a monochrome numpy bitmap ready for the path planner.

Pipeline:
    load -> resize -> optional contrast enhance -> threshold -> bitmap
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageOps

# ---------------------------------------------------------------------------
# Canvas defaults (Tomodachi Life 256x256 canvas)
# ---------------------------------------------------------------------------

CANVAS_WIDTH  = 256
CANVAS_HEIGHT = 256


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_and_process(
    path: str | Path,
    canvas_width:  int   = CANVAS_WIDTH,
    canvas_height: int   = CANVAS_HEIGHT,
    threshold:     int   = 128,
    invert:        bool  = False,
    contrast:      float = 1.0,
) -> np.ndarray:
    """
    Load an image file and convert it to a monochrome bitmap.

    Parameters
    ----------
    path          : source image file (PNG, JPG, …)
    canvas_width  : target canvas width in pixels
    canvas_height : target canvas height in pixels
    threshold     : 0-255 grayscale cutoff; pixels >= threshold become white
    invert        : if True, swap black and white after thresholding
    contrast      : Pillow contrast enhancement factor (1.0 = no change)

    Returns
    -------
    numpy bool array, shape (canvas_height, canvas_width)
    True  = pixel should be drawn (black)
    False = background (white / skip)
    """
    img = _load(path)
    img = _resize(img, canvas_width, canvas_height)
    img = _to_grayscale(img, contrast)
    bitmap = _threshold(img, threshold)
    if invert:
        bitmap = ~bitmap
    return bitmap


def load_raw(path: str | Path) -> Image.Image:
    """Load and return the PIL image without any processing."""
    return _load(path)


def bitmap_to_image(bitmap: np.ndarray) -> Image.Image:
    """Convert a bool bitmap back to a PIL Image (for preview/debugging)."""
    arr = (~bitmap).astype(np.uint8) * 255   # True=black -> 0 (black pixel)
    return Image.fromarray(arr, mode="L")


def save_preview(bitmap: np.ndarray, out_path: str | Path) -> None:
    """Save a processed bitmap as a PNG preview."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    bitmap_to_image(bitmap).save(out_path)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def load_rgb_array(
    path: str | Path,
    canvas_width:  int = CANVAS_WIDTH,
    canvas_height: int = CANVAS_HEIGHT,
) -> np.ndarray:
    """
    Load and resize an image, returning a (H, W, 3) uint8 RGB array.
    Preserves aspect ratio on a white background of exactly (W, H).
    """
    img = _load(path)
    img.thumbnail((canvas_width, canvas_height), Image.LANCZOS)
    canvas = Image.new("RGB", (canvas_width, canvas_height), color=(255, 255, 255))
    offset_x = (canvas_width  - img.width)  // 2
    offset_y = (canvas_height - img.height) // 2
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        img = bg.convert("RGB")
    else:
        img = img.convert("RGB")
    canvas.paste(img, (offset_x, offset_y))
    return np.array(canvas, dtype=np.uint8)


def palette_preview(indices: np.ndarray, palette_rgb: np.ndarray) -> Image.Image:
    """
    Convert a palette-index image back to RGB for preview/debugging.

    indices: (H, W) int array; -1 means white background.
    palette_rgb: (N, 3) uint8 RGB palette.
    """
    height, width = indices.shape
    arr = np.full((height, width, 3), 255, dtype=np.uint8)
    mask = indices >= 0
    arr[mask] = palette_rgb[indices[mask]]
    return Image.fromarray(arr, mode="RGB")


def save_palette_preview(indices: np.ndarray, palette_rgb: np.ndarray, out_path: str | Path) -> None:
    """Save a processed palette-index image as a PNG preview."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    palette_preview(indices, palette_rgb).save(out_path)


def _load(path: str | Path) -> Image.Image:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Image not found: {p}")
    return Image.open(p)


def _resize(img: Image.Image, width: int, height: int) -> Image.Image:
    """
    Resize image to fit within (width, height), preserving aspect ratio.
    The result is pasted on a white background of exactly (width, height).
    """
    img.thumbnail((width, height), Image.LANCZOS)
    canvas = Image.new("L", (width, height), color=255)
    offset_x = (width  - img.width)  // 2
    offset_y = (height - img.height) // 2
    # Convert to RGBA temporarily to handle transparency in source images
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        img = bg.convert("L")
    else:
        img = img.convert("L")
    canvas.paste(img, (offset_x, offset_y))
    return canvas


def _to_grayscale(img: Image.Image, contrast: float) -> Image.Image:
    img = img.convert("L")
    if contrast != 1.0:
        img = ImageEnhance.Contrast(img).enhance(contrast)
    return img


def _threshold(img: Image.Image, threshold: int) -> np.ndarray:
    """Return bool array: True where pixel value < threshold (i.e. dark pixel)."""
    arr = np.array(img, dtype=np.uint8)
    return arr < threshold
