#!/usr/bin/env python3
"""
Execute Music-producer job JSON (hands only).

Reads:  <song>/s1_jobs/current.json  (or --job)
Writes: <song>/s1_jobs/last_result.json  with vision + audio cues

Does NOT lock creative gates. Producer observes result and decides.

Usage:
  set S1_SONG_DIR=D:\\Songs\\MySong
  set PYTHONPATH=%CD%
  py -3.12 tools/execute_job.py
  py -3.12 tools/execute_job.py --song-dir PATH --dry-run
  py -3.12 tools/execute_job.py --no-prompt --max-sec 8
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

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
from s1_tools.ears import capture as ears_capture  # noqa: E402
from s1_tools.vision import (  # noqa: E402
    analyze_shot,
    detect_safety_dialog_uia,
    dismiss_safety_dialog,
    summarize_shots,
)
from s1_tools.job_schema import (  # noqa: E402
    normalize_options,
    resolve_midi_path,
    validate_job,
)
from s1_tools.arrange import add_instrument_tracks  # noqa: E402

GAP = 0.3


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_job(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_result(song: Path, result: Dict[str, Any]) -> Path:
    out = song / "s1_jobs" / "last_result.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return out


def stream_mid(s1, path: Path, *, label: str, eyes: Eyes, max_sec=None) -> int:
    mid = mido.MidiFile(str(path))
    total = float(mid.length) or 1.0
    bridge = s1.remote.instrument.bridge
    log(f"  STREAM {path.name} ~{total:.1f}s port={bridge.out_name!r}")
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


class JobRunner:
    def __init__(
        self,
        song: Path,
        job: Dict[str, Any],
        *,
        dry_run: bool = False,
        force_max_sec: Optional[float] = None,
        no_prompt: Optional[bool] = None,
    ):
        self.song = Path(song)
        self.job = job
        self.opts = normalize_options(job)
        if force_max_sec is not None:
            self.opts["max_sec"] = force_max_sec
        if no_prompt is not None:
            self.opts["no_prompt"] = no_prompt
        self.dry_run = dry_run
        self.eyes = Eyes(
            default_eyes_dir(self.song),
            enabled=not self.opts.get("no_eyes"),
        )
        self.ears_dir = self.song / "_vision" / "ears"
        self.step_results: List[Dict[str, Any]] = []
        self.shot_paths: List[Path] = []
        self.audio_reports: List[Dict[str, Any]] = []
        self.s1 = None
        self._fatal: Optional[str] = None

    def _record_step(self, op: str, **kw: Any) -> Dict[str, Any]:
        row = {"op": op, **kw}
        self.step_results.append(row)
        return row

    def _shot(self, tag: str) -> Optional[Path]:
        p = self.eyes.shot(tag)
        if p:
            self.shot_paths.append(p)
            rep = analyze_shot(p)
            log(f"  vision: rec_red={rep.rec_red} blue={rep.blue_pixel_hits} luma={rep.mean_luma:.0f}")
        return p

    def _ears(self, tag: str, seconds: float) -> Dict[str, Any]:
        if self.opts.get("no_ears"):
            return {"ok": False, "error": "no_ears"}
        rep = ears_capture(
            self.ears_dir,
            tag=tag,
            seconds=seconds,
            enabled=True,
        )
        d = rep.to_dict()
        self.audio_reports.append(d)
        return d

    def run(self) -> Dict[str, Any]:
        errs = validate_job(self.job)
        if errs:
            return self._finish(False, error="invalid_job", detail=errs)

        if self.dry_run:
            log("DRY RUN — validate + list steps only (not a real capture)")
            for i, s in enumerate(self.job["steps"]):
                log(f"  [{i}] {s.get('op')} { {k: v for k, v in s.items() if k != 'op'} }")
            # Mark dry_run so producer next_action does not treat as pocket-ready
            return self._finish(
                True,
                dry_run=True,
                steps_planned=len(self.job["steps"]),
            )

        ensure_s1remote_on_path()
        from s1remote.full_control import FullControl  # noqa: E402
        from s1remote.hotkeys import focus_studio_one, run_action, studio_one_running  # noqa: E402

        if not studio_one_running():
            return self._finish(False, error="studio_one_not_running")

        set_log_file(default_log_path(self.song, "execute_job_latest.log"))
        log(f"EXECUTE job id={self.job.get('id')} song={self.song}")
        self._shot("job_start")
        # Clear crash-recovery modal before any MIDI/arm work
        if detect_safety_dialog_uia():
            log("  preflight: dismissing Studio One Safety dialog")
            dismiss_safety_dialog()
            time.sleep(1.0)
            self._shot("after_preflight_safety")

        try:
            with FullControl() as s1:
                self.s1 = s1
                st = s1.status()
                log(
                    f"  status mcu={st.get('midi_connected')} "
                    f"notes={st.get('instrument_midi_connected')} "
                    f"out={st.get('instrument_midi_out')}"
                )
                for i, step in enumerate(self.job["steps"]):
                    op = step["op"]
                    log(f"=== step[{i}] {op} ===")
                    try:
                        ok = self._dispatch(step, focus_studio_one, run_action)
                    except Exception as e:
                        log(f"  FAIL step: {e}")
                        self._record_step(op, ok=False, error=str(e))
                        if not step.get("optional"):
                            self._fatal = f"step_{i}_{op}: {e}"
                            break
                        continue
                    if not ok and not step.get("optional"):
                        self._fatal = f"step_{i}_{op} failed"
                        break
        except Exception as e:
            self._fatal = str(e)
            log(f"FATAL: {e}")

        if self.opts.get("save_after") and self.s1 is not None and not self._fatal:
            try:
                from s1remote.hotkeys import run_action  # noqa: E402

                run_action("save", focus=True)
                self._record_step("save", ok=True, auto=True)
            except Exception as e:
                self._record_step("save", ok=False, error=str(e), auto=True)

        self._shot("job_end")
        ok = self._fatal is None
        return self._finish(ok, error=self._fatal)

    def _dispatch(self, step: Dict[str, Any], focus_studio_one, run_action) -> bool:
        op = step["op"]
        s1 = self.s1

        if op == "check_setup":
            st = s1.status()
            notes_ok = bool(st.get("instrument_midi_connected"))
            mcu_ok = bool(st.get("midi_connected"))
            running = bool(st.get("studio_one_running", True))
            self._record_step(
                op,
                ok=notes_ok and running,
                instrument_midi=notes_ok,
                mcu=mcu_ok,
                studio_one_running=running,
                status_snip={
                    k: st.get(k)
                    for k in (
                        "studio_one_running",
                        "midi_connected",
                        "instrument_midi_out",
                        "instrument_midi_connected",
                    )
                },
            )
            if not notes_ok:
                log("  FAIL: instrument MIDI (S1 Notes) not connected")
                return False
            return True

        if op == "ensure_workspace":
            focus_studio_one()
            time.sleep(0.2)
            # Crash recovery modal blocks all DAW work — clear it first
            if detect_safety_dialog_uia():
                dismissed = dismiss_safety_dialog()
                time.sleep(1.2)
                focus_studio_one()
                shot = self._shot("after_safety_dismiss")
                rep = analyze_shot(shot)
                still = detect_safety_dialog_uia() or rep.safety_dialog
                self._record_step(
                    op,
                    ok=dismissed and not still,
                    safety_dismissed=dismissed,
                    safety_still_present=still,
                    vision=rep.to_dict(),
                )
                if still:
                    log("  FAIL: Studio One Safety dialog still blocking")
                    return False
                return True
            shot = self._shot("workspace")
            rep = analyze_shot(shot)
            if rep.safety_dialog:
                dismissed = dismiss_safety_dialog()
                time.sleep(1.0)
                shot2 = self._shot("after_safety_dismiss")
                rep2 = analyze_shot(shot2)
                ok = dismissed and not rep2.safety_dialog
                self._record_step(
                    op,
                    ok=ok,
                    safety_dismissed=dismissed,
                    vision=rep2.to_dict(),
                )
                return ok
            self._record_step(op, ok=True, vision=rep.to_dict())
            return True

        if op == "create_tracks":
            count = int(step.get("count") or 1)
            focus_studio_one()
            n = add_instrument_tracks(count, focus_fn=focus_studio_one)
            self._shot(f"after_create_{n}")
            self._record_step(op, ok=n >= 1, created=n, requested=count)
            return n >= 1

        if op == "browser_load":
            name = step.get("name") or ""
            try:
                s1.browser_load(name)
                self._record_step(op, ok=True, name=name)
                return True
            except Exception as e:
                self._record_step(op, ok=False, name=name, error=str(e))
                return bool(step.get("optional"))

        if op == "rewind":
            try:
                s1.stop()
                s1.remote.mcu.rewind()
                time.sleep(0.1)
                s1.remote.mcu.rewind()
            except Exception as e:
                self._record_step(op, ok=False, error=str(e))
                return False
            self._record_step(op, ok=True)
            return True

        if op == "stop":
            try:
                s1.stop()
            except Exception:
                pass
            self._record_step(op, ok=True)
            return True

        if op == "save":
            try:
                run_action("save", focus=True)
                self._record_step(op, ok=True)
                return True
            except Exception as e:
                self._record_step(op, ok=False, error=str(e))
                return False

        if op == "shot":
            p = self._shot(step.get("tag") or "manual")
            self._record_step(op, ok=p is not None, path=str(p) if p else None)
            return True

        if op == "report":
            msg = step.get("message") or ""
            log(f"  REPORT: {msg}")
            self._record_step(op, ok=True, message=msg)
            return True

        if op == "play_listen":
            seconds = float(step.get("seconds") or self.opts.get("listen_sec") or 4.0)
            focus_studio_one()
            self._shot("before_listen")
            try:
                s1.play()
            except Exception as e:
                self._record_step(op, ok=False, error=str(e))
                return False
            audio = self._ears("play_listen", seconds)
            try:
                s1.stop()
            except Exception:
                pass
            self._shot("after_listen")
            self._record_step(op, ok=True, audio=audio, seconds=seconds)
            return True

        if op == "import_midi":
            # Best-effort: leave to dedicated tool; report path only
            midi = resolve_midi_path(self.song, step.get("midi") or "")
            self._record_step(
                op,
                ok=midi is not None,
                midi=str(midi) if midi else step.get("midi"),
                note="import_midi is best-effort; prefer stream_record",
            )
            return midi is not None or bool(step.get("optional"))

        if op == "stream_record":
            return self._stream_record(step, focus_studio_one)

        self._record_step(op, ok=False, error="unknown_op")
        return False

    def _stream_record(self, step: Dict[str, Any], focus_studio_one) -> bool:
        s1 = self.s1
        track = int(step["track"])
        label = str(step.get("label") or f"T{track}")
        midi_field = step.get("midi") or ""
        midi = resolve_midi_path(self.song, midi_field)
        if midi is None:
            self._record_step("stream_record", ok=False, error="midi_missing", midi=midi_field)
            return False

        max_sec = step.get("max_sec", self.opts.get("max_sec"))
        if max_sec is not None:
            max_sec = float(max_sec)

        focus_studio_one()
        time.sleep(0.15)
        try:
            s1.stop()
            s1.remote.mcu.rewind()
        except Exception:
            pass
        time.sleep(GAP)

        user_armed = bool(self.opts.get("user_armed") or step.get("user_armed"))
        armed = False
        if user_armed:
            log("  user_armed: skip agent arm")
            armed = True
        else:
            log(f"  arm_and_verify track={track}")
            try:
                armed = s1.arm_and_verify(track, eyes_dir=self.eyes.directory)
            except Exception as e:
                log(f"  arm_and_verify error: {e}")
                armed = False
            if not armed:
                log("  WARN: could not confirm Rec red")
                if self.opts.get("no_prompt"):
                    self._record_step(
                        "stream_record",
                        ok=False,
                        error="arm_unconfirmed",
                        track=track,
                        label=label,
                    )
                    return False
                try:
                    input("  Press Enter once Rec is red, or Ctrl-C to abort: ")
                    armed = True
                except EOFError:
                    self._record_step(
                        "stream_record",
                        ok=False,
                        error="arm_unconfirmed_no_tty",
                        track=track,
                    )
                    return False

        pre = self._shot(f"before_{label}")
        pre_v = analyze_shot(pre)
        s1.record()
        time.sleep(0.45)
        rec = self._shot(f"rec_{label}")
        rec_v = analyze_shot(rec)

        # Brief ears while notes stream (non-blocking sample after a short lead-in)
        n = stream_mid(s1, midi, label=label, eyes=self.eyes, max_sec=max_sec)

        # Capture what we hear after stream (tail / residual) + optional play
        listen_sec = float(step.get("listen_sec") or min(3.0, max_sec or 3.0))
        try:
            s1.stop()
        except Exception:
            pass
        time.sleep(0.2)
        try:
            s1.remote.mcu.rewind()
            s1.play()
            audio = self._ears(f"after_{label}", listen_sec)
            s1.stop()
        except Exception as e:
            audio = {"ok": False, "error": str(e)}

        after = self._shot(f"after_{label}")
        after_v = analyze_shot(after)

        ok = n > 0 and (rec_v.rec_red or armed)
        self._record_step(
            "stream_record",
            ok=ok,
            label=label,
            track=track,
            midi=str(midi),
            note_ons=n,
            armed_confirmed=rec_v.rec_red or pre_v.rec_red,
            vision={
                "pre": pre_v.to_dict(),
                "rec": rec_v.to_dict(),
                "after": after_v.to_dict(),
            },
            audio=audio,
        )
        log(f"  stream_record {label}: notes={n} rec_red={rec_v.rec_red} audio_signal={audio.get('has_signal')}")
        return ok

    def _finish(self, ok: bool, **extra: Any) -> Dict[str, Any]:
        vision_summary = summarize_shots(self.shot_paths) if self.shot_paths else {}
        result = {
            "ok": ok,
            "job_id": self.job.get("id"),
            "source": self.job.get("source"),
            "song_dir": str(self.song.resolve()),
            "finished_at": _utc(),
            "options": self.opts,
            "steps": self.step_results,
            "vision": vision_summary,
            "audio": self.audio_reports,
            "eyes_dir": str(self.eyes.directory),
            "shot_count": self.eyes.shot_count,
            **extra,
        }
        path = write_result(self.song, result)
        log(f"RESULT ok={ok} → {path}")
        return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Execute producer s1 job (hands only)")
    ap.add_argument("--song-dir", type=Path, default=None)
    ap.add_argument("--job", type=Path, default=None, help="Path to job JSON")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-prompt", action="store_true", help="Never block on input()")
    ap.add_argument("--max-sec", type=float, default=None)
    ap.add_argument("--no-eyes", action="store_true")
    ap.add_argument("--no-ears", action="store_true")
    args = ap.parse_args(argv)

    song = resolve_song_dir(args.song_dir)
    job_path = args.job or (song / "s1_jobs" / "current.json")
    if not job_path.is_file():
        log(f"FATAL: no job at {job_path}")
        log("  Producer: python -m song_pipeline_kb plan mvp --song-dir ...")
        return 2

    job = load_job(job_path)
    if args.no_eyes:
        job.setdefault("options", {})["no_eyes"] = True
    if args.no_ears:
        job.setdefault("options", {})["no_ears"] = True

    runner = JobRunner(
        song,
        job,
        dry_run=args.dry_run,
        force_max_sec=args.max_sec,
        no_prompt=args.no_prompt if args.no_prompt else None,
    )
    result = runner.run()
    print(json.dumps({"ok": result.get("ok"), "job_id": result.get("job_id"), "error": result.get("error")}, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
