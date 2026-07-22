"""Native window chrome (pywebview) — dark title bar / border to match Homebuy UI."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

# Homebuy page background (#0B0D10) — keep in sync with ``app.ui.theme.COLORS["bg"]``.
NATIVE_BG = "#0B0D10"
NATIVE_TITLE = "Homebuy"

# Win11+ DWM attributes (COLORREF is 0x00BBGGRR)
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_BORDER_COLOR = 34
_DWMWA_CAPTION_COLOR = 35
_DWMWA_TEXT_COLOR = 36


def _hex_to_colorref(hex_color: str) -> int:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return int(r | (g << 8) | (b << 16))


def apply_dark_frame(*, title: str = NATIVE_TITLE, bg_hex: str = NATIVE_BG) -> bool:
    """Force a dark Windows title bar + border for the Homebuy native window.

    Safe no-op on non-Windows or if the HWND is not found yet.
    """
    if sys.platform != "win32":
        return False
    user32 = ctypes.windll.user32
    dwmapi = ctypes.windll.dwmapi
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return False

    dark = ctypes.c_int(1)
    dwmapi.DwmSetWindowAttribute(
        wintypes.HWND(hwnd),
        _DWMWA_USE_IMMERSIVE_DARK_MODE,
        ctypes.byref(dark),
        ctypes.sizeof(dark),
    )

    color = ctypes.c_int(_hex_to_colorref(bg_hex))
    text = ctypes.c_int(_hex_to_colorref("#E8EDF4"))  # COLORS["text"]
    for attr in (_DWMWA_CAPTION_COLOR, _DWMWA_BORDER_COLOR):
        dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            attr,
            ctypes.byref(color),
            ctypes.sizeof(color),
        )
    dwmapi.DwmSetWindowAttribute(
        wintypes.HWND(hwnd),
        _DWMWA_TEXT_COLOR,
        ctypes.byref(text),
        ctypes.sizeof(text),
    )
    return True


def configure_native_window_args(window_args: dict) -> None:
    """Mutate NiceGUI ``app.native.window_args`` for dark chrome defaults."""
    window_args.setdefault("title", NATIVE_TITLE)
    window_args.setdefault("background_color", NATIVE_BG)
    window_args.setdefault("min_size", (960, 640))
