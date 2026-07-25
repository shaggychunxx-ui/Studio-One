#!/usr/bin/env python3
"""
Real-time autonomous song build in Studio One.

Default production start:
  1) Open Songs/Template/Template.song
  2) Save As a new song
  3) Compose MIDI → stream with eyes/ears

Usage:
  set PYTHONPATH=%CD%;%CD%\\tools
  py -3.12 tools/live_make_song.py --from-template --name "MySong" --max-sec 12
  set S1_SONG_DIR=...
  py -3.12 tools/live_make_song.py --max-sec 12
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import mido

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TOOLS))

from s1_tools.paths import default_eyes_dir, resolve_song_dir, ensure_s1remote_on_path  # noqa: E402
from s1_tools.logutil import log, set_log_file  # noqa: E402
from s1_tools.eyes import Eyes, scan_rec_red  # noqa: E402
from s1_tools.ears import capture  # noqa: E402
from s1_tools.vision import analyze_shot, detect_safety_dialog_uia, dismiss_safety_dialog  # noqa: E402

BPM = 100
BARS = 8  # ~19s full; streams may be max_sec capped


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def compose_all(midi_dir: Path) -> dict:
    midi_dir.mkdir(parents=True, exist_ok=True)
    tpb = 480
    import random

    rng = random.Random(int(time.time()) % 100000)

    def write(name, builder):
        mid = mido.MidiFile(ticks_per_beat=tpb)
        tr = mido.MidiTrack()
        mid.tracks.append(tr)
        tr.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(BPM)))
        events = []
        for bar in range(BARS):
            for n in builder(bar):
                t0 = max(0, int((bar * 4 + n["t"]) * tpb))
                t1 = t0 + max(1, int(n["d"] * tpb))
                events.append((t0, 1, n["p"], n["v"]))
                events.append((t1, 0, n["p"], 0))
        events.sort(key=lambda e: (e[0], e[1]))
        abs_t = 0
        for t, on, p, v in events:
            dt = max(0, t - abs_t)
            abs_t = t
            tr.append(
                mido.Message(
                    "note_on" if on else "note_off",
                    note=p,
                    velocity=v if on else 0,
                    time=dt,
                )
            )
        path = midi_dir / name
        mid.save(str(path))
        length = float(mido.MidiFile(str(path)).length)
        log(f"  compose {name} ~{length:.1f}s")
        return str(path), length

    def drums(bar):
        out = []
        for beat, p, v in [(0, 36, 112), (1, 38, 90), (2, 36, 105), (3, 38, 88)]:
            out.append({"t": float(beat), "d": 0.14, "p": p, "v": v})
        for i in range(8):
            out.append({"t": i * 0.5, "d": 0.08, "p": 42, "v": 58 + (8 if i % 2 == 0 else 0)})
        if bar % 4 == 3:
            out.append({"t": 3.5, "d": 0.1, "p": 39, "v": 100})
        return out

    def bass(bar):
        roots = [36, 36, 41, 39, 36, 34, 36, 41]
        r = roots[bar % 8]
        return [
            {"t": 0.0, "d": 0.85, "p": r, "v": 100},
            {"t": 1.5, "d": 0.35, "p": r, "v": 82},
            {"t": 2.0, "d": 0.85, "p": r + (7 if bar % 2 == 0 else 5), "v": 90},
            {"t": 3.5, "d": 0.3, "p": r, "v": 78},
        ]

    def lead(bar):
        if bar < 1:
            return []
        scale = [60, 62, 64, 65, 67, 69, 71, 72]
        deg = [0, 2, 4, 2] if bar % 2 == 0 else [4, 3, 1, 0]
        out = []
        for i, d in enumerate(deg):
            if bar % 4 == 3 and i >= 2:
                continue
            pitch = scale[d] + (12 if bar >= 4 and i == 0 else 0)
            out.append({"t": i * 1.0 + rng.uniform(-0.01, 0.01), "d": 0.65, "p": pitch, "v": 90 if i == 0 else 70})
        return out

    def bed(bar):
        ch = [[48, 52, 55], [50, 53, 57], [48, 52, 55], [46, 50, 53]][bar % 4]
        return [{"t": 0.0, "d": 3.7, "p": p, "v": 52} for p in ch]

    out = {}
    for name, fn in [
        ("drums.mid", drums),
        ("bass.mid", bass),
        ("lead.mid", lead),
        ("bed.mid", bed),
    ]:
        path, length = write(name, fn)
        out[name] = {"path": path, "length": length}
    return out


def stream_mid(s1, path: Path, *, label: str, eyes: Eyes, max_sec=None) -> int:
    mid = mido.MidiFile(str(path))
    total = float(mid.length) or 1.0
    bridge = s1.remote.instrument.bridge
    log(f"  STREAM {path.name} ~{total:.1f}s port={bridge.out_name!r}")
    eyes.start_watch(label, 7.0)
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
            if out.type in ("note_on", "note_off", "control_change", "program_change"):
                bridge.send(out)
            wall = time.perf_counter() - t0
            if wall - last >= 2.0:
                log(f"  … {label} notes={n_on} {wall:.1f}s {min(100, 100 * target / total):.0f}%")
                last = wall
    finally:
        eyes.stop_watch()
        try:
            s1.remote.instrument.all_notes_off(0)
        except Exception:
            pass
    log(f"  STREAM end notes={n_on}")
    return n_on


def prearm_click(track: int, eyes: Eyes) -> bool:
    """Best-effort click arm using calibrated column + row search."""
    import ctypes

    from s1remote.hotkeys import focus_studio_one

    user32 = ctypes.windll.user32
    focus_studio_one()
    time.sleep(0.15)
    pre = eyes.shot(f"prearm_t{track}")
    if scan_rec_red(pre, track) or scan_rec_red(pre):
        return True
    # Image fractions → screen (primary)
    # y ≈ 0.20 + (track-1)*0.028 based on live denser rows
    yf = 0.195 + max(0, track - 1) * 0.028
    for xf in (0.275, 0.285, 0.30, 0.32):
        for dy in (0.0, -0.01, 0.01, -0.02, 0.02):
            # full-screen grab coords
            x = int(1920 * xf)
            y = int(1080 * max(0.15, min(0.75, yf + dy)))
            user32.SetCursorPos(x, y)
            time.sleep(0.03)
            user32.mouse_event(0x0002, 0, 0, 0, 0)
            time.sleep(0.02)
            user32.mouse_event(0x0004, 0, 0, 0, 0)
            time.sleep(0.3)
            s = eyes.shot(f"prearm_try_t{track}")
            if scan_rec_red(s, track) or scan_rec_red(s):
                log(f"  prearm HIT track={track} @ ({x},{y})")
                return True
    return False


def record_part(s1, path: Path, *, track: int, label: str, eyes: Eyes, max_sec: float) -> dict:
    from s1remote.hotkeys import focus_studio_one

    log(f"######## LIVE {label} → track {track} ########")
    focus_studio_one()
    try:
        s1.stop()
        s1.remote.mcu.rewind()
    except Exception:
        pass
    time.sleep(0.25)

    armed = False
    try:
        armed = s1.arm_and_verify(track, eyes_dir=eyes.directory, retries=3)
    except Exception as e:
        log(f"  arm_and_verify err: {e}")
    if not armed:
        log("  arm retry via prearm_click")
        armed = prearm_click(track, eyes)
    if not armed:
        # recheck vision — thrash may have armed something
        s = eyes.shot(f"arm_recheck_{label}")
        armed = scan_rec_red(s, track) or scan_rec_red(s)
        log(f"  arm recheck={armed}")

    pre = eyes.shot(f"before_{label}")
    pre_v = analyze_shot(pre)
    s1.record()
    time.sleep(0.4)
    rec = eyes.shot(f"rec_{label}")
    rec_v = analyze_shot(rec)
    n = stream_mid(s1, path, label=label, eyes=eyes, max_sec=max_sec)
    try:
        s1.stop()
    except Exception:
        pass
    time.sleep(0.2)
    try:
        s1.remote.mcu.rewind()
        s1.play()
        audio = capture(eyes.directory.parent / "ears", tag=f"after_{label}", seconds=3.0)
        s1.stop()
        audio_d = audio.to_dict()
    except Exception as e:
        audio_d = {"ok": False, "error": str(e), "has_signal": False}
    after = eyes.shot(f"after_{label}")
    after_v = analyze_shot(after)
    clip_growth = (after_v.blue_pixel_hits or 0) > (pre_v.blue_pixel_hits or 0) + 60
    ok = n > 0 and (armed or rec_v.rec_red or clip_growth or audio_d.get("has_signal"))
    log(
        f"  RESULT {label}: ok={ok} notes={n} armed={armed} rec_red={rec_v.rec_red} "
        f"clips+={clip_growth} audio={audio_d.get('has_signal')}"
    )
    return {
        "label": label,
        "track": track,
        "ok": ok,
        "note_ons": n,
        "armed": armed,
        "rec_red": rec_v.rec_red,
        "clip_growth": clip_growth,
        "audio": audio_d,
        "vision_after": after_v.to_dict(),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--song-dir", type=Path, default=None)
    ap.add_argument(
        "--from-template",
        action="store_true",
        help="Open Songs/Template, Save As new song, then produce (required start policy)",
    )
    ap.add_argument(
        "--name",
        default=None,
        help="New song name when using --from-template (default: date_time)",
    )
    ap.add_argument("--max-sec", type=float, default=12.0, help="Per-part stream cap (realtime)")
    ap.add_argument("--skip-compose", action="store_true")
    ap.add_argument("--eyes-subdir", default="live_song", help="Subdir under _vision/")
    args = ap.parse_args()

    ensure_s1remote_on_path()

    if args.from_template or (args.song_dir is None and not os.environ.get("S1_SONG_DIR")):
        # Standing policy: open Template → Save As new song before production
        log("=== START FROM TEMPLATE (Save As new song) ===")
        from start_from_template import start_new_song_from_template

        summary = start_new_song_from_template(name=args.name)
        if not summary.get("ok"):
            log(f"FATAL: start_from_template failed: {summary.get('error')}")
            print(json.dumps(summary, indent=2))
            return 3
        song = Path(summary["song_dir"])
        log(f"  new song ready: {song}")
    else:
        song = resolve_song_dir(args.song_dir)

    vision = song / "_vision" / str(args.eyes_subdir)
    vision.mkdir(parents=True, exist_ok=True)
    set_log_file(vision / "live_make_song.log")

    from s1remote.full_control import FullControl
    from s1remote.hotkeys import focus_studio_one, run_action, studio_one_running

    log(f"LIVE MAKE SONG song={song} max_sec={args.max_sec}")
    if not studio_one_running():
        log("FATAL: Studio One not running — use --from-template or open a Song first")
        return 2

    if detect_safety_dialog_uia():
        log("dismissing Safety dialog")
        dismiss_safety_dialog()
        time.sleep(1.2)

    eyes = Eyes(vision, enabled=True)
    start = eyes.shot("01_session")
    log(f"  vision start: {analyze_shot(start).to_dict()}")

    if not args.skip_compose:
        log("=== COMPOSE MIDI ===")
        compose_all(song / "MIDI")
    else:
        log("=== SKIP COMPOSE (use existing MIDI/) ===")

    parts = [
        ("drums.mid", 1, "DRUMS"),
        ("bass.mid", 5, "BASS"),
        ("lead.mid", 3, "LEAD"),
        ("bed.mid", 7, "BED"),
        ("color.mid", 4, "COLOR"),  # stabs / ear candy on Mai Tai 2
    ]

    results = []
    with FullControl() as s1:
        st = s1.status()
        log(
            f"  ports mcu={st.get('midi_connected')} notes={st.get('instrument_midi_connected')} "
            f"out={st.get('instrument_midi_out')}"
        )
        if not st.get("instrument_midi_connected"):
            log("FATAL: S1 Notes not connected")
            return 3

        focus_studio_one()
        for fname, track, label in parts:
            path = song / "MIDI" / fname
            if not path.is_file():
                log(f"  MISS {path}")
                results.append({"label": label, "ok": False, "error": "midi_missing"})
                continue
            r = record_part(s1, path, track=track, label=label, eyes=eyes, max_sec=args.max_sec)
            results.append(r)
            # if failed, one retry with longer arm search
            if not r.get("ok"):
                log(f"  RETRY {label}")
                prearm_click(track, eyes)
                r2 = record_part(s1, path, track=track, label=label, eyes=eyes, max_sec=args.max_sec)
                results[-1] = r2
            time.sleep(0.4)

        # Full arrangement listen
        log("=== FULL MIX LISTEN 15s ===")
        focus_studio_one()
        try:
            s1.stop()
            s1.remote.mcu.rewind()
            s1.remote.mcu.rewind()
        except Exception:
            pass
        time.sleep(0.3)
        eyes.shot("mix_pre")
        s1.play()
        eyes.start_watch("fullmix", 5.0)
        mix_audio = capture(song / "_vision" / "ears", tag="live_fullmix_15s", seconds=15.0)
        eyes.stop_watch()
        s1.stop()
        mix_shot = eyes.shot("mix_after")
        log(f"  mix ears: {mix_audio.to_dict()}")
        log(f"  mix vision: {analyze_shot(mix_shot).to_dict()}")

        try:
            run_action("save", focus=True)
        except Exception as e:
            log(f"  save warn: {e}")

    final = eyes.shot("99_final")
    final_v = analyze_shot(final)
    ok_parts = sum(1 for r in results if r.get("ok"))
    summary = {
        "ok": ok_parts >= 2 and mix_audio.has_signal,
        "finished_at": _utc(),
        "song_dir": str(song),
        "parts": results,
        "parts_ok": ok_parts,
        "parts_total": len(parts),
        "full_mix": mix_audio.to_dict(),
        "final_vision": final_v.to_dict(),
        "final_shot": str(final),
    }
    out = song / "s1_jobs" / "live_song_result.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log(f"SUMMARY ok={summary['ok']} parts={ok_parts}/{len(parts)} → {out}")
    print(json.dumps({"ok": summary["ok"], "parts_ok": ok_parts, "mix_signal": mix_audio.has_signal}, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
