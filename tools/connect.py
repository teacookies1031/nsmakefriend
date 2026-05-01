"""
connect.py — Ensure ESP32 is connected to Nintendo Switch before drawing.

Steps:
    1. Query BT status via I command.
    2. If not ready, send BT RESET to re-advertise.
    3. Monitor serial until Switch connects (bt_ready_for_reports=true).
    4. Send TAP A to dismiss any "press any button" prompt on Switch.

Usage:
    python tools/connect.py
    python tools/connect.py --reset       # force BT RESET even if connected
    python tools/connect.py --no-tap      # skip wakeup TAP A
    python tools/connect.py --verbose
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

DEFAULT_PORT    = "/dev/ttyUSB0"
DEFAULT_BAUD    = 115200
CONNECT_TIMEOUT = 120.0   # seconds to wait for Switch to connect


class _RawLink:
    """Minimal serial helper used only by connect.py."""

    def __init__(self, port: str, baud: int) -> None:
        self._ser     = _serial.Serial(port, baud, timeout=0.5)
        self._session = os.urandom(4).hex()
        self._seq     = 0

    def close(self) -> None:
        self._ser.close()

    def cmd(self, command: str, timeout: float = 25.0) -> tuple[bool | None, dict]:
        """Send a SEQ-framed command; return (ok, info_dict)."""
        self._seq += 1
        frame = f"SEQ {self._session} {self._seq} {command}\n"
        self._ser.write(frame.encode())
        self._ser.flush()
        log.debug("TX: %s", frame.strip())

        info: dict[str, str] = {}
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            raw = self._ser.readline()
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            log.debug("RX: %s", line)
            if line.startswith("INFO "):
                kv = line[5:]
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    info[k.strip()] = v.strip()
            parts = line.split(None, 3)
            if (
                len(parts) >= 3
                and parts[1] == self._session
                and parts[2] == str(self._seq)
            ):
                return parts[0] == "OK", info
        return None, info  # timeout

    def wait_ready(self, timeout: float = CONNECT_TIMEOUT) -> bool:
        """Poll I command every 3s until bt_ready_for_reports=true or timeout."""
        log.info("Waiting for Switch to connect (timeout %ds) ...", int(timeout))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            time.sleep(3.0)
            ok, info = self.cmd("I", timeout=5.0)
            connected = info.get("bt_connected") == "true"
            ready     = info.get("bt_ready_for_reports") == "true"
            log.info("  poll — connected=%s  ready=%s", connected, ready)
            if ready:
                return True
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def connect(
    port:      str   = DEFAULT_PORT,
    baud:      int   = DEFAULT_BAUD,
    force_reset: bool = False,
    tap_wakeup:  bool = True,
) -> bool:
    """
    Establish BT connection between ESP32 and Switch.
    Returns True when ready, False on failure.
    """
    try:
        link = _RawLink(port, baud)
    except Exception as exc:
        log.error("Cannot open %s: %s", port, exc)
        return False

    try:
        time.sleep(0.5)

        ok, info = link.cmd("I", timeout=6.0)
        ready     = info.get("bt_ready_for_reports") == "true"
        connected = info.get("bt_connected") == "true"
        log.info("BT status — connected=%s  ready=%s", connected, ready)

        if force_reset or not ready:
            reason = "forced" if force_reset else "not connected"
            log.info("Sending BT RESET (%s) ...", reason)
            ok, _ = link.cmd("BT RESET", timeout=25.0)
            if not ok:
                log.error("BT RESET failed")
                return False
            log.info("BT RESET done.")
            log.info("On Switch: System Settings → Controllers → Change Grip/Order")
            ready = link.wait_ready()
            if not ready:
                log.error("Timed out waiting for Switch connection.")
                return False

        elif not ready:
            ready = link.wait_ready()
            if not ready:
                log.error("Timed out waiting for Switch connection.")
                return False

        log.info("Switch connected!")

        if tap_wakeup:
            log.info("Sending TAP A to dismiss any 'press any button' prompt ...")
            link.cmd("TAP A 1", timeout=3.0)

        log.info("ESP32 ready for drawing.")
        return True

    finally:
        link.close()


def main() -> None:
    p = argparse.ArgumentParser(
        description="Connect ESP32 to Nintendo Switch via Bluetooth."
    )
    p.add_argument("--port",    default=DEFAULT_PORT, help="Serial port (default: /dev/ttyUSB0)")
    p.add_argument("--baud",    default=DEFAULT_BAUD, type=int)
    p.add_argument("--reset",   action="store_true",  help="Force BT RESET even if already connected")
    p.add_argument("--no-tap",  action="store_true",  help="Skip TAP A wakeup after connect")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
    )

    ok = connect(
        port         = args.port,
        baud         = args.baud,
        force_reset  = args.reset,
        tap_wakeup   = not args.no_tap,
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
