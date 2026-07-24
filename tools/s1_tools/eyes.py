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
