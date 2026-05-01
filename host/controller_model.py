"""
Friend Maker text command builder.

All commands are plain ASCII strings sent over serial.
Framing (SEQ header) is handled by SerialLink — do not add it here.

Command reference (firmware/esp32/src/protocol.cpp):
    M  <dx> <dy>          Move cursor by (dx, dy) cells relative to current pos
    TAP   <button> <n>    Tap button n times
    HOLD  <button> <ms>   Hold button for ms milliseconds
    C  <slot>             Select palette slot
    BC <slot> <row> <col> Configure palette slot from basic colour grid
    H                     Return cursor to home position (top-left of canvas)
    E                     End session / release all inputs
    I                     Info query — device replies with firmware details
    BT RESET              Reset Bluetooth pairing

Button names:
    A  B  X  Y  L  R  ZL  ZR  Plus  Minus  Home  Capture
    Up  Down  Left  Right   (D-pad as named buttons)
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Button name constants
# ---------------------------------------------------------------------------

class Button:
    A       = "A"
    B       = "B"
    X       = "X"
    Y       = "Y"
    L       = "L"
    R       = "R"
    ZL      = "ZL"
    ZR      = "ZR"
    PLUS    = "Plus"
    MINUS   = "Minus"
    HOME    = "Home"
    CAPTURE = "Capture"
    UP      = "Up"
    DOWN    = "Down"
    LEFT    = "Left"
    RIGHT   = "Right"


# ---------------------------------------------------------------------------
# Command builders
# ---------------------------------------------------------------------------

class Cmd:
    """Factory for Friend Maker protocol command strings."""

    @staticmethod
    def move(dx: int, dy: int) -> str:
        """Move cursor relatively.  dx right, dy down."""
        return f"M {dx} {dy}"

    @staticmethod
    def tap(button: str, count: int = 1) -> str:
        """Tap a button n times."""
        return f"TAP {button} {count}"

    @staticmethod
    def hold(button: str, ms: int) -> str:
        """Hold a button for ms milliseconds."""
        return f"HOLD {button} {ms}"

    @staticmethod
    def draw() -> str:
        """Press the firmware's configured draw button."""
        return "P"

    @staticmethod
    def home() -> str:
        """Return cursor to home position."""
        return "H"

    @staticmethod
    def color(slot: int) -> str:
        """Select one of the 9 in-game palette slots."""
        return f"C {slot}"

    @staticmethod
    def basic_color(slot: int, row: int, col: int) -> str:
        """Configure a palette slot from the 7x12 basic colour grid."""
        return f"BC {slot} {row} {col}"

    @staticmethod
    def basic_color_reset() -> str:
        """Reset firmware-side tracking of basic colour slot positions."""
        return "BC RESET"

    @staticmethod
    def end() -> str:
        """End session and release all inputs."""
        return "E"

    @staticmethod
    def info() -> str:
        return "I"

    @staticmethod
    def bt_reset() -> str:
        return "BT RESET"
