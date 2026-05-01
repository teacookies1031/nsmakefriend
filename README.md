# Friend Maker Linux ESP32 Host

A Linux-friendly host workflow for drawing images on Nintendo Switch using an **ESP32-WROOM-32** as the controller-emulation bridge.

Based on [`friendmaker`](https://github.com/zhouxiyu1997/friendmaker): convert an image into drawing commands, send those commands over serial to an ESP32, and let the ESP32 act as a Nintendo Switch Pro Controller via Bluetooth Classic.

---

## Current Status

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 0 | Hardware and serial check | **Done** |
| Phase 1 | Friend Maker firmware + Switch pairing | **Done** |
| Phase 2 | Host-to-ESP32 serial control | **Done** — 100x TAP A, 0 failures |
| Phase 3 | Minimal drawing MVP | **In progress** — cursor works; drawing button TBD for Tomodachi Life |
| Phase 4 | Full image pipeline | Not started |
| Phase 5 | Friend Maker feature parity | Not started |

---

## Architecture

```text
Image
-> host/image_processor.py   resize, threshold, monochrome bitmap
-> host/path_planner.py      raster scan, DrawStep list
-> host/draw.py              convert to M/TAP commands, BT ready check
-> host/serial_link.py       SEQ framing, serial send, ACK/retry
-> USB serial (/dev/ttyUSB0)
-> ESP32-WROOM-32 (Friend Maker firmware)
-> Bluetooth Classic HID
-> Nintendo Switch drawing canvas
```

The Linux host **never** directly emulates a Switch controller.
The ESP32 is the hardware boundary.

---

## Quick Start

### Pair and connect

```bash
# First time or after BT RESET:
# On Switch → System Settings → Controllers → Change Grip/Order
python tools/connect.py --port /dev/ttyUSB0

# Dismiss any "press any button" prompt on Switch
python tools/tap_a.py --count 1
```

### Draw an image

```bash
# Dry run — check command count and preview
python -m host.draw --image examples/images/myimage.png --preview preview.png --dry-run

# Live draw
python -m host.draw --image examples/images/myimage.png --port /dev/ttyUSB0
```

---

## Serial Protocol

Friend Maker uses a **text-based line protocol**, not binary packets.

### Command frame (host → ESP32)

```text
SEQ <session_id> <sequence> <command>\n
```

### Acknowledgement (ESP32 → host)

```text
OK  <session_id> <sequence>
ERR <session_id> <sequence> <message>
```

### Boot message

```text
BOOT <name> board=<board> transport=<transport> mock=<0|1>
```

### Available commands

| Command | Effect |
|---------|--------|
| `M <dx> <dy>` | Move cursor by (dx, dy) cells relative to current position |
| `TAP <button> <n>` | Tap button n times |
| `HOLD <button> <ms>` | Hold button for ms milliseconds |
| `H` | Return cursor to home position (top-left of canvas) |
| `E` | End session, release all inputs |
| `I` | Info query |
| `BT RESET` | Reset Bluetooth pairing |
| `L+R` | Press L+R combo (confirm pairing on Switch) |

Button names: `A B X Y L R ZL ZR Plus Minus Home Capture Up Down Left Right`

Baud rate: **115200**

---

## Hardware

```text
Board: ESP32-WROOM-32
```

Required for Bluetooth Classic controller emulation.
Do not switch to ESP32-S2 / ESP32-S3 / ESP32-C3.

---

## Repository Layout

```text
nsmakefriend/
  README.md
  AGENTS.md
  platformio.ini          PlatformIO project (root-level)
  sdkconfig.defaults      ESP-IDF config (BT Classic, FreeRTOS HZ=1000)
  src/                    Friend Maker firmware source
  docs/
    friendmaker_esp32_linux_plan.md
  host/
    __init__.py
    controller_model.py   Cmd class — command builders
    serial_link.py        SEQ/OK/ERR protocol, bt_ready() check
    image_processor.py    PIL load, resize, threshold → bitmap
    path_planner.py       Raster scan → DrawStep list
    draw.py               CLI entry point
  firmware/
    README.md
  tools/
    connect.py            BT connection tool (use before drawing)
    tap_a.py              Send TAP A (dismiss prompts, manual test)
    button_test.py        Phase 1/2 button validation
    serial_check.py       Phase 0 port scan
  examples/
    images/
  logs/
```

---

## Dependencies

### Firmware / Flashing

```text
PlatformIO Core 6+
Arduino-ESP32 + ESP-IDF 4.4 (pulled in automatically)
USB data cable
Linux serial permissions — sudo usermod -aG dialout $USER
```

### Python Host

```text
Python 3.10+
pyserial
Pillow
numpy
```

---

## Known Issues

### BT sniff mode (fixed in firmware)

`src/classic_bt_controller_transport.cpp` — `sendCurrentInputReport()` now waits
up to 200ms for `readyForReports_` instead of immediately dropping the report.
Previously, rapid M commands during drawing caused cursor drift.

---

## References

```text
Friend Maker:    https://github.com/zhouxiyu1997/friendmaker
UARTSwitchCon:  https://github.com/nullstalgia/UARTSwitchCon
PyNSController: https://github.com/shinyypig/pynscontroller
ESP32 BT API:   https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/bluetooth/classic_bt.html
```
