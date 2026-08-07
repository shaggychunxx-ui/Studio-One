"""
Producer eyes — screenshot monitoring of the Studio One UI.

UIA often cannot see track Rec buttons or clip lanes. Eyes capture the screen
so agents/humans can verify Rec red and MIDI parts without trusting log counts.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .logutil import log


class Eyes:
    def __init__(self, directory: Path, *, enabled: bool = True, live: bool = True):
        self.directory = Path(directory)
        self.enabled = enabled
        self.live = live  # denser live vision during record
        self._watch: threading.Thread | None = None
        self._stop = threading.Event()
        self.shot_count = 0
        self.last_live: List[Path] = []

    def shot(self, tag: str, *, annotate: bool = False, hud: Optional[str] = None) -> Path | None:
        if not self.enabled:
            return None
        try:
            from PIL import ImageGrab, ImageDraw
        except ImportError:
            log("  eyes: PIL not installed (pip install pillow) — skip shot")
            return None
        try:
            # Align grab coords with human clicks under DPI scaling
            try:
                from .human_input import ensure_dpi_aware

                ensure_dpi_aware()
            except Exception:
                pass
            self.directory.mkdir(parents=True, exist_ok=True)
            path = self.directory / f"{datetime.now().strftime('%H%M%S')}_{tag}.png"
            img = ImageGrab.grab()
            if annotate or hud:
                dr = ImageDraw.Draw(img)
                w, h = img.size
                try:
                    x0, x1 = rec_x_band_for_width(w)
                except NameError:
                    x0, x1 = int(w * 0.315), int(w * 0.341)
                y0, y1 = int(h * 0.14), int(h * 0.82)
                dr.rectangle([x0, y0, x1, y1], outline=(0, 200, 255), width=1)
                if hud:
                    dr.text((16, 14), f"{hud[:60]} [{w}x{h}]"[:90], fill=(0, 255, 120))
            img.save(str(path))
            self.shot_count += 1
            log(f"  eyes 📷 {path.name}")
            return path
        except Exception as e:
            log(f"  eyes shot fail: {e}")
            return None

    def start_watch(self, label: str, interval: float | None = None) -> None:
        """Live vision: denser frames during record (default 2.5s when live=True)."""
        if not self.enabled:
            return
        if interval is None:
            interval = 2.5 if self.live else 8.0
        self._stop.clear()
        self.last_live = []

        def _run() -> None:
            n = 0
            while not self._stop.wait(interval):
                n += 1
                p = self.shot(f"live_{label}_{n:02d}", hud=f"LIVE {label} #{n}")
                if p:
                    self.last_live.append(p)
                    if len(self.last_live) > 40:
                        self.last_live = self.last_live[-40:]

        self._watch = threading.Thread(target=_run, daemon=True)
        self._watch.start()
        log(f"  eyes LIVE watch '{label}' every {interval:.1f}s")

    def stop_watch(self) -> None:
        self._stop.set()
        if self._watch is not None:
            self._watch.join(timeout=2.0)
            self._watch = None


def scan_rec_red(
    path: "Path | None",
    track: int | None = None,
    *,
    allow_fallback: bool = True,
    visible_row: int | None = None,
) -> bool:
    """
    Heuristic: bright-red pixels = Rec Enable armed.

    ``track`` / ``visible_row`` are 1-based. ``visible_row`` indexes the
    currently visible arrange header rows (preferred when S1 labels start at 3).

    When ``allow_fallback`` is False, only the target row band counts — used
    for exclusive-arm verify so a red on another track cannot fake success.
    """
    if path is None or not Path(path).exists():
        return False
    try:
        from PIL import Image
        import numpy as np

        img = Image.open(str(path)).convert("RGB")
        arr = np.asarray(img, dtype=np.int16)
        h, w = arr.shape[:2]
        # Restrict to Rec column only (avoid inspector Rec + selected Mute red)
        # Aspect-safe: scale calibrated 1920-wide band to actual grab width
        x1, x2 = rec_x_band_for_width(w)

        def count_red(y1: int, y2: int) -> int:
            y1 = max(0, min(h - 1, y1))
            y2 = max(y1 + 1, min(h, y2))
            region = arr[y1:y2, x1:x2]
            r, g, b = region[:, :, 0], region[:, :, 1], region[:, :, 2]
            mask = (r > 155) & (g < 110) & (b < 110) & (r > g + 45) & (r > b + 45)
            return int(mask.sum())

        row_idx = visible_row if visible_row is not None else track
        if row_idx is not None and row_idx >= 1:
            pts = locate_track_rec_buttons(path)
            if pts and 1 <= row_idx <= len(pts):
                _, py = pts[row_idx - 1]
                n = count_red(py - 12, py + 12)
                if n >= 3:
                    return True
                if not allow_fallback:
                    return False
            rows = find_rec_row_centers_frac(path)
            if rows and 1 <= row_idx <= len(rows):
                yf = rows[row_idx - 1]
                half = 0.02
                n = count_red(int(h * (yf - half)), int(h * (yf + half)))
                if n >= 3:
                    return True
                if not allow_fallback:
                    return False
            y_mid = 0.20 + (row_idx - 1) * 0.042
            n = count_red(int(h * (y_mid - 0.02)), int(h * (y_mid + 0.02)))
            if n >= 3:
                return True
            if not allow_fallback:
                return False
            # Global any-red fallback is dangerous (inspector / wrong track) — only when allowed
            return count_red(int(h * 0.14), int(h * 0.78)) >= 10

        return count_red(int(h * 0.14), int(h * 0.78)) >= 8
    except Exception:
        return False


def count_lane_clips(
    path: "Path | None",
    visible_row: int,
    *,
    half_band_px: int = 18,
    cy: int | None = None,
) -> int:
    """
    Count MIDI-part pixels (blue OR cyan OR green) in one arrange lane.

    Mojito/Impact parts are often green/cyan — blue-only checks false-failed.
    """
    if path is None or not Path(path).exists() or visible_row < 1:
        return 0
    try:
        from PIL import Image
        import numpy as np

        img = Image.open(str(path)).convert("RGB")
        arr = np.asarray(img, dtype=np.int16)
        h, w = arr.shape[:2]
        if cy is None:
            pts = locate_track_rec_buttons(path)
            if pts and visible_row <= len(pts):
                cy = pts[visible_row - 1][1]
            else:
                rows = find_rec_row_centers_frac(path)
                if rows and visible_row <= len(rows):
                    cy = int(h * rows[visible_row - 1])
                else:
                    cy = int(h * (0.20 + (visible_row - 1) * 0.042))
        y1, y2 = max(0, cy - half_band_px), min(h, cy + half_band_px)
        x1, x2 = int(w * 0.40), int(w * 0.72)
        region = arr[y1:y2, x1:x2]
        r, g, b = region[:, :, 0], region[:, :, 1], region[:, :, 2]
        blue = (b > 120) & (b > r + 15) & (b > g + 5) & (r < 210)
        cyan = (b > 100) & (g > 100) & (b > r + 15) & (g > r + 5)
        green = (g > 115) & (g > r + 18) & (g > b + 5) & (r < 190)
        return int((blue | cyan | green).sum())
    except Exception:
        return 0


def count_lane_blue(
    path: "Path | None",
    visible_row: int,
    *,
    half_band_px: int = 14,
) -> int:
    """Backward-compatible alias → multi-color lane clips."""
    return count_lane_clips(path, visible_row, half_band_px=half_band_px)


def lane_clip_growth(
    before: "Path | None",
    after: "Path | None",
    visible_row: int,
    *,
    min_delta: int = 50,
) -> Dict[str, Any]:
    """Before/after per-lane accuracy check."""
    b = count_lane_clips(before, visible_row)
    a = count_lane_clips(after, visible_row)
    return {
        "before": b,
        "after": a,
        "delta": a - b,
        "growth": (a - b) >= min_delta or (b < 120 and a > 250),
    }


def annotate_rec_hud(
    path: "Path | None",
    pts: List[Tuple[int, int]],
    *,
    armed_row: int | None = None,
    label: str = "",
) -> Path | None:
    """Draw Rec targets on a copy of the shot for human/agent review."""
    if path is None or not Path(path).exists():
        return None
    try:
        from PIL import Image, ImageDraw

        im = Image.open(path).convert("RGB")
        dr = ImageDraw.Draw(im)
        dr.rectangle([REC_X_BAND[0], 140, REC_X_BAND[1], 720], outline=(0, 200, 255), width=1)
        for i, (x, y) in enumerate(pts):
            col = (255, 60, 60) if armed_row == i + 1 else (0, 255, 0)
            dr.ellipse([x - 8, y - 8, x + 8, y + 8], outline=col, width=2)
            dr.text((x + 12, y - 8), f"T{i+1}", fill=(255, 255, 0))
        if label:
            dr.text((16, 14), label[:90], fill=(0, 255, 180))
        out = Path(path).with_name(Path(path).stem + "_hud.png")
        im.save(out)
        return out
    except Exception:
        return None


def check_display_dpi() -> Dict[str, Any]:
    """Warn if Windows DPI scaling may break click coords vs ImageGrab."""
    try:
        import ctypes

        user32 = ctypes.windll.user32
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                user32.SetProcessDPIAware()
            except Exception:
                pass
        dc = user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(dc, 88)  # LOGPIXELSX
        user32.ReleaseDC(0, dc)
        scale = dpi / 96.0
        ok = 0.95 <= scale <= 1.05
        if not ok:
            log(f"  WARN display DPI scale={scale:.2f} (dpi={dpi}) — clicks may miss Rec")
        return {"dpi": dpi, "scale": scale, "ok": ok}
    except Exception as e:
        return {"ok": True, "error": str(e)}


def list_armed_visible_rows(path: "Path | None") -> List[int]:
    """1-based visible row indices that look Rec-red."""
    if path is None or not Path(path).exists():
        return []
    pts = locate_track_rec_buttons(path)
    armed: List[int] = []
    for i in range(1, max(1, len(pts)) + 1):
        if scan_rec_red(path, visible_row=i, allow_fallback=False):
            armed.append(i)
    if not armed and scan_rec_red(path, track=None):
        # global red but row map failed
        return [-1]
    return armed


def find_rec_row_centers_frac(path: "Path | None") -> List[float]:
    """
    Find vertical centers (as fraction of image height) of track rows that
    look like they have an M/S/Rec control cluster in the arrange header.

    Uses mid-grey circular-ish blobs in the Rec column, clustered by Y.
    """
    if path is None or not Path(path).exists():
        return []
    try:
        from PIL import Image
        import numpy as np

        img = Image.open(str(path)).convert("RGB")
        arr = np.asarray(img, dtype=np.int16)
        h, w = arr.shape[:2]
        # Rec column band (M S Rec sit here on typical S1 layouts)
        x1, x2 = int(w * 0.28), int(w * 0.42)
        y1, y2 = int(h * 0.14), int(h * 0.82)
        region = arr[y1:y2, x1:x2]
        r, g, b = region[:, :, 0], region[:, :, 1], region[:, :, 2]
        # Mid-grey controls (not black, not white, low chroma)
        grey = (
            (r > 40)
            & (r < 120)
            & (g > 40)
            & (g < 120)
            & (b > 40)
            & (b < 120)
            & (np.abs(r.astype(int) - g) < 25)
            & (np.abs(g.astype(int) - b) < 25)
        )
        # Also already-red rec dots
        red = (r > 155) & (g < 110) & (b < 110) & (r > g + 45)
        mask = grey | red
        # Horizontal projection: density per row
        row_density = mask.sum(axis=1).astype(float)
        if row_density.max() < 3:
            return []
        # Smooth
        k = 5
        kernel = np.ones(k) / k
        smooth = np.convolve(row_density, kernel, mode="same")
        thr = max(3.0, float(smooth.max()) * 0.25)
        peaks: List[int] = []
        for i in range(2, len(smooth) - 2):
            if smooth[i] >= thr and smooth[i] >= smooth[i - 1] and smooth[i] >= smooth[i + 1]:
                if not peaks or i - peaks[-1] > 12:
                    peaks.append(i)
                elif smooth[i] > smooth[peaks[-1]]:
                    peaks[-1] = i
        # Convert to full-image Y fractions
        fracs = [(y1 + p) / float(h) for p in peaks]
        # Keep plausible track spacing (merge if too close)
        cleaned: List[float] = []
        for f in fracs:
            if not cleaned or abs(f - cleaned[-1]) > 0.015:
                cleaned.append(f)
        return cleaned[:32]
    except Exception:
        return []


def is_studio_one_arrange_shot(path: "Path | None") -> bool:
    """
    True if screenshot looks like a Studio One song arrange (not Grok/Terminal).

    Root-cause lesson: after S1 crash/focus loss, ImageGrab captured the agent
    TUI — arm clicks hit the chat window and never toggled Rec.
    """
    if path is None or not Path(path).exists():
        return False
    try:
        from PIL import Image
        import numpy as np

        img = Image.open(str(path)).convert("RGB")
        arr = np.asarray(img, dtype=np.int16)
        h, w = arr.shape[:2]
        if w < 800 or h < 500:
            return False
        r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
        pure_black = float(((r < 12) & (g < 12) & (b < 12)).mean())
        # Grok TUI is almost pure black with light text — reject early
        if pure_black > 0.45:
            return False

        chroma = np.maximum(np.maximum(r, g), b) - np.minimum(np.minimum(r, g), b)
        # Track color-index bars: thin high-chroma vertical strips left of M/S/Rec
        x0, x1 = int(w * 0.24), int(w * 0.38)
        y0, y1 = int(h * 0.15), int(h * 0.75)
        strip = (chroma[y0:y1, x0:x1] > 50) & (
            np.maximum(
                np.maximum(r[y0:y1, x0:x1], g[y0:y1, x0:x1]), b[y0:y1, x0:x1]
            )
            > 90
        )
        # Vertical projection — bars create tall thin peaks
        colsum = strip.sum(axis=0).astype(float)
        bar_cols = int((colsum > max(8.0, float(colsum.max()) * 0.2)).sum()) if colsum.size else 0
        # Blue/cyan MIDI parts in arrange grid
        gx0, gx1 = int(w * 0.40), int(w * 0.72)
        grid = arr[y0:y1, gx0:gx1]
        gr, gg, gb = grid[:, :, 0], grid[:, :, 1], grid[:, :, 2]
        midi_like = int(
            (
                ((gb > 120) & (gb > gr + 20))
                | ((gg > 120) & (gg > gr + 20) & (gg > gb))
            ).sum()
        )
        # Need track-color signature OR substantial MIDI clips
        if bar_cols >= 2 or midi_like > 800:
            return True
        return False
    except Exception:
        return False


# Calibrated Rec Enable X band on 1920px primary (S1 6.6 Artist).
# Armed Rec red lives at x≈619–652; Monitor speaker is to the RIGHT (x≈665–680).
# Older code used a wide grey-blob search and often returned Monitor, not Rec.
# Fractions scale to any resolution / aspect ratio (laptop 16:9, 16:10, etc.).
REC_X_BAND = (605, 655)  # absolute fallback for 1920-wide grabs
REC_X_FRAC = (605 / 1920.0, 655 / 1920.0)
MONITOR_X_MIN = 660
MONITOR_X_FRAC = 660 / 1920.0


def rec_x_band_for_width(w: int) -> Tuple[int, int]:
    """Rec column X band scaled to screenshot width (aspect-safe)."""
    if w <= 0:
        return REC_X_BAND
    # Prefer fractions so 1366/1600/1920/2560 and non-16:9 heights stay correct.
    x0 = int(round(w * REC_X_FRAC[0]))
    x1 = int(round(w * REC_X_FRAC[1]))
    if x1 <= x0:
        x1 = x0 + max(8, int(w * 0.02))
    return x0, min(w - 1, x1)


def get_screen_geometry() -> Dict[str, Any]:
    """
    Primary display size, aspect ratio, and DPI — required before trusting click coords.
    LAPTOP often differs from AI-CODING 1920x1080 calibration.
    """
    try:
        from .human_input import ensure_dpi_aware

        ensure_dpi_aware()
    except Exception:
        pass
    out: Dict[str, Any] = {
        "width": 0,
        "height": 0,
        "aspect": 0.0,
        "aspect_label": "unknown",
        "dpi": 96,
        "scale": 1.0,
        "ok": False,
    }
    try:
        import ctypes

        user32 = ctypes.windll.user32
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                user32.SetProcessDPIAware()
            except Exception:
                pass
        w = int(user32.GetSystemMetrics(0))
        h = int(user32.GetSystemMetrics(1))
        dc = user32.GetDC(0)
        dpi = int(ctypes.windll.gdi32.GetDeviceCaps(dc, 88))
        user32.ReleaseDC(0, dc)
        scale = dpi / 96.0
        aspect = (w / h) if h else 0.0
        # Label common ratios (tolerance ~2%)
        label = "custom"
        for name, ratio in (
            ("16:9", 16 / 9),
            ("16:10", 16 / 10),
            ("3:2", 3 / 2),
            ("4:3", 4 / 3),
            ("21:9", 21 / 9),
        ):
            if aspect and abs(aspect - ratio) / ratio < 0.025:
                label = name
                break
        out.update(
            {
                "width": w,
                "height": h,
                "aspect": round(aspect, 4),
                "aspect_label": label,
                "dpi": dpi,
                "scale": round(scale, 3),
                "ok": w > 0 and h > 0,
            }
        )
        log(
            f"  eyes geometry: {w}x{h} aspect={label} ({aspect:.3f}) "
            f"dpi={dpi} scale={scale:.2f}"
        )
        if not (0.95 <= scale <= 1.05):
            log(f"  WARN DPI scale={scale:.2f} — prefer fraction-based UI targets")
        return out
    except Exception as e:
        out["error"] = str(e)
        return out


def locate_track_rec_buttons(path: "Path | None") -> List[Tuple[int, int]]:
    """
    Return screen/image pixel (x,y) of **Rec Enable** for each visible track row.

    Critical: do **not** return Monitor (speaker) positions. Live calibration
    showed armed Rec red at x≈635; Monitor sits ~x≥665. Clicking Monitor
    enables input echo (cyan speaker) and leaves Rec grey — false “arm”.
    """
    if path is None or not Path(path).exists():
        return []
    try:
        from PIL import Image
        import numpy as np

        img = Image.open(str(path)).convert("RGB")
        arr = np.asarray(img, dtype=np.int16)
        h, w = arr.shape[:2]
        r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]

        # Anchor Rec X: any arrange-header red Rec, else aspect-scaled band center
        x_lo, x_hi = rec_x_band_for_width(w)
        mon_min = int(round(w * MONITOR_X_FRAC))
        y_top, y_bot = int(h * 0.14), int(h * 0.82)
        red = (r > 200) & (g < 120) & (b < 120) & (r > g + 50) & (r > b + 50)
        mask = red.copy()
        mask[:, : max(0, x_lo - 10)] = False
        mask[:, min(w, x_hi + 10) :] = False
        mask[:y_top, :] = False
        mask[y_bot:, :] = False
        ys, xs = np.where(mask)
        if len(xs) >= 8:
            rec_x = int(np.median(xs))
        else:
            rec_x = int((x_lo + x_hi) // 2)

        # Never drift into Monitor column (right of Rec; scales with width)
        rec_x = max(x_lo, min(min(x_hi, mon_min - 1), rec_x))

        def row_score(y: int) -> int:
            y0, y1 = max(0, y - 6), min(h, y + 7)
            x0, x1 = max(0, rec_x - 14), min(w, rec_x + 15)
            reg = arr[y0:y1, x0:x1]
            rr, gg, bb = reg[:, :, 0].astype(int), reg[:, :, 1].astype(int), reg[:, :, 2].astype(int)
            rn = int(((rr > 180) & (gg < 130) & (bb < 130) & (rr > gg + 40)).sum())
            # Unarmed Rec is mid-grey disc (not as dark as track body)
            gn = int(
                (
                    (rr >= 65)
                    & (rr <= 150)
                    & (gg >= 65)
                    & (gg <= 150)
                    & (bb >= 65)
                    & (bb <= 150)
                    & (np.abs(rr - gg) < 28)
                    & (np.abs(gg - bb) < 28)
                ).sum()
            )
            return rn * 5 + gn

        y_scan0 = y_top + 15
        y_scan1 = max(y_scan0 + 1, y_bot - 20)
        scores = np.array([row_score(y) for y in range(y_scan0, y_scan1)], dtype=float)
        if scores.size == 0:
            return []
        sm = np.convolve(scores, np.ones(5) / 5, mode="same")
        peaks: List[int] = []
        for i in range(8, len(sm) - 8):
            if sm[i] >= 25 and sm[i] >= sm[i - 6 : i + 7].max():
                y = y_scan0 + i
                # Min spacing ~ one track (compact ~40–50px; expanded ~80+)
                if not peaks or y - peaks[-1] >= 38:
                    peaks.append(y)
                elif sm[i] > sm[peaks[-1] - y_scan0]:
                    peaks[-1] = y

        # Prefer control-row peaks (higher score) when two peaks are within one track
        cleaned: List[int] = []
        for y in peaks:
            if cleaned and y - cleaned[-1] < 55:
                # keep better score
                if row_score(y) > row_score(cleaned[-1]):
                    cleaned[-1] = y
            else:
                cleaned.append(y)

        return [(rec_x, int(y)) for y in cleaned[:24]]
    except Exception:
        return []


def rec_click_point_for_track(
    path: "Path | None",
    track: int,
    window_rect: Optional[Tuple[int, int, int, int]] = None,
) -> Optional[Tuple[int, int]]:
    """
    Screen (x,y) to click Rec Enable for 1-based arrange track.
    Prefer vision-located Rec buttons; fall back to Rec X band + row pitch.
    Never returns Monitor column (x >= 660).
    """
    if path is None or track < 1:
        return None
    pts = locate_track_rec_buttons(path)
    if pts and track <= len(pts):
        x, y = pts[track - 1]
        if x >= MONITOR_X_MIN:
            x = (REC_X_BAND[0] + REC_X_BAND[1]) // 2
        return int(x), int(y)
    try:
        from PIL import Image

        img = Image.open(str(path))
        iw, ih = img.size
        yf = 0.20 + (track - 1) * 0.042
        # Absolute Rec X on typical 1920 desktop; scale if needed
        x = 635 if iw >= 1800 else int(iw * 0.33)
        x = max(REC_X_BAND[0], min(REC_X_BAND[1], x))
        return int(x), int(ih * yf)
    except Exception:
        return None
