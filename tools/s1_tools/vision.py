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


def _find_safety_dialog():
    """
    Studio One Safety is often a *child Dialog* of the main window,
    not a top-level HWND. Search both.
    """
    try:
        from pywinauto import Desktop

        desk = Desktop(backend="uia")
        for w in desk.windows():
            try:
                t = (w.window_text() or "").strip()
            except Exception:
                continue
            if "studio one safety" in t.lower():
                return w
            # Child dialog under main Studio One
            if t.startswith("Studio One") and "safety" not in t.lower():
                try:
                    for d in w.descendants(control_type="Dialog"):
                        dt = (d.window_text() or "").strip()
                        if "safety" in dt.lower():
                            return d
                except Exception:
                    pass
                try:
                    for d in w.descendants():
                        dt = (d.window_text() or "").strip()
                        if dt.lower() == "studio one safety":
                            return d
                except Exception:
                    pass
    except Exception:
        pass
    return None


def detect_safety_dialog_uia() -> bool:
    """True if a 'Studio One Safety' window/dialog is present (crash recovery)."""
    return _find_safety_dialog() is not None


def dismiss_safety_dialog() -> bool:
    """
    Dismiss Studio One Safety crash dialog by starting normally.
    Prefers UIA invoke on Start; falls back to keyboard.
    """
    try:
        from pywinauto.keyboard import send_keys

        safety = _find_safety_dialog()
        if safety is None:
            return False
        log("  vision: Studio One Safety dialog detected — dismissing")
        # Prefer "Start normally" radio if present, then Start button
        try:
            for r in safety.descendants(control_type="RadioButton"):
                name = (r.window_text() or "").strip().lower()
                if "start normally" in name:
                    try:
                        r.invoke()
                    except Exception:
                        r.select()
                    time.sleep(0.2)
                    break
        except Exception:
            pass
        for btn in safety.descendants(control_type="Button"):
            try:
                name = (btn.window_text() or "").strip().lower()
            except Exception:
                continue
            if name == "start":
                try:
                    btn.invoke()
                except Exception:
                    try:
                        btn.click_input()
                    except Exception:
                        send_keys("{ENTER}")
                time.sleep(1.5)
                log("  vision: clicked Safety Start")
                return not detect_safety_dialog_uia()
        try:
            safety.set_focus()
        except Exception:
            pass
        send_keys("{ENTER}")
        time.sleep(1.5)
        log("  vision: Safety Enter fallback")
        return not detect_safety_dialog_uia()
    except Exception as e:
        log(f"  vision: dismiss_safety failed: {e}")
        return False


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
