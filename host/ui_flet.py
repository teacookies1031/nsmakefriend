"""
ui_flet.py — Desktop GUI for NSMakeFriend Switch Drawing Tool.

Run:
    python -m host.ui_flet
"""
from __future__ import annotations

import io
import logging
import queue
import threading
from datetime import datetime
from pathlib import Path

import flet as ft
from PIL import Image as PILImage

from .draw import (
    DEFAULT_MAX_COLORS,
    _color_plan_to_commands,
    _order_palette_for_drawing,
    _steps_to_commands,
)
from .image_processor import (
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    load_and_process,
    load_rgb_array,
    save_palette_preview,
    save_preview,
)
from .palette import PALETTE_RGB, quantize, reduce_to_top_colors
from .path_planner import count_pixels, plan_iter

# ── Blank 1×1 PNG ───────────────────────────────────────────────────────────────
_BLANK_PNG: bytes = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc`\x00\x00"
    b"\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
)

# ── Colour palette ───────────────────────────────────────────────────────────────
BG        = "#FFF8F5"
CARD      = "#FFFFFF"
PRIMARY   = "#F4829A"   # soft pink — badges, active buttons
SECONDARY = "#C9B8E8"   # lavender — dry run
ACCENT    = "#F5C09A"   # peach — start drawing
SUCCESS   = "#6BBF8E"   # soft green
DANGER    = "#F4A0A0"   # soft red — stop
WARN      = "#F5D87A"
TEXT      = "#5D4B6E"
MUTED     = "#9B8FAE"
BORDER    = "#F0D0D8"
SUBTLE    = "#FAF0F3"   # very light pink bg for cards
LOG_BG    = "#FAFAFA"
VERSION   = "0.1.0"
FIRMWARE  = "1.2.0"

PRESETS: dict[str, dict] = {
    "Default":    dict(width=256, height=256, brush_size=1, threshold=128, contrast=1.0, invert=False, color=False, max_colors=84, bg_threshold=230),
    "Line Art":   dict(width=256, height=256, brush_size=1, threshold=180, contrast=1.2, invert=False, color=False, max_colors=84, bg_threshold=230),
    "Photo B&W":  dict(width=256, height=256, brush_size=1, threshold=128, contrast=1.4, invert=False, color=False, max_colors=84, bg_threshold=230),
    "Pixel Art":  dict(width=256, height=256, brush_size=2, threshold=128, contrast=1.0, invert=False, color=False, max_colors=84, bg_threshold=230),
    "Soft Color": dict(width=256, height=256, brush_size=1, threshold=128, contrast=1.0, invert=False, color=True,  max_colors=42, bg_threshold=220),
    "Full Color": dict(width=256, height=256, brush_size=1, threshold=128, contrast=1.0, invert=False, color=True,  max_colors=84, bg_threshold=230),
}

PORT_CANDIDATES = ["/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyACM0", "/dev/ttyACM1"]
SECS_PER_CMD = 0.058  # rough empirical estimate


# ── Helpers ──────────────────────────────────────────────────────────────────────

def _img_to_bytes(path: str | Path, max_size: int = 380) -> bytes | None:
    try:
        with PILImage.open(path) as img:
            img = img.copy()
            img.thumbnail((max_size, max_size), PILImage.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
    except Exception:
        return None


def _fmt_time(seconds: float) -> str:
    if seconds < 60:
        return f"~ {int(seconds)} sec"
    minutes = seconds / 60
    if minutes < 60:
        return f"~ {minutes:.0f} min"
    return f"~ {minutes/60:.1f} hr"


class _QueueLogHandler(logging.Handler):
    def __init__(self, q: queue.Queue):
        super().__init__()
        self._q = q

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._q.put_nowait(("log", record))
        except queue.Full:
            pass


# ── UI helpers ───────────────────────────────────────────────────────────────────

def _badge(num: int) -> ft.Container:
    return ft.Container(
        content=ft.Text(str(num), size=11, color="white", weight=ft.FontWeight.BOLD),
        bgcolor=PRIMARY, width=22, height=22, border_radius=11,
        alignment=ft.alignment.center,
    )


def _section_title(num: int, title: str, right=None) -> ft.Row:
    items = [_badge(num), ft.Text(title.upper(), size=11, weight=ft.FontWeight.BOLD,
                                   color=TEXT, letter_spacing=1.2)]
    if right:
        items.append(ft.Container(expand=True))
        items.append(right)
    return ft.Row(items, spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)


def _divider() -> ft.Divider:
    return ft.Divider(height=1, color=BORDER)


def _stat_row(icon: str, label: str, value_ctrl) -> ft.Row:
    return ft.Row([
        ft.Icon(icon, color=MUTED, size=15),
        ft.Text(label, color=MUTED, size=12, expand=True),
        value_ctrl,
    ], spacing=6)


def _card_container(content, width=None, expand=None, padding=16) -> ft.Container:
    return ft.Container(
        content=content,
        bgcolor=CARD,
        border=ft.border.all(1, BORDER), border_radius=14,
        padding=padding, width=width, expand=expand,
    )


# ── App ───────────────────────────────────────────────────────────────────────────

class NSMakeFriendApp:
    OUTPUT_DIR = Path(__file__).parent.parent / "output"

    def __init__(self, page: ft.Page):
        self.page = page
        # State
        self._image_path: Path | None = None
        self._is_bw = True
        self._width = 256
        self._height = 256
        self._brush_size = 1
        self._threshold = 128
        self._contrast = 1.0
        self._invert = False
        self._max_colors = 84
        self._bg_threshold = 230
        self._port = "/dev/ttyUSB0"
        self._baud = 115200
        self._is_preview_generated = False
        self._is_device_connected = False
        self._is_drawing = False
        self._stop_event = threading.Event()
        self._ui_queue: queue.Queue = queue.Queue(maxsize=500)
        self._log_lock = threading.Lock()
        self._analysis: dict = {}

        # Capture pipeline logs
        self._log_handler = _QueueLogHandler(self._ui_queue)
        self._log_handler.setLevel(logging.DEBUG)
        for name in ("host.draw", "host.image_processor", "host.palette",
                     "host.path_planner", "host.serial_link"):
            lg = logging.getLogger(name)
            lg.addHandler(self._log_handler)
            lg.setLevel(logging.DEBUG)

        self.OUTPUT_DIR.mkdir(exist_ok=True)
        self._init_controls()
        self._build_page()
        self.page.run_task(self._drain_queue)

    # ── Control initialisation ────────────────────────────────────────────────────

    def _init_controls(self):
        self._file_picker = ft.FilePicker()
        self.page.overlay.append(self._file_picker)

        # ── 1. Image ──────────────────────────────────────────────────────────
        self._orig_image = ft.Image(src=_BLANK_PNG, visible=False,
                                    width=170, height=160, fit=ft.BoxFit.CONTAIN)
        self._img_drop_placeholder = ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.IMAGE, color=MUTED, size=46),
                ft.Text("PNG, JPG, WEBP", color=MUTED, size=11),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER,
               alignment=ft.MainAxisAlignment.CENTER, spacing=6),
            width=170, height=160,
            border=ft.border.all(2, BORDER), border_radius=10,
            alignment=ft.alignment.center,
        )
        self._img_name  = ft.Text("—",    color=TEXT,  size=11, weight=ft.FontWeight.W_500)
        self._img_dims  = ft.Text("—",    color=MUTED, size=11)
        self._img_fmt   = ft.Text("—",    color=MUTED, size=11)
        self._img_size  = ft.Text("—",    color=MUTED, size=11)
        self._img_info_card = ft.Container(visible=False)

        self._drop_zone = ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.CLOUD_UPLOAD, color=MUTED, size=28),
                ft.Text("Drag & Drop Image\nor click to browse", color=MUTED,
                        size=11, text_align=ft.TextAlign.CENTER),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER,
               alignment=ft.MainAxisAlignment.CENTER, spacing=4),
            width=170, height=76,
            border=ft.border.all(1.5, BORDER), border_radius=10,
            alignment=ft.alignment.center,
            on_click=self._on_pick_file,
            ink=True,
        )

        # ── 2. Parameters ─────────────────────────────────────────────────────
        self._preset_dd = ft.Dropdown(
            value="Default", width=148,
            options=[ft.DropdownOption(key=k, text=k) for k in PRESETS],
            border_color=BORDER, focused_border_color=PRIMARY,
            text_size=12, color=TEXT, on_select=self._on_preset_change,
            dense=True,
        )
        self._mode_btn = ft.SegmentedButton(
            segments=[ft.Segment(value="bw",    label=ft.Text("Black & White", size=12)),
                      ft.Segment(value="color", label=ft.Text("Color", size=12))],
            selected=["bw"], allow_empty_selection=False,
            on_change=self._on_mode_change,
        )
        # Width stepper
        self._width_val  = ft.Text("256", size=13, color=TEXT,
                                   weight=ft.FontWeight.W_500, width=36,
                                   text_align=ft.TextAlign.CENTER)
        self._height_val = ft.Text("256", size=13, color=TEXT,
                                   weight=ft.FontWeight.W_500, width=36,
                                   text_align=ft.TextAlign.CENTER)
        self._size_warning = ft.Text("", color=ACCENT, size=10)

        self._brush_btn = ft.SegmentedButton(
            segments=[ft.Segment(value=str(i), label=ft.Text(str(i), size=12))
                      for i in range(1, 5)],
            selected=["1"], allow_empty_selection=False,
            on_change=self._on_brush_change,
        )
        # B&W controls
        self._thr_slider = ft.Slider(value=128, min=0, max=255, divisions=255,
                                     label="{value:.0f}", active_color=PRIMARY,
                                     expand=True, on_change=self._on_threshold_change)
        self._thr_val_text = ft.Text("128", color=TEXT, size=12, width=32,
                                     text_align=ft.TextAlign.RIGHT)
        self._con_slider = ft.Slider(value=1.0, min=0.5, max=3.0, divisions=25,
                                     label="{value:.1f}", active_color=PRIMARY,
                                     expand=True, on_change=self._on_contrast_change)
        self._con_val_text = ft.Text("1.20", color=TEXT, size=12, width=36,
                                     text_align=ft.TextAlign.RIGHT)
        self._invert_sw = ft.Switch(value=False, active_color=PRIMARY,
                                    on_change=self._on_invert_change)
        self._bw_group = ft.Column(visible=True, spacing=6)

        # Color controls
        self._mc_slider = ft.Slider(value=84, min=1, max=84, divisions=83,
                                    label="{value:.0f}", active_color=PRIMARY,
                                    expand=True, on_change=self._on_max_colors_change)
        self._mc_val_text = ft.Text("84", color=TEXT, size=12, width=28,
                                    text_align=ft.TextAlign.RIGHT)
        self._bgt_slider = ft.Slider(value=230, min=0, max=255, divisions=255,
                                     label="{value:.0f}", active_color=PRIMARY,
                                     expand=True, on_change=self._on_bgt_change)
        self._bgt_val_text = ft.Text("230", color=TEXT, size=12, width=32,
                                     text_align=ft.TextAlign.RIGHT)
        self._color_group = ft.Column(visible=False, spacing=6)

        # ── 3. Preview ────────────────────────────────────────────────────────
        self._preview_img = ft.Image(src=_BLANK_PNG, visible=False,
                                     expand=True, fit=ft.BoxFit.CONTAIN)
        self._palette_img = ft.Image(src=_BLANK_PNG, visible=False,
                                     expand=True, fit=ft.BoxFit.CONTAIN)
        self._preview_placeholder = ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.AUTO_AWESOME, color=MUTED, size=52),
                ft.Text("Generate preview to see result", color=MUTED, size=12),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER,
               alignment=ft.MainAxisAlignment.CENTER),
            expand=True, border=ft.border.all(2, BORDER), border_radius=10,
            alignment=ft.alignment.center,
        )
        self._preview_ring  = ft.ProgressRing(visible=False, color=PRIMARY,
                                               width=28, height=28)
        self._active_tab = "processed"
        self._tab_processed = ft.TextButton(
            "Processed Preview",
            on_click=lambda _: self._switch_preview_tab("processed"),
            style=ft.ButtonStyle(color=PRIMARY),
        )
        self._tab_palette = ft.TextButton(
            "Palette Preview",
            on_click=lambda _: self._switch_preview_tab("palette"),
            style=ft.ButtonStyle(color=MUTED),
        )
        self._gen_btn = ft.ElevatedButton(
            "Generate Preview", icon=ft.Icons.AUTO_AWESOME,
            on_click=self._on_gen_preview,
            style=ft.ButtonStyle(bgcolor=PRIMARY, color="white"),
        )

        # ── 4. Analysis ───────────────────────────────────────────────────────
        def _stat_text(v="—") -> ft.Text:
            return ft.Text(v, color=TEXT, size=13, weight=ft.FontWeight.BOLD,
                           text_align=ft.TextAlign.RIGHT)

        self._stat_pixels    = _stat_text()
        self._stat_commands  = _stat_text()
        self._stat_time      = _stat_text()
        self._stat_black     = _stat_text()
        self._stat_colors    = _stat_text()
        self._stat_palette   = _stat_text()
        self._status_dot     = ft.Container(width=20, height=20, bgcolor=SUCCESS,
                                            border_radius=10,
                                            content=ft.Icon(ft.Icons.CHECK, color="white",
                                                            size=12),
                                            alignment=ft.alignment.center,
                                            visible=False)
        self._status_title   = ft.Text("No image selected", color=MUTED, size=13,
                                       weight=ft.FontWeight.BOLD)
        self._status_body    = ft.Text("Select an image to get started.", color=MUTED,
                                       size=11)
        self._status_card    = ft.Container(visible=False)

        # ── 5. Device ─────────────────────────────────────────────────────────
        import glob as _glob
        ports = list(PORT_CANDIDATES)
        for p in sorted(set(_glob.glob("/dev/ttyUSB*") + _glob.glob("/dev/ttyACM*"))):
            if p not in ports:
                ports.append(p)
        self._port_dd = ft.Dropdown(
            value=self._port,
            options=[ft.DropdownOption(key=p, text=p) for p in ports],
            label="Serial Port", border_color=BORDER, focused_border_color=PRIMARY,
            text_size=12, color=TEXT, on_select=self._on_port_change, expand=True,
        )
        self._baud_dd = ft.Dropdown(
            value="115200",
            options=[ft.DropdownOption(key="115200", text="115200"),
                     ft.DropdownOption(key="9600",   text="9600")],
            label="Baud Rate", border_color=BORDER, focused_border_color=PRIMARY,
            text_size=12, color=TEXT, on_select=self._on_baud_change,
        )
        self._conn_dot    = ft.Container(width=8, height=8, bgcolor=MUTED,
                                         border_radius=4)
        self._conn_label  = ft.Text("Not connected", color=MUTED, size=12)
        self._conn_btn    = ft.OutlinedButton(
            "Check Connection", icon=ft.Icons.LINK,
            on_click=self._on_check_conn,
            style=ft.ButtonStyle(color=SECONDARY),
        )

        # ── 6. Actions ────────────────────────────────────────────────────────
        self._dry_btn  = ft.ElevatedButton(
            "Dry Run (Preview Only)", icon=ft.Icons.SCIENCE,
            on_click=self._on_dry_run,
            style=ft.ButtonStyle(bgcolor=SECONDARY, color="white"),
            expand=True,
        )
        self._draw_btn = ft.ElevatedButton(
            "Start Drawing", icon=ft.Icons.PLAY_ARROW,
            on_click=self._on_start_drawing,
            style=ft.ButtonStyle(bgcolor=ACCENT, color="white"),
            expand=True,
        )
        self._stop_btn = ft.ElevatedButton(
            "Stop", icon=ft.Icons.STOP,
            on_click=self._on_stop, disabled=True,
            style=ft.ButtonStyle(bgcolor=DANGER, color="white"),
            expand=True,
        )

        # ── Log ───────────────────────────────────────────────────────────────
        self._log_list = ft.ListView(expand=True, spacing=1, auto_scroll=True)

        # ── Footer ────────────────────────────────────────────────────────────
        self._footer_conn_dot   = ft.Container(width=8, height=8, bgcolor=MUTED,
                                               border_radius=4)
        self._footer_conn_label = ft.Text("NS Controller: Not Connected",
                                          color=MUTED, size=11)

    # ── Layout ───────────────────────────────────────────────────────────────────

    def _param_slider_row(self, label: str, slider, val_ctrl, lo: str, hi: str) -> ft.Column:
        return ft.Column([
            ft.Row([ft.Text(label, color=TEXT, size=12, expand=True), val_ctrl], spacing=4),
            ft.Row([ft.Text(lo, color=MUTED, size=10, width=20),
                    slider,
                    ft.Text(hi, color=MUTED, size=10, width=28,
                            text_align=ft.TextAlign.RIGHT)], spacing=2),
        ], spacing=2)

    def _stepper_widget(self, label: str, val_ctrl,
                        on_minus, on_plus) -> ft.Row:
        def _step_btn(icon, cb):
            return ft.Container(
                content=ft.Icon(icon, size=14, color=MUTED),
                on_click=cb, ink=True,
                border=ft.border.all(1, BORDER), border_radius=4,
                padding=ft.padding.symmetric(horizontal=5, vertical=3),
            )
        return ft.Row([
            ft.Text(label, color=MUTED, size=11, width=44),
            _step_btn(ft.Icons.REMOVE, on_minus),
            val_ctrl,
            _step_btn(ft.Icons.ADD, on_plus),
        ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _build_page(self):
        self.page.title = "NSMakeFriend · Switch Drawing Tool"
        self.page.bgcolor = BG
        self.page.padding = 0
        self.page.window = ft.Window(
            width=1300, height=900, min_width=980, min_height=680,
        )

        # Populate param slider groups
        self._bw_group.controls = [
            self._param_slider_row("Threshold", self._thr_slider,
                                   self._thr_val_text, "0", "255"),
            self._param_slider_row("Contrast",  self._con_slider,
                                   self._con_val_text, "0.5", "3.0"),
            ft.Row([ft.Text("Invert", color=TEXT, size=12, expand=True),
                    self._invert_sw], spacing=4),
        ]
        self._color_group.controls = [
            self._param_slider_row("Max Colors",      self._mc_slider,
                                   self._mc_val_text, "1", "84"),
            self._param_slider_row("BG Threshold",    self._bgt_slider,
                                   self._bgt_val_text, "0", "255"),
        ]

        # ── Top bar ───────────────────────────────────────────────────────────
        top_bar = ft.Container(
            content=ft.Row([
                ft.Container(width=80),   # left spacer
                ft.Row([
                    ft.Icon(ft.Icons.BRUSH, color=PRIMARY, size=20),
                    ft.Text("NSMakeFriend", size=17, weight=ft.FontWeight.BOLD, color=TEXT),
                    ft.Text("·  Switch Drawing Tool", size=13, color=MUTED),
                ], spacing=6),
                ft.Row([
                    ft.TextButton("Help",     icon=ft.Icons.HELP_OUTLINE,
                                  style=ft.ButtonStyle(color=MUTED)),
                    ft.TextButton("Settings", icon=ft.Icons.SETTINGS_OUTLINED,
                                  style=ft.ButtonStyle(color=MUTED)),
                ], spacing=0),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
               vertical_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor=CARD,
            padding=ft.padding.symmetric(horizontal=20, vertical=10),
            border=ft.border.only(bottom=ft.BorderSide(1, BORDER)),
        )

        # ── Col 1: Image panel ────────────────────────────────────────────────
        img_info_rows = ft.Column([
            ft.Row([ft.Text("Format",    color=MUTED, size=11, expand=True),
                    self._img_fmt], spacing=4),
            ft.Row([ft.Text("Size",      color=MUTED, size=11, expand=True),
                    self._img_dims], spacing=4),
            ft.Row([ft.Text("File Size", color=MUTED, size=11, expand=True),
                    self._img_size], spacing=4),
        ], spacing=4)
        self._img_info_card = _card_container(
            ft.Column([
                ft.Text("Image Info", size=11, color=MUTED,
                        weight=ft.FontWeight.W_500),
                _divider(),
                img_info_rows,
            ], spacing=6),
            padding=10,
        )
        self._img_info_card.visible = False

        col1 = _card_container(
            ft.Column([
                _section_title(1, "Image"),
                _divider(),
                ft.ElevatedButton(
                    "Select Image", icon=ft.Icons.FOLDER_OPEN,
                    on_click=self._on_pick_file,
                    style=ft.ButtonStyle(bgcolor=PRIMARY, color="white"),
                    expand=True,
                ),
                ft.Stack([self._img_drop_placeholder, self._orig_image],
                         width=170, height=160),
                self._img_info_card,
                self._drop_zone,
            ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            width=208, padding=14,
        )

        # ── Col 2: Parameters panel ───────────────────────────────────────────
        load_preset_row = ft.Row([
            ft.Text("Load Preset", color=MUTED, size=11),
            self._preset_dd,
            ft.IconButton(icon=ft.Icons.SAVE_OUTLINED, icon_size=16,
                          icon_color=MUTED, tooltip="Save preset"),
        ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        canvas_row = ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.LINK, color=MUTED, size=14),
                ft.Text("Canvas Size", color=TEXT, size=12),
            ], spacing=4),
            ft.Row([
                self._stepper_widget("Width",  self._width_val,
                                     self._on_width_minus, self._on_width_plus),
                ft.Container(width=12),
                self._stepper_widget("Height", self._height_val,
                                     self._on_height_minus, self._on_height_plus),
            ], spacing=0),
            self._size_warning,
        ], spacing=4)

        bw_options_header = ft.Row([
            ft.Icon(ft.Icons.WB_SUNNY_OUTLINED, color=PRIMARY, size=15),
            ft.Text("Black & White Options", color=TEXT, size=12,
                    weight=ft.FontWeight.W_500),
        ], spacing=6)

        color_options_header = ft.Row([
            ft.Icon(ft.Icons.PALETTE_OUTLINED, color=PRIMARY, size=15),
            ft.Text("Color Options", color=TEXT, size=12,
                    weight=ft.FontWeight.W_500),
        ], spacing=6)

        reset_btn = ft.TextButton(
            "Reset to Defaults", icon=ft.Icons.REFRESH,
            on_click=self._on_reset_defaults,
            style=ft.ButtonStyle(color=MUTED),
        )

        col2 = _card_container(
            ft.Column([
                ft.Row([
                    _section_title(2, "Parameters"),
                ], spacing=8),
                load_preset_row,
                _divider(),
                ft.Column([
                    ft.Text("Mode", color=MUTED, size=11),
                    self._mode_btn,
                ], spacing=4),
                _divider(),
                canvas_row,
                _divider(),
                ft.Column([
                    ft.Text("Brush Size", color=MUTED, size=11),
                    self._brush_btn,
                ], spacing=4),
                _divider(),
                ft.Column([bw_options_header, self._bw_group], spacing=8,
                          visible=True, ref=None),
                ft.Column([color_options_header, self._color_group], spacing=8,
                          visible=False, ref=None),
                reset_btn,
            ], spacing=10, scroll=ft.ScrollMode.AUTO),
            width=310, padding=14,
        )
        # keep references to the options columns for visibility toggle
        inner = col2.content
        self._bw_options_col    = inner.controls[9]
        self._color_options_col = inner.controls[10]

        # ── Col 3: Preview panel ──────────────────────────────────────────────
        tab_row = ft.Row([
            ft.Container(
                content=self._tab_processed,
                border=ft.border.only(bottom=ft.BorderSide(2, PRIMARY)),
                padding=ft.padding.only(bottom=2),
            ),
            self._tab_palette,
        ], spacing=0)

        preview_area = ft.Container(
            content=ft.Stack([
                self._preview_placeholder,
                self._preview_img,
                self._palette_img,
            ]),
            expand=True, border_radius=10,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )
        self._zoom_label = ft.Text("100%", color=MUTED, size=11)

        col3 = _card_container(
            ft.Column([
                ft.Row([
                    _section_title(3, "Preview"),
                    ft.Container(expand=True),
                    self._gen_btn,
                    self._preview_ring,
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                tab_row,
                _divider(),
                preview_area,
            ], spacing=8, expand=True),
            expand=True, padding=14,
        )

        # ── Col 4: Analysis + Device + Actions ────────────────────────────────
        status_card_inner = ft.Container(
            content=ft.Column([
                ft.Row([self._status_dot, self._status_title], spacing=8),
                self._status_body,
            ], spacing=4),
            bgcolor=SUBTLE, border_radius=10, padding=10,
            border=ft.border.all(1, BORDER),
            visible=False,
        )
        self._status_card_container = status_card_inner

        analysis_card = _card_container(
            ft.Column([
                _section_title(4, "Analysis"),
                _divider(),
                _stat_row(ft.Icons.GRID_ON,      "Pixels to Draw",  self._stat_pixels),
                _stat_row(ft.Icons.TERMINAL,     "Command Count",   self._stat_commands),
                _stat_row(ft.Icons.SCHEDULE,     "Estimated Time",  self._stat_time),
                _stat_row(ft.Icons.CIRCLE,       "Black Pixels",    self._stat_black),
                _stat_row(ft.Icons.PALETTE,      "Color Count",     self._stat_colors),
                _stat_row(ft.Icons.COLOR_LENS,   "Palette Usage",   self._stat_palette),
                _divider(),
                status_card_inner,
            ], spacing=8),
            width=270, padding=14,
        )

        device_card = _card_container(
            ft.Column([
                _section_title(5, "Device"),
                _divider(),
                ft.Text("Serial Port", color=MUTED, size=11),
                ft.Row([self._port_dd,
                        ft.IconButton(icon=ft.Icons.REFRESH, icon_size=16,
                                      icon_color=MUTED, on_click=self._on_refresh_ports,
                                      tooltip="Refresh ports")],
                       spacing=4),
                ft.Text("Baud Rate", color=MUTED, size=11),
                self._baud_dd,
                ft.Row([self._conn_dot, self._conn_label], spacing=6),
                self._conn_btn,
            ], spacing=8),
            width=270, padding=14,
        )

        actions_card = _card_container(
            ft.Column([
                _section_title(6, "Actions"),
                _divider(),
                ft.Row([self._dry_btn],  expand=True),
                ft.Row([self._draw_btn], expand=True),
                ft.Row([self._stop_btn], expand=True),
            ], spacing=10),
            width=270, padding=14,
        )

        col4 = ft.Column(
            [analysis_card, device_card, actions_card],
            spacing=12, width=282,
            scroll=ft.ScrollMode.AUTO,
        )

        # ── Log panel ─────────────────────────────────────────────────────────
        log_panel = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.LIST_ALT, color=MUTED, size=14),
                    ft.Text("LOG", size=11, weight=ft.FontWeight.BOLD,
                            color=TEXT, letter_spacing=1.2),
                    ft.Container(expand=True),
                    ft.TextButton("Clear", icon=ft.Icons.DELETE_OUTLINE,
                                  on_click=self._on_clear_log,
                                  style=ft.ButtonStyle(color=MUTED)),
                ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Container(
                    content=self._log_list,
                    bgcolor=LOG_BG, border=ft.border.all(1, BORDER),
                    border_radius=8, padding=8, height=140,
                ),
            ], spacing=6),
            bgcolor=CARD,
            border=ft.border.only(top=ft.BorderSide(1, BORDER)),
            padding=ft.padding.fromLTRB(14, 10, 14, 10),
        )

        # ── Footer ────────────────────────────────────────────────────────────
        footer = ft.Container(
            content=ft.Row([
                ft.Row([self._footer_conn_dot, self._footer_conn_label], spacing=6),
                ft.Row([
                    ft.Text(f"Firmware: {FIRMWARE}", color=MUTED, size=11),
                    ft.Text("  ·  ", color=BORDER, size=11),
                    ft.Text(f"App Version: {VERSION}", color=MUTED, size=11),
                ], spacing=0),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            bgcolor=CARD,
            padding=ft.padding.symmetric(horizontal=20, vertical=6),
            border=ft.border.only(top=ft.BorderSide(1, BORDER)),
        )

        # ── Main content row ──────────────────────────────────────────────────
        main_row = ft.Container(
            content=ft.Row(
                [col1, col2, col3, col4],
                spacing=12,
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.START,
                expand=True,
            ),
            expand=True,
            padding=ft.padding.symmetric(horizontal=14, vertical=12),
        )

        self.page.add(ft.Column(
            [top_bar, main_row, log_panel, footer],
            spacing=0, expand=True,
        ))

    # ── Event handlers ────────────────────────────────────────────────────────────

    async def _on_pick_file(self, e):
        files = await self._file_picker.pick_files(
            dialog_title="Select Image",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["png", "jpg", "jpeg", "webp"],
        )
        if not files:
            return
        path = Path(files[0].path)
        self._image_path = path
        self._is_preview_generated = False
        self._reset_stats()
        self._load_original_image(path)
        self._log(f"Image Loaded: {path.name}")
        self._set_status("image_loaded")
        self.page.update()

    def _load_original_image(self, path: Path):
        img_bytes = _img_to_bytes(path, 170)
        if img_bytes is None:
            self._log("Failed to load image.", "error")
            return
        self._orig_image.src = img_bytes
        self._orig_image.visible = True
        self._img_drop_placeholder.visible = False
        try:
            with PILImage.open(path) as img:
                w, h = img.size
                fmt  = img.format or path.suffix[1:].upper()
                sz   = path.stat().st_size
                self._img_fmt.value  = fmt
                self._img_dims.value = f"{w} × {h}"
                sz_str = f"{sz/1024:.1f} KB" if sz < 1_048_576 else f"{sz/1_048_576:.1f} MB"
                self._img_size.value = sz_str
                self._img_name.value = path.name
        except Exception:
            pass
        self._img_info_card.visible = True

    def _on_mode_change(self, e):
        self._is_bw = "bw" in e.control.selected
        self._bw_options_col.visible    = self._is_bw
        self._color_options_col.visible = not self._is_bw
        self.page.update()

    # ── Width / Height steppers ───────────────────────────────────────────────

    def _on_width_minus(self, e):
        self._width = max(self._brush_size, self._width - self._brush_size)
        self._width_val.value = str(self._width)
        self._check_size_warning()
        self.page.update()

    def _on_width_plus(self, e):
        self._width += self._brush_size
        self._width_val.value = str(self._width)
        self._check_size_warning()
        self.page.update()

    def _on_height_minus(self, e):
        self._height = max(self._brush_size, self._height - self._brush_size)
        self._height_val.value = str(self._height)
        self._check_size_warning()
        self.page.update()

    def _on_height_plus(self, e):
        self._height += self._brush_size
        self._height_val.value = str(self._height)
        self._check_size_warning()
        self.page.update()

    def _check_size_warning(self):
        if self._width % self._brush_size or self._height % self._brush_size:
            self._size_warning.value = f"Tip: canvas divisible by brush size ({self._brush_size}) gives best output."
        else:
            self._size_warning.value = ""

    def _on_brush_change(self, e):
        sel = e.control.selected
        if sel:
            self._brush_size = int(sel[0])
        self._check_size_warning()
        self.page.update()

    def _on_threshold_change(self, e):
        self._threshold = int(e.control.value)
        self._thr_val_text.value = str(self._threshold)
        self.page.update()

    def _on_contrast_change(self, e):
        self._contrast = round(e.control.value, 2)
        self._con_val_text.value = f"{self._contrast:.2f}"
        self.page.update()

    def _on_invert_change(self, e):
        self._invert = e.control.value

    def _on_max_colors_change(self, e):
        self._max_colors = int(e.control.value)
        self._mc_val_text.value = str(self._max_colors)
        self.page.update()

    def _on_bgt_change(self, e):
        self._bg_threshold = int(e.control.value)
        self._bgt_val_text.value = str(self._bg_threshold)
        self.page.update()

    def _on_port_change(self, e):
        self._port = e.control.value or "/dev/ttyUSB0"
        self._is_device_connected = False
        self._conn_label.value = "Not connected"
        self._conn_label.color = MUTED
        self._conn_dot.bgcolor = MUTED
        self.page.update()

    def _on_baud_change(self, e):
        try:
            self._baud = int(e.control.value)
        except (TypeError, ValueError):
            pass

    def _on_refresh_ports(self, e):
        import glob as _glob
        ports = list(PORT_CANDIDATES)
        for p in sorted(set(_glob.glob("/dev/ttyUSB*") + _glob.glob("/dev/ttyACM*"))):
            if p not in ports:
                ports.append(p)
        self._port_dd.options = [ft.DropdownOption(key=p, text=p) for p in ports]
        self.page.update()

    def _on_preset_change(self, e):
        name = e.control.value
        if name not in PRESETS:
            return
        p = PRESETS[name]
        self._width       = p["width"]
        self._height      = p["height"]
        self._brush_size  = p["brush_size"]
        self._threshold   = p["threshold"]
        self._contrast    = p["contrast"]
        self._invert      = p["invert"]
        self._is_bw       = not p["color"]
        self._max_colors  = p["max_colors"]
        self._bg_threshold = p["bg_threshold"]
        self._sync_param_controls()
        self._log(f"Preset applied: {name}")
        self.page.update()

    def _on_reset_defaults(self, e):
        p = PRESETS["Default"]
        self._preset_dd.value = "Default"
        self._width = p["width"]; self._height = p["height"]
        self._brush_size = p["brush_size"]
        self._threshold = p["threshold"]; self._contrast = p["contrast"]
        self._invert = p["invert"]; self._is_bw = not p["color"]
        self._max_colors = p["max_colors"]; self._bg_threshold = p["bg_threshold"]
        self._sync_param_controls()
        self._log("Parameters reset to defaults.")
        self.page.update()

    def _sync_param_controls(self):
        self._width_val.value  = str(self._width)
        self._height_val.value = str(self._height)
        self._brush_btn.selected   = [str(self._brush_size)]
        self._mode_btn.selected    = ["bw" if self._is_bw else "color"]
        self._bw_options_col.visible    = self._is_bw
        self._color_options_col.visible = not self._is_bw
        self._thr_slider.value    = float(self._threshold)
        self._thr_val_text.value  = str(self._threshold)
        self._con_slider.value    = self._contrast
        self._con_val_text.value  = f"{self._contrast:.2f}"
        self._invert_sw.value     = self._invert
        self._mc_slider.value     = float(self._max_colors)
        self._mc_val_text.value   = str(self._max_colors)
        self._bgt_slider.value    = float(self._bg_threshold)
        self._bgt_val_text.value  = str(self._bg_threshold)
        self._check_size_warning()

    # ── Preview / Dry-run / Draw ──────────────────────────────────────────────────

    def _switch_preview_tab(self, tab: str):
        self._active_tab = tab
        if tab == "processed":
            self._tab_processed.style = ft.ButtonStyle(color=PRIMARY)
            self._tab_palette.style   = ft.ButtonStyle(color=MUTED)
            self._preview_img.visible = self._is_preview_generated
            self._palette_img.visible = False
        else:
            self._tab_processed.style = ft.ButtonStyle(color=MUTED)
            self._tab_palette.style   = ft.ButtonStyle(color=PRIMARY)
            self._palette_img.visible = self._is_preview_generated
            self._preview_img.visible = False
        self.page.update()

    def _on_gen_preview(self, e):
        if not self._image_path:
            self._log("No image selected.", "error")
            return
        self._set_busy(True)
        self._preview_ring.visible = True
        self._preview_placeholder.visible = True
        self._preview_img.visible = False
        self._palette_img.visible = False
        self.page.update()
        threading.Thread(target=self._bg_gen_preview, daemon=True).start()

    def _bg_gen_preview(self):
        try:
            params = self._params()
            pw = params["width"] // params["brush_size"]
            ph = params["height"] // params["brush_size"]
            self._log(f"Canvas: {params['width']} × {params['height']}, Brush Size: {params['brush_size']}")

            preview_path  = self.OUTPUT_DIR / "preview.png"
            palette_path  = self.OUTPUT_DIR / "palette_preview.png"

            if params["color"]:
                self._log("Color Mode")
                rgb = load_rgb_array(self._image_path, canvas_width=pw, canvas_height=ph)
                indices = quantize(rgb, bg_threshold=params["bg_threshold"])
                indices, order = reduce_to_top_colors(indices, params["max_colors"])
                save_palette_preview(indices, PALETTE_RGB, str(preview_path))
                save_palette_preview(indices, PALETTE_RGB, str(palette_path))
                pixels = int((indices >= 0).sum())
                n_colors = len(order)
                total = pw * ph
                self._stat_pixels.value  = f"{pixels:,}"
                self._stat_black.value   = "—"
                self._stat_colors.value  = str(n_colors)
                self._stat_palette.value = f"{n_colors} colors"
                self._analysis = {"pixels": pixels, "colors": n_colors, "total": total}
            else:
                self._log("Black & White Mode")
                self._log(f"Threshold: {params['threshold']}, Contrast: {params['contrast']:.2f}, Invert: {'On' if params['invert'] else 'Off'}")
                bitmap = load_and_process(
                    self._image_path, canvas_width=pw, canvas_height=ph,
                    threshold=params["threshold"], invert=params["invert"],
                    contrast=params["contrast"],
                )
                save_preview(bitmap, str(preview_path))
                pixels = count_pixels(bitmap)
                total  = pw * ph
                pct    = pixels / total * 100 if total else 0
                self._stat_pixels.value  = f"{pixels:,}"
                self._stat_black.value   = f"{pixels:,} ({pct:.1f}%)"
                self._stat_colors.value  = "—"
                self._stat_palette.value = "—"
                self._analysis = {"pixels": pixels, "total": total}

            pb = _img_to_bytes(preview_path, 400)
            if pb:
                self._preview_img.src = pb
                self._preview_img.visible = (self._active_tab == "processed")
                self._preview_placeholder.visible = False

            palb = _img_to_bytes(palette_path, 400) if palette_path.exists() else None
            if palb:
                self._palette_img.src = palb
                self._palette_img.visible = (self._active_tab == "palette")

            self._is_preview_generated = True
            self._log("Processed preview generated")
            self._set_status("preview_generated")
        except Exception as ex:
            self._log(f"Preview failed: {ex}", "error")
            self._set_status("error")
        finally:
            self._preview_ring.visible = False
            self._set_busy(False)
            self.page.update()

    def _on_dry_run(self, e):
        if not self._image_path:
            self._log("No image selected.", "error")
            return
        self._set_busy(True)
        self.page.update()
        threading.Thread(target=self._bg_dry_run, daemon=True).start()

    def _bg_dry_run(self):
        try:
            params = self._params()
            pw = params["width"] // params["brush_size"]
            ph = params["height"] // params["brush_size"]
            self._log("Starting dry run…")
            count = 0
            if params["color"]:
                rgb = load_rgb_array(self._image_path, canvas_width=pw, canvas_height=ph)
                indices = quantize(rgb, bg_threshold=params["bg_threshold"])
                indices, order = reduce_to_top_colors(indices, params["max_colors"])
                order = _order_palette_for_drawing(order)
                for _ in _color_plan_to_commands(
                    indices, order, params["width"], params["height"], params["brush_size"]
                ):
                    count += 1
            else:
                bitmap = load_and_process(
                    self._image_path, canvas_width=pw, canvas_height=ph,
                    threshold=params["threshold"], invert=params["invert"],
                    contrast=params["contrast"],
                )
                for _ in _steps_to_commands(
                    plan_iter(bitmap), params["width"], params["height"], params["brush_size"]
                ):
                    count += 1

            est = count * SECS_PER_CMD
            self._stat_commands.value = f"{count:,}"
            self._stat_time.value     = _fmt_time(est)
            self._log(f"Analysis complete")
            self._log(f"Command count: {count:,}")
            self._set_status("analysis_complete")
        except Exception as ex:
            self._log(f"Dry run failed: {ex}", "error")
            self._set_status("error")
        finally:
            self._set_busy(False)
            self.page.update()

    def _on_start_drawing(self, e):
        if not self._image_path:
            self._log("No image selected.", "error")
            return
        if not self._is_preview_generated:
            self._log("Please generate a preview before drawing.", "error")
            return
        self._stop_event.clear()
        self._is_drawing = True
        self._set_busy(True)
        self._stop_btn.disabled = False
        self._set_status("drawing")
        self.page.update()
        threading.Thread(target=self._bg_draw, daemon=True).start()

    def _bg_draw(self):
        try:
            params = self._params()
            self._log(f"Opening serial on {self._port} @ {self._baud}…")
            from .draw import draw as _draw
            _draw(
                image_path=self._image_path,
                port=self._port, baud=self._baud,
                canvas_width=params["width"], canvas_height=params["height"],
                brush_size=params["brush_size"],
                threshold=params["threshold"], contrast=params["contrast"],
                invert=params["invert"], color=params["color"],
                max_colors=params["max_colors"], bg_threshold=params["bg_threshold"],
                dry_run=False,
            )
            self._log("Drawing complete!")
            self._set_status("done")
        except Exception as ex:
            self._log(f"Drawing failed: {ex}", "error")
            self._set_status("error")
        finally:
            self._is_drawing = False
            self._set_busy(False)
            self._stop_btn.disabled = True
            self.page.update()

    def _on_stop(self, e):
        self._stop_event.set()
        self._log("Stop requested.")
        self._stop_btn.disabled = True
        self.page.update()

    def _on_check_conn(self, e):
        threading.Thread(target=self._bg_check_conn, daemon=True).start()

    def _bg_check_conn(self):
        try:
            from .serial_link import SerialLink
            self._log(f"Checking {self._port}…")
            with SerialLink(port=self._port, baud=self._baud) as link:
                ok = link.bt_ready()
            if ok:
                self._is_device_connected = True
                self._conn_dot.bgcolor    = SUCCESS
                self._conn_label.value    = "Connected"
                self._conn_label.color    = SUCCESS
                self._footer_conn_dot.bgcolor    = SUCCESS
                self._footer_conn_label.value    = "NS Controller: Connected"
                self._footer_conn_label.color    = SUCCESS
                self._log("Device connected.")
                self._set_status("device_connected")
            else:
                self._conn_dot.bgcolor  = DANGER
                self._conn_label.value  = "Not connected"
                self._conn_label.color  = MUTED
                self._log("Device not found. Check Nintendo Switch pairing.", "error")
        except Exception as ex:
            self._conn_dot.bgcolor  = DANGER
            self._conn_label.value  = "Error"
            self._conn_label.color  = DANGER
            self._log(f"Connection error: {ex}", "error")
        self.page.update()

    def _on_clear_log(self, e):
        self._log_list.controls.clear()
        self.page.update()

    # ── Helpers ───────────────────────────────────────────────────────────────────

    def _params(self) -> dict:
        return dict(
            width=max(1, self._width), height=max(1, self._height),
            brush_size=self._brush_size,
            threshold=self._threshold, contrast=self._contrast, invert=self._invert,
            color=not self._is_bw,
            max_colors=self._max_colors, bg_threshold=self._bg_threshold,
        )

    def _set_busy(self, busy: bool):
        self._gen_btn.disabled  = busy
        self._dry_btn.disabled  = busy
        self._draw_btn.disabled = busy

    def _reset_stats(self):
        for ctrl in (self._stat_pixels, self._stat_commands, self._stat_time,
                     self._stat_black, self._stat_colors, self._stat_palette):
            ctrl.value = "—"

    def _set_status(self, state: str):
        _map = {
            "no_image":          (MUTED,     False,  "No image selected",
                                              "Select an image to get started."),
            "image_loaded":      (SECONDARY, False,  "Image Loaded",
                                              "Adjust parameters and generate a preview."),
            "preview_generated": (SUCCESS,   True,   "Preview Ready",
                                              "Run Dry Run to count commands, or start drawing."),
            "analysis_complete": (SUCCESS,   True,   "Ready to Draw!",
                                              "Analysis complete. You can now test with Dry Run or start drawing."),
            "device_connected":  (SUCCESS,   True,   "Device Connected",
                                              "Switch is connected. Ready to start drawing."),
            "drawing":           (ACCENT,    False,  "Drawing in Progress…",
                                              "Sending commands to the Switch."),
            "done":              (SUCCESS,   True,   "Drawing Complete!",
                                              "All commands sent successfully."),
            "stopped":           (WARN,      False,  "Drawing Stopped",
                                              "Stopped by user."),
            "error":             (DANGER,    False,  "Something Went Wrong",
                                              "Check the log panel for details."),
        }
        color, show_check, title, body = _map.get(
            state, (MUTED, False, state, ""))
        self._status_dot.bgcolor = color
        self._status_dot.visible = show_check
        self._status_title.value = title
        self._status_title.color = color
        self._status_body.value  = body
        self._status_card_container.visible = True
        self._status_card_container.border  = ft.border.all(1, color + "66")

    def _log(self, text: str, level: str = "info"):
        _colors = {"info": TEXT, "error": DANGER, "warning": WARN, "success": SUCCESS}
        ts = datetime.now().strftime("%H:%M:%S")
        color = _colors.get(level, TEXT)
        row = ft.Text(f"[{ts}] {text}", size=11, color=color,
                      font_family="monospace", selectable=True)
        with self._log_lock:
            self._log_list.controls.append(row)
            if len(self._log_list.controls) > 500:
                self._log_list.controls.pop(0)

    async def _drain_queue(self):
        import asyncio
        while True:
            updated = False
            while not self._ui_queue.empty():
                try:
                    item = self._ui_queue.get_nowait()
                except queue.Empty:
                    break
                if item[0] == "log":
                    rec: logging.LogRecord = item[1]
                    lvl = rec.levelname.lower()
                    level = ("error"   if lvl in ("error", "critical") else
                             "warning" if lvl == "warning" else "info")
                    self._log(rec.getMessage(), level)
                    updated = True
            if updated:
                self.page.update()
            await asyncio.sleep(0.25)


# ── Entry point ───────────────────────────────────────────────────────────────────

async def main(page: ft.Page):
    NSMakeFriendApp(page)


if __name__ == "__main__":
    ft.app(target=main)
