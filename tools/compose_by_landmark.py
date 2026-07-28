#!/usr/bin/env python3
"""
One-track-at-a-time compose using VISUAL landmarks.

Landmark: Mai Tai row = arrange lane with the most blue MIDI clip pixels.
Then offset rows by measured track pitch to hit Impact / Mojito / Presence / Mai Tai 2.

Every step screenshots and logs.
"""
from __future__ import annotations

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


def _click(x: int, y: int, *, alt: bool = False) -> None:
    import ctypes

    u = ctypes.windll.user32
    if alt:
        u.keybd_event(0x12, 0, 0, 0)
        time.sleep(0.03)
    u.SetCursorPos(int(x), int(y))
    time.sleep(0.05)
    u.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.04)
    u.mouse_event(0x0004, 0, 0, 0, 0)
    if alt:
        time.sleep(0.03)
        u.keybd_event(0x12, 0, 2, 0)


def analyze_layout(shot: Path) -> dict:
    """Find Rec X, Mai Tai Y (blue clips), track pitch, and named targets."""
    arr = np.asarray(Image.open(shot).convert("RGB"), dtype=np.int16)
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    h, w = arr.shape[:2]

    # Rec X from red or default
    red = (r > 200) & (g < 120) & (b < 120) & (r > g + 50)
    m = red.copy()
    m[:, :550] = False
    m[:, 700:] = False
    m[:150, :] = False
    m[700:, :] = False
    ys, xs = np.where(m)
    rec_x = int(np.median(xs)) if len(xs) else 635

    # Blue clips in arrange grid
    x0, x1 = int(w * 0.42), int(w * 0.70)
    blue = (b > 130) & (b > r + 25) & (b > g + 15) & (r < 200)
    row_sum = blue[:, x0:x1].sum(axis=1).astype(float)
    # smooth
    sm = np.convolve(row_sum, np.ones(11) / 11, mode="same")
    # find strongest contiguous band (Mai Tai notes)
    thr = max(30.0, float(sm.max()) * 0.25)
    best = (0, 0, 0)  # start, end, score
    i = 150
    while i < 700:
        if sm[i] >= thr:
            j = i
            while j < 700 and sm[j] >= thr * 0.5:
                j += 1
            score = float(sm[i:j].sum())
            if score > best[2]:
                best = (i, j, score)
            i = j
        else:
            i += 1
    mai_y0, mai_y1, _ = best
    mai_cy = (mai_y0 + mai_y1) // 2 if mai_y1 > mai_y0 else 400
    mai_h = max(40, mai_y1 - mai_y0)

    # Rec Y for Mai Tai: search in blue band upper for red/grey button
    def btn(y):
        reg = arr[max(0, y - 6) : y + 7, rec_x - 12 : rec_x + 13]
        rr, gg, bb = reg[:, :, 0].astype(int), reg[:, :, 1].astype(int), reg[:, :, 2].astype(int)
        rn = int(((rr > 180) & (gg < 130) & (bb < 130) & (rr > gg + 40)).sum())
        gn = int(
            (
                (rr >= 70)
                & (rr <= 145)
                & (gg >= 70)
                & (gg <= 145)
                & (bb >= 70)
                & (bb <= 145)
                & (np.abs(rr - gg) < 28)
            ).sum()
        )
        return rn * 4 + gn, rn

    best_y, best_s = mai_y0, -1
    for y in range(max(150, mai_y0 - 15), min(700, mai_y1 + 5)):
        s, _ = btn(y)
        if s > best_s:
            best_s, best_y = s, y
    mai_rec_y = best_y

    # Pitch: distance between successive grey-rec peaks near rec_x
    scores = np.array([btn(y)[0] for y in range(160, 720)], float)
    smp = np.convolve(scores, np.ones(5) / 5, mode="same")
    peaks = []
    for i in range(8, len(smp) - 8):
        if smp[i] >= 30 and smp[i] >= smp[i - 6 : i + 7].max():
            y = 160 + i
            if not peaks or y - peaks[-1] >= 38:
                peaks.append(y)
    # pitch from peaks near Mai Tai
    pitch = float(mai_h)  # fallback band height
    if len(peaks) >= 2:
        diffs = [peaks[i + 1] - peaks[i] for i in range(len(peaks) - 1)]
        diffs = [d for d in diffs if 35 <= d <= 100]
        if diffs:
            pitch = float(sorted(diffs)[len(diffs) // 2])

    # Map relative to Mai Tai (track 3):
    # Impact = Mai Tai - 2*pitch
    # Impact2 = Mai Tai - 1*pitch
    # Mai Tai = 0
    # Mai Tai2 = +1
    # Mojito = +2
    # Mojito2 = +3
    # Presence = +4
    offsets = {
        "Impact": -2,
        "Impact2": -1,
        "Mai Tai": 0,
        "Mai Tai 2": 1,
        "Mojito": 2,
        "Mojito 2": 3,
        "Presence": 4,
        "Presence 2": 5,
        "SampleOne": 6,
    }
    targets = {}
    for name, off in offsets.items():
        y = int(mai_rec_y + off * pitch)
        if 160 <= y <= 720:
            targets[name] = (rec_x, y)

    # annotate
    im = Image.open(shot).convert("RGB")
    dr = ImageDraw.Draw(im)
    dr.rectangle([x0, mai_y0, x1, mai_y1], outline=(0, 200, 255), width=2)
    for name, (x, y) in targets.items():
        dr.ellipse([x - 8, y - 8, x + 8, y + 8], outline=(0, 255, 0), width=2)
        dr.text((x + 12, y - 8), name[:6], fill=(255, 255, 0))
    out = shot.with_name(shot.stem + "_landmark.png")
    im.save(out)

    layout = {
        "rec_x": rec_x,
        "mai_rec_y": mai_rec_y,
        "mai_band": [mai_y0, mai_y1],
        "pitch": pitch,
        "targets": {k: list(v) for k, v in targets.items()},
        "peaks": peaks,
        "annotate": str(out),
    }
    log(f"  LANDMARK mai_rec_y={mai_rec_y} pitch={pitch:.1f} targets={list(targets)}")
    return layout


def is_red(shot: Path | None, x: int, y: int) -> bool:
    if not shot or not Path(shot).exists():
        return False
    arr = np.asarray(Image.open(shot).convert("RGB"), dtype=np.int16)
    reg = arr[max(0, y - 8) : y + 9, max(0, x - 12) : x + 13]
    rr, gg, bb = reg[:, :, 0], reg[:, :, 1], reg[:, :, 2]
    return int(((rr > 180) & (gg < 130) & (bb < 130) & (rr > gg + 40)).sum()) >= 12


def lane_blue(shot: Path | None, y: int, half: int = 22) -> int:
    if not shot or not Path(shot).exists():
        return 0
    arr = np.asarray(Image.open(shot).convert("RGB"), dtype=np.int16)
    h, w = arr.shape[:2]
    y0, y1 = max(0, y - half), min(h, y + half)
    x0, x1 = int(w * 0.42), int(w * 0.70)
    reg = arr[y0:y1, x0:x1]
    r, g, b = reg[:, :, 0], reg[:, :, 1], reg[:, :, 2]
    return int(((b > 120) & (b > r + 20) & (b > g + 10) & (r < 200)).sum())


def find_all_red_recs(shot: Path, rec_x: int) -> list[int]:
    arr = np.asarray(Image.open(shot).convert("RGB"), dtype=np.int16)
    reds = []
    for y in range(160, 720, 2):
        if is_red(shot, rec_x, y):
            if not reds or y - reds[-1] > 25:
                reds.append(y)
    return reds


def disarm(rec_x: int, eyes: Eyes) -> None:
    from s1remote.hotkeys import focus_studio_one

    focus_studio_one()
    for r in range(5):
        shot = eyes.shot(f"disarm_{r}")
        reds = find_all_red_recs(shot, rec_x) if shot else []
        if not reds:
            log(f"  VISUAL disarm clear r{r}")
            return
        log(f"  VISUAL disarm reds y={reds}")
        for y in reds:
            _click(rec_x, y)
            time.sleep(0.2)
        time.sleep(0.25)


def exclusive_arm(x: int, y: int, rec_x: int, eyes: Eyes, label: str) -> bool:
    from s1remote.hotkeys import focus_studio_one

    disarm(rec_x, eyes)
    focus_studio_one()
    time.sleep(0.2)
    # search small Y window for best button
    best = (x, y)
    shot0 = eyes.shot(f"arm_search_{label}")
    if shot0:
        arr = np.asarray(Image.open(shot0).convert("RGB"), dtype=np.int16)
        best_s = -1
        for yy in range(y - 18, y + 19, 2):
            reg = arr[max(0, yy - 5) : yy + 6, x - 10 : x + 11]
            rr, gg, bb = reg[:, :, 0].astype(int), reg[:, :, 1].astype(int), reg[:, :, 2].astype(int)
            gn = int(
                (
                    (rr >= 70)
                    & (rr <= 145)
                    & (gg >= 70)
                    & (gg <= 145)
                    & (bb >= 70)
                    & (bb <= 145)
                    & (np.abs(rr - gg) < 28)
                ).sum()
            )
            rn = int(((rr > 180) & (gg < 130) & (bb < 130) & (rr > gg + 40)).sum())
            s = rn * 3 + gn
            if s > best_s:
                best_s = s
                best = (x, yy)
    log(f"  ARM {label}: Alt+click @ {best}")
    _click(best[0], best[1], alt=True)
    time.sleep(0.5)
    after = eyes.shot(f"armed_{label}")
    if after and is_red(after, best[0], best[1]):
        reds = find_all_red_recs(after, rec_x)
        log(f"  VISUAL arm OK {label} reds_y={reds}")
        return True
    log(f"  ARM {label} plain click retry")
    _click(best[0], best[1], alt=False)
    time.sleep(0.45)
    after2 = eyes.shot(f"armed_retry_{label}")
    ok = bool(after2 and is_red(after2, best[0], best[1]))
    log(f"  VISUAL arm retry {label}={ok}")
    return ok


def stream(s1, path: Path, label: str, eyes: Eyes, max_sec: float) -> int:
    mid = mido.MidiFile(str(path))
    bridge = s1.remote.instrument.bridge
    log(f"  STREAM {label} {path.name} cap={max_sec}s")
    eyes.start_watch(label, 7.0)
    t0 = time.perf_counter()
    target = 0.0
    n = 0
    try:
        for msg in mid:
            target += msg.time
            if target > max_sec:
                break
            d = target - (time.perf_counter() - t0)
            if d > 0.0005:
                time.sleep(d)
            if msg.is_meta:
                continue
            try:
                out = msg.copy(channel=0)
            except Exception:
                out = msg
            if out.type == "note_on" and getattr(out, "velocity", 0) > 0:
                n += 1
            if out.type in ("note_on", "note_off", "control_change"):
                bridge.send(out)
    finally:
        eyes.stop_watch()
        try:
            s1.remote.instrument.all_notes_off(0)
        except Exception:
            pass
    return n


def one_track(s1, eyes, layout, midi: Path, instrument: str, label: str, max_sec: float) -> dict:
    from s1remote.hotkeys import focus_studio_one

    log("")
    log("#" * 60)
    log(f"ONE TRACK: {label} → {instrument}")
    log("#" * 60)
    focus_studio_one()
    try:
        s1.stop()
        s1.remote.mcu.rewind()
    except Exception:
        pass
    time.sleep(0.3)

    # refresh landmark each track
    cal = eyes.shot(f"01_{label}_layout")
    layout = analyze_layout(cal)
    rec_x = layout["rec_x"]
    if instrument not in layout["targets"]:
        return {"label": label, "ok": False, "error": f"no target for {instrument}", "layout": layout}

    x, y = layout["targets"][instrument]
    log(f"  target {instrument} @ ({x},{y}) pitch={layout['pitch']:.1f}")

    if not exclusive_arm(x, y, rec_x, eyes, label):
        return {"label": label, "ok": False, "error": "arm_failed", "xy": [x, y], "layout": layout}

    pre = eyes.shot(f"02_{label}_pre")
    pre_b = lane_blue(pre, y)
    log(f"  VISUAL pre lane_blue={pre_b} armed={is_red(pre, x, y)}")

    s1.record()
    time.sleep(0.5)
    recs = eyes.shot(f"03_{label}_recording")
    log(f"  VISUAL recording red={is_red(recs, x, y)}")

    n = stream(s1, midi, label, eyes, max_sec)
    try:
        s1.stop()
    except Exception:
        pass
    time.sleep(0.5)

    after = eyes.shot(f"04_{label}_after")
    post_b = lane_blue(after, y)
    # growth relative to THIS lane; also check if any NEW blue appeared near target
    growth = post_b > pre_b + 60
    ok = n > 0 and growth
    # secondary: if pre was empty-ish and post has content
    if n > 0 and pre_b < 200 and post_b > 300:
        ok = True
        growth = True
    log(f"  VISUAL RESULT {label}: notes={n} blue {pre_b}→{post_b} growth={growth} ok={ok}")

    disarm(rec_x, eyes)
    eyes.shot(f"05_{label}_done")
    return {
        "label": label,
        "instrument": instrument,
        "ok": ok,
        "note_ons": n,
        "lane_blue_before": pre_b,
        "lane_blue_after": post_b,
        "clip_growth": growth,
        "xy": [x, y],
        "after_shot": str(after) if after else None,
    }


def main() -> int:
    from s1remote.full_control import FullControl
    from s1remote.hotkeys import focus_studio_one, run_action, studio_one_running

    song = Path.home() / "Documents" / "Studio One" / "Songs" / "2026-07-25 ralph rodrigues"
    midi_dir = song / "MIDI"
    vision = song / "_vision" / "landmark"
    vision.mkdir(parents=True, exist_ok=True)
    set_log_file(vision / "compose.log")

    if not studio_one_running():
        log("FATAL: S1 not running")
        return 2
    if detect_safety_dialog_uia():
        dismiss_safety_dialog()
        time.sleep(1)

    eyes = Eyes(vision)
    focus_studio_one()
    time.sleep(0.3)
    start = eyes.shot("00_start")
    layout = analyze_layout(start)
    log(f"  start vision {analyze_shot(start).to_dict()}")

    # Empty tracks first (Mai Tai already has lead)
    sequence = [
        ("drums.mid", "Impact", "DRUMS"),
        ("bass.mid", "Mojito", "BASS"),
        ("bed.mid", "Presence", "BED"),
        ("color.mid", "Mai Tai 2", "COLOR"),
    ]
    max_sec = 40.0
    results = []

    with FullControl() as s1:
        st = s1.status()
        log(f"  notes={st.get('instrument_midi_connected')} out={st.get('instrument_midi_out')}")
        if not st.get("instrument_midi_connected"):
            log("FATAL: S1 Notes disconnected")
            return 3

        for fname, inst, label in sequence:
            path = midi_dir / fname
            if not path.is_file():
                results.append({"label": label, "ok": False, "error": "missing_midi"})
                continue
            r = one_track(s1, eyes, layout, path, inst, label, max_sec)
            results.append(r)
            time.sleep(0.6)

        try:
            run_action("save", focus=True)
            time.sleep(1.5)
        except Exception:
            pass

    final = eyes.shot("99_final")
    if final:
        fl = analyze_layout(final)
    else:
        fl = {}
    n_ok = sum(1 for r in results if r.get("ok"))
    summary = {
        "ok": n_ok >= 2,
        "n_ok": n_ok,
        "parts": results,
        "final_layout": fl,
        "final_shot": str(final) if final else None,
        "final_vision": analyze_shot(final).to_dict() if final else {},
        "finished_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    out = song / "s1_jobs" / "compose_landmark_result.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log(f"DONE {n_ok}/{len(results)} → {out}")
    print(json.dumps({
        "ok": summary["ok"],
        "n_ok": n_ok,
        "parts": [(r.get("label"), r.get("instrument"), r.get("ok"), r.get("note_ons"), r.get("clip_growth"), r.get("lane_blue_after")) for r in results],
        "final_shot": summary["final_shot"],
    }, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
