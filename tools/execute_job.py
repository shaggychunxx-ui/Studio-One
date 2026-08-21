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
    return json.loads(path.read_text(encoding="utf-8-sig"))


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
    # Live vision: denser frames during record
    eyes.start_watch(label, 2.5 if getattr(eyes, "live", True) else 8.0)
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
            live=True,
        )
        self.ears_dir = self.song / "_vision" / "ears"
        self.step_results: List[Dict[str, Any]] = []
        self.shot_paths: List[Path] = []
        self.audio_reports: List[Dict[str, Any]] = []
        self.s1 = None
        self._fatal: Optional[str] = None
        self._last_failure: Optional[Dict[str, Any]] = None

    def _record_step(self, op: str, **kw: Any) -> Dict[str, Any]:
        row = {"op": op, **kw}
        self.step_results.append(row)
        return row

    def _fail(
        self,
        domain: str,
        primary_cause: str,
        *,
        op: str = "",
        remediations: Optional[List[str]] = None,
        next_action: str = "inspect_last_failure_json",
        evidence: Optional[Dict[str, Any]] = None,
        causes: Optional[List[str]] = None,
        error: Optional[str] = None,
        also_named: Optional[str] = None,
        record_step: bool = True,
        **ctx: Any,
    ) -> Dict[str, Any]:
        """Structured failure (same shape as arm diagnosis) for every fail path."""
        from s1_tools.failure_log import record_failure

        rec = record_failure(
            self.song,
            domain=domain,
            primary_cause=primary_cause,
            causes=causes,
            remediations=remediations,
            next_action=next_action,
            evidence=evidence,
            context={"op": op, "job_id": self.job.get("id"), **ctx},
            error=error,
            also_named=also_named or f"{domain}_failure",
        )
        self._last_failure = rec
        if record_step and op:
            self._record_step(
                op,
                ok=False,
                error=error or primary_cause,
                primary_cause=primary_cause,
                causes=rec.get("causes"),
                remediations=rec.get("remediations"),
                next_action=rec.get("next_action"),
                failure=rec,
            )
        return rec

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
            self._fail(
                "job",
                "invalid_job",
                op="validate",
                remediations=[
                    "Fix s1_jobs/current.json against job_schema KNOWN_OPS",
                    "Producer: re-run plan mvp / plan stream",
                ],
                next_action="fix_job_json",
                evidence={"validation_errors": errs},
                also_named="job_failure",
            )
            return self._finish(False, error="invalid_job", detail=errs, failure=self._last_failure)

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
        from s1_tools.failure_log import failure_s1_not_running  # noqa: E402

        if not studio_one_running():
            rec = failure_s1_not_running(self.song, job_id=self.job.get("id"))
            self._last_failure = rec
            self._fatal = rec["primary_cause"]
            return self._finish(False, error=self._fatal, failure=rec)

        set_log_file(default_log_path(self.song, "execute_job_latest.log"))
        log(f"EXECUTE job id={self.job.get('id')} song={self.song}")
        self._shot("job_start")

        # Hard UI gate: stay on this song; clear New/Safety; STOP if unavailable
        expected = self.song.name  # e.g. Meridian_Pulse
        try:
            from s1_tools.ui_gate import check_ui_available

            gate = check_ui_available(
                expected_song=expected,
                eyes=self.eyes,
                auto_dismiss=True,
                song_dir=self.song,
                log_failure=True,
            )
            if not gate.available:
                self._last_failure = {
                    "ok": False,
                    "domain": "workspace",
                    "primary_cause": "ui_unavailable",
                    "causes": gate.reasons,
                    "blocking_dialogs": gate.blocking_dialogs,
                    "remediations": [
                        f"Stay on {expected}; Cancel New/Open dialogs",
                        "Do not continue until arrange is free",
                    ],
                    "next_action": "clear_blockers_stay_on_song",
                    "evidence": gate.to_dict(),
                }
                self._fatal = "ui_unavailable"
                log(f"  STOP: UI unavailable — {gate.reasons}")
                return self._finish(False, error="ui_unavailable", failure=self._last_failure)
        except Exception as e:
            log(f"  ui_gate preflight warn: {e}")

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
                        self._fail(
                            "job",
                            "step_exception",
                            op=op,
                            error=str(e),
                            remediations=[
                                "Read traceback in execute_job_latest.log",
                                "Check S1 still open and focused",
                            ],
                            next_action="retry_step_after_fix",
                            evidence={"exception": str(e)},
                            step_index=i,
                        )
                        if not step.get("optional"):
                            self._fatal = f"step_{i}_{op}: {e}"
                            break
                        continue
                    if not ok and not step.get("optional"):
                        # Prefer structured failure already recorded on step
                        last = self.step_results[-1] if self.step_results else {}
                        if not last.get("failure") and not last.get("primary_cause"):
                            self._fail(
                                "job",
                                last.get("error") or f"{op}_failed",
                                op=op,
                                remediations=[
                                    "See step result in last_result.json",
                                    "Open last_failure.json for remediations",
                                ],
                                next_action="inspect_last_failure_json",
                                evidence={"step": last},
                                step_index=i,
                            )
                        self._fatal = (
                            (last.get("primary_cause") or last.get("error") or f"step_{i}_{op} failed")
                        )
                        break
        except Exception as e:
            self._fail(
                "job",
                "step_exception",
                op="FullControl",
                error=str(e),
                remediations=["Restart S1 Notes/MCU ports", "Relaunch Studio One"],
                next_action="recover_s1_ui",
            )
            self._fatal = str(e)
            log(f"FATAL: {e}")

        if self.opts.get("save_after") and self.s1 is not None and not self._fatal:
            try:
                from s1remote.hotkeys import run_action  # noqa: E402

                run_action("save", focus=True)
                self._record_step("save", ok=True, auto=True)
            except Exception as e:
                self._fail(
                    "save",
                    "save_failed",
                    op="save",
                    error=str(e),
                    remediations=["Ctrl+S manually", "Check disk full / song path writable"],
                    next_action="manual_save",
                )

        self._shot("job_end")
        ok = self._fatal is None
        return self._finish(ok, error=self._fatal, failure=self._last_failure)

    def _dispatch(self, step: Dict[str, Any], focus_studio_one, run_action) -> bool:
        op = step["op"]
        s1 = self.s1

        if op == "check_setup":
            st = s1.status()
            notes_ok = bool(st.get("instrument_midi_connected"))
            mcu_ok = bool(st.get("midi_connected"))
            running = bool(st.get("studio_one_running", True))
            snip = {
                k: st.get(k)
                for k in (
                    "studio_one_running",
                    "midi_connected",
                    "instrument_midi_out",
                    "instrument_midi_connected",
                )
            }
            ok = notes_ok and running
            self._record_step(
                op,
                ok=ok,
                instrument_midi=notes_ok,
                mcu=mcu_ok,
                studio_one_running=running,
                status_snip=snip,
            )
            if not running:
                from s1_tools.failure_log import failure_s1_not_running

                self._last_failure = failure_s1_not_running(self.song, op=op)
                return False
            if not notes_ok:
                from s1_tools.failure_log import failure_midi_port

                self._last_failure = failure_midi_port(self.song, status=snip, op=op)
                return False
            if not mcu_ok:
                self._fail(
                    "setup",
                    "mcu_midi_not_connected",
                    op=op,
                    remediations=[
                        "loopMIDI S1 Controller pair",
                        "External Devices Mackie Receive/Send ports",
                    ],
                    next_action="fix_mcu_ports",
                    evidence={"status": snip},
                    record_step=False,
                )
                # MCU optional for notes stream — warn only
                log("  WARN: MCU not connected (transport may be limited)")
            return True

        if op == "ensure_workspace":
            from s1_tools.eyes import check_display_dpi
            from s1_tools.ui_gate import check_ui_available

            dpi = check_display_dpi()
            gate = check_ui_available(
                expected_song=self.song.name,
                eyes=self.eyes,
                auto_dismiss=True,
                song_dir=self.song,
                log_failure=True,
            )
            self._record_step(
                op,
                ok=gate.available,
                vision={"shot": gate.shot},
                is_s1_arrange=gate.is_arrange,
                dpi=dpi,
                ui_gate=gate.to_dict(),
                blocking_dialogs=gate.blocking_dialogs,
                song_title=gate.song_title,
            )
            if not gate.available:
                self._last_failure = {
                    "ok": False,
                    "domain": "workspace",
                    "primary_cause": (
                        "blocking_dialog"
                        if gate.blocking_dialogs
                        else "ui_unavailable"
                    ),
                    "causes": gate.reasons,
                    "remediations": [
                        f"Stay on {self.song.name}",
                        "Cancel New/Open/Save As if open (never OK a new song mid-session)",
                        "Dismiss Safety if present",
                    ],
                    "next_action": "clear_blockers_stay_on_song",
                    "evidence": gate.to_dict(),
                }
            return gate.available

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

        if op == "transport":
            act = (step.get("action") or step.get("do") or "stop").lower()
            try:
                if act == "play":
                    s1.play()
                elif act == "stop":
                    s1.stop()
                elif act == "record":
                    s1.record()
                elif act == "rewind":
                    s1.stop()
                    s1.remote.mcu.rewind()
                    time.sleep(0.1)
                    s1.remote.mcu.rewind()
                else:
                    self._record_step(op, ok=False, error=f"bad action {act}")
                    return False
                self._record_step(op, ok=True, action=act)
                return True
            except Exception as e:
                self._record_step(op, ok=False, action=act, error=str(e))
                return False

        if op == "set_fader":
            try:
                from s1_tools.tracks_map import resolve_track

                if step.get("role") is not None:
                    track = resolve_track(self.song, step["role"])
                    ch = max(0, track - 1)
                elif step.get("track") is not None:
                    ch = max(0, int(step["track"]) - 1)
                else:
                    ch = int(step.get("channel", 0))
                db = float(step.get("db", step.get("level", -6.0)))
                s1.fader(ch, db)
                self._record_step(op, ok=True, channel=ch, db=db)
                return True
            except Exception as e:
                self._record_step(op, ok=False, error=str(e))
                return bool(step.get("optional"))

        if op == "set_pan":
            try:
                ch = int(step.get("channel", 0))
                # MCU V-Pot pan in channel mode — delta-ish; absolute pan not always available
                delta = int(step.get("delta", 0))
                if hasattr(s1, "vpot"):
                    s1.vpot(ch, delta)
                self._record_step(op, ok=True, channel=ch, delta=delta, note="MCU vpot delta")
                return True
            except Exception as e:
                self._record_step(op, ok=False, error=str(e))
                return bool(step.get("optional"))

        if op == "mix_balance":
            try:
                from s1_tools.mix_ops import apply_mix_balance

                result = apply_mix_balance(
                    s1,
                    self.song,
                    levels=step.get("levels"),
                    preset=step.get("preset") or "full_static",
                )
                self._record_step(op, ok=bool(result.get("ok")), **result)
                return bool(result.get("ok")) or bool(step.get("optional"))
            except Exception as e:
                self._record_step(op, ok=False, error=str(e))
                return bool(step.get("optional"))

        if op == "export_mixdown":
            try:
                from s1_tools.mix_ops import export_mixdown_hotkey

                # Save first
                try:
                    run_action("save", focus=True)
                except Exception:
                    pass
                result = export_mixdown_hotkey(run_action, focus=True)
                masters = self.song / "Masters"
                masters.mkdir(parents=True, exist_ok=True)
                result["masters_dir"] = str(masters)
                result["requested_path"] = step.get("path") or str(masters / "Auto_Master.wav")
                self._record_step(op, **result)
                return bool(result.get("ok")) or bool(step.get("optional"))
            except Exception as e:
                self._record_step(op, ok=False, error=str(e))
                return bool(step.get("optional"))

        if op == "sleep":
            sec = float(step.get("seconds", step.get("sec", 0.5)))
            time.sleep(max(0.0, sec))
            self._record_step(op, ok=True, seconds=sec)
            return True

        if op == "ears_check":
            seconds = float(step.get("seconds") or 2.5)
            min_peak = float(step.get("min_peak_db", self.opts.get("min_peak_db", -45.0)))
            tag = step.get("tag") or "ears_check"
            # Optionally play first
            if step.get("play", True):
                try:
                    s1.play()
                except Exception:
                    pass
            audio = self._ears(tag, seconds)
            if step.get("play", True):
                try:
                    s1.stop()
                except Exception:
                    pass
            peak_db = float(audio.get("peak_db", -120))
            ok = bool(audio.get("has_signal")) and peak_db >= min_peak
            self._record_step(
                op,
                ok=ok,
                audio=audio,
                min_peak_db=min_peak,
                peak_db=peak_db,
            )
            return ok or bool(step.get("optional"))

        if op == "program_change":
            try:
                program = int(step.get("program", step.get("pc", 0)))
                channel = int(step.get("channel", 0))
                bridge = s1.remote.instrument.bridge
                import mido as _mido

                bridge.send(_mido.Message("program_change", channel=channel, program=program))
                self._record_step(op, ok=True, program=program, channel=channel)
                return True
            except Exception as e:
                self._record_step(op, ok=False, error=str(e))
                return bool(step.get("optional"))

        if op == "stream_record":
            return self._stream_record(step, focus_studio_one)

        self._fail(
            "job",
            "unknown_job_op",
            op=op,
            remediations=["Use only KNOWN_OPS from job_schema.py", "Re-plan job from producer"],
            next_action="fix_job_json",
            evidence={"op": op},
        )
        return False

    def _stream_record(self, step: Dict[str, Any], focus_studio_one) -> bool:
        s1 = self.s1
        # Resolve role name (drums/bass/…) via tracks.json before arm
        try:
            from s1_tools.tracks_map import resolve_track

            track = resolve_track(self.song, step.get("role") or step.get("track"))
        except Exception:
            track = int(step["track"])
        label = str(step.get("label") or f"T{track}")
        midi_field = step.get("midi") or ""
        midi = resolve_midi_path(self.song, midi_field)
        if midi is None:
            from s1_tools.failure_log import failure_midi_missing

            self._last_failure = failure_midi_missing(
                self.song, midi=str(midi_field), label=label, track=track
            )
            self._record_step(
                "stream_record",
                ok=False,
                error="midi_missing",
                midi=midi_field,
                failure=self._last_failure,
                primary_cause="midi_file_missing",
            )
            return False

        max_sec = step.get("max_sec", self.opts.get("max_sec"))
        if max_sec is not None:
            max_sec = float(max_sec)

        # Re-check UI before arm/stream — stop if New/Safety/wrong song
        try:
            from s1_tools.ui_gate import check_ui_available

            gate = check_ui_available(
                expected_song=self.song.name,
                eyes=self.eyes,
                auto_dismiss=True,
                song_dir=self.song,
                log_failure=True,
            )
            if not gate.available:
                self._record_step(
                    "stream_record",
                    ok=False,
                    error="ui_unavailable",
                    primary_cause="ui_unavailable",
                    label=label,
                    track=track,
                    ui_gate=gate.to_dict(),
                )
                self._last_failure = {
                    "ok": False,
                    "domain": "workspace",
                    "primary_cause": "ui_unavailable",
                    "causes": gate.reasons,
                    "next_action": "clear_blockers_stay_on_song",
                    "evidence": gate.to_dict(),
                }
                return False
        except Exception as e:
            log(f"  stream ui_gate warn: {e}")

        focus_studio_one()
        time.sleep(0.15)
        try:
            s1.stop()
            s1.remote.mcu.rewind()
        except Exception:
            pass
        time.sleep(GAP)

        user_armed = bool(self.opts.get("user_armed") or step.get("user_armed"))
        prefer_import = bool(self.opts.get("prefer_import") or step.get("prefer_import"))
        armed = False
        method = "stream"
        if prefer_import and not user_armed:
            log(f"  prefer_import: File import path for {label}")
            try:
                from import_and_verify_midi import import_one_file
                from s1remote.menus import open_menu_path
                from s1remote.hotkeys import focus_studio_one as _f

                ok_imp = import_one_file(midi, open_menu_path=open_menu_path, focus_studio_one=_f)
                after_i = self._shot(f"import_{label}")
                if ok_imp:
                    self._record_step(
                        "stream_record",
                        ok=True,
                        label=label,
                        track=track,
                        midi=str(midi),
                        method="import_fallback",
                        imported=True,
                        note_ons=0,
                        armed_confirmed=False,
                        clip_growth=None,
                        vision={"after": analyze_shot(after_i).to_dict() if after_i else {}},
                    )
                    return True
                log("  prefer_import returned false — fall through to live stream")
            except Exception as e:
                log(f"  import fallback fail ({e}) — try live stream")

        if user_armed:
            log("  user_armed: skip agent arm")
            armed = True
        else:
            allow_mouse = bool(self.opts.get("allow_mouse") or step.get("allow_mouse"))
            log(
                f"  arm_and_verify track={track} "
                f"(keyboard→MIDI only; mouse={'ON' if allow_mouse else 'OFF'})"
            )
            arm_diag: Dict[str, Any] = {}
            try:
                armed = s1.arm_and_verify(
                    track,
                    eyes_dir=self.eyes.directory,
                    retries=3,
                    allow_mouse=allow_mouse,
                    song_dir=self.song,
                )
                arm_diag = getattr(s1, "last_arm_result", None) or {}
            except Exception as e:
                log(f"  arm_and_verify error: {e}")
                armed = False
                arm_diag = {"ok": False, "error": str(e), "primary_cause": "exception"}
            if not armed:
                from s1_tools.eyes import scan_rec_red as _scan

                recheck = self._shot(f"arm_recheck_{label}")
                if _scan(recheck, track, allow_fallback=False):
                    log("  arm recheck: Rec red on target — proceed")
                    armed = True
                else:
                    # Record *why* so next run can fix root cause (not thrash)
                    primary = arm_diag.get("primary_cause") or "arm_failed"
                    next_act = arm_diag.get("next_action") or "inspect_arm_diagnosis_json"
                    log(f"  ARM FAILED — primary_cause={primary} next={next_act}")
                    for rem in (arm_diag.get("remediations") or [])[:4]:
                        log(f"  → {rem}")

                    # Optional import only after diagnosis is saved
                    if self.opts.get("import_on_arm_fail", True):
                        log("  after diagnosis: try import_midi (no mouse thrash)")
                        try:
                            from import_and_verify_midi import import_one_file
                            from s1remote.menus import open_menu_path
                            from s1remote.hotkeys import focus_studio_one as _f

                            ok_imp = import_one_file(
                                midi, open_menu_path=open_menu_path, focus_studio_one=_f
                            )
                            self._record_step(
                                "stream_record",
                                ok=bool(ok_imp),
                                label=label,
                                track=track,
                                midi=str(midi),
                                method="import_fallback",
                                imported=bool(ok_imp),
                                note_ons=0,
                                armed_confirmed=False,
                                arm_diagnosis=arm_diag,
                                error=None if ok_imp else f"arm_fail:{primary}",
                            )
                            return bool(ok_imp)
                        except Exception as e:
                            log(f"  import fallback error: {e}")

                    if not self.opts.get("no_prompt"):
                        try:
                            input(
                                f"  Arm failed ({primary}). "
                                "Arm target track with [R] manually, then Enter: "
                            )
                            armed = True
                        except EOFError:
                            self._record_step(
                                "stream_record",
                                ok=False,
                                error=f"arm_failed:{primary}",
                                track=track,
                                arm_diagnosis=arm_diag,
                            )
                            return False
                    else:
                        from s1_tools.failure_log import wrap_arm_diagnosis

                        if arm_diag and arm_diag.get("primary_cause"):
                            self._last_failure = wrap_arm_diagnosis(arm_diag, self.song)
                        else:
                            self._fail(
                                "arm",
                                primary,
                                op="stream_record",
                                remediations=arm_diag.get("remediations") if arm_diag else None,
                                next_action=next_act,
                                evidence={"arm_diagnosis": arm_diag},
                                track=track,
                                label=label,
                                record_step=False,
                            )
                        self._record_step(
                            "stream_record",
                            ok=False,
                            error=f"arm_failed:{primary}",
                            track=track,
                            label=label,
                            arm_diagnosis=arm_diag,
                            next_action=next_act,
                            primary_cause=primary,
                            failure=self._last_failure,
                        )
                        return False

        from s1_tools.eyes import lane_clip_growth, count_lane_clips, annotate_rec_hud, locate_track_rec_buttons

        pre = self._shot(f"before_{label}")
        pre_v = analyze_shot(pre)
        pre_lane = count_lane_clips(pre, track)
        s1.record()
        time.sleep(0.45)
        rec = self._shot(f"rec_{label}")
        rec_v = analyze_shot(rec)
        try:
            annotate_rec_hud(
                rec,
                locate_track_rec_buttons(rec) if rec else [],
                armed_row=track if rec_v.rec_red else None,
                label=f"REC {label} t{track}",
            )
        except Exception:
            pass

        # Cap long streams for efficiency unless step asks full
        stream_cap = max_sec
        if stream_cap is None and self.opts.get("probe_first", True):
            stream_cap = float(self.opts.get("probe_sec") or 15.0)
            log(f"  probe_first: stream cap {stream_cap}s (set options.probe_first=false for full)")

        n = stream_mid(s1, midi, label=label, eyes=self.eyes, max_sec=stream_cap)

        listen_sec = float(step.get("listen_sec") or min(3.0, stream_cap or 3.0))
        try:
            s1.stop()
        except Exception:
            pass
        time.sleep(0.25)
        # Live ears: play + capture; then null bus check after stop
        audio: Dict[str, Any]
        null_bus: Dict[str, Any] = {}
        try:
            s1.remote.mcu.rewind()
            s1.play()
            audio = self._ears(f"after_{label}", listen_sec)
            s1.stop()
            time.sleep(0.3)
            from s1_tools.ears import null_bus_check

            null_bus = null_bus_check(
                self.song / "_vision" / "ears",
                tag=f"null_{label}",
                enabled=not self.opts.get("no_ears"),
            )
        except Exception as e:
            audio = {"ok": False, "error": str(e)}

        after = self._shot(f"after_{label}")
        after_v = analyze_shot(after)
        growth = lane_clip_growth(pre, after, track)
        clip_growth = bool(growth.get("growth"))
        # Global blue fallback only if lane map failed
        if not clip_growth and (after_v.blue_pixel_hits or 0) > (pre_v.blue_pixel_hits or 0) + 120:
            clip_growth = True
            growth["global_blue_fallback"] = True

        # Success requires evidence: lane clips OR audio signal (not notes alone)
        ok = n > 0 and (clip_growth or bool(audio.get("has_signal")))
        if n > 0 and armed and (rec_v.rec_red or pre_v.rec_red) and not ok:
            method = "stream_attempted_no_clip"
            ok = False
        elif ok and clip_growth:
            method = "stream"
        elif ok and audio.get("has_signal"):
            method = "stream_audio_only"

        self._record_step(
            "stream_record",
            ok=ok,
            label=label,
            track=track,
            midi=str(midi),
            note_ons=n,
            armed_confirmed=bool(
                rec_v.rec_red
                or armed
            ),
            method=method,
            clip_growth=clip_growth,
            lane=growth,
            lane_blue_before=pre_lane,
            vision={
                "pre": pre_v.to_dict(),
                "rec": rec_v.to_dict(),
                "after": after_v.to_dict(),
            },
            audio=audio,
            null_bus=null_bus,
            live_shots=len(getattr(self.eyes, "last_live", []) or []),
        )
        log(
            f"  stream_record {label}: notes={n} lane {growth.get('before')}→{growth.get('after')} "
            f"growth={clip_growth} audio={audio.get('has_signal')} ok={ok}"
        )
        if not ok:
            from s1_tools.failure_log import failure_stream_no_evidence

            self._last_failure = failure_stream_no_evidence(
                self.song,
                note_ons=n,
                clip_growth=clip_growth,
                has_signal=bool(audio.get("has_signal")),
                arm_diagnosis=None,
                label=label,
                track=track,
                method=method,
                lane=growth,
            )
            # attach to last step if just recorded
            if self.step_results and self.step_results[-1].get("op") == "stream_record":
                self.step_results[-1]["failure"] = self._last_failure
                self.step_results[-1]["primary_cause"] = self._last_failure.get("primary_cause")
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
