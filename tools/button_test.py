"""
button_test.py — Phase 1 / Phase 2 button input validation.

Sends a scripted sequence of Friend Maker text commands over serial.
Watch the Nintendo Switch screen to confirm each input is received.

Usage:
    python tools/button_test.py --port /dev/ttyUSB0
    python tools/button_test.py --port /dev/ttyUSB0 --test dpad
    python tools/button_test.py --port /dev/ttyUSB0 --test all --repeat 3

Available tests:
    a       TAP A button 5 times
    dpad    Move cursor UP / RIGHT / DOWN / LEFT by 1 cell each
    home    Send H (go to home position)
    info    Send I (device replies with firmware info)
    all     Run info, a, dpad, home in sequence

What to look for on the Switch:
    a       On-screen prompt reacts or cursor selects an option
    dpad    Cursor moves in the expected direction
    home    Cursor jumps to top-left of canvas (or home menu opens)
    info    No visible Switch reaction; check --verbose for device reply

If the Switch shows NO reaction:
    - Confirm ESP32 is paired (check serial monitor for BOOT + BT ready message)
    - Run with --verbose to see TX/RX lines
    - Confirm baud rate matches firmware (default 115200)
"""

from __future__ import annotations

import argparse
import logging
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

from host.controller_model import Button, Cmd
from host.serial_link import SerialLink

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Test sequences
# ---------------------------------------------------------------------------

def test_info(link: SerialLink, repeat: int = 1) -> None:
    print(f"  Sending I (info) x{repeat} ...")
    for i in range(repeat):
        ok = link.send(Cmd.info())
        print(f"    I {i+1}/{repeat}: {'OK' if ok else 'FAIL'}")


def test_a(link: SerialLink, repeat: int = 5) -> None:
    print(f"  Sending TAP A x{repeat} ...")
    for i in range(repeat):
        ok = link.send(Cmd.tap(Button.A, 1))
        print(f"    TAP A {i+1}/{repeat}: {'OK' if ok else 'FAIL'}")


def test_dpad(link: SerialLink, repeat: int = 1) -> None:
    moves = [
        (Cmd.move(0, -1), "UP"),
        (Cmd.move(1,  0), "RIGHT"),
        (Cmd.move(0,  1), "DOWN"),
        (Cmd.move(-1, 0), "LEFT"),
    ]
    print(f"  Sending D-pad UP/RIGHT/DOWN/LEFT x{repeat} ...")
    for _ in range(repeat):
        for cmd, name in moves:
            ok = link.send(cmd)
            print(f"    {name}: {'OK' if ok else 'FAIL'}")


def test_home(link: SerialLink, repeat: int = 1) -> None:
    print(f"  Sending H (home) x{repeat} ...")
    for i in range(repeat):
        ok = link.send(Cmd.home())
        print(f"    H {i+1}/{repeat}: {'OK' if ok else 'FAIL'}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

TESTS = {
    "info": test_info,
    "a":    test_a,
    "dpad": test_dpad,
    "home": test_home,
}


def main() -> None:
    p = argparse.ArgumentParser(
        description="Phase 1/2 button input validation — watch the Switch screen."
    )
    p.add_argument("--port",    default="/dev/ttyUSB0",
                   help="Serial port (default: /dev/ttyUSB0)")
    p.add_argument("--baud",    default=115200, type=int,
                   help="Baud rate (default: 115200)")
    p.add_argument("--test",    default="a",
                   choices=list(TESTS) + ["all"],
                   help="Which test to run (default: a)")
    p.add_argument("--repeat",  default=1, type=int,
                   help="Repeat count for each test (default: 1)")
    p.add_argument("--verbose", action="store_true",
                   help="Show TX/RX lines")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
    )

    sequence = list(TESTS.keys()) if args.test == "all" else [args.test]

    print()
    print("Phase 1/2 button test")
    print(f"  port:   {args.port}  @  {args.baud} baud")
    print(f"  tests:  {', '.join(sequence)}  (repeat={args.repeat})")
    print()
    print("Watch the Nintendo Switch screen for reactions.")
    print("Press Ctrl-C to abort.\n")

    try:
        with SerialLink(port=args.port, baud=args.baud) as link:
            for name in sequence:
                print(f"[{name.upper()}]")
                TESTS[name](link, repeat=args.repeat)
                print()
    except KeyboardInterrupt:
        print("\nAborted by user.")
    except Exception as exc:
        log.error("Test failed: %s", exc)
        sys.exit(1)

    print("Phase 1 pass criteria:")
    print("  - All commands show OK (no FAIL lines above)")
    print("  - Switch reacts visibly to A and dpad inputs")


if __name__ == "__main__":
    main()
