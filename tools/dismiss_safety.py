#!/usr/bin/env python3
"""CLI: detect/dismiss Studio One Safety dialog (crash recovery).

Usage (on Template host, interactive desktop):
  py -3.12 tools/dismiss_safety.py
  py -3.12 tools/dismiss_safety.py --hard   # kill S1 + clear crash markers
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

from s1_tools.vision import (  # noqa: E402
    detect_safety_dialog_uia,
    dismiss_safety_dialog,
    hard_clear_safety,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Dismiss Studio One Safety dialog")
    ap.add_argument(
        "--hard",
        action="store_true",
        help="If soft dismiss fails: kill Studio One and clear crash markers",
    )
    args = ap.parse_args()

    present = detect_safety_dialog_uia()
    print(f"safety_present_before={present}")
    if not present:
        print("OK: no visible Safety dialog")
        return 0

    ok = dismiss_safety_dialog(retries=5)
    print(f"soft_dismiss_ok={ok} safety_after={detect_safety_dialog_uia()}")
    if ok:
        return 0
    if args.hard:
        hard_ok = hard_clear_safety(kill_s1=True)
        print(f"hard_clear_ok={hard_ok} safety_after={detect_safety_dialog_uia()}")
        return 0 if hard_ok else 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
