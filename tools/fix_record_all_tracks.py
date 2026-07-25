#!/usr/bin/env python3
"""
Fix empty tracks: exclusive-arm each instrument row and re-record MIDI.

Root causes of "only one track has clips":
  1) Multiple streams landed on the same armed track (usually Mai Tai).
  2) track index treated as absolute S1 number while vision uses *visible row*.
  3) scan_rec_red fell back to "any red" → arm_and_verify returned True falsely.
  4) clip growth was global blue count, not per-lane.

Solution:
  disarm all → Alt+click Rec on target visible row only → strict red verify
  → transport Record → stream → stop → per-lane blue growth check.

Usage:
  set PYTHONPATH=%CD%;%CD%\\tools
  set S1_SONG_DIR=...
  py -3.12 tools/fix_record_all_tracks.py --max-sec 45
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import mido

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TOOLS))

from s1_tools.paths import ensure_s1remote_on_path, resolve_song_dir  # noqa: E402
from s1_tools.logutil import log, set_log_file  # noqa: E402
from s1_tools.eyes import (  # noqa: E402
    Eyes,
    scan_rec_red,
    locate_track_rec_buttons,
    count_lane_blue,
    list_armed_visible_rows,
)
from s1_tools.ears import capture  # noqa: E402
from s1_tools.vision import analyze_shot, detect_safety_dialog_uia, dismiss_safety_dialog  # noqa: E402


def _click(x: int, y: int, *, alt: bool = False) -> None:
    import ctypes

    u = ctypes.windll.user32
    # VK_MENU = 0x12
    if alt:
        u.keybd_event(0x12, 0, 0, 0)
        time.sleep(0.03)
    u.SetCursorPos(int(x), int(y))
    time.sleep(0.03)
    u.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.03)
    u.mouse_event(0x0004, 0, 0, 0, 0)
    if alt:
        time.sleep(0.03)
        u.keybd_event(0x12, 0, 2, 0)  # KEYEVENTF_KEYUP


def disarm_all(eyes: Eyes, rounds: int = 6) -> None:
    """Turn off every Rec-red by clicking armed rows (plain click = toggle off)."""
    from s1remote.hotkeys import focus_studio_one

    focus_studio_one()
    for r in range(rounds):
        shot = eyes.shot(f"disarm_scan_{r}")
        armed = list_armed_visible_rows(shot)
        if not armed or armed == [-1]:
            if not scan_rec_red(shot):
                log(f"  disarm: clear (round {r})")
                return
            # global red but no row map — click all located buttons once
            pts = locate_track_rec_buttons(shot)
            for x, y in pts[:12]:
                _click(x, y)
                time.sleep(0.12)
            continue
        log(f"  disarm: armed rows {armed}")
        pts = locate_track_rec_buttons(shot)
        for row in armed:
            if 1 <= row <= len(pts):
                x, y = pts[row - 1]
                _click(x, y)
                time.sleep(0.18)
        time.sleep(0.2)
    log("  disarm: done best-effort")


def exclusive_arm_row(visible_row: int, eyes: Eyes, label: str) -> bool:
    """
    Disarm all, Alt+click Rec on visible row (Studio One exclusive arm),
    verify ONLY that row is red.
    """
    from s1remote.hotkeys import focus_studio_one

    disarm_all(eyes)
    focus_studio_one()
    time.sleep(0.25)

    shot = eyes.shot(f"arm_locate_{label}_r{visible_row}")
    pts = locate_track_rec_buttons(shot)
    if not pts:
        log(f"  exclusive arm FAIL: no rec buttons located for {label}")
        return False
    if visible_row < 1 or visible_row > len(pts):
        log(f"  exclusive arm FAIL: row {visible_row} out of range (have {len(pts)})")
        return False

    x, y = pts[visible_row - 1]
    log(f"  exclusive Alt+click {label} row={visible_row} @ ({x},{y}) n_pts={len(pts)}")
    # Alt+click = exclusive record enable in Studio One
    _click(x, y, alt=True)
    time.sleep(0.45)

    after = eyes.shot(f"arm_after_{label}_r{visible_row}")
    armed_rows = list_armed_visible_rows(after)
    strict = scan_rec_red(after, visible_row=visible_row, allow_fallback=False)
    log(f"  arm check {label}: strict={strict} armed_rows={armed_rows}")

    if strict and (armed_rows == [visible_row] or visible_row in armed_rows):
        # Prefer exclusive; accept if target is armed even if detector sees extras
        if armed_rows == [visible_row]:
            return True
        if visible_row in armed_rows and len(armed_rows) <= 2:
            log(f"  WARN {label}: extra armed {armed_rows} — continuing")
            return True

    # Retry: plain click if still grey (Alt may have missed)
    if not strict:
        log(f"  retry plain click {label}")
        _click(x, y, alt=False)
        time.sleep(0.4)
        after2 = eyes.shot(f"arm_retry_{label}_r{visible_row}")
        strict = scan_rec_red(after2, visible_row=visible_row, allow_fallback=False)
        armed_rows = list_armed_visible_rows(after2)
        log(f"  arm retry {label}: strict={strict} armed_rows={armed_rows}")
        if strict:
            return True

    # Last: keyboard select via Down from top + [R]
    try:
        from s1remote.full_control import FullControl
        from s1remote.hotkeys import run_action
        from pywinauto.keyboard import send_keys

        focus_studio_one()
        send_keys("{ESC}")
        time.sleep(0.1)
        # Click track name area left of Rec to select the row
        _click(x - 80, y)
        time.sleep(0.2)
        run_action("arm", focus=False)
        time.sleep(0.4)
        after3 = eyes.shot(f"arm_kb_{label}_r{visible_row}")
        strict = scan_rec_red(after3, visible_row=visible_row, allow_fallback=False)
        log(f"  arm kb {label}: strict={strict} rows={list_armed_visible_rows(after3)}")
        if strict:
            return True
    except Exception as e:
        log(f"  arm kb err: {e}")

    return False


def stream_mid(s1, path: Path, *, label: str, eyes: Eyes, max_sec=None) -> int:
    mid = mido.MidiFile(str(path))
    total = float(mid.length) or 1.0
    bridge = s1.remote.instrument.bridge
    log(f"  STREAM {path.name} ~{total:.1f}s (cap={max_sec})")
    eyes.start_watch(label, 8.0)
    t0 = time.perf_counter()
    target = 0.0
    n_on = 0
    last = 0.0
    try:
        for msg in mid:
            target += msg.time
            if max_sec is not None and target > max_sec:
                break
            delay = target - (time.perf_counter() - t0)
            if delay > 0.0005:
                time.sleep(delay)
            if msg.is_meta:
                continue
            try:
                out = msg.copy(channel=0)
            except Exception:
                out = msg
            if out.type == "note_on" and getattr(out, "velocity", 0) > 0:
                n_on += 1
            if out.type in ("note_on", "note_off", "control_change"):
                bridge.send(out)
            wall = time.perf_counter() - t0
            if wall - last >= 3.0:
                log(f"  … {label} notes={n_on} {wall:.1f}s {min(100, 100 * target / total):.0f}%")
                last = wall
    finally:
        eyes.stop_watch()
        try:
            s1.remote.instrument.all_notes_off(0)
        except Exception:
            pass
    return n_on


def record_one(
    s1,
    path: Path,
    visible_row: int,
    label: str,
    eyes: Eyes,
    max_sec: float,
) -> dict:
    from s1remote.hotkeys import focus_studio_one

    log(f"######## FIX RECORD {label} → visible row {visible_row} ########")
    focus_studio_one()
    try:
        s1.stop()
        s1.remote.mcu.rewind()
    except Exception:
        pass
    time.sleep(0.3)

    armed = exclusive_arm_row(visible_row, eyes, label)
    if not armed:
        log(f"  FAIL arm {label}")
        return {
            "label": label,
            "visible_row": visible_row,
            "ok": False,
            "error": "arm_failed",
        }

    pre = eyes.shot(f"fix_before_{label}")
    pre_blue = count_lane_blue(pre, visible_row)
    pre_global = analyze_shot(pre)
    log(f"  pre lane_blue={pre_blue} global_blue={pre_global.blue_pixel_hits}")

    # Confirm still armed right before record
    if not scan_rec_red(pre, visible_row=visible_row, allow_fallback=False):
        log(f"  FAIL {label}: lost arm before record")
        return {
            "label": label,
            "visible_row": visible_row,
            "ok": False,
            "error": "lost_arm",
            "lane_blue_before": pre_blue,
        }

    s1.record()
    time.sleep(0.5)
    rec = eyes.shot(f"fix_rec_{label}")
    if not scan_rec_red(rec, visible_row=visible_row, allow_fallback=False):
        log("  WARN: target not red after transport Record — continuing")
    else:
        log(f"  rec confirmed red on row {visible_row}")

    n = stream_mid(s1, path, label=label, eyes=eyes, max_sec=max_sec)
    try:
        s1.stop()
    except Exception:
        pass
    time.sleep(0.4)

    after = eyes.shot(f"fix_after_{label}")
    after_blue = count_lane_blue(after, visible_row)
    after_v = analyze_shot(after)
    clip_growth = after_blue > pre_blue + 40
    log(
        f"  FIX {label}: notes={n} lane_blue {pre_blue}→{after_blue} "
        f"growth={clip_growth} global={after_v.blue_pixel_hits}"
    )

    # Disarm for next exclusive pass
    disarm_all(eyes, rounds=3)

    ok = n > 0 and clip_growth
    if n > 0 and not clip_growth:
        log(f"  NO CLIP GROWTH on {label} despite {n} notes — mark fail")
    return {
        "label": label,
        "visible_row": visible_row,
        "ok": ok,
        "note_ons": n,
        "clip_growth": clip_growth,
        "lane_blue_before": pre_blue,
        "lane_blue_after": after_blue,
        "blue_global_after": after_v.blue_pixel_hits,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--song-dir", type=Path, default=None)
    ap.add_argument("--max-sec", type=float, default=45.0)
    ap.add_argument(
        "--map",
        default="ralph",
        choices=("ralph", "agent"),
        help="Track layout: ralph = open song rows; agent = old autonomy test map",
    )
    args = ap.parse_args()

    ensure_s1remote_on_path()
    song = resolve_song_dir(args.song_dir)
    vision = song / "_vision" / "fix_record"
    vision.mkdir(parents=True, exist_ok=True)
    set_log_file(vision / "fix_record.log")

    from s1remote.full_control import FullControl
    from s1remote.hotkeys import focus_studio_one, run_action, studio_one_running

    if not studio_one_running():
        log("FATAL: Studio One not running")
        return 2
    if detect_safety_dialog_uia():
        dismiss_safety_dialog()
        time.sleep(1.2)

    eyes = Eyes(vision)
    focus_studio_one()
    start = eyes.shot("00_before_fix")
    pts0 = locate_track_rec_buttons(start)
    armed0 = list_armed_visible_rows(start)
    log(f"  before: rec_pts={len(pts0)} armed={armed0} vision={analyze_shot(start).to_dict()}")

    # Visible-row maps (1-based among locate_track_rec_buttons order).
    # ralph song screenshot: row1=Mai Tai(t3), 2=Mai Tai2, 3=Mojito, 5=Presence, 7=SampleOne
    if args.map == "ralph":
        parts = [
            ("drums.mid", 7, "DRUMS"),   # SampleOne row
            ("bass.mid", 3, "BASS"),     # Mojito
            ("color.mid", 2, "COLOR"),   # Mai Tai 2
            ("bed.mid", 5, "BED"),       # Presence
            ("lead.mid", 1, "LEAD"),     # Mai Tai (refresh full form)
        ]
    else:
        # legacy absolute-ish map (often wrong when labels start at 3)
        parts = [
            ("drums.mid", 1, "DRUMS"),
            ("bass.mid", 5, "BASS"),
            ("lead.mid", 3, "LEAD"),
            ("bed.mid", 7, "BED"),
            ("color.mid", 4, "COLOR"),
        ]

    results = []
    with FullControl() as s1:
        st = s1.status()
        if not st.get("instrument_midi_connected"):
            log("FATAL: S1 Notes not connected")
            return 3
        log(f"  notes ok out={st.get('instrument_midi_out')}")

        for fname, row, label in parts:
            path = song / "MIDI" / fname
            if not path.is_file():
                # try agent autonomy test MIDI folder as fallback
                alt = Path(
                    r"C:\Users\Box One\Documents\Studio One\Songs\_agent_autonomy_test\MIDI"
                ) / fname
                if alt.is_file():
                    path = alt
                else:
                    results.append({"label": label, "ok": False, "error": "missing_midi"})
                    continue
            r = record_one(s1, path, row, label, eyes, args.max_sec)
            results.append(r)
            time.sleep(0.4)

        # mix listen
        focus_studio_one()
        try:
            s1.stop()
            for _ in range(3):
                s1.remote.mcu.rewind()
                time.sleep(0.08)
            for ch in range(8):
                try:
                    s1.fader(ch, -2)
                except Exception:
                    pass
            s1.play()
        except Exception as e:
            log(f"  play err {e}")
        eyes.start_watch("mix", 6.0)
        audio = capture(song / "_vision" / "ears", tag="after_fix_mix_15s", seconds=15.0)
        eyes.stop_watch()
        try:
            s1.stop()
        except Exception:
            pass
        try:
            run_action("save", focus=True)
        except Exception:
            pass

    final = eyes.shot("99_after_fix")
    final_v = analyze_shot(final)
    # count lanes with blue
    lanes_with_clips = []
    for row in range(1, 10):
        b = count_lane_blue(final, row)
        if b > 80:
            lanes_with_clips.append({"row": row, "blue": b})

    n_ok = sum(1 for r in results if r.get("ok"))
    summary = {
        "ok": n_ok >= 3,
        "finished_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "parts": results,
        "lanes_with_clips": lanes_with_clips,
        "mix": audio.to_dict(),
        "final_vision": final_v.to_dict(),
        "final_shot": str(final),
        "map": args.map,
        "note": "Exclusive Alt+click arm + per-lane blue verify",
    }
    out = song / "s1_jobs" / "fix_record_result.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log(f"SUMMARY ok_parts={n_ok}/5 lanes={lanes_with_clips} → {out}")
    print(
        json.dumps(
            {
                "ok": summary["ok"],
                "parts": [
                    (r.get("label"), r.get("ok"), r.get("note_ons"), r.get("clip_growth"), r.get("lane_blue_after"))
                    for r in results
                ],
                "lanes_with_clips": lanes_with_clips,
                "mix": audio.has_signal,
            },
            indent=2,
        )
    )
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
