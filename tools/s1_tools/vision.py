"""
Visual cue analysis for Studio One screenshots.

Complements Eyes (capture). Producer/agent uses these metrics to decide
whether Rec is armed, whether the UI looks like a Song is open, etc.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .logutil import log


@dataclass
class VisionReport:
    path: str
    ok: bool
    rec_red: bool
    red_pixel_hits: int
    blue_pixel_hits: int
    mean_luma: float
    likely_song_ui: bool
    safety_dialog: bool
    green_button_hits: int
    notes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _control_visible(w) -> bool:
    """True if window/control is visible with a usable non-zero rectangle."""
    try:
        if hasattr(w, "is_visible") and not w.is_visible():
            return False
    except Exception:
        return False
    try:
        r = w.rectangle()
        wdt = int(r.right) - int(r.left)
        hgt = int(r.bottom) - int(r.top)
        # Safety dialog is a real modal; ignore zero/ghost UIA nodes
        if wdt < 80 or hgt < 60:
            return False
    except Exception:
        # If rect fails but is_visible passed, still try
        pass
    return True


def _safety_title_match(title: str) -> bool:
    low = (title or "").strip().lower()
    if not low:
        return False
    if "studio one safety" in low:
        return True
    # PreSonus also labels it Recovery / Safety Options in some builds
    if "safety" in low and ("studio one" in low or "recovery" in low or "options" in low):
        return True
    return False


def _find_safety_dialog():
    """
    Studio One Safety is often a *child Dialog* of the main window,
    not a top-level HWND. Search UIA + win32; require visible + real size.

    AI-CODING 085: dismiss loops failed while titles stayed
    ['Studio One', 'Studio One Safety'] — prior code matched invisible/stale
    UIA nodes and only tried exact Button name 'Start' (Qt often weak UIA).
    """
    try:
        from pywinauto import Desktop
    except Exception:
        return None

    for backend in ("uia", "win32"):
        try:
            desk = Desktop(backend=backend)
            for w in desk.windows():
                try:
                    t = (w.window_text() or "").strip()
                except Exception:
                    continue
                if not t:
                    continue
                if _safety_title_match(t) and _control_visible(w):
                    return w
                # Child dialog under main Studio One
                if t.startswith("Studio One") and "safety" not in t.lower():
                    try:
                        kids = []
                        try:
                            kids.extend(list(w.descendants(control_type="Dialog")))
                        except Exception:
                            pass
                        try:
                            kids.extend(list(w.descendants()))
                        except Exception:
                            pass
                        seen = set()
                        for d in kids:
                            try:
                                idd = id(d.element_info) if hasattr(d, "element_info") else id(d)
                            except Exception:
                                idd = id(d)
                            if idd in seen:
                                continue
                            seen.add(idd)
                            try:
                                dt = (d.window_text() or "").strip()
                            except Exception:
                                continue
                            if _safety_title_match(dt) and _control_visible(d):
                                return d
                    except Exception:
                        pass
        except Exception:
            continue
    return None


def detect_safety_dialog_uia() -> bool:
    """True if a visible 'Studio One Safety' window/dialog is present."""
    return _find_safety_dialog() is not None


def _safety_button_names(btn_text: str) -> bool:
    """Match Start (and safe proceed) buttons; never Diagnostics Report."""
    name = (btn_text or "").strip().lower()
    if not name:
        return False
    if "diagnostic" in name or "report" in name or "cancel" in name:
        return False
    if name == "start" or name.startswith("start "):
        return True
    if name in ("ok", "continue", "proceed"):
        return True
    return False


def _click_safety_start_coords(safety) -> bool:
    """
    Qt fallback: Start is bottom-right of the Safety dialog.
    Avoid bottom-left (Create Diagnostics Report is green there).
    """
    try:
        from .human_input import click_human, ensure_dpi_aware

        ensure_dpi_aware()
        r = safety.rectangle()
        left, top, right, bottom = int(r.left), int(r.top), int(r.right), int(r.bottom)
        wdt = right - left
        hgt = bottom - top
        if wdt < 100 or hgt < 80:
            return False
        # Bottom-right cluster: primary Start, plus slight left in case of padding
        targets = [
            (left + int(wdt * 0.88), top + int(hgt * 0.92)),
            (left + int(wdt * 0.82), top + int(hgt * 0.90)),
            (left + int(wdt * 0.75), top + int(hgt * 0.93)),
        ]
        for x, y in targets:
            log(f"  vision: Safety coord Start click @ ({x},{y})")
            click_human(x, y, label="safety_start_coord")
            time.sleep(1.2)
            if not detect_safety_dialog_uia():
                return True
        return False
    except Exception as e:
        log(f"  vision: Safety coord click failed: {e}")
        return False


def _dump_safety_controls(safety) -> None:
    """Log control names once for next-session diagnosis (no secrets)."""
    names: List[str] = []
    try:
        for c in safety.descendants():
            try:
                n = (c.window_text() or "").strip()
                ct = ""
                try:
                    ct = str(c.element_info.control_type)
                except Exception:
                    pass
                if n:
                    names.append(f"{ct}:{n}" if ct else n)
            except Exception:
                continue
    except Exception:
        pass
    if names:
        log(f"  vision: Safety controls sample={names[:24]}")


def dismiss_safety_dialog(*, retries: int = 4) -> bool:
    """
    Dismiss Studio One Safety (crash recovery) by starting normally.

    Strategy order (each retry):
      1) Select 'Start normally' radio if present
      2) UIA/win32 Button click_input/invoke on Start
      3) Focus dialog + Enter / Space
      4) Coordinate click bottom-right (Qt weak-UIA fallback)
    Returns True when no visible Safety dialog remains.
    """
    try:
        from pywinauto.keyboard import send_keys
    except Exception:
        send_keys = None  # type: ignore

    if not detect_safety_dialog_uia():
        return True

    log("  vision: Studio One Safety dialog detected — dismissing (multi-strategy)")
    dumped = False

    for attempt in range(1, max(1, retries) + 1):
        safety = _find_safety_dialog()
        if safety is None:
            log("  vision: Safety gone before attempt")
            return True
        if not dumped:
            _dump_safety_controls(safety)
            dumped = True
        log(f"  vision: Safety dismiss attempt {attempt}/{retries}")

        # 1) Prefer Start normally radio / checkbox options
        try:
            for ctype in ("RadioButton", "CheckBox"):
                try:
                    for r in safety.descendants(control_type=ctype):
                        name = (r.window_text() or "").strip().lower()
                        if "start normally" in name or name == "start normally":
                            try:
                                r.click_input()
                            except Exception:
                                try:
                                    r.invoke()
                                except Exception:
                                    try:
                                        r.select()
                                    except Exception:
                                        pass
                            time.sleep(0.25)
                            break
                except Exception:
                    continue
        except Exception:
            pass

        # 2) Buttons: exact Start preferred; avoid Diagnostics Report
        clicked = False
        try:
            buttons = list(safety.descendants(control_type="Button"))
        except Exception:
            buttons = []
        # Also scan all descendants in case Qt mislabels control type
        try:
            extra = list(safety.descendants())
        except Exception:
            extra = []
        candidates = buttons + [c for c in extra if c not in buttons]
        for btn in candidates:
            try:
                name = (btn.window_text() or "").strip()
            except Exception:
                continue
            if not _safety_button_names(name):
                continue
            try:
                btn.set_focus()
            except Exception:
                pass
            time.sleep(0.05)
            for method in ("click_input", "invoke", "click"):
                try:
                    getattr(btn, method)()
                    clicked = True
                    log(f"  vision: Safety button {name!r} via {method}")
                    break
                except Exception:
                    continue
            if clicked:
                break
            # Last: click center of button rect
            try:
                from .human_input import click_human, ensure_dpi_aware

                ensure_dpi_aware()
                r = btn.rectangle()
                cx = (int(r.left) + int(r.right)) // 2
                cy = (int(r.top) + int(r.bottom)) // 2
                click_human(cx, cy, label=f"safety_btn:{name}")
                clicked = True
                log(f"  vision: Safety button {name!r} via human rect")
            except Exception:
                pass
            if clicked:
                break

        if clicked:
            time.sleep(1.8)
            if not detect_safety_dialog_uia():
                log("  vision: Safety cleared after button")
                return True

        # 3) Keyboard default action (Start is default focus on many builds)
        try:
            safety.set_focus()
        except Exception:
            pass
        time.sleep(0.15)
        if send_keys is not None:
            for keys in ("{ENTER}", " ", "%s", "{TAB}{TAB}{ENTER}"):
                try:
                    send_keys(keys)
                    time.sleep(1.0)
                    if not detect_safety_dialog_uia():
                        log(f"  vision: Safety cleared via keys {keys!r}")
                        return True
                except Exception:
                    continue

        # 4) Coordinate fallback (Qt)
        if _click_safety_start_coords(safety):
            log("  vision: Safety cleared via coord Start")
            return True

        time.sleep(0.6)

    still = detect_safety_dialog_uia()
    log(f"  vision: Safety dismiss finished still_present={still}")
    return not still


def clear_safety_crash_markers() -> List[str]:
    """
    Best-effort remove PreSonus crash/recovery markers so next launch
    may skip Safety. Safe paths only; no secrets. Returns action strings.
    """
    import os
    from pathlib import Path

    actions: List[str] = []
    roots = []
    for envk in ("APPDATA", "LOCALAPPDATA"):
        base = os.environ.get(envk)
        if base:
            roots.append(Path(base) / "PreSonus")
    for root in roots:
        if not root.is_dir():
            continue
        # Studio One 5/6/7 user data trees
        for pattern in (
            "**/crash*",
            "**/Crash*",
            "**/recovery*",
            "**/Recovery*",
            "**/*safety*",
            "**/*Safety*",
            "**/unsaved*",
            "**/*.lock",
        ):
            try:
                for p in root.glob(pattern):
                    if not p.is_file():
                        continue
                    # Never delete huge logs blindly; only small marker-like files
                    try:
                        if p.stat().st_size > 2_000_000:
                            continue
                    except Exception:
                        continue
                    try:
                        p.unlink()
                        actions.append(f"deleted:{p}")
                        log(f"  vision: cleared crash marker {p}")
                    except Exception as e:
                        actions.append(f"delete_fail:{p}:{e}")
            except Exception as e:
                actions.append(f"glob_err:{root}:{e}")
    return actions


def hard_clear_safety(*, kill_s1: bool = True) -> bool:
    """
    Last resort when dismiss_safety_dialog fails:
    kill Studio One, clear crash markers, leave process down for caller relaunch.
    """
    log("  vision: hard_clear_safety starting")
    if kill_s1:
        try:
            import subprocess

            for image in ("Studio One.exe", "Studio One 6.exe", "Studio One 7.exe"):
                subprocess.run(
                    ["taskkill", "/IM", image, "/F"],
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
            time.sleep(2.0)
        except Exception as e:
            log(f"  vision: taskkill S1 warn: {e}")
    clear_safety_crash_markers()
    time.sleep(0.5)
    gone = not detect_safety_dialog_uia()
    log(f"  vision: hard_clear_safety done safety_gone={gone}")
    return gone


def analyze_shot(path: Optional[Path]) -> VisionReport:
    if path is None or not Path(path).exists():
        return VisionReport(
            path=str(path or ""),
            ok=False,
            rec_red=False,
            red_pixel_hits=0,
            blue_pixel_hits=0,
            mean_luma=0.0,
            likely_song_ui=False,
            safety_dialog=False,
            green_button_hits=0,
            notes=["missing image"],
        )
    path = Path(path)
    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        return VisionReport(
            path=str(path),
            ok=False,
            rec_red=False,
            red_pixel_hits=0,
            blue_pixel_hits=0,
            mean_luma=0.0,
            likely_song_ui=False,
            safety_dialog=False,
            green_button_hits=0,
            notes=["PIL unavailable"],
        )

    try:
        img = Image.open(str(path)).convert("RGB")
        # Downsample for speed
        img_s = img.resize((img.width // 4, img.height // 4))
        arr = np.asarray(img_s, dtype=np.int16)
        r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
        red_mask = (r > 180) & (g < 80) & (b < 80)
        # MIDI clips in S1 are often blue-ish blocks
        blue_mask = (b > 140) & (b > r + 30) & (b > g + 10)
        # Safety dialog has a bright green "Create Diagnostics Report" button
        green_mask = (g > 140) & (g > r + 40) & (g > b + 40)
        red_hits = int(red_mask.sum())
        blue_hits = int(blue_mask.sum())
        green_hits = int(green_mask.sum())
        luma = (0.2126 * r + 0.7152 * g + 0.0722 * b).mean()
        mean_luma = float(luma)
        rec_red = red_hits > 30
        safety_uia = detect_safety_dialog_uia()
        # Pixel-only heuristic is weak (browser/plugin greens false-positive).
        # Hard block only when UIA sees the Safety dialog; pixel is a soft note.
        safety_px = green_hits > 400 and 40.0 < mean_luma < 75.0
        safety = bool(safety_uia)
        # Song UI: not UIA-safety, not empty
        likely_song = (
            not safety
            and 15.0 < mean_luma < 220.0
            and (arr.shape[0] * arr.shape[1] > 10000)
        )
        notes: List[str] = []
        if safety:
            notes.append("safety_dialog_blocking")
            notes.append("safety_uia")
        elif safety_px:
            notes.append("safety_green_pixel_hint_only")
        if rec_red:
            notes.append("rec_red_likely")
        if blue_hits > 200:
            notes.append("blue_regions_possible_midi_clips")
        if not likely_song and not safety:
            notes.append("ui_uncertain")
        return VisionReport(
            path=str(path),
            ok=True,
            rec_red=rec_red,
            red_pixel_hits=red_hits,
            blue_pixel_hits=blue_hits,
            mean_luma=mean_luma,
            likely_song_ui=likely_song,
            safety_dialog=safety,
            green_button_hits=green_hits,
            notes=notes,
        )
    except Exception as e:
        return VisionReport(
            path=str(path),
            ok=False,
            rec_red=False,
            red_pixel_hits=0,
            blue_pixel_hits=0,
            mean_luma=0.0,
            likely_song_ui=False,
            safety_dialog=False,
            green_button_hits=0,
            notes=[f"error:{e}"],
        )


def summarize_shots(paths: List[Path]) -> Dict[str, Any]:
    reports = [analyze_shot(p) for p in paths if p]
    any_rec = any(r.rec_red for r in reports)
    any_blue = any(r.blue_pixel_hits > 200 for r in reports)
    any_safety = any(r.safety_dialog for r in reports)
    ok_count = sum(1 for r in reports if r.ok)
    log(
        f"  vision: shots={len(reports)} ok={ok_count} "
        f"any_rec_red={any_rec} blue_clip_hint={any_blue} safety={any_safety}"
    )
    return {
        "shot_count": len(reports),
        "ok_count": ok_count,
        "any_rec_red": any_rec,
        "blue_clip_hint": any_blue,
        "any_safety_dialog": any_safety,
        "reports": [r.to_dict() for r in reports[-12:]],  # cap size
    }
