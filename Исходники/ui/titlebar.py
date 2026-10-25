from __future__ import annotations

import ctypes
import sys

from PySide6.QtWidgets import QWidget


def apply_light_windows_titlebar(widget: QWidget) -> None:
    if sys.platform != "win32":
        return
    try:
        hwnd = int(widget.winId())
        dwm = ctypes.windll.dwmapi
        white = ctypes.c_int(0x00FFFFFF)
        dark = ctypes.c_int(0x00172033)
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(white), ctypes.sizeof(white))
        dwm.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(dark), ctypes.sizeof(dark))
    except (AttributeError, OSError, ValueError):
        pass
