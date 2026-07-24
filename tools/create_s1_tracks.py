#!/usr/bin/env python3
"""
Add Instrument Track(s) to the open Studio One Song via menu UIA.

  Track → Add Instrument Track

No song-folder hardcoding. Optional browser_load is best-effort (user drag preferred).

Env:
  S1_REMOTE  — path to s1-remote (optional if run from this repo)

Usage:
  py -3.12 tools/create_s1_tracks.py --count 2
  py -3.12 tools/create_s1_tracks.py --count 1 --no-load
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from s1_tools.paths import ensure_s1remote_on_path  # noqa: E402
from s1_tools.logutil import log  # noqa: E402
from s1_tools.arrange import add_instrument_tracks  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Add Instrument Tracks (menu UIA)")
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--no-load", action="store_true", help="Skip browser_load attempts")
    ap.add_argument("--load", nargs="*", default=[], help="Optional instrument search names")
    ap.add_argument("--s1-remote", type=Path, default=None)
    args = ap.parse_args()

    ensure_s1remote_on_path(args.s1_remote)
    from s1remote.full_control import FullControl  # noqa: E402
    from s1remote.hotkeys import focus_studio_one  # noqa: E402
    from pywinauto.keyboard import send_keys  # noqa: E402

    log("Create instrument tracks in open Studio One session")
    n = add_instrument_tracks(args.count, focus_fn=focus_studio_one)
    if n < 1:
        log("FAIL: no tracks created")
        return 1
    log(f"Created {n} instrument track(s)")

    if not args.no_load and args.load:
        try:
            with FullControl() as s1:
                for i, name in enumerate(args.load):
                    log(f"  browser_load {name!r} (may not assign VST — user drag preferred)")
                    s1.browser_load(name)
                    time.sleep(1.0)
                    if i + 1 < len(args.load):
                        send_keys("{DOWN}")
                        time.sleep(0.2)
        except Exception as e:
            log(f"  load warn: {e}")

    log("Done — confirm instruments with eyes/UI (browser_load is not reliable).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
