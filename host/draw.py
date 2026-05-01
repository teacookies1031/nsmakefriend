"""
draw.py — CLI entry point for the Nintendo Switch drawing pipeline.

Usage examples:

    # Draw an image
    python -m host.draw --image examples/images/test.png --port /dev/ttyUSB0

    # Dry-run: process image and print commands without sending
    python -m host.draw --image examples/images/test.png --dry-run

    # Save a preview of the processed bitmap
    python -m host.draw --image examples/images/test.png --preview out.png --dry-run

    # Adjust threshold and canvas size
    python -m host.draw --image photo.jpg --threshold 100 --width 320 --height 120

    # Invert colours (draw white on black source)
    python -m host.draw --image logo.png --invert

Pipeline:
    image -> image_processor -> bitmap
    bitmap -> path_planner   -> DrawSteps (absolute canvas positions)
    DrawSteps -> _steps_to_commands -> "M dx dy" / "TAP A 1" strings
    commands -> serial_link  -> ESP32
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Generator, Iterator

from .controller_model  import Button, Cmd
from .image_processor   import (
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    load_and_process,
    load_rgb_array,
    save_palette_preview,
    save_preview,
)
from .palette           import PALETTE_RGB, palette_cell, quantize, reduce_to_top_colors
from .path_planner      import DrawStep, count_pixels, plan_iter
from .serial_link       import SerialLink

log = logging.getLogger(__name__)

MAX_MOVE_CHUNK = 8
DEFAULT_MAX_COLORS = 84


# ---------------------------------------------------------------------------
# DrawStep -> Friend Maker command conversion
# ---------------------------------------------------------------------------

def _move_axis_commands(dx: int = 0, dy: int = 0) -> Iterator[str]:
    """
    Split longer cursor moves into short serial commands.

    Firmware executes M one cell at a time and ACKs only after the full move.
    Keeping each framed command small prevents host-side ACK timeouts during
    Bluetooth sniff-mode pauses.
    """
    if dx != 0 and dy != 0:
        raise ValueError("_move_axis_commands accepts only one non-zero axis")

    remaining = dx if dx != 0 else dy
    while remaining:
        if remaining > 0:
            step = min(remaining, MAX_MOVE_CHUNK)
        else:
            step = max(remaining, -MAX_MOVE_CHUNK)

        remaining -= step
        if dx != 0:
            yield Cmd.move(step, 0)
        else:
            yield Cmd.move(0, step)


def _steps_to_commands(
    steps: Iterator[DrawStep],
    canvas_width: int,
    canvas_height: int,
    brush_size: int = 1,
    start_x: int | None = None,
    start_y: int | None = None,
    include_end: bool = True,
) -> Generator[str, None, tuple[int, int]]:
    """
    Convert an iterator of DrawSteps (pixel-map positions) into Friend Maker
    text commands.

    The game opens the drawing screen with the cursor at the canvas centre,
    so we initialise our tracking position there.  Each DrawStep (x, y) is in
    pixel-map space; we convert to canvas space by multiplying by brush_size
    and adding the half-brush centre offset.
    """
    cursor_x = canvas_width // 2 if start_x is None else start_x
    cursor_y = canvas_height // 2 if start_y is None else start_y

    for step in steps:
        target_x = step.x * brush_size + brush_size // 2
        target_y = step.y * brush_size + brush_size // 2
        dx = target_x - cursor_x
        dy = target_y - cursor_y

        if dy != 0 and dx != 0:
            yield from _move_axis_commands(dy=dy)
            yield from _move_axis_commands(dx=dx)
        elif dy != 0:
            yield from _move_axis_commands(dy=dy)
        elif dx != 0:
            yield from _move_axis_commands(dx=dx)

        cursor_x = target_x
        cursor_y = target_y

        if step.draw:
            yield Cmd.draw()

    if include_end:
        yield Cmd.end()

    return cursor_x, cursor_y


def _color_plan_to_commands(
    palette_indices,
    palette_order: list[int],
    canvas_width: int,
    canvas_height: int,
    brush_size: int,
) -> Iterator[str]:
    """
    Draw a palette-index image one colour at a time.

    Configure up to 9 colour slots, then draw each slot's pixels.  This mirrors
    Friend Maker's official-mode flow and avoids repeatedly entering the basic
    colour picker between drawn batches.
    """
    slot_count = 9
    cursor_x = canvas_width // 2
    cursor_y = canvas_height // 2
    yield Cmd.basic_color_reset()

    for batch_start in range(0, len(palette_order), slot_count):
        batch = palette_order[batch_start : batch_start + slot_count]

        for slot, palette_index in enumerate(batch):
            row, col = palette_cell(palette_index)
            yield Cmd.basic_color(slot, row, col)

        for slot, palette_index in enumerate(batch):
            bitmap = palette_indices == palette_index
            if count_pixels(bitmap) == 0:
                continue

            yield Cmd.color(slot)
            cursor_x, cursor_y = yield from _steps_to_commands(
                plan_iter(bitmap),
                canvas_width,
                canvas_height,
                brush_size,
                start_x=cursor_x,
                start_y=cursor_y,
                include_end=False,
            )

    yield Cmd.end()


def _palette_summary(indices, palette_order: list[int]) -> str:
    counts = {
        int(index): int((indices == index).sum())
        for index in palette_order
    }
    parts = []
    for index in palette_order:
        row, col = palette_cell(index)
        red, green, blue = PALETTE_RGB[index]
        parts.append(
            f"{index}:r{row}c{col}=#{int(red):02x}{int(green):02x}{int(blue):02x}({counts[index]})"
        )
    return ", ".join(parts)


def _palette_luminance(index: int) -> int:
    red, green, blue = PALETTE_RGB[index]
    return int(red) * 299 + int(green) * 587 + int(blue) * 114


def _order_palette_for_drawing(palette_order: list[int]) -> list[int]:
    return sorted(palette_order, key=_palette_luminance, reverse=True)


# ---------------------------------------------------------------------------
# Main drawing function
# ---------------------------------------------------------------------------

def draw(
    image_path:    str | Path,
    port:          str   = "/dev/ttyUSB0",
    baud:          int   = 115200,
    canvas_width:  int   = CANVAS_WIDTH,
    canvas_height: int   = CANVAS_HEIGHT,
    brush_size:    int   = 1,
    threshold:     int   = 128,
    invert:        bool  = False,
    contrast:      float = 1.0,
    color:         bool  = False,
    max_colors:    int   = DEFAULT_MAX_COLORS,
    bg_threshold:  int   = 230,
    preview_path:  str | Path | None = None,
    dry_run:       bool  = False,
) -> None:
    if brush_size < 1:
        raise ValueError("--brush-size must be >= 1")
    if canvas_width < brush_size or canvas_height < brush_size:
        raise ValueError("--width/--height must be at least --brush-size")

    pixel_map_width  = canvas_width  // brush_size
    pixel_map_height = canvas_height // brush_size
    if canvas_width % brush_size or canvas_height % brush_size:
        log.warning(
            "Canvas %dx%d is not evenly divisible by brush %d; using pixel map %dx%d.",
            canvas_width,
            canvas_height,
            brush_size,
            pixel_map_width,
            pixel_map_height,
        )

    log.info(
        "Processing image: %s  (canvas %dx%d, pixel map %dx%d, brush %d%s)",
        image_path,
        canvas_width,
        canvas_height,
        pixel_map_width,
        pixel_map_height,
        brush_size,
        ", color" if color else "",
    )

    if color:
        rgb = load_rgb_array(
            image_path,
            canvas_width=pixel_map_width,
            canvas_height=pixel_map_height,
        )
        palette_indices = quantize(rgb, bg_threshold=bg_threshold)
        palette_indices, palette_order = reduce_to_top_colors(palette_indices, max_colors)
        palette_order = _order_palette_for_drawing(palette_order)
        total_pixels = int((palette_indices >= 0).sum())
        log.info(
            "Pixels to draw: %d / %d across %d color(s)",
            total_pixels,
            pixel_map_width * pixel_map_height,
            len(palette_order),
        )
        log.info("Palette order: %s", _palette_summary(palette_indices, palette_order))

        if preview_path:
            save_palette_preview(palette_indices, PALETTE_RGB, preview_path)
            log.info("Preview saved: %s", preview_path)

        commands = _color_plan_to_commands(
            palette_indices,
            palette_order,
            canvas_width,
            canvas_height,
            brush_size,
        )
    else:
        bitmap = load_and_process(
            image_path,
            canvas_width=pixel_map_width,
            canvas_height=pixel_map_height,
            threshold=threshold,
            invert=invert,
            contrast=contrast,
        )

        total_pixels = count_pixels(bitmap)
        log.info("Pixels to draw: %d / %d", total_pixels, pixel_map_width * pixel_map_height)

        if preview_path:
            save_preview(bitmap, preview_path)
            log.info("Preview saved: %s", preview_path)

        commands = _steps_to_commands(plan_iter(bitmap), canvas_width, canvas_height, brush_size)

    if dry_run:
        count = 0
        for cmd in commands:
            log.debug("CMD %s", cmd)
            count += 1
        log.info("Dry run complete — %d commands would be sent.", count)
        return

    log.info("Opening serial port %s @ %d baud ...", port, baud)
    with SerialLink(port=port, baud=baud) as link:
        if not link.bt_ready():
            log.error(
                "Switch is not connected. Run  python tools/connect.py  first, "
                "or use  --connect  flag to auto-connect."
            )
            return
        log.info("Switch connected. Starting draw ...  (Ctrl-C to stop safely)")
        try:
            sent = link.send_sequence(commands)
        except KeyboardInterrupt:
            link.stop()
            log.info("Interrupted by user.")
            sent = -1

    log.info("Done. Sent %d commands.", sent)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Draw an image on Nintendo Switch via ESP32 serial link."
    )
    p.add_argument("--image",     required=True, help="Source image file (PNG, JPG, ...)")
    p.add_argument("--port",      default="/dev/ttyUSB0", help="Serial port (default: /dev/ttyUSB0)")
    p.add_argument("--baud",      default=115200, type=int, help="Baud rate (default: 115200)")
    p.add_argument("--width",      default=CANVAS_WIDTH,  type=int, help="Canvas width  (default: 256)")
    p.add_argument("--height",     default=CANVAS_HEIGHT, type=int, help="Canvas height (default: 256)")
    p.add_argument("--brush-size", default=1, type=int, help="Brush size used in-game (default: 1). Use 3 to match the vendor default.")
    p.add_argument("--threshold",  default=128, type=int,   help="Grayscale threshold 0-255 (default: 128)")
    p.add_argument("--invert",    action="store_true",     help="Invert black/white")
    p.add_argument("--contrast",  default=1.0, type=float, help="Contrast enhancement (default: 1.0)")
    p.add_argument("--color",     action="store_true",     help="Draw using the Tomodachi basic colour palette")
    p.add_argument("--max-colors", default=DEFAULT_MAX_COLORS, type=int, help="Maximum colours to draw in --color mode (default: 84)")
    p.add_argument("--bg-threshold", default=230, type=int, help="RGB background cutoff for --color mode (default: 230)")
    p.add_argument("--preview",   default=None,            help="Save processed bitmap preview to PNG")
    p.add_argument("--dry-run",   action="store_true",     help="Process image but do not send over serial")
    p.add_argument("--verbose",   action="store_true",     help="Enable debug logging")
    return p


def main() -> None:
    args = _build_parser().parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
    )
    draw(
        image_path    = args.image,
        port          = args.port,
        baud          = args.baud,
        canvas_width  = args.width,
        canvas_height = args.height,
        brush_size    = args.brush_size,
        threshold     = args.threshold,
        invert        = args.invert,
        contrast      = args.contrast,
        color         = args.color,
        max_colors    = args.max_colors,
        bg_threshold  = args.bg_threshold,
        preview_path  = args.preview,
        dry_run       = args.dry_run,
    )


if __name__ == "__main__":
    main()
