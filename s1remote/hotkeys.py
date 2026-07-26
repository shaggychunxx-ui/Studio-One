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
    "browser_instruments": ([], "F6"),
    "browser_effects": ([], "F7"),
    "browser_loops": ([], "F8"),
    "browser_files": ([], "F9"),
    "browser_pool": ([], "F10"),
    "editor": ([], "F2"),
    "mixer": ([], "F3"),
    "channel_editor": ([], "F11"),
    "instrument_editor": (["shift"], "F11"),
    "fullscreen": ([], "F11"),
    "transport_play": ([], "SPACE"),
    "new_song": (["ctrl"], "N"),
    "open": (["ctrl"], "O"),
    "close": (["ctrl"], "W"),
    "zoom_in": ([], "E"),
    "zoom_out": ([], "W"),
    "loop_toggle": (["ctrl"], "L"),
    "metronome": ([], "C"),
    "precount": (["shift"], "C"),
    "preroll": ([], "O"),
    "auto_punch": ([], "I"),
    "quantize": (["ctrl"], "Q"),
    "quantize_selection": ([], "Q"),
    "add_tracks": ([], "T"),
    "arm": ([], "R"),
    "track_mute": ([], "M"),
    "track_solo": ([], "S"),
    "control_link_assign": (["alt"], "M"),
    "escape": ([], "ESCAPE"),
    "export_mixdown": (["ctrl"], "E"),
    "bounce_selection": (["ctrl"], "B"),
    "find_track": (["ctrl", "alt"], "T"),
    "find_channel": (["ctrl", "alt"], "C"),
    "command_search": (["ctrl"], "K"),
    "group_tracks": (["ctrl"], "G"),
    "dissolve_group": (["ctrl", "shift"], "G"),
    "merge": ([], "G"),
    "split_at_cursor": (["alt"], "X"),
    "crossfade": ([], "X"),
    "nudge_left": (["alt"], "LEFT"),
    "nudge_right": (["alt"], "RIGHT"),
    "automation_lanes": ([], "A"),
    "return_zero": ([], "HOME"),  # , key is unreliable; Home often works
    "tool_arrow": ([], "1"),
    "tool_range": ([], "2"),
    "tool_split": ([], "3"),
    "tool_eraser": ([], "4"),
    "tool_paint": ([], "5"),
    "tool_mute": ([], "6"),
    "options": (["ctrl"], ","),  # may need special handling
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
    """Find real Studio One DAW window — not Grok/Terminal titles that contain the words."""
    result: list[int] = []
    skip_sub = (
        "grok",
        "unique track creation",
        "crash",
        "visual studio",
        "windows terminal",
        "powershell",
        "cmd.exe",
        "chrome",
        "edge",
        "firefox",
    )

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
        low = title.lower()
        if "studio one" not in low:
            return True
        if any(s in low for s in skip_sub):
            return True
        # Prefer main song window over splash
        result.append(hwnd)
        return True

    user32.EnumWindows(_cb, 0)
    if not result:
        return None
    # Prefer titles like "Studio One - <song>" over bare splash
    for hwnd in result:
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if " - " in buf.value:
            return hwnd
    return result[0]


def focus_studio_one() -> bool:
    """Bring real Studio One to foreground (robust against other apps stealing focus)."""
    hwnd = _enum_s1_hwnd()
    if not hwnd:
        return False
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    # AttachThreadInput helps SetForegroundWindow succeed on modern Windows
    fg = user32.GetForegroundWindow()
    cur_tid = kernel32.GetCurrentThreadId()
    pid = ctypes.c_ulong()
    fg_tid = user32.GetWindowThreadProcessId(fg, ctypes.byref(pid)) if fg else 0
    s1_tid = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if fg_tid:
        user32.AttachThreadInput(cur_tid, fg_tid, True)
    if s1_tid:
        user32.AttachThreadInput(cur_tid, s1_tid, True)
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    if fg_tid:
        user32.AttachThreadInput(cur_tid, fg_tid, False)
    if s1_tid:
        user32.AttachThreadInput(cur_tid, s1_tid, False)
    time.sleep(0.08)
    return user32.GetForegroundWindow() == hwnd or True  # hwnd valid even if FG steal fails


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
        ",": 0xBC,
        "COMMA": 0xBC,
        "OEM_COMMA": 0xBC,
        "HOME": 0x24,
        "END": 0x23,
        "LEFT": 0x25,
        "UP": 0x26,
        "RIGHT": 0x27,
        "DOWN": 0x28,
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


def run_action(name: str, *, focus: bool = True, allow_new_song: bool = False) -> None:
    """
    Send a named hotkey. Production policy: block file.new (Ctrl+N) unless
    allow_new_song=True — accidental New dialog steals Meridian_Pulse etc.
    """
    import os

    if name not in ACTIONS:
        raise KeyError(f"Unknown hotkey action: {name}. Try: {', '.join(sorted(ACTIONS))}")
    # Hard block New Song mid-production (stays on current song)
    if name == "new_song" and not allow_new_song:
        if os.environ.get("S1_ALLOW_NEW_SONG", "").strip() not in ("1", "true", "yes"):
            raise RuntimeError(
                "Blocked hotkey new_song (Ctrl+N): would leave current song. "
                "Set allow_new_song=True or S1_ALLOW_NEW_SONG=1 only when intentional."
            )
    mods, key = ACTIONS[name]
    # F-keys stored oddly for console etc.
    if key.startswith("F") and key[1:].isdigit():
        mods = []
    if focus:
        ok = focus_studio_one()
        if not ok:
            # retry once — S1 may still be focusing after launch
            time.sleep(0.35)
            ok = focus_studio_one()
        if not ok and not studio_one_running():
            raise RuntimeError("Studio One window not found / not focused")
        # If process is up but FG steal failed, still send keys (best-effort)
    send_hotkey(mods, key)
