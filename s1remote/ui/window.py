"""Studio One window attach — HWND, client rect, DPI, process."""

from __future__ import annotations

import ctypes
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional, Tuple

from ..hotkeys import focus_studio_one, studio_one_running

user32 = ctypes.windll.user32

SW_RESTORE = 9


@dataclass
class WindowInfo:
    running: bool
    hwnd: Optional[int] = None
    title: str = ""
    left: int = 0
    top: int = 0
    right: int = 0
    bottom: int = 0
    width: int = 0
    height: int = 0
    client_left: int = 0
    client_top: int = 0
    client_width: int = 0
    client_height: int = 0
    dpi: int = 96
    scale: float = 1.0
    focused: bool = False
    page: str = "unknown"  # start | song | project | show | unknown

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def rect(self) -> Tuple[int, int, int, int]:
        return self.left, self.top, self.right, self.bottom

    @property
    def client_rect(self) -> Tuple[int, int, int, int]:
        return (
            self.client_left,
            self.client_top,
            self.client_left + self.client_width,
            self.client_top + self.client_height,
        )


def ensure_dpi_aware() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def studio_one_hwnd() -> Optional[int]:
    """Public HWND of the real Studio One window (not Grok / Terminal)."""
    from ..hotkeys import _enum_s1_hwnd

    return _enum_s1_hwnd()


def _window_title(hwnd: int) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _guess_page(title: str) -> str:
    low = (title or "").lower()
    if "safety" in low:
        return "safety"
    if " - " not in title:
        return "start"
    # Song / Project / Show titles look like "Studio One - Name"
    # Start page is usually just "Studio One".
    if "project" in low and "studio one -" in low:
        return "project"
    if "show" in low and "studio one -" in low:
        return "show"
    return "song"


def _client_origin(hwnd: int) -> Tuple[int, int, int, int]:
    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    wr = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(wr))
    cr = RECT()
    user32.GetClientRect(hwnd, ctypes.byref(cr))
    pt = POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    return int(pt.x), int(pt.y), int(cr.right - cr.left), int(cr.bottom - cr.top)


def _dpi_for_hwnd(hwnd: int) -> int:
    try:
        return int(ctypes.windll.user32.GetDpiForWindow(hwnd))
    except Exception:
        try:
            dc = user32.GetDC(hwnd)
            dpi = int(ctypes.windll.gdi32.GetDeviceCaps(dc, 88))
            user32.ReleaseDC(hwnd, dc)
            return dpi or 96
        except Exception:
            return 96


def attach(*, focus: bool = False) -> WindowInfo:
    """Locate Studio One. Does not launch it."""
    ensure_dpi_aware()
    info = WindowInfo(running=studio_one_running())
    hwnd = studio_one_hwnd()
    if not hwnd:
        return info
    if focus:
        focus_studio_one()
        time.sleep(0.05)
    title = _window_title(hwnd)
    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    wr = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(wr))
    cl, ct, cw, ch = _client_origin(hwnd)
    dpi = _dpi_for_hwnd(hwnd)
    fg = user32.GetForegroundWindow()
    info.hwnd = int(hwnd)
    info.title = title
    info.left, info.top = int(wr.left), int(wr.top)
    info.right, info.bottom = int(wr.right), int(wr.bottom)
    info.width = info.right - info.left
    info.height = info.bottom - info.top
    info.client_left, info.client_top = cl, ct
    info.client_width, info.client_height = cw, ch
    info.dpi = dpi
    info.scale = dpi / 96.0
    info.focused = int(fg) == int(hwnd)
    info.page = _guess_page(title)
    info.running = True
    return info


def restore_and_focus() -> WindowInfo:
    info = attach(focus=False)
    if not info.hwnd:
        return info
    user32.ShowWindow(info.hwnd, SW_RESTORE)
    focus_studio_one()
    time.sleep(0.08)
    return attach(focus=False)
