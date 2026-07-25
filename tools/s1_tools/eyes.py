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
    Heuristic: scan a screenshot for bright-red pixels that indicate
    a Rec button is armed in Studio One (Rec Enable = red).

    Focuses on the Arrange track-header band. If ``track`` (1-based) is
    given, only that row's vertical band is checked (avoids false OK when
    another track is still armed).
    """
    if path is None or not Path(path).exists():
        return False
    try:
        from PIL import Image
        import numpy as np

        img = Image.open(str(path)).convert("RGB")
        # Downsample but keep enough detail for ~12px Rec dots
        scale = max(1, img.width // 960)
        if scale > 1:
            img = img.resize((img.width // scale, img.height // scale))
        arr = np.asarray(img, dtype=np.int16)
        h, w = arr.shape[:2]
        # Rec column ~25–45% width of full grab
        x1 = int(w * 0.25)
        x2 = int(w * 0.48)
        if track is not None and track >= 1:
            # Calibrated: track1 ~20% height, pitch ~4.2%
            y_mid = 0.20 + (track - 1) * 0.042
            half = 0.022
            y1 = int(h * max(0.10, y_mid - half))
            y2 = int(h * min(0.90, y_mid + half))
        else:
            y1 = int(h * 0.12)
            y2 = int(h * 0.88)
        region = arr[y1:y2, x1:x2]
        r, g, b = region[:, :, 0], region[:, :, 1], region[:, :, 2]
        # Rec enable is saturated red/orange-red
        mask = (r > 160) & (g < 100) & (b < 100) & (r > g + 50) & (r > b + 50)
        red_count = int(mask.sum())
        return red_count >= 6
    except Exception:
        return False
