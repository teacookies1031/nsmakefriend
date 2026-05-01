"""
serial_check.py — Phase 0 hardware check script.

Verifies the Linux host can see the ESP32 on a serial port and receives
the BOOT message from the Friend Maker firmware.

Usage:
    python tools/serial_check.py
    python tools/serial_check.py --port /dev/ttyACM0
    python tools/serial_check.py --list

Checks performed:
    1. List USB/ACM serial ports
    2. Confirm the device file exists and is accessible
    3. Open the port at 115200 baud
    4. Wait up to 5 s for the BOOT message from the firmware
"""

from __future__ import annotations

import argparse
import sys
import time

try:
    import serial
    import serial.tools.list_ports
    PYSERIAL_AVAILABLE = True
except ImportError:
    PYSERIAL_AVAILABLE = False

DEFAULT_PORT = "/dev/ttyUSB0"
DEFAULT_BAUD = 115200
BOOT_TIMEOUT = 5.0   # seconds to wait for BOOT message


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_list_ports() -> list[str]:
    if not PYSERIAL_AVAILABLE:
        _warn("pyserial not installed. Run: pip install pyserial")
        return []
    ports = serial.tools.list_ports.comports()
    return [
        p.device for p in ports
        if "USB" in (p.description or "").upper()
        or "ACM" in p.device
        or "USB" in p.device
        or p.vid is not None
    ]


def check_device_file(port: str) -> bool:
    import os, stat
    try:
        mode = os.stat(port).st_mode
        if stat.S_ISCHR(mode):
            _ok(f"{port} exists and is a character device.")
            return True
        else:
            _warn(f"{port} exists but is not a character device.")
            return False
    except FileNotFoundError:
        _fail(f"{port} not found. Is the ESP32 plugged in?")
        return False
    except PermissionError:
        _fail(
            f"Permission denied on {port}. "
            "Add yourself to dialout:  sudo usermod -aG dialout $USER"
        )
        return False


def check_port_open(port: str, baud: int) -> bool:
    if not PYSERIAL_AVAILABLE:
        _warn("pyserial not installed.")
        return False
    try:
        with serial.Serial(port=port, baudrate=baud, timeout=0.1):
            _ok(f"Port opened: {port} @ {baud} baud")
            return True
    except serial.SerialException as exc:
        _fail(f"Could not open {port}: {exc}")
        return False


def check_boot_message(port: str, baud: int) -> bool:
    """
    Open port and wait for the BOOT line from Friend Maker firmware.
    Expected format:  BOOT <name> board=<board> transport=<t> mock=<0|1>
    """
    if not PYSERIAL_AVAILABLE:
        return False
    try:
        with serial.Serial(port=port, baudrate=baud, timeout=0.1) as ser:
            _info(f"Waiting up to {BOOT_TIMEOUT:.0f}s for BOOT message ...")
            _info("(Press the ESP32 reset button if nothing appears.)")
            deadline = time.monotonic() + BOOT_TIMEOUT
            while time.monotonic() < deadline:
                raw = ser.readline()
                if not raw:
                    continue
                line = raw.decode("ascii", errors="replace").strip()
                if not line:
                    continue
                _info(f"RX: {line}")
                if line.startswith("BOOT"):
                    _ok(f"BOOT message received: {line}")
                    return True
            _warn(
                "No BOOT message seen. This is expected if the smoke-test "
                "firmware (main.cpp) is still flashed instead of the "
                "Friend Maker firmware."
            )
            _info(
                "With smoke-test firmware you should see 'ESP32 upload OK' "
                "and 'tick' lines instead — that still confirms Phase 0."
            )
            return False
    except serial.SerialException as exc:
        _fail(f"Serial error: {exc}")
        return False


# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------

def _ok(msg: str)   -> None: print(f"  [PASS]  {msg}")
def _fail(msg: str) -> None: print(f"  [FAIL]  {msg}", file=sys.stderr)
def _warn(msg: str) -> None: print(f"  [WARN]  {msg}")
def _info(msg: str) -> None: print(f"  [INFO]  {msg}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_checks(port: str, baud: int) -> None:
    print("=" * 60)
    print("  nsmakefriend — Phase 0 Serial Check")
    print("=" * 60)

    print("\n[1] Scanning for USB/ACM serial ports ...")
    found = check_list_ports()
    if found:
        _ok(f"Found {len(found)} port(s): {', '.join(found)}")
        if port not in found:
            _warn(
                f"Requested port {port!r} not in detected list. "
                "Try a different --port."
            )
    else:
        _warn("No USB/ACM ports detected. Check cable and permissions.")

    print("\n[2] Device file check ...")
    if not check_device_file(port):
        print("\nCheck failed at device file. Stopping.")
        sys.exit(1)

    print("\n[3] Opening serial port ...")
    if not check_port_open(port, baud):
        print("\nCheck failed at port open. Stopping.")
        sys.exit(1)

    print("\n[4] Waiting for firmware boot message ...")
    check_boot_message(port, baud)

    print()
    print("=" * 60)
    print("  Phase 0 check complete.")
    print("  If port opened OK, the toolchain is working.")
    print("  Next: flash Friend Maker firmware and re-run for BOOT message.")
    print("=" * 60)


def main() -> None:
    p = argparse.ArgumentParser(
        description="Phase 0: verify Linux host can communicate with ESP32."
    )
    p.add_argument("--port", default=DEFAULT_PORT, help=f"Serial port (default: {DEFAULT_PORT})")
    p.add_argument("--baud", default=DEFAULT_BAUD, type=int, help="Baud rate (default: 115200)")
    p.add_argument("--list", action="store_true", help="List detected USB/ACM ports and exit")
    args = p.parse_args()

    if args.list:
        ports = check_list_ports()
        if ports:
            print("Detected serial ports:")
            for port in ports:
                print(f"  {port}")
        else:
            print("No USB/ACM serial ports detected.")
        return

    run_checks(args.port, args.baud)


if __name__ == "__main__":
    main()
