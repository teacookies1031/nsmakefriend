"""
tap_a.py — Send TAP A to Nintendo Switch via ESP32.

Usage:
    python tools/tap_a.py
    python tools/tap_a.py --count 3
    python tools/tap_a.py --port /dev/ttyUSB0 --count 5
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import serial as _serial

log = logging.getLogger(__name__)

DEFAULT_PORT = "/dev/ttyUSB0"
DEFAULT_BAUD = 115200


def tap_a(port: str = DEFAULT_PORT, baud: int = DEFAULT_BAUD, count: int = 1) -> None:
    session = os.urandom(4).hex()
    s = _serial.Serial(port, baud, timeout=3)
    time.sleep(0.3)

    for seq in range(1, count + 1):
        s.write(f"SEQ {session} {seq} TAP A 1\n".encode())
        log.info("TX: TAP A 1  (%d/%d)", seq, count)
        deadline = time.time() + 4
        while time.time() < deadline:
            line = s.readline().decode("utf-8", errors="replace").strip()
            if not line:
                continue
            log.debug("RX: %s", line)
            if ("OK" in line or "ERR" in line) and session in line:
                status = "OK" if "OK" in line else "FAIL"
                log.info("  -> %s", status)
                break
        time.sleep(0.3)

    s.close()


def main() -> None:
    p = argparse.ArgumentParser(description="Send TAP A to Nintendo Switch.")
    p.add_argument("--port",    default=DEFAULT_PORT)
    p.add_argument("--baud",    default=DEFAULT_BAUD, type=int)
    p.add_argument("--count",   default=1, type=int, help="Number of TAP A to send (default: 1)")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
    )

    tap_a(port=args.port, baud=args.baud, count=args.count)


if __name__ == "__main__":
    main()
