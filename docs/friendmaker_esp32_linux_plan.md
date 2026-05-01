# Friend Maker ESP32-WROOM-32 Linux Host — Architecture & Decisions

## Goal

Build a Linux CLI workflow for drawing images on Nintendo Switch via **ESP32-WROOM-32**,
without using the Linux host as a direct Bluetooth controller.

```text
Linux host
  -> USB serial (115200 baud)
  -> ESP32-WROOM-32 (Friend Maker firmware)
  -> Bluetooth Classic HID
  -> Nintendo Switch drawing canvas
```

---

## Current Progress

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 0 | **Done** | Toolchain, build, flash, serial monitor confirmed |
| Phase 1 | **Done** | Firmware flashed, paired with Switch, basic buttons OK |
| Phase 2 | **Done** | 100x TAP A stability — 0 failures |
| Phase 3 | **In progress** | Cursor movement works; drawing button TBD for Tomodachi Life |
| Phase 4 | Not started | |
| Phase 5 | Not started | |

---

## Architecture Decisions (Final)

- Base: **Friend Maker** — do not start from scratch
- Hardware: **ESP32-WROOM-32** only — required for Bluetooth Classic HID
- Host layer: **Python** (replaces Friend Maker's TypeScript desktop app)
- Protocol: **SEQ/OK/ERR text protocol** at 115200 baud
- Framework: **arduino + espidf** — both required; `espidf` alone does not support Arduino APIs

Do **not**:
- Use Linux host as direct Bluetooth controller
- Rewrite ESP32 firmware from scratch
- Use ESP32-S2 / S3 / C3 (no Bluetooth Classic)
- Start with color drawing before monochrome works

---

## Firmware Structure

```text
src/
  main.cpp                              Arduino setup/loop, serial read, command dispatch
  protocol.cpp / .h                     SEQ/OK/ERR parser, executeCommand()
  controller.cpp / .h                   SwitchController — moveCursor, tapButton, palette
  classic_bt_controller_transport.cpp/h Bluetooth Classic HID transport
  mock_controller_transport.cpp / .h    Mock transport (no hardware needed)
  controller_transport.h               Abstract interface
  config.h                             Timing constants, BT device name
```

### Key timing constants (config.h)

| Constant | Value |
|----------|-------|
| Baud rate | 115200 |
| Cell movement | 80 ms |
| Input delay | 40 ms |
| Button press | 60 ms |
| BT device name | "Pro Controller" |
| Pairing PIN | "1234" |

### Command timeouts (host side)

| Command | Timeout |
|---------|---------|
| `M dx dy` | 2500ms + 350ms × steps |
| `H` | 6000ms |
| `BT RESET` | 20000ms |
| Default | 2000ms |

---

## Confirmed Serial Protocol

### Command frame

```text
SEQ <session_id> <sequence> <command>\n
```

- `session_id` — 8-char lowercase hex, fixed per session
- `sequence` — integer starting at 1, increments per command

### Responses

```text
OK  <session_id> <sequence>
ERR <session_id> <sequence> <message>
BOOT <name> board=<board> transport=<transport> mock=<0|1>
```

### Commands

| Command | Effect |
|---------|--------|
| `M <dx> <dy>` | Move cursor relatively |
| `TAP <button> <n>` | Tap button n times |
| `HOLD <button> <ms>` | Hold button ms milliseconds |
| `H` | Go to home position |
| `E` | End session |
| `I` | Info / status query |
| `BT RESET` | Reset Bluetooth stack and NVS pairing data |
| `L+R` | Press L+R combo simultaneously |

---

## Layer Responsibilities

### Python Host

```text
- image loading, resize, threshold, quantization
- path planning (raster scan → DrawStep list)
- command generation (M, TAP, HOLD, H, E)
- SEQ framing, serial send
- ACK / retry
- BT ready check before drawing
```

### ESP32 Firmware

```text
- receive SEQ-framed commands
- parse text commands
- emulate Switch controller input (buttons, d-pad, sticks)
- send Bluetooth Classic HID reports to Switch
```

---

## Bluetooth Connection Flow

1. ESP32 boots → advertises as "Pro Controller"
2. Switch → System Settings → Controllers → Change Grip/Order → sees and pairs
3. After pairing: `bt_connected=true`, `bt_ready_for_reports=true`
4. Run `python tools/connect.py` to verify connection before drawing
5. After any disconnect: run `python tools/connect.py --reset` to re-advertise

### BT status fields (from `I` command)

Key fields to watch:
- `bt_connected` — ACL connection active
- `bt_ready_for_reports` — HID layer ready to send input reports
- `bt_paired` — pairing data stored in NVS

---

## Known Issues and Fixes

### BT sniff mode report drops

**Problem:** When the Switch puts the BT connection into sniff mode (power saving),
`readyForReports_` goes false. Previously, `sendCurrentInputReport` immediately
skipped (logged `WARN bt report skipped reason=not-ready`), causing cursor drift
during rapid M commands.

**Fix:** `sendCurrentInputReport` now busy-waits up to 200ms for `readyForReports_`
to recover before skipping. Applied in `src/classic_bt_controller_transport.cpp`.

### connect.py must poll, not passively monitor

**Problem:** `bt_ready_for_reports=true` only appears in `I` command response,
not as a spontaneous serial event after reconnect.

**Fix:** `tools/connect.py` `wait_ready()` sends `I` every 3s until ready.

### Drawing button varies by game

**Problem:** `TAP A` is the draw command in Friend Maker's original design,
but some games use different buttons or hold-drag mechanics.

**Status:** Under investigation for Tomodachi Life: Living the Dream.
Confirm which button draws by testing manually in-game first.

---

## Phase Plan

### Phase 3: Minimal Drawing MVP

Acceptance criteria:
```text
- draw one straight line on canvas
- draw a simple 16×16 monochrome bitmap
- draw a simple 64×64 monochrome bitmap
```

Blocker: confirm drawing button for target game.

### Phase 4: Image Pipeline

```text
- load PNG/JPG
- convert to monochrome bitmap
- generate drawing path
- send via serial with ACK/retry
- support pause / resume / safe stop
```

### Phase 5: Feature Parity

Only after Phase 4 is stable:
```text
- color palette support
- brush size support
- 256×256 canvas
- path optimization
- background removal
- progress checkpointing
```

---

## References

```text
Friend Maker:    https://github.com/zhouxiyu1997/friendmaker
UARTSwitchCon:  https://github.com/nullstalgia/UARTSwitchCon
PyNSController: https://github.com/shinyypig/pynscontroller
ESP32 BT API:   https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/bluetooth/classic_bt.html
```
