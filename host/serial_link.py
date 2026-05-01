"""
Serial link — Friend Maker text-based SEQ/OK/ERR protocol.

Each command is framed as:
    SEQ <session_id> <sequence> <command>\n

Where:
    session_id  8-character lowercase hex string, fixed for the lifetime of
                this SerialLink instance
    sequence    integer starting at 1, incremented per command

The ESP32 replies with:
    OK  <session_id> <sequence>
    ERR <session_id> <sequence> <message>

On boot the ESP32 sends:
    BOOT <name> board=<board> transport=<transport> mock=<0|1>

Reference: apps/desktop/src/serial/sender.ts in friendmaker repo
"""

from __future__ import annotations

import logging
import os
import time
from typing import Iterator

import serial  # pyserial

log = logging.getLogger(__name__)

DEFAULT_PORT    = "/dev/ttyUSB0"
DEFAULT_BAUD    = 115200
DEFAULT_TIMEOUT = 2.0   # seconds — overridden per command type by _cmd_timeout()


# ---------------------------------------------------------------------------
# SerialLink
# ---------------------------------------------------------------------------

class SerialLink:
    """
    Manages the serial connection to the ESP32 and sends framed text commands.

    Usage:
        with SerialLink("/dev/ttyUSB0") as link:
            link.send("TAP A 1")
            link.send("M 5 0")
    """

    def __init__(
        self,
        port:        str   = DEFAULT_PORT,
        baud:        int   = DEFAULT_BAUD,
        max_retries: int   = 3,
    ) -> None:
        self.port        = port
        self.baud        = baud
        self.max_retries = max_retries

        # Session ID is fixed per instance; sequence resets to 0 on new session.
        self._session_id: str          = os.urandom(4).hex()
        self._seq:        int          = 0
        self._ser:        serial.Serial | None = None
        self._stop_requested           = False
        self._paused                   = False

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        if self._ser and self._ser.is_open:
            return
        self._ser = serial.Serial(
            port=self.port,
            baudrate=self.baud,
            timeout=0.1,  # short readline timeout; we loop with a deadline
        )
        log.info("Opened %s @ %d baud  session=%s", self.port, self.baud, self._session_id)
        self._wait_for_boot()

    def close(self) -> None:
        if self._ser and self._ser.is_open:
            try:
                self._write_line("E")
            except Exception:
                pass
            self._ser.close()
            log.info("Closed %s", self.port)

    def __enter__(self) -> SerialLink:
        self.open()
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Flow control
    # ------------------------------------------------------------------

    def pause(self) -> None:
        self._paused = True
        log.info("Paused.")

    def resume(self) -> None:
        self._paused = False
        log.info("Resumed.")

    def stop(self) -> None:
        self._stop_requested = True
        log.info("Stop requested.")

    def reset_stop(self) -> None:
        self._stop_requested = False

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    def send(self, command: str) -> bool:
        """
        Send one command string (without framing).  Handles framing, ACK
        waiting, and retries internally.

        Returns True on OK, False if all retries are exhausted or stop was
        requested.
        """
        if self._ser is None or not self._ser.is_open:
            raise RuntimeError("Serial port is not open. Call open() first.")

        while self._paused and not self._stop_requested:
            time.sleep(0.1)
        if self._stop_requested:
            return False

        timeout = _cmd_timeout(command)

        for attempt in range(1, self.max_retries + 1):
            self._seq += 1
            framed = f"SEQ {self._session_id} {self._seq} {command}"
            self._write_line(framed)
            log.debug("TX [%d] %s", self._seq, command)

            result = self._wait_ack(self._session_id, self._seq, timeout)
            if result is True:
                return True
            if result is False:
                log.warning("ERR on command %r (attempt %d/%d)", command, attempt, self.max_retries)
            else:
                log.warning("Timeout on command %r (attempt %d/%d)", command, attempt, self.max_retries)
                # On timeout bump the sequence so the next attempt is a fresh frame
                # (the firmware may have missed it entirely)

        log.error("Command failed after %d retries: %r", self.max_retries, command)
        return False

    def send_sequence(self, commands: Iterator[str]) -> int:
        """
        Send an iterator of command strings.
        Returns the number of successfully sent commands.
        Stops early on failure or if stop() was called.
        """
        sent = 0
        for cmd in commands:
            if self._stop_requested:
                log.info("Stopped after %d commands.", sent)
                break
            if self.send(cmd):
                sent += 1
            else:
                log.error("Aborting at command %d.", sent + 1)
                break
        return sent

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _write_line(self, text: str) -> None:
        self._ser.write((text + "\n").encode("ascii"))
        self._ser.flush()

    def _wait_ack(self, sid: str, seq: int, timeout: float) -> bool | None:
        """
        Read lines until we see OK/ERR for this (sid, seq).
        Returns True (OK), False (ERR), or None (timeout).
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            raw = self._ser.readline()
            if not raw:
                continue
            line = raw.decode("ascii", errors="replace").strip()
            if not line:
                continue
            log.debug("RX %s", line)
            parts = line.split(None, 3)
            if len(parts) >= 3 and parts[1] == sid and parts[2] == str(seq):
                if parts[0] == "OK":
                    return True
                if parts[0] == "ERR":
                    msg = parts[3] if len(parts) > 3 else ""
                    log.warning("ERR from device: %s", msg)
                    return False
        return None  # timeout

    def bt_ready(self) -> bool:
        """
        Send I and return True if bt_ready_for_reports=true.
        Use this to confirm the Switch is connected before drawing.
        """
        if self._ser is None or not self._ser.is_open:
            raise RuntimeError("Serial port is not open.")
        self._seq += 1
        framed = f"SEQ {self._session_id} {self._seq} I"
        self._write_line(framed)
        log.debug("TX [%d] I", self._seq)
        deadline = time.monotonic() + 6.0
        ready = False
        while time.monotonic() < deadline:
            raw = self._ser.readline()
            if not raw:
                continue
            line = raw.decode("ascii", errors="replace").strip()
            if not line:
                continue
            log.debug("RX %s", line)
            if "bt_ready_for_reports=true" in line:
                ready = True
            parts = line.split(None, 3)
            if (
                len(parts) >= 3
                and parts[1] == self._session_id
                and parts[2] == str(self._seq)
                and parts[0] in ("OK", "ERR")
            ):
                return ready
        return False

    def _wait_for_boot(self, timeout: float = 5.0) -> None:
        """
        Read lines until BOOT message or timeout.
        Not fatal if no BOOT is seen (firmware may already be running).
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            raw = self._ser.readline()
            if not raw:
                continue
            line = raw.decode("ascii", errors="replace").strip()
            if line.startswith("BOOT"):
                log.info("Device boot: %s", line)
                return
            log.debug("Pre-boot: %s", line)
        log.info("No BOOT message seen within %.1fs (device may already be running).", timeout)


# ---------------------------------------------------------------------------
# Per-command timeout (mirrors desktop sender logic)
# ---------------------------------------------------------------------------

def _cmd_timeout(cmd: str) -> float:
    parts = cmd.strip().split()
    if not parts:
        return DEFAULT_TIMEOUT
    verb = parts[0].upper()
    if verb == "M" and len(parts) >= 3:
        try:
            steps = abs(int(parts[1])) + abs(int(parts[2]))
        except ValueError:
            return DEFAULT_TIMEOUT

        # Firmware performs one press/release cycle per cell:
        # BUTTON_PRESS_DURATION_MS + INPUT_DELAY_MS = about 100ms, plus serial,
        # Switch UI, and occasional Bluetooth sniff-mode recovery overhead.
        return 2.5 + steps * 0.35
    if verb == "BT":
        return 20.0
    if verb == "H":
        return 6.0
    if verb == "BC":
        return 15.0
    if verb == "PC":
        return 20.0
    if verb == "C":
        return 8.0
    return DEFAULT_TIMEOUT
