"""
Windows hotkeys sent to the focused Studio One window.

Studio One has no full public IPC API. For menu/view actions that are not on
the Mackie surface, we focus the Studio One process and emit keystrokes that
match default Studio One shortcuts (Windows).
"""

from __future__ import annotations

import ctypes
import subprocess
import time
from typing import Optional

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Virtual key codes
VK = {
    "SPACE": 0x20,
    "RETURN": 0x0D,
    "ENTER": 0x0D,
    "ESCAPE": 0x1B,
    "ESC": 0x1B,
    "TAB": 0x09,
    "DELETE": 0x2E,
    "BACK": 0x08,
    "HOME": 0x24,
    "END": 0x23,
    "LEFT": 0x25,
    "UP": 0x26,
    "RIGHT": 0x27,
    "DOWN": 0x28,
    "F1": 0x70,
    "F2": 0x71,
    "F3": 0x72,
    "F4": 0x73,
    "F5": 0x74,
    "F6": 0x75,
    "F7": 0x76,
    "F8": 0x77,
    "F9": 0x78,
    "F10": 0x79,
    "F11": 0x7A,
    "F12": 0x7B,
    "0": 0x30,
    "1": 0x31,
    "2": 0x32,
    "3": 0x33,
    "4": 0x34,
    "5": 0x35,
    "6": 0x36,
    "7": 0x37,
    "8": 0x38,
    "9": 0x39,
}
for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    VK[c] = ord(c)

MOD_CTRL = 0x0002
MOD_ALT = 0x0001
MOD_SHIFT = 0x0004
KEYEVENTF_KEYUP = 0x0002

# Named Studio One actions → (modifiers_list, key)
# modifiers: "ctrl", "alt", "shift"
ACTIONS: dict[str, tuple[list[str], str]] = {
    "save": (["ctrl"], "S"),
    "save_as": (["ctrl", "shift"], "S"),
    "undo": (["ctrl"], "Z"),
    "redo": (["ctrl", "shift"], "Z"),
    "cut": (["ctrl"], "X"),
    "copy": (["ctrl"], "C"),
    "paste": (["ctrl"], "V"),
    "select_all": (["ctrl"], "A"),
    "delete": ([], "DELETE"),
    "duplicate": (["ctrl"], "D"),
    "split": ([], "E"),
    "console": ([], "F3"),
    "inspector": ([], "F4"),
    "browser": ([], "F5"),
    "editor": ([], "F2"),
    "mixer": ([], "F3"),
    "fullscreen": ([], "F11"),
    "transport_play": ([], "SPACE"),
    "new_song": (["ctrl"], "N"),
    "open": (["ctrl"], "O"),
    "close": (["ctrl"], "W"),
    "zoom_in": ([], "E"),
    "zoom_out": ([], "W"),
    "loop_toggle": (["ctrl"], "L"),
    "metronome": ([], "C"),
    "quantize": (["ctrl"], "Q"),
    "add_tracks": ([], "T"),
    "arm": ([], "R"),
    "track_mute": ([], "M"),
    "track_solo": ([], "S"),
    "control_link_assign": (["alt"], "M"),
    "escape": ([], "ESCAPE"),
}


def studio_one_running() -> bool:
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq Studio One.exe", "/NH"],
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        return "Studio One.exe" in out
    except Exception:
        return False


def _enum_s1_hwnd() -> Optional[int]:
    result: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def _cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        if "Studio One" in title and "crash" not in title.lower():
            # Prefer main song window over splash
            result.append(hwnd)
        return True

    user32.EnumWindows(_cb, 0)
    return result[0] if result else None


def focus_studio_one() -> bool:
    hwnd = _enum_s1_hwnd()
    if not hwnd:
        return False
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.05)
    return True


def _key_event(vk: int, up: bool = False) -> None:
    flags = KEYEVENTF_KEYUP if up else 0
    user32.keybd_event(vk, 0, flags, 0)


def send_hotkey(modifiers: list[str], key: str) -> None:
    key = key.upper()
    # Special cases
    extra = {
        "EQUAL": 0xBB,
        "MINUS": 0xBD,
        "SPACE": 0x20,
        "DELETE": 0x2E,
        "RETURN": 0x0D,
        "ENTER": 0x0D,
        "ESCAPE": 0x1B,
        "ESC": 0x1B,
    }
    if key in extra:
        vk = extra[key]
    elif key in VK:
        vk = VK[key]
    elif len(key) == 1:
        vk = ord(key.upper())
    else:
        raise ValueError(f"Unknown key: {key}")

    mod_vks = []
    for m in modifiers:
        m = m.lower()
        if m == "ctrl":
            mod_vks.append(0x11)
        elif m == "alt":
            mod_vks.append(0x12)
        elif m == "shift":
            mod_vks.append(0x10)
        elif m in ("f3", "f4", "f5", "f6"):
            # treated as the key itself when alone
            pass

    for mv in mod_vks:
        _key_event(mv, False)
    _key_event(vk, False)
    time.sleep(0.02)
    _key_event(vk, True)
    for mv in reversed(mod_vks):
        _key_event(mv, True)


def run_action(name: str, *, focus: bool = True) -> None:
    if name not in ACTIONS:
        raise KeyError(f"Unknown hotkey action: {name}. Try: {', '.join(sorted(ACTIONS))}")
    mods, key = ACTIONS[name]
    # F-keys stored oddly for console etc.
    if key.startswith("F") and key[1:].isdigit():
        mods = []
    if focus:
        if not focus_studio_one():
            raise RuntimeError("Studio One window not found / not focused")
    send_hotkey(mods, key)
