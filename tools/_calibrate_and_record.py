#!/usr/bin/env python3
"""Calibrate Rec buttons on current arrange, exclusive-arm, short-record each empty track."""
from __future__ import annotations

import json
import sys
import time
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
    """Return (red_n, grey_n, total)."""
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
    """Locate Rec Enable centers for visible tracks (top→bottom)."""
    arr = np.asarray(Image.open(shot).convert("RGB"), dtype=np.int16)
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    h, w = arr.shape[:2]

    # Anchor: red Rec in arrange header (exclude left inspector)
    red = (r > 200) & (g < 120) & (b < 120) & (r > g + 50) & (r > b + 50)
    mask = red.copy()
    mask[:, :520] = False
    mask[:, 720:] = False
    mask[:145, :] = False
    mask[720:, :] = False
    ys, xs = np.where(mask)
    if len(xs):
        cx = int(np.median(xs))
        cy = int(np.median(ys))
        log(f"  anchor red Rec @ ({cx},{cy})")
    else:
        cx, cy = 635, 220
        log(f"  no red Rec — fallback cx={cx}")

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

    # Prefer peaks that look like real buttons
    pts: list[tuple[int, int]] = []
    for y in peaks:
        rn, gn, tot = button_score(arr, cx, y)
        if tot >= 15:
            pts.append((cx, y))
            log(f"  rec row y={y} red={rn} grey={gn}")

    # Debug overlay
    im = Image.open(shot).convert("RGB")
    dr = ImageDraw.Draw(im)
    for i, (x, y) in enumerate(pts):
        dr.ellipse([x - 8, y - 8, x + 8, y + 8], outline=(0, 255, 0), width=2)
        dr.text((x + 12, y - 8), f"R{i+1}", fill=(255, 255, 0))
    out = Path(shot).parent / "debug_rec_pts.png"
    im.save(out)
    log(f"  wrote {out} n={len(pts)}")
    return pts


def lane_blue(shot: Path, y: int, half: int = 18) -> int:
    arr = np.asarray(Image.open(shot).convert("RGB"), dtype=np.int16)
    h, w = arr.shape[:2]
    y0, y1 = max(0, y - half), min(h, y + half)
    x0, x1 = int(w * 0.40), int(w * 0.72)
    reg = arr[y0:y1, x0:x1]
    r, g, b = reg[:, :, 0], reg[:, :, 1], reg[:, :, 2]
    blue = (b > 120) & (b > r + 20) & (b > g + 10) & (r < 200)
    return int(blue.sum())


def is_red(shot: Path, x: int, y: int) -> bool:
    arr = np.asarray(Image.open(shot).convert("RGB"), dtype=np.int16)
    rn, _, _ = button_score(arr, x, y)
    return rn >= 12


def disarm_all(pts: list[tuple[int, int]], eyes: Eyes) -> None:
    for round_i in range(5):
        shot = eyes.shot(f"disarm_{round_i}")
        if shot is None:
            return
        armed = [(x, y) for x, y in pts if is_red(shot, x, y)]
        if not armed:
            log(f"  disarm clear round {round_i}")
            return
        log(f"  disarm click {len(armed)} reds")
        for x, y in armed:
            _click(x, y)
            time.sleep(0.18)
        time.sleep(0.2)


def exclusive_arm(pts: list[tuple[int, int]], idx: int, eyes: Eyes, label: str) -> bool:
    """idx 0-based into pts. Alt+click exclusive."""
    from s1remote.hotkeys import focus_studio_one

    if idx < 0 or idx >= len(pts):
        log(f"  arm fail {label}: idx {idx} out of range {len(pts)}")
        return False
    disarm_all(pts, eyes)
    focus_studio_one()
    time.sleep(0.2)
    x, y = pts[idx]
    log(f"  Alt+click {label} idx={idx} @ ({x},{y})")
    _click(x, y, alt=True)
    time.sleep(0.45)
    after = eyes.shot(f"arm_{label}")
    if after and is_red(after, x, y):
        # Check exclusivity
        others = [i for i, (xx, yy) in enumerate(pts) if i != idx and is_red(after, xx, yy)]
        log(f"  armed OK {label}; other reds={others}")
        return True
    # plain click retry
    log(f"  plain click retry {label}")
    _click(x, y, alt=False)
    time.sleep(0.4)
    after2 = eyes.shot(f"arm_retry_{label}")
    ok = bool(after2 and is_red(after2, x, y))
    log(f"  arm retry {label}={ok}")
    return ok


def stream_mid(s1, path: Path, *, label: str, eyes: Eyes, max_sec: float) -> int:
    mid = mido.MidiFile(str(path))
    bridge = s1.remote.instrument.bridge
    log(f"  STREAM {path.name} cap={max_sec}s")
    eyes.start_watch(label, 8.0)
    t0 = time.perf_counter()
    target = 0.0
    n_on = 0
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
    finally:
        eyes.stop_watch()
        try:
            s1.remote.instrument.all_notes_off(0)
        except Exception:
            pass
    return n_on


def main() -> int:
    from s1remote.full_control import FullControl
    from s1remote.hotkeys import focus_studio_one, run_action, studio_one_running

    song = Path(r"C:\Users\Box One\Documents\Studio One\Songs\2026-07-25 ralph rodrigues")
    midi_dir = song / "MIDI"
    vision = song / "_vision" / "fix_v2"
    vision.mkdir(parents=True, exist_ok=True)
    set_log_file(vision / "fix_v2.log")

    if not studio_one_running():
        log("FATAL: S1 not running")
        return 2
    if detect_safety_dialog_uia():
        dismiss_safety_dialog()
        time.sleep(1)

    eyes = Eyes(vision)
    focus_studio_one()
    time.sleep(0.4)
    base = eyes.shot("00_base")
    pts = find_rec_points(base)
    if len(pts) < 4:
        log(f"FATAL: only {len(pts)} rec points")
        return 3

    # Visible layout from screenshot (scrolled so track 3 Mai Tai is first):
    # R1 = Mai Tai (t3) — already has lead
    # R2 = Mai Tai 2 (t4) — COLOR
    # R3 = Mojito (t5) — BASS
    # R4 = Mojito 2
    # R5 = Presence (t7) — BED
    # R6 = Presence 2
    # R7 = SampleOne — DRUMS fallback
    # R8 = SampleOne 2
    # R9 = Surge XT
    #
    # Map parts → rec-point index (0-based). Skip re-recording lead if already there.
    parts = [
        ("color.mid", 1, "COLOR"),   # Mai Tai 2
        ("bass.mid", 2, "BASS"),     # Mojito
        ("bed.mid", 4, "BED"),       # Presence
        ("drums.mid", 6, "DRUMS"),   # SampleOne
    ]

    results = []
    with FullControl() as s1:
        st = s1.status()
        log(f"  status notes={st.get('instrument_midi_connected')} out={st.get('instrument_midi_out')}")
        if not st.get("instrument_midi_connected"):
            log("FATAL: S1 Notes not connected")
            return 4

        for fname, idx, label in parts:
            path = midi_dir / fname
            if not path.is_file():
                results.append({"label": label, "ok": False, "error": "missing_midi"})
                continue

            log(f"######## {label} → rec idx {idx} ########")
            focus_studio_one()
            try:
                s1.stop()
                s1.remote.mcu.rewind()
            except Exception:
                pass
            time.sleep(0.25)

            # Re-calibrate each pass (scroll may not change but UI may)
            cal = eyes.shot(f"cal_{label}")
            pts = find_rec_points(cal)
            if idx >= len(pts):
                results.append({"label": label, "ok": False, "error": f"idx {idx} >= {len(pts)}"})
                continue

            if not exclusive_arm(pts, idx, eyes, label):
                results.append({"label": label, "ok": False, "error": "arm_failed", "idx": idx})
                continue

            x, y = pts[idx]
            pre = eyes.shot(f"pre_{label}")
            pre_b = lane_blue(pre, y) if pre else 0
            log(f"  pre lane_blue={pre_b}")

            s1.record()
            time.sleep(0.5)
            rec_shot = eyes.shot(f"rec_{label}")
            if rec_shot and not is_red(rec_shot, x, y):
                log("  WARN lost red during record")

            n = stream_mid(s1, path, label=label, eyes=eyes, max_sec=35.0)
            try:
                s1.stop()
            except Exception:
                pass
            time.sleep(0.45)
            after = eyes.shot(f"after_{label}")
            post_b = lane_blue(after, y) if after else 0
            growth = post_b > pre_b + 40
            ok = n > 0 and growth
            log(f"  RESULT {label}: notes={n} blue {pre_b}→{post_b} growth={growth} ok={ok}")
            results.append(
                {
                    "label": label,
                    "idx": idx,
                    "ok": ok,
                    "note_ons": n,
                    "lane_blue_before": pre_b,
                    "lane_blue_after": post_b,
                    "clip_growth": growth,
                    "xy": [x, y],
                }
            )
            disarm_all(pts, eyes)
            time.sleep(0.3)

        try:
            run_action("save", focus=True)
        except Exception:
            pass

    final = eyes.shot("99_final")
    # Lane blues for all pts
    lanes = []
    if final:
        fpts = find_rec_points(final)
        for i, (x, y) in enumerate(fpts):
            lanes.append({"idx": i, "y": y, "blue": lane_blue(final, y), "red": is_red(final, x, y)})

    summary = {
        "parts": results,
        "lanes": lanes,
        "ok": sum(1 for r in results if r.get("ok")) >= 2,
        "final_vision": analyze_shot(final).to_dict() if final else {},
    }
    out = song / "s1_jobs" / "fix_v2_result.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log(f"SUMMARY → {out}")
    print(json.dumps(summary, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
