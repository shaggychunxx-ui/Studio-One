#!/usr/bin/env python3
"""
Diagnose Rec-arm issues offline (saved shots) and live (if S1 open).

Reports:
  - Is shot actually Studio One arrange? (vs Grok/Terminal)
  - Located Rec points (X must be in Rec band 605–655, not Monitor ≥660)
  - Which rows look Rec-red (strict)
  - Live: try arm_and_verify track 1..N once each

Usage:
  py -3.12 tools/diagnose_arm.py
  py -3.12 tools/diagnose_arm.py --shot path\\to.png
  py -3.12 tools/diagnose_arm.py --live --tracks 1 3 5
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TOOLS))

from s1_tools.eyes import (  # noqa: E402
    is_studio_one_arrange_shot,
    locate_track_rec_buttons,
    scan_rec_red,
    list_armed_visible_rows,
    REC_X_BAND,
    MONITOR_X_MIN,
)


def diagnose_shot(path: Path) -> dict:
    ok_ui = is_studio_one_arrange_shot(path)
    pts = locate_track_rec_buttons(path) if ok_ui else []
    armed = list_armed_visible_rows(path) if ok_ui else []
    issues = []
    if not ok_ui:
        issues.append("NOT_S1_ARRANGE — focus loss/crash; clicks hit wrong window")
    for i, (x, y) in enumerate(pts):
        if x >= MONITOR_X_MIN:
            issues.append(f"row{i+1} x={x} looks like MONITOR not Rec")
        if not (REC_X_BAND[0] <= x <= REC_X_BAND[1]):
            issues.append(f"row{i+1} x={x} outside Rec band {REC_X_BAND}")
    # annotate
    if path.exists():
        im = Image.open(path).convert("RGB")
        dr = ImageDraw.Draw(im)
        # Rec band
        dr.rectangle([REC_X_BAND[0], 140, REC_X_BAND[1], 720], outline=(0, 180, 255), width=1)
        dr.line([(MONITOR_X_MIN, 140), (MONITOR_X_MIN, 720)], fill=(255, 128, 0), width=1)
        for i, (x, y) in enumerate(pts):
            col = (0, 255, 0) if REC_X_BAND[0] <= x <= REC_X_BAND[1] else (255, 0, 0)
            dr.ellipse([x - 8, y - 8, x + 8, y + 8], outline=col, width=2)
            dr.text((x + 12, y - 8), f"R{i+1}", fill=(255, 255, 0))
            if scan_rec_red(path, visible_row=i + 1, allow_fallback=False):
                dr.text((x + 12, y + 6), "RED", fill=(255, 80, 80))
        out = path.with_name(path.stem + "_arm_diag.png")
        im.save(out)
    else:
        out = None
    return {
        "path": str(path),
        "is_s1_arrange": ok_ui,
        "rec_pts": pts,
        "armed_rows": armed,
        "issues": issues,
        "annotate": str(out) if out else None,
        "rec_x_band": REC_X_BAND,
        "monitor_x_min": MONITOR_X_MIN,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shot", type=Path, nargs="*", default=[])
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--tracks", type=int, nargs="*", default=[1, 3, 5])
    args = ap.parse_args()

    shots = list(args.shot)
    if not shots:
        # default known problem shots
        base = Path(
            r"C:\Users\Box One\Documents\Studio One\Songs\2026-07-25 ralph rodrigues\_vision"
        )
        for rel in (
            "drums_only/081418_arm_fail.png",
            "finish/081003_arm_BED.png",
            "finish/mapped.png",
            "one_track/075846_armed_BASS.png",
        ):
            p = base / rel
            if p.exists():
                shots.append(p)

    print("=" * 60)
    print("REC ARM DIAGNOSIS")
    print("=" * 60)
    print(f"Rec X band (must click here): {REC_X_BAND}")
    print(f"Monitor column starts at x>={MONITOR_X_MIN} — NEVER click as arm")
    print()

    for p in shots:
        rep = diagnose_shot(p)
        print(f"--- {p.name} ---")
        print(f"  is_s1_arrange: {rep['is_s1_arrange']}")
        print(f"  rec_pts ({len(rep['rec_pts'])}): {rep['rec_pts']}")
        print(f"  armed_rows: {rep['armed_rows']}")
        if rep["issues"]:
            for iss in rep["issues"]:
                print(f"  ISSUE: {iss}")
        else:
            print("  issues: none")
        print(f"  annotate: {rep['annotate']}")
        print()

    if args.live:
        from s1remote.hotkeys import studio_one_running, focus_studio_one
        from s1remote.full_control import FullControl
        from s1_tools.eyes import Eyes

        if not studio_one_running():
            print("LIVE: Studio One not running — skip")
            return 0
        focus_studio_one()
        eyes = Eyes(Path("_vision") / "arm_diag_live")
        with FullControl() as s1:
            for t in args.tracks:
                print(f"LIVE arm_and_verify track={t} …")
                ok = s1.arm_and_verify(t, eyes_dir=eyes.directory, retries=3)
                print(f"  → {ok}")
                # disarm with [R] if armed so next track is clean
                if ok:
                    from s1remote.hotkeys import run_action

                    run_action("arm", focus=True)
                    import time

                    time.sleep(0.3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
