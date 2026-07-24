#!/usr/bin/env python3
"""
Monitored S1 pipeline stages (path-agnostic).

Phases:
  status          — ports + MIDI file presence
  compose-lead    — write MIDI/lead.mid (needs --song-dir)
  stream-drums    — stream drums.mid (default track 1)
  stream-bass     — stream bass.mid (default track 2)
  stream-lead     — stream lead.mid
  continue        — status + compose-lead + stop for arm mouse if needed

Producer eyes: screenshots via s1_tools.eyes

Env: S1_SONG_DIR, S1_REMOTE

Usage:
  set S1_SONG_DIR=D:\\Songs\\MySong
  py -3.12 tools/pipeline_monitored.py --phase=status
  py -3.12 tools/pipeline_monitored.py --phase=stream-drums --armed
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import mido

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from s1_tools.paths import (  # noqa: E402
    default_eyes_dir,
    default_log_path,
    ensure_s1remote_on_path,
    resolve_song_dir,
)
from s1_tools.logutil import log, set_log_file  # noqa: E402
from s1_tools.eyes import Eyes  # noqa: E402

BPM = 80.0
BARS = 32
GAP = 0.35


def compose_lead(midi_dir: Path) -> Path:
    import numpy as np

    rng = np.random.default_rng(8801)
    scale = [57, 59, 60, 62, 64, 65, 67, 69]
    notes: list[dict] = []
    for bar in range(BARS):
        base = bar * 4.0
        if bar < 4:
            continue
        cyc = bar % 8
        degrees = [0, 2, 4, 2] if cyc < 4 else ([3, 2, 0, 2] if cyc < 6 else [1, 0, 2, 0])
        if bar % 2 == 0:
            for off, deg, dur in zip([0.0, 1.0, 2.0, 3.0], degrees, [0.85, 0.85, 0.85, 0.7]):
                if bar % 4 == 3 and off >= 2.0:
                    continue
                pitch = scale[min(deg, len(scale) - 1)]
                if cyc >= 6 and off == 0.0:
                    pitch = 58
                t = max(0.0, base + off + float(rng.normal(0, 0.008)))
                v = float(max(0.25, min(1.0, (0.72 if off == 0 else 0.58) + rng.normal(0, 0.05))))
                notes.append({"key": pitch, "time": t, "duration": dur, "vel": v})
        else:
            pitch = scale[4] if cyc < 6 else scale[0]
            t = max(0.0, base + 0.5 + float(rng.normal(0, 0.008)))
            notes.append({"key": pitch, "time": t, "duration": 2.8, "vel": float(max(0.25, min(1.0, 0.55 + rng.normal(0, 0.05))))})

    path = midi_dir / "lead.mid"
    mid = mido.MidiFile(ticks_per_beat=480)
    tr = mido.MidiTrack()
    mid.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(BPM)))
    tpb = 480
    ev = []
    for n in notes:
        t0 = int(n["time"] * tpb)
        t1 = int((n["time"] + n["duration"]) * tpb)
        vel = max(1, min(127, int(n["vel"] * 127)))
        ev.append((t0, 1, int(n["key"]), vel))
        ev.append((t1, 0, int(n["key"]), 0))
    ev.sort(key=lambda e: (e[0], e[1]))
    abs_t = 0
    for t, on, key, vel in ev:
        dt = max(0, t - abs_t)
        abs_t = t
        tr.append(
            mido.Message("note_on" if on else "note_off", note=key, velocity=vel if on else 0, time=dt)
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    mid.save(str(path))
    log(f"  wrote {path} notes={len(notes)} ~{mido.MidiFile(str(path)).length:.1f}s")
    return path


def stream_file(s1, path: Path, *, label: str, eyes: Eyes, max_sec=None) -> int:
    mid = mido.MidiFile(str(path))
    total = float(mid.length) or 1.0
    bridge = s1.remote.instrument.bridge
    log(f"  STREAM {path.name} ~{total:.1f}s port={bridge.out_name!r}")
    eyes.start_watch(label, 8.0)
    t0 = time.perf_counter()
    target = 0.0
    n_on_i = 0
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
                n_on_i += 1
            if out.type in ("note_on", "note_off", "control_change", "program_change"):
                bridge.send(out)
            wall = time.perf_counter() - t0
            if wall - last >= 2.0:
                log(f"  … {label} notes={n_on_i} {wall:.1f}s {min(100, 100 * target / total):.0f}%")
                last = wall
    finally:
        eyes.stop_watch()
        try:
            s1.remote.instrument.all_notes_off(0)
        except Exception:
            pass
    log(f"  STREAM end notes={n_on_i}")
    return n_on_i


def phase_stream(args, *, mid_name: str, track: int, label: str) -> int:
    song = resolve_song_dir(args.song_dir)
    ensure_s1remote_on_path(args.s1_remote)
    from s1remote.full_control import FullControl  # noqa: E402
    from s1remote.hotkeys import focus_studio_one, run_action  # noqa: E402

    set_log_file(default_log_path(song, "pipeline_monitored_latest.log"))
    eyes = Eyes(args.eyes_dir or default_eyes_dir(song), enabled=not args.no_eyes)
    path = Path(args.midi) if args.midi else (song / "MIDI" / mid_name)
    if not path.is_file():
        log(f"FATAL missing {path}")
        return 1

    if not args.armed and not args.auto_arm:
        log("MOUSE / ARM required: leave Rec RED on target track, then re-run with --armed")
        log(f"  target track {track} file {path.name}")
        return 10

    with FullControl() as s1:
        st = s1.status()
        log(f"  notes_ok={st.get('instrument_midi_connected')} out={st.get('instrument_midi_out')}")
        if not st.get("instrument_midi_connected"):
            return 2
        focus_studio_one()
        try:
            s1.stop()
            s1.remote.mcu.rewind()
        except Exception:
            pass
        time.sleep(GAP)
        if args.auto_arm:
            strip = track - 1
            try:
                s1.select(strip)
                s1.remote.mcu.rec_arm(strip)
                log(f"  auto-arm MCU strip {strip} (verify eyes — may not arm Arrange)")
            except Exception as e:
                log(f"  auto-arm warn: {e}")
        eyes.shot(f"before_{label}")
        s1.record()
        time.sleep(0.45)
        eyes.shot(f"rec_{label}")
        n = stream_file(s1, path, label=label, eyes=eyes, max_sec=args.max_sec)
        try:
            s1.stop()
        except Exception:
            pass
        eyes.shot(f"after_{label}")
        try:
            run_action("save", focus=True)
        except Exception:
            pass
        log(f"DONE {label} notes={n} — confirm clip on track {track}")
        return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", default="status")
    ap.add_argument("--song-dir", type=Path, default=None)
    ap.add_argument("--s1-remote", type=Path, default=None)
    ap.add_argument("--track", type=int, default=None)
    ap.add_argument("--midi", type=Path, default=None)
    ap.add_argument("--max-sec", type=float, default=None)
    ap.add_argument("--armed", action="store_true")
    ap.add_argument("--auto-arm", action="store_true")
    ap.add_argument("--no-eyes", action="store_true")
    ap.add_argument("--eyes-dir", type=Path, default=None)
    args = ap.parse_args()

    phase = args.phase
    log(f"pipeline_monitored phase={phase}")

    if phase == "status":
        song = resolve_song_dir(args.song_dir, required=False)
        ensure_s1remote_on_path(args.s1_remote)
        from s1remote.full_control import FullControl  # noqa: E402

        with FullControl() as s1:
            st = s1.status()
            log(f"  status { {k: st.get(k) for k in ('studio_one_running','midi_connected','instrument_midi_out','instrument_midi_connected')} }")
        if song:
            for name in ("drums", "bass", "lead"):
                p = song / "MIDI" / f"{name}.mid"
                log(f"  {'OK' if p.is_file() else 'MISS'} {p}")
        return 0

    if phase == "compose-lead":
        song = resolve_song_dir(args.song_dir)
        compose_lead(song / "MIDI")
        return 0

    if phase in ("stream-drums", "record-drums"):
        return phase_stream(args, mid_name="drums.mid", track=args.track or 1, label="DRUMS")
    if phase in ("stream-bass", "record-bass"):
        return phase_stream(args, mid_name="bass.mid", track=args.track or 2, label="BASS")
    if phase in ("stream-lead", "record-lead"):
        return phase_stream(args, mid_name="lead.mid", track=args.track or 3, label="LEAD")

    if phase == "continue":
        song = resolve_song_dir(args.song_dir)
        ensure_s1remote_on_path(args.s1_remote)
        set_log_file(default_log_path(song, "pipeline_monitored_latest.log"))
        compose_lead(song / "MIDI")
        log("STOP for arm: set Rec red on track 1, then:")
        log("  py -3.12 tools/pipeline_monitored.py --phase=stream-drums --armed --song-dir ...")
        return 10

    log(f"unknown phase {phase}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
