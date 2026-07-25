"""
Human-like mouse input — no thrash grids, smooth moves, small jitter.

Policy:
  - Max 1 deliberate click per intent (never spam 50 points)
  - Ease cursor to target (~120–220ms) with slight overshoot correction
  - Tiny random jitter so clicks don't look robotic
  - Prefer keyboard arm over mouse when possible (callers decide)
"""

from __future__ import annotations

import random
import time
from typing import Optional, Tuple

from .logutil import log

# Hard caps — kill thrash loops
MAX_CLICKS_PER_ARM = 2
MAX_ARM_ATTEMPTS = 3
MIN_MOVE_MS = 0.10
MAX_MOVE_MS = 0.28


def _user32():
    import ctypes

    return ctypes.windll.user32


_DPI_READY = False


def ensure_dpi_aware() -> None:
    """Match ImageGrab physical pixels to SetCursorPos (fixes 125%/150% scale misses)."""
    global _DPI_READY
    if _DPI_READY:
        return
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
    except Exception:
        pass
    _DPI_READY = True


def get_cursor() -> Tuple[int, int]:
    import ctypes

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    pt = POINT()
    _user32().GetCursorPos(ctypes.byref(pt))
    return int(pt.x), int(pt.y)


def move_human(x: int, y: int, *, duration: Optional[float] = None) -> None:
    """Ease cursor to (x,y) with a short curved path."""
    ensure_dpi_aware()
    u = _user32()
    x0, y0 = get_cursor()
    x1, y1 = int(x), int(y)
    dist = max(1.0, ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5)
    if duration is None:
        # ~0.15s for short hops, up to MAX for long
        duration = min(MAX_MOVE_MS, max(MIN_MOVE_MS, dist / 2500.0))
    steps = max(6, int(duration * 60))
    # slight arc control point
    mid_x = (x0 + x1) / 2 + random.uniform(-12, 12)
    mid_y = (y0 + y1) / 2 + random.uniform(-8, 8)
    for i in range(1, steps + 1):
        t = i / steps
        # ease in-out
        te = t * t * (3 - 2 * t)
        # quadratic bezier
        xa = x0 + (mid_x - x0) * te
        ya = y0 + (mid_y - y0) * te
        xb = mid_x + (x1 - mid_x) * te
        yb = mid_y + (y1 - mid_y) * te
        xi = int(xa + (xb - xa) * te)
        yi = int(ya + (yb - ya) * te)
        u.SetCursorPos(xi, yi)
        time.sleep(duration / steps)
    # final settle with tiny jitter
    jx = x1 + random.randint(-1, 1)
    jy = y1 + random.randint(-1, 1)
    u.SetCursorPos(jx, jy)
    time.sleep(random.uniform(0.02, 0.05))


def click_human(
    x: int,
    y: int,
    *,
    alt: bool = False,
    double: bool = False,
    label: str = "",
) -> None:
    """Move like a human, then single (or double) click. Optional Alt held."""
    import ctypes

    u = _user32()
    if label:
        log(f"  human click {label} @ ({int(x)},{int(y)}) alt={alt}")
    move_human(x, y)
    if alt:
        u.keybd_event(0x12, 0, 0, 0)  # VK_MENU down
        time.sleep(0.04)
    time.sleep(random.uniform(0.03, 0.07))
    u.mouse_event(0x0002, 0, 0, 0, 0)  # left down
    time.sleep(random.uniform(0.04, 0.09))
    u.mouse_event(0x0004, 0, 0, 0, 0)  # left up
    if double:
        time.sleep(random.uniform(0.05, 0.1))
        u.mouse_event(0x0002, 0, 0, 0, 0)
        time.sleep(random.uniform(0.03, 0.06))
        u.mouse_event(0x0004, 0, 0, 0, 0)
    if alt:
        time.sleep(0.03)
        u.keybd_event(0x12, 0, 2, 0)  # key up
    time.sleep(random.uniform(0.08, 0.14))


def pause_think(seconds: float = 0.25) -> None:
    """Short human pause between actions."""
    time.sleep(seconds + random.uniform(0.0, 0.12))
