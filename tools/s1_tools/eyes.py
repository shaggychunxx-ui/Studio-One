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
from typing import List, Optional, Tuple

from .logutil import log


class Eyes:
    def __init__(self, directory: Path, *, enabled: bool = True):
        self.directory = Path(directory)
        self.enabled = enabled
        self._watch: threading.Thread | None = None
        self._stop = threading.Event()
        self.shot_count = 0

    def shot(self, tag: str) -> Path | None:
        if not self.enabled:
            return None
        try:
            from PIL import ImageGrab
        except ImportError:
            log("  eyes: PIL not installed (pip install pillow) — skip shot")
            return None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            path = self.directory / f"{datetime.now().strftime('%H%M%S')}_{tag}.png"
            ImageGrab.grab().save(str(path))
            self.shot_count += 1
            log(f"  eyes 📷 {path.name}")
            return path
        except Exception as e:
            log(f"  eyes shot fail: {e}")
            return None

    def start_watch(self, label: str, interval: float = 8.0) -> None:
        if not self.enabled:
            return
        self._stop.clear()

        def _run() -> None:
            n = 0
            while not self._stop.wait(interval):
                n += 1
                self.shot(f"watch_{label}_{n:02d}")

        self._watch = threading.Thread(target=_run, daemon=True)
        self._watch.start()

    def stop_watch(self) -> None:
        self._stop.set()
        if self._watch is not None:
            self._watch.join(timeout=2.0)
            self._watch = None


def scan_rec_red(path: "Path | None", track: int | None = None) -> bool:
    """
    Heuristic: bright-red pixels = Rec Enable armed.

    If ``track`` is set, first check that row band; if empty, fall back to the
    full Rec column so a slightly-wrong pitch calibration still works.
    """
    if path is None or not Path(path).exists():
        return False
    try:
        from PIL import Image
        import numpy as np

        img = Image.open(str(path)).convert("RGB")
        arr = np.asarray(img, dtype=np.int16)
        h, w = arr.shape[:2]
        x1, x2 = int(w * 0.22), int(w * 0.50)

        def count_red(y1: int, y2: int) -> int:
            y1 = max(0, min(h - 1, y1))
            y2 = max(y1 + 1, min(h, y2))
            region = arr[y1:y2, x1:x2]
            r, g, b = region[:, :, 0], region[:, :, 1], region[:, :, 2]
            mask = (r > 155) & (g < 110) & (b < 110) & (r > g + 45) & (r > b + 45)
            return int(mask.sum())

        if track is not None and track >= 1:
            # Prefer live row pitch from image if we can find rec candidates
            rows = find_rec_row_centers_frac(path)
            if rows and 1 <= track <= len(rows):
                yf = rows[track - 1]
                half = 0.025
                n = count_red(int(h * (yf - half)), int(h * (yf + half)))
                if n >= 4:
                    return True
            # Fallback fixed pitch
            y_mid = 0.20 + (track - 1) * 0.042
            n = count_red(int(h * (y_mid - 0.025)), int(h * (y_mid + 0.025)))
            if n >= 4:
                return True
            # Last resort: any rec red in column (still better than silent fail)
            return count_red(int(h * 0.12), int(h * 0.88)) >= 8

        return count_red(int(h * 0.12), int(h * 0.88)) >= 6
    except Exception:
        return False


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


def locate_track_rec_buttons(path: "Path | None") -> List[Tuple[int, int]]:
    """
    Return screen/image pixel (x,y) of Rec Enable for each visible track row.

    Detects color-index bars + grey control cluster (M S Rec …) in Arrange.
    ImageGrab full-desktop coords == screen coords on primary display.
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
        chroma = np.maximum(np.maximum(r, g), b) - np.minimum(np.minimum(r, g), b)
        colorful = (chroma > 40) & (np.maximum(np.maximum(r, g), b) > 80)
        x1, x2 = int(w * 0.18), int(w * 0.55)
        y1, y2 = int(h * 0.14), int(h * 0.78)
        colsum = colorful[y1:y2, x1:x2].sum(axis=0)
        peaks_x: List[int] = []
        for i in range(2, len(colsum) - 2):
            if colsum[i] > 25 and colsum[i] >= colsum[i - 1] and colsum[i] >= colsum[i + 1]:
                if not peaks_x or i - peaks_x[-1] > 12:
                    peaks_x.append(i)
        bar_x = x1 + peaks_x[0] if peaks_x else int(w * 0.28)
        cx1, cx2 = bar_x + 15, min(w - 1, bar_x + 140)
        grey = (
            (r > 45)
            & (r < 115)
            & (g > 45)
            & (g < 115)
            & (b > 45)
            & (b < 115)
            & (np.abs(r.astype(int) - g) < 22)
            & (np.abs(g.astype(int) - b) < 22)
        )
        rowsum = grey[y1:y2, cx1:cx2].sum(axis=1).astype(float)
        rows: List[int] = []
        for i in range(4, len(rowsum) - 4):
            if rowsum[i] > 12 and rowsum[i] >= rowsum[max(0, i - 10) : i + 11].max():
                if not rows or i - rows[-1] > 18:
                    rows.append(i)
        pts: List[Tuple[int, int]] = []
        for ry in rows:
            y = y1 + ry
            strip = grey[max(0, y - 5) : min(h, y + 6), cx1:cx2].sum(axis=0)
            xs: List[int] = []
            for i in range(2, len(strip) - 2):
                if strip[i] > 2 and strip[i] >= strip[i - 1] and strip[i] >= strip[i + 1]:
                    if not xs or i - xs[-1] > 10:
                        xs.append(i)
            # Rec is usually the 3rd compact control (M=0 S=1 Rec=2)
            if len(xs) >= 3:
                x = cx1 + xs[2]
            elif xs:
                x = cx1 + xs[-1]
            else:
                x = cx1 + 40
            pts.append((int(x), int(y)))
        return pts
    except Exception:
        return []


def rec_click_point_for_track(
    path: "Path | None",
    track: int,
    window_rect: Optional[Tuple[int, int, int, int]] = None,
) -> Optional[Tuple[int, int]]:
    """
    Screen (x,y) to click Rec Enable for 1-based arrange track.
    Prefer vision-located buttons; fall back to layout fractions.
    """
    if path is None or track < 1:
        return None
    pts = locate_track_rec_buttons(path)
    if pts and track <= len(pts):
        return pts[track - 1]
    try:
        from PIL import Image

        img = Image.open(str(path))
        iw, ih = img.size
        yf = 0.20 + (track - 1) * 0.025  # denser pitch from live map (~27px)
        xf = 0.275
        return int(iw * xf), int(ih * yf)
    except Exception:
        return None
