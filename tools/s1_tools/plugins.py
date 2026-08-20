"""Keyboard/UIA helpers to put instruments and effects onto tracks.

Studio One's Browser is custom-drawn, so drag-from-Browser is not automated.
These paths are the ones the manual still allows without Explorer drag:

- Instruments tab (F6) / Effects tab (F7) + search + Enter
- Replace dialog (UIA) when S1 asks to replace the current instrument
- Channel Editor (F11) Inserts menu
- Inspector (F4) Output combo (best-effort)

Eyes/window titles decide PASS vs FAIL — search-and-Enter alone is not proof.
"""

from __future__ import annotations

import time
from typing import Iterable, List, Optional, Sequence, Tuple

from .logutil import log

INSTRUMENT_NEEDLES = ("mojito", "presence", "mai tai", "maitai", "impact", "sampleone", "sample one")
EFFECT_NEEDLES = ("pro eq", "proeq", "compressor", "mixtool", "channel editor")
REPLACE_TITLES = ("replace", "already exists", "confirm")
SKIP_TITLES = ("grok", "powershell", "cursor", "chrome", "visual studio", "code")


def _desk(backend: str = "uia"):
    from pywinauto import Desktop

    return Desktop(backend=backend)


def visible_titles() -> List[str]:
    out: List[str] = []
    for backend in ("uia", "win32"):
        try:
            for w in _desk(backend).windows():
                try:
                    if not w.is_visible():
                        continue
                    t = (w.window_text() or "").strip()
                except Exception:
                    continue
                if t and t.lower() not in (x.lower() for x in out):
                    out.append(t)
        except Exception:
            continue
    return out


def titles_matching(needles: Iterable[str]) -> List[str]:
    want = [n.lower() for n in needles]
    hits = []
    for t in visible_titles():
        low = t.lower()
        if any(s in low for s in SKIP_TITLES):
            continue
        if any(n in low for n in want):
            hits.append(t)
    return hits


def plugin_window_visible(*, kind: str = "any") -> List[str]:
    if kind == "instrument":
        needles = INSTRUMENT_NEEDLES
    elif kind == "effect":
        needles = EFFECT_NEEDLES
    else:
        needles = INSTRUMENT_NEEDLES + EFFECT_NEEDLES
    return titles_matching(needles)


def _iter_descendants(root, control_types: Sequence[str]):
    for ct in control_types:
        try:
            for c in root.descendants(control_type=ct):
                yield c
        except Exception:
            continue


def _control_name(c) -> str:
    try:
        return (c.window_text() or "").strip()
    except Exception:
        return ""


def click_named_control(
    names: Sequence[str],
    *,
    control_types: Sequence[str] = ("Button", "MenuItem", "SplitButton", "Hyperlink"),
    timeout: float = 2.5,
) -> Tuple[bool, str]:
    """Invoke a visible UIA control whose name contains one of *names*."""
    want = [n.lower() for n in names]
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        try:
            for w in _desk("uia").windows():
                try:
                    if not w.is_visible():
                        continue
                    title = (w.window_text() or "").strip()
                except Exception:
                    continue
                if any(s in title.lower() for s in SKIP_TITLES):
                    continue
                for c in _iter_descendants(w, control_types):
                    name = _control_name(c)
                    if not name:
                        continue
                    base = name.split("\t")[0].strip().rstrip("…").rstrip("...")
                    low = base.lower()
                    if any(n in low or low == n for n in want):
                        last = name
                        try:
                            c.invoke()
                        except Exception:
                            try:
                                c.click_input()
                            except Exception as e:
                                last = f"{name} invoke-fail {e}"
                                continue
                        log(f"  plugins UIA invoke {name!r}")
                        time.sleep(0.35)
                        return True, name
        except Exception as e:
            last = str(e)[:120]
        time.sleep(0.12)
    return False, last or "not found"


def click_replace_dialog() -> Tuple[bool, str]:
    """If S1 shows Replace/Confirm after a browser load, accept it."""
    hits = titles_matching(REPLACE_TITLES)
    ok, detail = click_named_control(
        ("Replace", "Yes", "OK"),
        control_types=("Button", "MenuItem"),
        timeout=1.8,
    )
    if ok:
        return True, f"clicked {detail} titles={hits[:3]}"
    if hits:
        return False, f"replace-like window but no button: {hits[:3]}"
    return False, "no replace dialog"


def try_inserts_menu(effect_name: str) -> Tuple[bool, str]:
    """Channel Editor Inserts menu — stock FX without Browser drag."""
    from pywinauto.keyboard import send_keys

    ok, which = click_named_control(
        ("Inserts", "Insert", "+ Insert"),
        control_types=("Button", "MenuItem", "SplitButton", "Edit"),
        timeout=2.0,
    )
    if not ok:
        return False, f"Inserts control missing ({which})"
    time.sleep(0.25)
    # Type into the open menu/search if it accepts keys
    safe = effect_name.replace("{", "{{").replace("}", "}}")
    try:
        send_keys(safe, with_spaces=True, pause=0.04)
        time.sleep(0.25)
        send_keys("{ENTER}")
        time.sleep(0.4)
    except Exception as e:
        return False, f"Inserts open but type failed: {e}"
    return True, f"Inserts typed {effect_name!r}"


def inspector_output_combos() -> List[str]:
    """Names of Inspector combos that look like instrument Output."""
    names: List[str] = []
    try:
        for w in _desk("uia").windows():
            try:
                t = (w.window_text() or "")
                if not t.startswith("Studio One"):
                    continue
            except Exception:
                continue
            for c in _iter_descendants(w, ("ComboBox", "Edit", "Button")):
                name = _control_name(c)
                low = name.lower()
                if any(k in low for k in ("output", "instrument", "mai", "presence", "mojito", "none")):
                    names.append(name)
    except Exception as e:
        log(f"  inspector combo scan: {e}")
    return names[:12]


def after_load_proof(*, kind: str) -> Tuple[bool, str]:
    """True when a plugin editor/window is actually on screen."""
    time.sleep(0.35)
    replaced, rdetail = click_replace_dialog()
    time.sleep(0.4)
    wins = plugin_window_visible(kind=kind)
    bits = []
    if replaced:
        bits.append(rdetail)
    if wins:
        bits.append("windows=" + ";".join(wins[:4]))
        return True, " | ".join(bits)
    combos = inspector_output_combos()
    if combos:
        bits.append("inspector=" + ";".join(combos[:4]))
        # Inspector showing a named instrument (not empty/None) is weak-PASS
        joined = " ".join(combos).lower()
        if any(n in joined for n in INSTRUMENT_NEEDLES + EFFECT_NEEDLES):
            return True, " | ".join(bits)
    return False, "no plugin window; " + ("; ".join(bits) if bits else rdetail)
