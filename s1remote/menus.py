"""
Deliberate Studio One menu navigation via Alt + accelerator keys.

Keyboard-only — no mouse thrash.
"""

from __future__ import annotations

import ctypes
import time
from typing import Sequence

from .hotkeys import KEYEVENTF_KEYUP, VK, focus_studio_one

user32 = ctypes.windll.user32

# First-letter accelerators for English S1 menus (default UI language)
MENU_ACCEL = {
    "File": "F",
    "Edit": "E",
    "Song": "S",
    "Track": "T",
    "Event": "N",
    "Audio": "A",
    "Transport": "R",
    "View": "V",
    "Studio One": "U",
    "Help": "H",
}


def _tap(vk: int, hold: float = 0.04) -> None:
    user32.keybd_event(vk, 0, 0, 0)
    time.sleep(hold)
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.06)


def _tap_char(ch: str) -> None:
    ch = ch.upper()
    if ch in VK:
        _tap(VK[ch])
    elif len(ch) == 1:
        _tap(ord(ch))


def open_menu_path(path: Sequence[str], *, focus: bool = True) -> None:
    """
    Open a menu path, e.g. ['Track', 'Add Tracks…'].
    Alt focuses the menu bar, then first-letter accelerators.
    """
    if not path:
        return
    if focus and not focus_studio_one():
        raise RuntimeError("Studio One not focused")

    # Clear any open menu, then Alt to enter menu bar
    _tap(VK["ESCAPE"])
    time.sleep(0.06)
    user32.keybd_event(0x12, 0, 0, 0)  # Alt down
    time.sleep(0.04)
    user32.keybd_event(0x12, 0, KEYEVENTF_KEYUP, 0)  # Alt up
    time.sleep(0.12)

    top = path[0]
    letter = MENU_ACCEL.get(top, top[:1].upper())
    _tap_char(letter)
    time.sleep(0.18)

    for item in path[1:]:
        clean = "".join(c for c in item if c.isalnum() or c.isspace()).strip()
        if not clean:
            _tap(VK["DOWN"])
            continue
        _tap_char(clean[0])
        time.sleep(0.15)

    _tap(VK["RETURN"])
    time.sleep(0.15)


def dismiss_menus() -> None:
    if focus_studio_one():
        _tap(VK["ESCAPE"])
        time.sleep(0.04)
        _tap(VK["ESCAPE"])
