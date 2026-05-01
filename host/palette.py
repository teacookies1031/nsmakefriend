"""
Official 7×12 colour palette for Tomodachi Life drawing canvas.
"""
from __future__ import annotations

import numpy as np

OFFICIAL_COLOR_GRID: list[list[str]] = [
    ["#f2eff5","#e4dff1","#d8d9f3","#d6e1f3","#d5e9e4","#d8e4de","#dfe8df","#f2efcf","#f2dfe2","#e4d5e2","#d9cec4","#e6252a"],
    ["#d4d3df","#c6c1de","#bfc7e7","#b7d3f0","#b3e0d2","#aec3ba","#badbb1","#efeab1","#edc1bb","#d9afb9","#c9b39a","#ecea21"],
    ["#bebdc6","#a79ad8","#90a2d9","#87c9f1","#85d8b7","#83b48d","#a7d271","#f0e962","#f0a080","#d37a78","#b38b58","#3bcf22"],
    ["#9da0a8","#6919e6","#1940da","#25abf0","#20cb79","#29a814","#7ad410","#f4e316","#f37a22","#dc2f23","#996a24","#25d0de"],
    ["#7a7d88","#5515cd","#1838b6","#1b94d6","#20a864","#2a9922","#82c118","#d8d119","#d37824","#c03929","#7e5124","#1e1be6"],
    ["#4f5159","#3d119f","#123086","#1b7cb5","#208b57","#1e6f14","#668e18","#989f18","#a75f23","#8f281f","#4e2f16","#6b18e5"],
    ["#0f1012","#0e0c3d","#0b1d53","#0e446a","#0f5335","#0b4315","#445c1c","#666d1d","#4e2d1a","#441610","#1a110d","#d81bb7"],
]

PALETTE_ROWS = 7
PALETTE_COLS = 12
PALETTE_SIZE = PALETTE_ROWS * PALETTE_COLS  # 84

_FLAT = [c for row in OFFICIAL_COLOR_GRID for c in row]


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


PALETTE_RGB: np.ndarray = np.array(
    [_hex_to_rgb(c) for c in _FLAT], dtype=np.uint8
)  # shape (84, 3)


def palette_cell(index: int) -> tuple[int, int]:
    """Return (row, col) in the official 7×12 grid."""
    return divmod(index, PALETTE_COLS)


def quantize(rgb: np.ndarray, bg_threshold: int = 230) -> np.ndarray:
    """
    Quantize an (H, W, 3) uint8 RGB array to official palette indices.

    Returns (H, W) int32.  Pixels with all channels >= bg_threshold are
    treated as background and set to -1 (skip).
    """
    H, W, _ = rgb.shape
    flat = rgb.reshape(-1, 3).astype(np.int32)           # (N, 3)
    pal  = PALETTE_RGB.astype(np.int32)                  # (84, 3)
    flat_sq = np.sum(flat ** 2, axis=1, keepdims=True)   # (N, 1)
    pal_sq  = np.sum(pal  ** 2, axis=1)                  # (84,)
    dot     = flat @ pal.T                                # (N, 84)
    dist    = flat_sq + pal_sq - 2 * dot                  # (N, 84)
    indices = np.argmin(dist, axis=1).astype(np.int32)   # (N,)
    indices[np.all(flat >= bg_threshold, axis=1)] = -1
    return indices.reshape(H, W)


def reduce_to_top_colors(indices: np.ndarray, max_colors: int) -> tuple[np.ndarray, list[int]]:
    """
    Keep the most frequent palette colours and remap other drawn pixels to the
    nearest kept colour. Background pixels (-1) stay untouched.
    """
    if max_colors < 1:
        raise ValueError("max_colors must be >= 1")

    drawn = indices[indices >= 0]
    if drawn.size == 0:
        return indices.copy(), []

    counts = np.bincount(drawn, minlength=PALETTE_SIZE)
    selected_by_count = [
        int(index)
        for index in np.argsort(counts)[::-1]
        if counts[index] > 0
    ][:max_colors]
    selected = sorted(
        selected_by_count,
        key=lambda index: (
            int(PALETTE_RGB[index][0]) * 299
            + int(PALETTE_RGB[index][1]) * 587
            + int(PALETTE_RGB[index][2]) * 114
        ),
    )

    if len(selected) == int(np.count_nonzero(counts)):
        return indices.copy(), selected

    selected_rgb = PALETTE_RGB[selected].astype(np.int32)
    all_rgb = PALETTE_RGB.astype(np.int32)
    diff = all_rgb[:, None, :] - selected_rgb[None, :, :]
    nearest_selected = np.argmin(np.sum(diff * diff, axis=2), axis=1)

    remapped = indices.copy()
    mask = remapped >= 0
    remapped[mask] = np.array(selected, dtype=np.int32)[nearest_selected[remapped[mask]]]
    return remapped, selected
