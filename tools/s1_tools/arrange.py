"""Arrange / menu helpers (UIA + keyboard) — no mouse movements."""

from __future__ import annotations

import time

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


def click_menu_item(main, desk, top_menu: str, item_name: str) -> bool:
    """Navigate to a menu item using UIA invoke (no mouse click)."""
    for m in main.descendants(control_type="MenuItem"):
        if m.window_text() == top_menu:
            try:
                m.invoke()  # UIA InvokePattern — keyboard-safe, no mouse
            except Exception:
                m.set_focus()
                send_keys("{ENTER}")
            time.sleep(0.35)
            break
    else:
        log(f"  no top menu {top_menu!r}")
        return False

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
            base = name.split("\t")[0].strip()
            if base == item_name or name == item_name:
                log(f"  invoke {name!r}")
                try:
                    mi.invoke()  # UIA InvokePattern — keyboard-safe, no mouse
                except Exception:
                    mi.set_focus()
                    send_keys("{ENTER}")
                time.sleep(0.45)
                return True
    log(f"  item not found: {item_name!r}")
    send_keys("{ESC}")
    return False


def add_instrument_tracks(count: int = 1, *, focus_fn=None) -> int:
    if focus_fn is not None:
        if not focus_fn():
            log("Could not focus Studio One")
            return 0
    time.sleep(0.2)
    send_keys("{ESC}{ESC}")
    time.sleep(0.15)
    main, desk = get_main_window()
    log(f"  window: {main.window_text()!r}")
    created = 0
    for i in range(count):
        log(f"=== Add Instrument Track #{i + 1} ===")
        main, desk = get_main_window()
        if click_menu_item(main, desk, "Track", "Add Instrument Track"):
            created += 1
        time.sleep(0.3)
    return created
