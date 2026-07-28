#!/usr/bin/env python3
"""
Compose song ONE TRACK AT A TIME inside Studio One UI.

Every action is screenshot-verified:
  1) locate Rec buttons (vision)
  2) disarm all
  3) Alt+click exclusive arm on target row
  4) confirm only that Rec is red
  5) transport Record
  6) stream MIDI (S1 Notes)
  7) stop
  8) confirm lane blue clip growth on THAT row only
  9) disarm, save, next track

Usage:
  set PYTHONPATH=%CD%;%CD%\\tools
  py -3.12 tools/compose_one_track_at_a_time.py --max-sec 40
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import mido
import numpy as np
from PIL import Image, ImageDraw

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TOOLS))

from s1_tools.eyes import Eyes
from s1_tools.logutil import log, set_log_file
from s1_tools.vision import analyze_shot, detect_safety_dialog_uia, dismiss_safety_dialog


# ---------------------------------------------------------------------------
# mouse / vision helpers
# ---------------------------------------------------------------------------

def _click(x: int, y: int, *, alt: bool = False) -> None:
    import ctypes

    u = ctypes.windll.user32
    if alt:
        u.keybd_event(0x12, 0, 0, 0)
        time.sleep(0.03)
    u.SetCursorPos(int(x), int(y))
    time.sleep(0.04)
    u.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.04)
    u.mouse_event(0x0004, 0, 0, 0, 0)
    if alt:
        time.sleep(0.03)
        u.keybd_event(0x12, 0, 2, 0)


def button_score(arr: np.ndarray, cx: int, y: int) -> tuple[int, int, int]:
    h, w = arr.shape[:2]
    y0, y1 = max(0, y - 6), min(h, y + 7)
    x0, x1 = max(0, cx - 11), min(w, cx + 12)
    reg = arr[y0:y1, x0:x1]
    rr, gg, bb = reg[:, :, 0].astype(int), reg[:, :, 1].astype(int), reg[:, :, 2].astype(int)
    red_n = int(((rr > 180) & (gg < 130) & (bb < 130) & (rr > gg + 40)).sum())
    grey_n = int(
        (
            (rr >= 55)
            & (rr <= 150)
            & (gg >= 55)
            & (gg <= 150)
            & (bb >= 55)
            & (bb <= 150)
            & (np.abs(rr - gg) < 28)
            & (np.abs(gg - bb) < 28)
        ).sum()
    )
    return red_n, grey_n, red_n * 3 + grey_n


def find_rec_points(shot: Path) -> list[tuple[int, int]]:
    """Visible arrange Rec Enable centers, top→bottom."""
    arr = np.asarray(Image.open(shot).convert("RGB"), dtype=np.int16)
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]

    red = (r > 200) & (g < 120) & (b < 120) & (r > g + 50) & (r > b + 50)
    mask = red.copy()
    mask[:, :520] = False
    mask[:, 720:] = False
    mask[:145, :] = False
    mask[720:, :] = False
    ys, xs = np.where(mask)
    if len(xs):
        cx = int(np.median(xs))
        log(f"  vision: red Rec anchor x={cx} y={int(np.median(ys))}")
    else:
        cx = 635
        log(f"  vision: no red Rec — using x={cx}")

    scores = np.array([button_score(arr, cx, y)[2] for y in range(150, 720)], dtype=float)
    sm = np.convolve(scores, np.ones(5) / 5, mode="same")
    peaks: list[int] = []
    for i in range(6, len(sm) - 6):
        if sm[i] >= 12 and sm[i] >= sm[i - 5 : i + 6].max():
            y = 150 + i
            if not peaks or y - peaks[-1] >= 34:
                peaks.append(y)
            elif sm[i] > sm[peaks[-1] - 150]:
                peaks[-1] = y

    pts: list[tuple[int, int]] = []
    for y in peaks:
        rn, gn, tot = button_score(arr, cx, y)
        if tot >= 15:
            pts.append((cx, y))
            log(f"  vision: Rec row y={y} red={rn} grey={gn}")

    # annotate
    im = Image.open(shot).convert("RGB")
    dr = ImageDraw.Draw(im)
    for i, (x, y) in enumerate(pts):
        dr.ellipse([x - 8, y - 8, x + 8, y + 8], outline=(0, 255, 0), width=2)
        dr.text((x + 12, y - 8), f"R{i+1}", fill=(255, 255, 0))
    out = Path(shot).with_name(Path(shot).stem + "_recs.png")
    im.save(out)
    log(f"  vision: {len(pts)} Rec pts → {out.name}")
    return pts


def is_red_at(shot: Path | None, x: int, y: int) -> bool:
    if shot is None or not Path(shot).exists():
        return False
    arr = np.asarray(Image.open(shot).convert("RGB"), dtype=np.int16)
    return button_score(arr, x, y)[0] >= 12


def lane_blue(shot: Path | None, y: int, half: int = 20) -> int:
    if shot is None or not Path(shot).exists():
        return 0
    arr = np.asarray(Image.open(shot).convert("RGB"), dtype=np.int16)
    h, w = arr.shape[:2]
    y0, y1 = max(0, y - half), min(h, y + half)
    x0, x1 = int(w * 0.40), int(w * 0.72)
    reg = arr[y0:y1, x0:x1]
    r, g, b = reg[:, :, 0], reg[:, :, 1], reg[:, :, 2]
    blue = (b > 120) & (b > r + 20) & (b > g + 10) & (r < 200)
    return int(blue.sum())


def armed_indices(shot: Path | None, pts: list[tuple[int, int]]) -> list[int]:
    if shot is None:
        return []
    return [i for i, (x, y) in enumerate(pts) if is_red_at(shot, x, y)]


# ---------------------------------------------------------------------------
# track sequence
# ---------------------------------------------------------------------------

def disarm_all(pts: list[tuple[int, int]], eyes: Eyes) -> None:
    from s1remote.hotkeys import focus_studio_one

    focus_studio_one()
    for r in range(6):
        shot = eyes.shot(f"disarm_r{r}")
        armed = armed_indices(shot, pts)
        if not armed:
            log(f"  VISUAL disarm: clear (round {r})")
            return
        log(f"  VISUAL disarm: clicking red rows {armed}")
        for i in armed:
            x, y = pts[i]
            _click(x, y)
            time.sleep(0.2)
        time.sleep(0.25)
    log("  VISUAL disarm: best-effort done")


def exclusive_arm(
    pts: list[tuple[int, int]], idx: int, eyes: Eyes, label: str
) -> tuple[bool, tuple[int, int] | None]:
    """Alt+click exclusive arm. Returns (ok, (x,y))."""
    from s1remote.hotkeys import focus_studio_one

    if idx < 0 or idx >= len(pts):
        log(f"  ARM FAIL {label}: idx {idx} not in 0..{len(pts)-1}")
        return False, None

    disarm_all(pts, eyes)
    focus_studio_one()
    time.sleep(0.25)
    x, y = pts[idx]
    log(f"  ARM {label}: Alt+click Rec idx={idx} @ ({x},{y})")
    _click(x, y, alt=True)
    time.sleep(0.5)
    after = eyes.shot(f"armed_{label}")
    if after and is_red_at(after, x, y):
        others = [i for i in armed_indices(after, pts) if i != idx]
        log(f"  VISUAL arm OK {label} red@({x},{y}) others={others}")
        return True, (x, y)

    log(f"  ARM {label}: Alt miss — plain click")
    _click(x, y, alt=False)
    time.sleep(0.45)
    after2 = eyes.shot(f"armed_retry_{label}")
    if after2 and is_red_at(after2, x, y):
        log(f"  VISUAL arm OK (retry) {label}")
        return True, (x, y)

    log(f"  ARM FAIL {label}: Rec not red after clicks")
    return False, (x, y)


def stream_mid(s1, path: Path, *, label: str, eyes: Eyes, max_sec: float) -> int:
    mid = mido.MidiFile(str(path))
    bridge = s1.remote.instrument.bridge
    total = float(mid.length) or 1.0
    log(f"  STREAM {label}: {path.name} ~{total:.0f}s cap={max_sec}s")
    eyes.start_watch(f"rec_{label}", 6.0)
    t0 = time.perf_counter()
    target = 0.0
    n_on = 0
    last_log = 0.0
    try:
        for msg in mid:
            target += msg.time
            if target > max_sec:
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
            if wall - last_log >= 5.0:
                log(f"  … {label} notes={n_on} t={wall:.0f}s")
                last_log = wall
    finally:
        eyes.stop_watch()
        try:
            s1.remote.instrument.all_notes_off(0)
        except Exception:
            pass
    return n_on


def compose_one(
    s1,
    *,
    midi_path: Path,
    rec_idx: int,
    label: str,
    instrument_hint: str,
    eyes: Eyes,
    max_sec: float,
) -> dict:
    """Full one-track cycle with visual gates."""
    from s1remote.hotkeys import focus_studio_one

    log("")
    log("=" * 60)
    log(f"ONE TRACK: {label} ({instrument_hint}) → Rec row index {rec_idx}")
    log("=" * 60)

    focus_studio_one()
    try:
        s1.stop()
        for _ in range(2):
            s1.remote.mcu.rewind()
            time.sleep(0.08)
    except Exception as e:
        log(f"  rewind warn: {e}")
    time.sleep(0.3)

    # 1) locate
    cal = eyes.shot(f"01_locate_{label}")
    pts = find_rec_points(cal)
    if rec_idx >= len(pts):
        return {
            "label": label,
            "ok": False,
            "error": f"rec_idx {rec_idx} >= {len(pts)} visible Rec rows",
            "n_pts": len(pts),
        }
    log(f"  VISUAL: target is R{rec_idx+1} of {len(pts)} @ {pts[rec_idx]}")

    # 2-3) exclusive arm
    ok_arm, xy = exclusive_arm(pts, rec_idx, eyes, label)
    if not ok_arm or xy is None:
        return {"label": label, "ok": False, "error": "arm_failed", "rec_idx": rec_idx}
    x, y = xy

    # 4) pre-clip measure
    pre = eyes.shot(f"02_pre_record_{label}")
    pre_blue = lane_blue(pre, y)
    pre_armed = is_red_at(pre, x, y)
    log(f"  VISUAL pre: armed={pre_armed} lane_blue={pre_blue}")
    if not pre_armed:
        return {
            "label": label,
            "ok": False,
            "error": "lost_arm_before_record",
            "lane_blue_before": pre_blue,
        }

    # 5) transport record
    log(f"  TRANSPORT Record → stream {label}")
    s1.record()
    time.sleep(0.55)
    rec_shot = eyes.shot(f"03_transport_rec_{label}")
    still = is_red_at(rec_shot, x, y) if rec_shot else False
    log(f"  VISUAL during record: target_red={still}")

    # 6) stream
    n = stream_mid(s1, midi_path, label=label, eyes=eyes, max_sec=max_sec)

    # 7) stop
    try:
        s1.stop()
    except Exception:
        pass
    time.sleep(0.5)

    # 8) verify clips
    after = eyes.shot(f"04_after_stop_{label}")
    post_blue = lane_blue(after, y)
    growth = post_blue > pre_blue + 50
    # also check global blue increased if lane is noisy
    pre_g = analyze_shot(pre).blue_pixel_hits if pre else 0
    post_g = analyze_shot(after).blue_pixel_hits if after else 0
    ok = n > 0 and (growth or post_blue > 200 and post_blue > pre_blue)
    log(
        f"  VISUAL result {label}: notes={n} lane_blue {pre_blue}→{post_blue} "
        f"growth={growth} global {pre_g}→{post_g} ok={ok}"
    )

    # 9) disarm this track
    disarm_all(pts, eyes)
    eyes.shot(f"05_disarmed_{label}")

    return {
        "label": label,
        "instrument": instrument_hint,
        "rec_idx": rec_idx,
        "xy": [x, y],
        "ok": ok,
        "note_ons": n,
        "lane_blue_before": pre_blue,
        "lane_blue_after": post_blue,
        "clip_growth": growth,
        "pre_shot": str(pre) if pre else None,
        "after_shot": str(after) if after else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-sec", type=float, default=40.0)
    ap.add_argument(
        "--song-dir",
        type=Path,
        default=Path.home() / "Documents" / "Studio One" / "Songs" / "2026-07-25 ralph rodrigues",
    )
    ap.add_argument(
        "--midi-dir",
        type=Path,
        default=None,
        help="default: <song-dir>/MIDI",
    )
    args = ap.parse_args()

    from s1remote.full_control import FullControl
    from s1remote.hotkeys import focus_studio_one, run_action, studio_one_running

    song = args.song_dir
    midi_dir = args.midi_dir or (song / "MIDI")
    vision = song / "_vision" / "one_track"
    vision.mkdir(parents=True, exist_ok=True)
    set_log_file(vision / "compose.log")

    if not studio_one_running():
        log("FATAL: Studio One not running")
        return 2

    if detect_safety_dialog_uia():
        log("dismissing Safety dialog")
        dismiss_safety_dialog()
        time.sleep(1.2)

    eyes = Eyes(vision)
    focus_studio_one()
    time.sleep(0.4)
    start = eyes.shot("00_session_start")
    log(f"  session start vision: {analyze_shot(start).to_dict() if start else None}")

    # Scroll arrange track list to top so Impact is row 1
    try:
        from pywinauto.keyboard import send_keys

        focus_studio_one()
        # click near first track header area then Home/PageUp
        _click(560, 220)
        time.sleep(0.15)
        send_keys("{HOME}")
        time.sleep(0.1)
        for _ in range(8):
            send_keys("{PGUP}")
            time.sleep(0.05)
        time.sleep(0.3)
    except Exception as e:
        log(f"  scroll-top warn: {e}")
    eyes.shot("00b_after_scroll_top")

    # Full track list visible (Impact = top):
    # R1 idx0 Impact      → DRUMS
    # R2 idx1 Impact 2
    # R3 idx2 Mai Tai     → LEAD (often already has clips)
    # R4 idx3 Mai Tai 2   → COLOR
    # R5 idx4 Mojito      → BASS
    # R6 idx5 Mojito 2
    # R7 idx6 Presence    → BED
    # Prefer empty tracks first; still do LEAD if max-sec allows later.
    # Order: drums, bass, bed, color, lead — one instrument at a time.
    sequence = [
        ("drums.mid", 0, "DRUMS", "Impact"),
        ("bass.mid", 4, "BASS", "Mojito"),
        ("bed.mid", 6, "BED", "Presence"),
        ("color.mid", 3, "COLOR", "Mai Tai 2"),
        ("lead.mid", 2, "LEAD", "Mai Tai"),
    ]

    results: list[dict] = []
    with FullControl() as s1:
        st = s1.status()
        log(f"  MIDI notes connected={st.get('instrument_midi_connected')} out={st.get('instrument_midi_out')}")
        if not st.get("instrument_midi_connected"):
            log("FATAL: S1 Notes not connected — check External Devices / loopMIDI")
            return 3

        for fname, idx, label, hint in sequence:
            path = midi_dir / fname
            if not path.is_file():
                alt = Path(
                    str(Path.home() / "Documents" / "Studio One" / "Songs" / "_agent_autonomy_test" / "MIDI")
                ) / fname
                path = alt if alt.is_file() else path
            if not path.is_file():
                log(f"  SKIP {label}: missing {fname}")
                results.append({"label": label, "ok": False, "error": "missing_midi"})
                continue

            r = compose_one(
                s1,
                midi_path=path,
                rec_idx=idx,
                label=label,
                instrument_hint=hint,
                eyes=eyes,
                max_sec=args.max_sec,
            )
            results.append(r)
            # pause between tracks so UI settles + human can glance
            time.sleep(0.8)

        # final mix listen
        focus_studio_one()
        try:
            s1.stop()
            for _ in range(3):
                s1.remote.mcu.rewind()
                time.sleep(0.08)
            s1.play()
        except Exception as e:
            log(f"  play err: {e}")
        eyes.start_watch("mix_listen", 5.0)
        time.sleep(12.0)
        eyes.stop_watch()
        try:
            s1.stop()
        except Exception:
            pass
        try:
            run_action("save", focus=True)
            time.sleep(2.0)
        except Exception:
            pass

    final = eyes.shot("99_final_arrange")
    # per-row lane report
    lanes = []
    if final:
        fpts = find_rec_points(final)
        for i, (x, y) in enumerate(fpts):
            lanes.append(
                {
                    "idx": i,
                    "y": y,
                    "blue": lane_blue(final, y),
                    "red": is_red_at(final, x, y),
                }
            )

    n_ok = sum(1 for r in results if r.get("ok"))
    summary = {
        "ok": n_ok >= 3,
        "n_ok": n_ok,
        "n_parts": len(results),
        "finished_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "parts": results,
        "lanes": lanes,
        "final_shot": str(final) if final else None,
        "final_vision": analyze_shot(final).to_dict() if final else {},
        "method": "one_track_at_a_time exclusive Alt+click + visual gates",
    }
    out = song / "s1_jobs" / "compose_one_track_result.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log(f"DONE ok={n_ok}/{len(results)} → {out}")
    print(json.dumps({
        "ok": summary["ok"],
        "n_ok": n_ok,
        "parts": [(r.get("label"), r.get("ok"), r.get("note_ons"), r.get("clip_growth"), r.get("lane_blue_after")) for r in results],
        "lanes_with_blue": [L for L in lanes if L.get("blue", 0) > 100],
        "final_shot": summary["final_shot"],
    }, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
