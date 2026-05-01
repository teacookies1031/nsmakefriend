# AGENTS.md — AI Agent Guide for nsmakefriend

This file is the entry point for any AI agent working on this project.
Read this before touching any code.

---

## Project Summary

Draw images on Nintendo Switch via:

```text
Linux host
  -> USB serial (115200 baud)
  -> ESP32-WROOM-32 (Friend Maker firmware)
  -> Bluetooth Classic HID controller emulation
  -> Nintendo Switch drawing canvas
```

The Linux host **never** emulates a Switch controller directly.
The ESP32 is the hardware boundary between the host and the Switch.

---

## Current Status

| Phase | Status |
|-------|--------|
| Phase 0 | **Done** — toolchain builds, flashes, serial monitor works |
| Phase 1 | **Done** — Friend Maker firmware flashed, paired with Switch |
| Phase 2 | **Done** — 100x TAP A stability test passed (0 failures) |
| Phase 3 | **In progress** — cursor moves correctly; drawing button TBD for Tomodachi Life |
| Phase 4 | Not started |
| Phase 5 | Not started |

### Current blocker (Phase 3)

Testing on **Tomodachi Life: Living the Dream**.
Cursor movement (M commands) works. TAP A does not draw — the correct drawing
button for this game is not yet confirmed. Need to test in-game and verify which
button triggers drawing on the canvas.

---

## Mandatory Read Before Coding

```text
docs/friendmaker_esp32_linux_plan.md
```

Contains architecture decisions, protocol spec, phase plan, and non-goals.

---

## Primary Reference Repository

```text
Friend Maker: https://github.com/zhouxiyu1997/friendmaker
```

Do not start from scratch. Build on top of Friend Maker.

---

## Serial Protocol — Friend Maker SEQ/OK/ERR

The firmware uses a **text-based line protocol**, not binary packets.

### Command frame (host → ESP32)

```text
SEQ <session_id> <sequence> <command>\n
```

- `session_id` — 8-character lowercase hex, fixed per `SerialLink` instance
- `sequence`   — integer starting at 1, incremented per command

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
| `M <dx> <dy>` | Move cursor relatively (dx right, dy down) |
| `TAP <button> <n>` | Tap button n times |
| `HOLD <button> <ms>` | Hold button for ms milliseconds |
| `H` | Return cursor to home position |
| `E` | End session, release all inputs |
| `I` | Info query |
| `BT RESET` | Reset Bluetooth pairing |
| `L+R` | Press L+R combo (used to confirm pairing on Switch) |

Button names: `A B X Y L R ZL ZR Plus Minus Home Capture Up Down Left Right`

Baud rate: **115200**

---

## Layer Boundary — Do Not Mix

```text
Python host  =  image processing, path planning,
                Cmd builders (M / TAP / HOLD / H / E),
                SEQ framing, serial send, ACK wait, retry, pause/stop

ESP32        =  serial receive (SEQ framing), text command parsing,
                controller emulation, Bluetooth HID output to Switch
```

Do not move controller logic into Python.
Do not move image logic into firmware.

---

## What Is Already Built

```text
platformio.ini
  env:esp32dev          Phase 0 smoke test
  env:esp32dev_wireless Phase 1+ with -DSWITCH_AUTO_DRAW_USE_CLASSIC_BT=1
                        framework = arduino, espidf  (required for BT Classic)

sdkconfig.defaults      Required ESP-IDF config: FREERTOS_HZ=1000, BT_HID_ENABLED, etc.

src/
  main.cpp                        Friend Maker entry point
  controller.cpp / .h             SwitchController — cursor, buttons, palette
  protocol.cpp / .h               SEQ/OK/ERR text command parser
  classic_bt_controller_transport.cpp / .h   BT Classic HID transport
  mock_controller_transport.cpp / .h         Mock transport for testing
  controller_transport.h          Abstract transport interface
  config.h                        Timing constants, BT device name

host/controller_model.py  Cmd class — text command builders
host/serial_link.py       SEQ/OK/ERR framing, ACK wait, retry, bt_ready() check
host/image_processor.py   PIL load, resize, threshold → bool numpy bitmap
host/path_planner.py      Raster scan → DrawStep list (absolute canvas positions)
host/draw.py              CLI entry point — checks BT ready before drawing

tools/connect.py          BT connection tool — BT RESET if needed, polls until ready,
                          sends TAP A wakeup. Use before drawing.
tools/tap_a.py            Send TAP A n times — for dismissing prompts or manual tests
tools/button_test.py      Phase 1/2 validation — TAP A, M dx dy, H
tools/serial_check.py     Phase 0 port scan + BOOT message check
```

---

## Repository Layout

```text
nsmakefriend/             (repo root = PlatformIO project root)
  README.md
  AGENTS.md               (this file)
  platformio.ini
  sdkconfig.defaults      ESP-IDF config for BT Classic + Arduino
  src/                    Friend Maker firmware source (copied from upstream)
  docs/
    friendmaker_esp32_linux_plan.md
  host/
    __init__.py
    controller_model.py
    serial_link.py
    image_processor.py
    path_planner.py
    draw.py
  firmware/
    README.md
  tools/
    connect.py
    tap_a.py
    button_test.py
    serial_check.py
  examples/
    images/
  logs/
```

---

## Standard Workflow (Phase 3+)

```bash
# 1. Connect ESP32 to PC via USB

# 2. Pair with Switch (only needed after BT RESET or first time)
#    Switch → System Settings → Controllers → Change Grip/Order
python tools/connect.py --port /dev/ttyUSB0

# 3. On Switch: open drawing canvas, dismiss any prompts
python tools/tap_a.py --count 1

# 4. Draw
python -m host.draw --image examples/images/myimage.png --port /dev/ttyUSB0
```

---

## Known Issues / Firmware Fixes

### BT sniff mode report drops (fixed)

`src/classic_bt_controller_transport.cpp` — `sendCurrentInputReport()` now waits
up to 200ms for `readyForReports_` instead of immediately skipping when the Switch
is in Bluetooth sniff mode. Previously, rapid M commands caused many reports to be
dropped, making the cursor drift.

### connect.py polls instead of passive monitoring

`tools/connect.py` — `wait_ready()` sends `I` every 3s to poll BT status.
Passive line monitoring is unreliable because `bt_ready_for_reports` only appears
in the `I` command response, not as a spontaneous serial event.

---

## Implementation Order

Follow this order strictly. Do not skip phases.

```text
Phase 0  Hardware check         DONE
Phase 1  Firmware + pairing     DONE
Phase 2  Host-to-ESP32 control  DONE
Phase 3  Minimal drawing MVP    In progress — confirm drawing button first
Phase 4  Image pipeline         Not started
Phase 5  Feature parity         Not started
```

### Validation commands

```bash
# Phase 3
python -m host.draw --image examples/images/test.png --dry-run
python -m host.draw --image examples/images/test.png --port /dev/ttyUSB0

# Phase 4+
python -m host.draw --image examples/images/test.png --preview preview.png --dry-run
```

---

## Hardware Constraint

```text
Board: ESP32-WROOM-32
```

Required for Bluetooth Classic controller emulation.
Do not suggest ESP32-S2 / ESP32-S3 / ESP32-C3 unless the design explicitly
changes to USB HID or BLE.

---

## Non-Goals — Do Not Implement Early

```text
- do not rewrite ESP32 firmware from scratch
- do not implement Bluetooth HID from zero
- do not use Linux host as a direct Bluetooth controller
- do not start with full-color drawing
- do not optimize drawing speed before stability
- do not automate online gameplay or competitive actions
```

---

## Python Host Dependencies

```text
Python 3.10+
pyserial
Pillow
numpy
```

---

## Firmware / Flashing Dependencies

```text
PlatformIO Core 6+
Arduino-ESP32 + ESP-IDF 4.4 (pulled in automatically)
USB data cable
Linux serial permissions: sudo usermod -aG dialout $USER
```

---

## Key References

```text
Friend Maker (primary):
  https://github.com/zhouxiyu1997/friendmaker

UARTSwitchCon (low-level firmware reference):
  https://github.com/nullstalgia/UARTSwitchCon

PyNSController (Python proof-of-concept reference):
  https://github.com/shinyypig/pynscontroller

ESP32 Classic BT API:
  https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/bluetooth/classic_bt.html
```

---

## Safety Note

This project is for offline or non-competitive drawing automation only.
Do not use it for online competitive gameplay, resource farming, or any
activity that violates Nintendo's or a game's terms of service.
