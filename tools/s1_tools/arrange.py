"""Arrange / menu helpers (UIA + keyboard) — no mouse movements."""

from __future__ import annotations

import time
from typing import List, Optional, Sequence

from pywinauto.keyboard import send_keys

from .logutil import log


def get_main_window():
    from pywinauto import Desktop

    desk = Desktop(backend="uia")
    for w in desk.windows():
        try:
            t = w.window_text() or ""
        except Exception:
            continue
        if t.startswith("Studio One") and "Add Track" not in t and w.is_visible():
            return w, desk
    raise RuntimeError("Studio One main window not found (is a Song open?)")


def _invoke_menuitem(mi) -> None:
    try:
        mi.invoke()
    except Exception:
        try:
            mi.set_focus()
            send_keys("{ENTER}")
        except Exception:
            pass


def _find_menu_items(desk):
    for w in desk.windows():
        try:
            items = w.descendants(control_type="MenuItem")
        except Exception:
            continue
        for mi in items:
            try:
                name = mi.window_text() or ""
            except Exception:
                continue
            if name.strip():
                yield mi, name


def click_menu_path(main, desk, path: Sequence[str]) -> bool:
    """
    Open nested menu path e.g. ('Track', 'Add', 'Instrument Track').
    Matches item base name before tab/shortcut.
    """
    if not path:
        return False
    # Open top-level
    top = path[0]
    for m in main.descendants(control_type="MenuItem"):
        if (m.window_text() or "") == top:
            _invoke_menuitem(m)
            time.sleep(0.4)
            break
    else:
        log(f"  no top menu {top!r}")
        return False

    for step in path[1:]:
        found = False
        for mi, name in _find_menu_items(desk):
            base = name.split("\t")[0].strip().rstrip("…").rstrip("...")
            # Allow partial: "Instrument Track" matches "Add Instrument Track"
            if base == step or name == step or base.endswith(step) or step in base:
                log(f"  invoke {name!r}")
                _invoke_menuitem(mi)
                time.sleep(0.45)
                found = True
                break
        if not found:
            log(f"  item not found: {step!r} in path {list(path)}")
            send_keys("{ESC}{ESC}")
            return False
    return True


def click_menu_item(main, desk, top_menu: str, item_name: str) -> bool:
    """Navigate to a menu item using UIA invoke (no mouse click)."""
    return click_menu_path(main, desk, [top_menu, item_name])


def _add_instrument_via_t_dialog() -> bool:
    """
    Open Add Tracks with [T], accept defaults (often Instrument), Enter.
    Studio One Track menu is often custom-drawn and invisible to UIA.
    Returns True if dialog interaction completed without exception.
    """
    send_keys("{ESC}")
    time.sleep(0.1)
    send_keys("t")
    time.sleep(0.65)
    # Confirm Add Tracks (default type is often Instrument)
    send_keys("{ENTER}")
    time.sleep(0.55)
    # Dismiss any leftover focus; do not count Esc as failure
    send_keys("{ESC}")
    time.sleep(0.15)
    return True


def add_instrument_tracks(count: int = 1, *, focus_fn=None) -> int:
    if focus_fn is not None:
        if not focus_fn():
            log("Could not focus Studio One")
            return 0
    time.sleep(0.2)
    send_keys("{ESC}{ESC}")
    time.sleep(0.15)
    try:
        main, desk = get_main_window()
        log(f"  window: {main.window_text()!r}")
    except Exception as e:
        log(f"  main window warn: {e}")
        main, desk = None, None
    created = 0
    # Studio One 6 variants: flat item vs Add submenu
    candidates: List[Sequence[str]] = [
        ("Track", "Add Instrument Track"),
        ("Track", "Add Instrument Track…"),
        ("Track", "Add", "Instrument Track"),
        ("Track", "Add", "Instrument Track…"),
        ("Track", "Add Tracks…"),
        ("Track", "Add Tracks"),
        ("Track", "Add Track"),
    ]
    for i in range(count):
        log(f"=== Add Instrument Track #{i + 1} ===")
        ok = False
        if main is not None:
            for path in candidates:
                send_keys("{ESC}")
                time.sleep(0.1)
                try:
                    main, desk = get_main_window()
                    if click_menu_path(main, desk, path):
                        ok = True
                        break
                except Exception:
                    continue
        if not ok:
            log("  menu UIA failed — falling back to [T] Add Tracks dialog")
            try:
                ok = _add_instrument_via_t_dialog()
            except Exception as e:
                log(f"  T dialog fail: {e}")
                ok = False
        if ok:
            created += 1
            time.sleep(0.25)
        else:
            log("  all methods failed for Add Instrument Track")
        time.sleep(0.3)
    return created


def add_audio_tracks(count: int = 1, *, focus_fn=None) -> int:
    if focus_fn is not None:
        if not focus_fn():
            return 0
    send_keys("{ESC}{ESC}")
    time.sleep(0.15)
    created = 0
    candidates = [
        ("Track", "Add Audio Track"),
        ("Track", "Add", "Audio Track"),
        ("Track", "Add", "Audio Track (stereo)"),
    ]
    for i in range(count):
        main, desk = get_main_window()
        for path in candidates:
            send_keys("{ESC}")
            time.sleep(0.1)
            main, desk = get_main_window()
            if click_menu_path(main, desk, path):
                created += 1
                break
        time.sleep(0.3)
    return created
