下面呢份可以直接 copy 給 local AI agent 用。重點我已經收斂好：**Desktop App、Flet、溫柔淺色 UI、先做本機 draw.py GUI，不做 Web / X super app。**

````markdown
# Task: Build Desktop GUI for NSMakeFriend Switch Drawing Tool

## Goal

Create a desktop GUI for the existing `nsmakefriend` repo.

The GUI should wrap the existing `host/draw.py` functionality and allow users to:

1. Select an image
2. Adjust drawing parameters visually
3. Generate processed preview
4. Run dry-run analysis
5. Start drawing to device
6. View logs and device status

This is a **desktop app MVP**, not a web app.

Use **Flet** as the Python desktop UI framework.

---

## Tech Choice

Use:

```bash
pip install flet
````

Main GUI file:

```text
host/ui_flet.py
```

The GUI should import and reuse existing drawing logic instead of reimplementing image processing.

Preferred approach:

```python
from host.draw import draw
```

Do not duplicate the logic from `draw.py` unless absolutely necessary.

---

## Visual Style / UI Direction

Target users are likely female, so the overall design should feel:

* Soft
* Gentle
* Light
* Friendly
* Clean
* Beginner-friendly

Avoid dark / heavy / technical-looking UI.

### Recommended Theme

Use a light pastel theme:

```text
Background: warm off-white / soft cream
Primary color: soft pink
Secondary color: lavender / light purple
Accent color: peach / soft orange
Success color: soft green
Danger color: soft red
Text: dark brown / muted purple-gray
Cards: white / very light pink
Borders: subtle light pink / beige
```

The UI should not look like a hacker tool or command-line wrapper.
It should look like a friendly creative drawing tool.

---

## Main Layout

Use a desktop-style dashboard layout.

Recommended structure:

```text
Top Bar
------------------------------------------------
| App title: NSMakeFriend · Switch Drawing Tool |
| Help | Settings                               |
------------------------------------------------

Main Content
------------------------------------------------
| Image Panel | Parameters Panel | Preview Panel | Side Panel |
------------------------------------------------

Bottom
------------------------------------------------
| Log Output                                      |
------------------------------------------------

Footer / Status Bar
------------------------------------------------
| NS Controller: Connected / Not Connected       |
| Firmware / App Version                         |
------------------------------------------------
```

### Panel Groups

Use clear numbered sections:

```text
1. Image
2. Parameters
3. Preview
4. Analysis
5. Device
6. Actions
```

This helps users understand the workflow.

---

## UX Principle

The app flow should be:

```text
Select Image
→ Adjust Parameters
→ Generate Preview
→ Dry Run
→ Start Drawing
```

Do not let the user start drawing blindly without seeing a processed preview first.

The main UX idea is:

```text
調參 → 看 preview → 看 command count → 再畫
```

The user should always understand what will happen before sending commands to the device.

---

## Section 1: Image Panel

### Required UI Elements

* `Select Image` button
* Drag & drop image area
* Original image preview
* Image info display

Supported formats:

```text
PNG, JPG, JPEG, WEBP
```

### Image Info

Show:

```text
File name
Image width × height
File type
File size
```

Example:

```text
example.png
1024 × 1024
PNG
1.2 MB
```

### UX Notes

* After selecting an image, show thumbnail immediately.
* If no image is selected, show a soft empty state.
* Do not require the user to type image path manually.

---

## Section 2: Parameters Panel

This panel controls the arguments from `host/draw.py`.

### Core Parameters

Expose these parameters in the UI:

| UI Label             | draw.py Argument | Type                          | Default       |
| -------------------- | ---------------- | ----------------------------- | ------------- |
| Width                | `--width`        | Number input                  | `256`         |
| Height               | `--height`       | Number input                  | `256`         |
| Brush Size           | `--brush-size`   | Segmented button / select     | `1`           |
| Mode                 | `--color`        | Toggle: Black & White / Color | Black & White |
| Threshold            | `--threshold`    | Slider                        | `128`         |
| Invert               | `--invert`       | Switch                        | `False`       |
| Contrast             | `--contrast`     | Slider                        | `1.0`         |
| Max Colors           | `--max-colors`   | Slider / number input         | `84`          |
| Background Threshold | `--bg-threshold` | Slider                        | `230`         |

---

## Parameter UX Rules

### Canvas Size

Show:

```text
Canvas Size
Width:  [256]
Height: [256]
```

Add validation:

```text
width > 0
height > 0
width >= brush_size
height >= brush_size
```

Recommended warning:

```text
Width / Height should be divisible by Brush Size for better output.
```

Do not block the user unless the value is invalid.

---

### Brush Size

Use segmented control:

```text
Brush Size: [1] [2] [3] [4]
```

Default:

```text
1
```

Brush size is important because it affects final pixel density.

---

### Mode

Use segmented control:

```text
Mode:
[Black & White] [Color]
```

Default:

```text
Black & White
```

### Black & White Mode Options

Only show / enable these when mode is Black & White:

```text
Threshold
Contrast
Invert
```

Controls:

```text
Threshold: slider 0–255
Contrast: slider 0.5–3.0
Invert: switch
```

Recommended defaults:

```text
Threshold = 128
Contrast = 1.0
Invert = False
```

### Color Mode Options

Only show / enable these when mode is Color:

```text
Max Colors
Background Threshold
```

Controls:

```text
Max Colors: slider 1–84
Background Threshold: slider 0–255
```

Recommended defaults:

```text
Max Colors = 84
Background Threshold = 230
```

Do not confuse users by showing all options as equally important.

---

## Section 3: Preview Panel

The preview panel is the visual center of the app.

### Required UI Elements

* Processed preview image
* Optional tab switch:

```text
[Processed Preview] [Palette Preview]
```

For MVP, `Processed Preview` is required.
`Palette Preview` can be added later if easy.

### Preview Actions

Add button:

```text
Generate Preview
```

This should call existing draw logic with:

```text
dry_run=True
preview_path=<generated_preview_path>
```

Example internal output path:

```text
output/preview.png
```

### Preview UX

* Preview should update after clicking `Generate Preview`.
* Do not auto-run expensive drawing logic on every slider movement in the first MVP.
* It is acceptable to show a small loading indicator while preview is generating.
* Show user-friendly error if preview generation fails.

Example:

```text
Failed to generate preview. Please check image format or parameters.
```

---

## Section 4: Analysis Panel

This panel displays dry-run result and drawing statistics.

### Required Fields

Show:

```text
Pixels to Draw
Command Count
Estimated Time
Black Pixels
Color Count
Palette Usage
```

For MVP, required:

```text
Command Count
Pixels to Draw
Status
```

If some values are not available from current `draw.py`, show:

```text
—
```

Do not fake values.

### Status Card

Show a friendly status card:

```text
Ready to Draw!
Analysis complete. You can now test with Dry Run or start drawing.
```

States:

```text
No image selected
Preview generated
Analysis complete
Device connected
Drawing in progress
Drawing stopped
Error
```

Use soft colors:

```text
Green = ready / connected
Yellow = warning
Red = error
Pink / lavender = neutral
```

---

## Section 5: Device Panel

Expose device-related settings.

### Required UI Elements

```text
Serial Port
Baud Rate
Connection Status
Check Connection button
```

### Parameters

| UI Label    | draw.py Argument | Default        |
| ----------- | ---------------- | -------------- |
| Serial Port | `--port`         | `/dev/ttyUSB0` |
| Baud Rate   | `--baud`         | `115200`       |

### Serial Port UX

Use dropdown if possible.

Recommended port candidates on Linux:

```text
/dev/ttyUSB0
/dev/ttyUSB1
/dev/ttyACM0
/dev/ttyACM1
```

Also allow manual text input if easy.

### Baud Rate UX

Use dropdown:

```text
115200
```

Keep this in normal UI but visually less important than image parameters.

---

## Section 6: Actions Panel

Required buttons:

```text
Dry Run (Preview Only)
Start Drawing
Stop
```

### Button Style

Use clear color hierarchy:

```text
Dry Run: lavender / purple
Start Drawing: peach / soft orange
Stop: soft red
```

### Button Behavior

#### Dry Run

Should call draw logic with:

```text
dry_run=True
```

Dry run should not send real drawing commands.

#### Start Drawing

Should call draw logic with:

```text
dry_run=False
```

Before starting, validate:

```text
Image is selected
Preview has been generated
Serial port is set
Device is connected or user has checked connection
```

If validation fails, show friendly message.

Example:

```text
Please generate a preview before starting drawing.
```

#### Stop

For MVP:

* Include Stop button in UI
* It can be disabled if stop/cancel is not yet implemented
* If possible, implement drawing in a background thread/process so Stop can interrupt it later

Do not freeze the UI during drawing.

---

## Log Panel

Add a log panel at the bottom.

### Required Features

Show timestamped logs:

```text
[10:30:15] Image loaded: example.png
[10:30:16] Processing image...
[10:30:17] Preview generated
[10:30:17] Analysis complete
[10:30:17] Command count: 12,456
```

Add:

```text
Clear Log button
```

### UX Notes

* Logs should be readable but not too dominant.
* Use monospace font for logs.
* Use soft green for success lines if supported.
* Use soft red for error lines if supported.

---

## Presets

Add a simple preset dropdown if easy.

Recommended presets:

```text
Default
Line Art
Photo Black & White
Pixel Art
Soft Color
Full Color
```

For MVP, preset UI can exist but does not need complex save/load logic.

Example preset values:

### Default

```text
width = 256
height = 256
brush_size = 1
threshold = 128
contrast = 1.0
invert = False
color = False
max_colors = 84
bg_threshold = 230
```

### Line Art

```text
threshold = 180
contrast = 1.2
invert = False
color = False
```

### Photo Black & White

```text
threshold = 128
contrast = 1.4
invert = False
color = False
```

### Pixel Art

```text
brush_size = 2
threshold = 128
contrast = 1.0
color = False
```

### Full Color

```text
color = True
max_colors = 84
bg_threshold = 230
```

---

## Error Handling

Show user-friendly errors.

Examples:

```text
No image selected.
Invalid canvas size.
Preview generation failed.
Device not connected.
Serial port not found.
Drawing failed.
```

Also log the technical error in the log panel.

Do not crash the app on bad input.

---

## Implementation Notes

### Suggested File Structure

```text
host/
  draw.py
  ui_flet.py

output/
  preview.png
  processed.png
```

### Recommended Internal State

Maintain state like:

```python
selected_image_path
preview_path
mode
width
height
brush_size
threshold
contrast
invert
max_colors
bg_threshold
serial_port
baud_rate
is_preview_generated
is_device_connected
is_drawing
```

### Avoid Reimplementing Core Logic

The GUI should call existing `draw.py` functions.

Do not create a separate image-processing pipeline inside the UI.

---

## MVP Acceptance Criteria

The MVP is complete when:

1. User can select an image
2. Original image preview is shown
3. User can adjust core parameters
4. User can generate processed preview
5. User can run dry-run
6. Analysis / command count is shown if available
7. User can set serial port and baud rate
8. User can start drawing
9. Logs are shown in the UI
10. App does not freeze during long operations
11. Overall UI uses soft pastel light design

---

## Design Reminder

This tool is for creative drawing, not engineering debugging.

The interface should feel:

```text
friendly
soft
safe
clear
visual-first
```

Avoid:

```text
dark hacker theme
too many technical controls at once
command-line style UI
overcrowded panels
```

Main UX principle:

```text
Preview first, draw later.
```

The user should always see what will be drawn before sending commands to the device.

```
