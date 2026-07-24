#!/usr/bin/env python3
"""
Watched pocket live-record (producer eyes).

Streams drums.mid → track 1, bass.mid → track 2 by default.
Uses screenshots as eyes — does not claim success from note counts alone.

Arm policy (see docs/ARM_RECORD_LESSONS.md):
  default        arm_and_verify: MCU rec_arm + hotkey [R] retries + screenshot check
  --user-armed   skip agent arm entirely — user leaves Rec red before running

Env:
  S1_SONG_DIR   song with MIDI/drums.mid MIDI/bass.mid
  S1_REMOTE

Usage:
  set S1_SONG_DIR=D:\\Songs\\MySong
  py -3.12 tools/run_pocket_watched.py
  py -3.12 tools/run_pocket_watched.py --user-armed
  py -3.12 tools/run_pocket_watched.py --song-dir ... --max-sec 12 --drums-only
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

GAP = 0.3


def rewind(s1) -> None:
    try:
        s1.stop()
    except Exception:
        pass
    time.sleep(GAP)
    try:
        s1.remote.mcu.rewind()
        time.sleep(0.1)
        s1.remote.mcu.rewind()
    except Exception as e:
        log(f"  rewind warn: {e}")
    time.sleep(GAP)


def stream_mid(s1, path: Path, *, label: str, eyes: Eyes, max_sec=None) -> int:
    mid = mido.MidiFile(str(path))
    total = float(mid.length) or 1.0
    bridge = s1.remote.instrument.bridge
    log(f"  STREAM {path.name} ~{total:.1f}s port={bridge.out_name!r}")
    eyes.start_watch(label, 8.0)
    t0 = time.perf_counter()
    target = 0.0
    n_on = 0
    last_prog = 0.0
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
            if wall - last_prog >= 2.0:
                log(f"  … {label} notes={n_on} {wall:.1f}s {min(100, 100 * target / total):.0f}%")
                last_prog = wall
    finally:
        eyes.stop_watch()
        try:
            s1.remote.instrument.all_notes_off(0)
        except Exception:
            pass
    log(f"  STREAM end notes={n_on} (not proof of clip — check eyes + Arrange)")
    return n_on


def record_pass(
    s1,
    path: Path,
    *,
    track: int,
    label: str,
    eyes: Eyes,
    user_armed: bool,
    max_sec=None,
) -> int:
    strip = track - 1
    log(f"######## {label} → track {track} (MCU strip {strip}) ########")
    from s1remote.hotkeys import focus_studio_one  # noqa: WPS433

    focus_studio_one()
    time.sleep(0.2)
    rewind(s1)
    eyes.shot(f"01_home_{label}")

    if user_armed:
        log("  user-armed: NO [R], NO MCU rec — only transport + stream")
    else:
        log(f"  auto-arm: arm_and_verify track={track} (MCU + hotkey + screenshot)")
        try:
            armed = s1.arm_and_verify(track, eyes_dir=eyes.directory)
        except AttributeError:
            # Fallback for older FullControl without arm_and_verify
            armed = False
            try:
                s1.select(strip)
                time.sleep(0.25)
                s1.remote.mcu.rec_arm(strip)
                time.sleep(0.35)
            except Exception as e:
                log(f"  arm warn: {e}")
        else:
            pass
        if not armed:
            log(
                f"  WARN: arm_and_verify could not confirm Rec red on track {track}. "
                "Please arm manually (Rec button red) before continuing."
            )
            # Wait for user to intervene rather than streaming into an unarmed track
            input("  Press Enter once Rec is red, or Ctrl-C to abort: ")

    eyes.shot(f"02_armed_{label}")
    log("  TRANSPORT RECORD")
    s1.record()
    time.sleep(0.5)
    eyes.shot(f"03_recording_{label}")

    n = stream_mid(s1, path, label=label, eyes=eyes, max_sec=max_sec)
    try:
        s1.stop()
    except Exception:
        pass
    time.sleep(0.3)
    eyes.shot(f"04_stopped_{label}")
    log(f"  {label} midi_notes={n} — verify Rec red + clip on track {track} via eyes")
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description="Watched pocket stream (eyes)")
    ap.add_argument("--song-dir", type=Path, default=None)
    ap.add_argument("--s1-remote", type=Path, default=None)
    ap.add_argument("--drums", type=Path, default=None)
    ap.add_argument("--bass", type=Path, default=None)
    ap.add_argument("--drums-track", type=int, default=1)
    ap.add_argument("--bass-track", type=int, default=2)
    ap.add_argument("--max-sec", type=float, default=None)
    ap.add_argument("--drums-only", action="store_true")
    ap.add_argument("--bass-only", action="store_true")
    ap.add_argument(
        "--user-armed",
        action="store_true",
        default=False,
        help="Skip agent arm — user must set Rec red manually before running",
    )
    ap.add_argument("--no-eyes", action="store_true")
    ap.add_argument("--eyes-dir", type=Path, default=None)
    ap.add_argument(
        "--arm-retries",
        type=int,
        default=3,
        help="Max arm_and_verify attempts before asking user (default 3)",
    )
    args = ap.parse_args()

    song = resolve_song_dir(args.song_dir)
    ensure_s1remote_on_path(args.s1_remote)
    from s1remote.full_control import FullControl  # noqa: E402
    from s1remote.hotkeys import focus_studio_one, run_action  # noqa: E402

    set_log_file(default_log_path(song, "pocket_watched_latest.log"))
    eyes_dir = args.eyes_dir or default_eyes_dir(song)
    eyes = Eyes(eyes_dir, enabled=not args.no_eyes)

    drums = args.drums or (song / "MIDI" / "drums.mid")
    bass = args.bass or (song / "MIDI" / "bass.mid")
    if not drums.is_file() or not bass.is_file():
        log(f"FATAL missing MIDI: {drums} / {bass}")
        return 1

    log("POCKET WATCHED — eyes on Arrange Rec + clips")
    log(f"  song={song} user_armed={args.user_armed} arm_retries={args.arm_retries}")

    try:
        with FullControl() as s1:
            st = s1.status()
            log(
                f"  mcu={st.get('midi_connected')} notes={st.get('instrument_midi_out')} "
                f"notes_ok={st.get('instrument_midi_connected')}"
            )
            if not st.get("instrument_midi_connected"):
                log("FATAL: instrument MIDI (S1 Notes) not connected")
                return 2

            n_d = n_b = 0
            if not args.bass_only:
                n_d = record_pass(
                    s1,
                    drums,
                    track=args.drums_track,
                    label="DRUMS",
                    eyes=eyes,
                    user_armed=args.user_armed,
                    max_sec=args.max_sec,
                )
                time.sleep(0.5)
            if not args.drums_only:
                n_b = record_pass(
                    s1,
                    bass,
                    track=args.bass_track,
                    label="BASS",
                    eyes=eyes,
                    user_armed=args.user_armed,
                    max_sec=args.max_sec,
                )

            focus_studio_one()
            try:
                run_action("save", focus=True)
            except Exception:
                pass
            log(f"COMPLETE stream drums_notes={n_d} bass_notes={n_b}")
            log(f"  eyes dir: {eyes_dir}  shots~{eyes.shot_count}")
            log("  Confirm clips on instrument tracks before approving pocket.")
            return 0
    except Exception as e:
        log(f"FATAL: {e}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
