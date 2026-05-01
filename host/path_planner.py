"""
Path planner: converts a monochrome bitmap into a sequence of DrawSteps.

Each DrawStep is (x, y, draw) where:
  x, y  -- absolute canvas coordinates (0-based, top-left origin)
  draw  -- True if the draw button should be held at this position

Strategy: raster scan with run-length encoding
  - Scan rows top to bottom
  - Within each row, find runs of consecutive black pixels
  - For each run: navigate to start, hold draw button, sweep right, release

The output is a flat list of DrawSteps.  The serial sender translates these
into actual controller state transitions (cursor movement + button presses).

A DrawStep with draw=False is a cursor move with the button released.
A DrawStep with draw=True  is a cursor move (or hold) with the button held.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import numpy as np


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class DrawStep:
    x:    int
    y:    int
    draw: bool  # True = hold draw button at this (x, y)


@dataclass(slots=True)
class DrawRun:
    """A horizontal run of pixels to draw on a single row."""
    row:   int
    x_start: int
    x_end:   int  # inclusive


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def plan(bitmap: np.ndarray) -> list[DrawStep]:
    """
    Convert a bool bitmap to a DrawStep list.

    Parameters
    ----------
    bitmap : 2-D bool array, shape (height, width)
             True = pixel to draw, False = skip

    Returns
    -------
    List of DrawStep in execution order.
    """
    steps: list[DrawStep] = []
    for run in _raster_runs(bitmap):
        _append_run(steps, run)
    return steps


def plan_iter(bitmap: np.ndarray) -> Iterator[DrawStep]:
    """Generator version of plan() — useful for large canvases."""
    for run in _raster_runs(bitmap):
        yield from _run_to_steps(run)


def count_pixels(bitmap: np.ndarray) -> int:
    """Return number of pixels that will be drawn."""
    return int(np.sum(bitmap))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _raster_runs(bitmap: np.ndarray) -> Iterator[DrawRun]:
    """Yield every horizontal run of True pixels in raster order."""
    height, width = bitmap.shape
    for row in range(height):
        line = bitmap[row]
        in_run    = False
        run_start = 0
        for col in range(width):
            if line[col] and not in_run:
                in_run    = True
                run_start = col
            elif not line[col] and in_run:
                in_run = False
                yield DrawRun(row=row, x_start=run_start, x_end=col - 1)
        if in_run:
            yield DrawRun(row=row, x_start=run_start, x_end=width - 1)


def _append_run(steps: list[DrawStep], run: DrawRun) -> None:
    for step in _run_to_steps(run):
        steps.append(step)


def _run_to_steps(run: DrawRun) -> Iterator[DrawStep]:
    # Move to run start with button released
    yield DrawStep(x=run.x_start, y=run.row, draw=False)
    # Sweep across the run with button held
    for x in range(run.x_start, run.x_end + 1):
        yield DrawStep(x=x, y=run.row, draw=True)
