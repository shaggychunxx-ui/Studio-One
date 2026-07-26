#!/usr/bin/env python3
"""
Zero-human entry: Template → Save As → compose MIDI → produce parts → mix → export intent.

Usage:
  set PYTHONPATH=%CD%;%CD%\\tools
  py -3.12 tools\\autonomous_run.py --name AutoSong --parts drums,bass,lead --max-sec 40
  py -3.12 tools\\autonomous_run.py --resume --song-dir PATH --prefer-import

Does not lock Music-producer artistic gates. Writes produce_result + autonomy_result.json.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TOOLS))

from s1_tools.logutil import log, set_log_file  # noqa: E402
from s1_tools.paths import ensure_s1remote_on_path, resolve_song_dir  # noqa: E402
from s1_tools.tracks_map import ensure_default_tracks  # noqa: E402
from s1_tools.state import set_state  # noqa: E402


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class CrashWatch:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.crash_count = 0

    def start(self) -> None:
        from s1remote.hotkeys import studio_one_running

        self._was = studio_one_running()

        def loop() -> None:
            from s1remote.hotkeys import studio_one_running

            dump_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "PreSonus"
            known = set()
            if dump_dir.is_dir():
                known = {p.name for p in dump_dir.glob("Studio One*.dmp")}
            while not self._stop.wait(2.0):
                running = studio_one_running()
                if self._was and not running:
                    self.crash_count += 1
                    self.events.append({"t": _utc(), "kind": "process_exit", "detail": "S1 stopped"})
                    log("[CRASHWATCH] Studio One process exited")
                self._was = running
                if dump_dir.is_dir():
                    now = {p.name for p in dump_dir.glob("Studio One*.dmp")}
                    for n in now - known:
                        self.crash_count += 1
                        self.events.append({"t": _utc(), "kind": "dump", "detail": n})
                        log(f"[CRASHWATCH] new dump {n}")
                    known = now

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)


def compose_if_needed(song: Path, *, seed: int | None, force: bool) -> dict:
    midi_dir = song / "MIDI"
    midi_dir.mkdir(parents=True, exist_ok=True)
    need = ["drums.mid", "bass.mid", "lead.mid", "bed.mid", "color.mid"]
    missing = [n for n in need if not (midi_dir / n).is_file()]
    if not missing and not force:
        return {"ok": True, "skipped": True, "have": need}
    cmd = [sys.executable, str(TOOLS / "compose_professional.py"), "--song-dir", str(song)]
    if seed is not None:
        cmd.extend(["--seed", str(seed)])
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + str(TOOLS) + os.pathsep + env.get("PYTHONPATH", "")
    env["S1_SONG_DIR"] = str(song)
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=str(ROOT))
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-1500:],
        "stderr_tail": (proc.stderr or "")[-800:],
        "missing_before": missing,
    }


def run_produce(song: Path, parts: str, max_sec: float, prefer_import: bool) -> dict:
    from produce import main as produce_main  # type: ignore

    argv = ["--resume", "--song-dir", str(song), "--parts", parts, "--max-sec", str(max_sec)]
    if prefer_import:
        argv.append("--prefer-import")
    # produce.main uses argparse of sys.argv — call subprocess for isolation
    cmd = [sys.executable, str(TOOLS / "produce.py")] + argv
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + str(TOOLS) + os.pathsep + env.get("PYTHONPATH", "")
    env["S1_SONG_DIR"] = str(song)
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=str(ROOT))
    result_path = song / "s1_jobs" / "produce_result.json"
    body = {}
    if result_path.is_file():
        try:
            body = json.loads(result_path.read_text(encoding="utf-8"))
        except Exception:
            body = {}
    return {
        "ok": proc.returncode == 0 and body.get("ok", False),
        "returncode": proc.returncode,
        "produce_result": body,
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-1000:],
    }


def run_mix_export(song: Path) -> dict:
    """One job: mix_balance + play_listen ears + export_mixdown intent."""
    from execute_job import JobRunner, load_job, write_result  # noqa: F401

    job = {
        "version": 1,
        "id": f"mix-export-{_utc().replace(':', '')}",
        "source": "autonomous_run",
        "options": {"no_prompt": True, "save_after": True, "no_ears": False},
        "steps": [
            {"op": "check_setup"},
            {"op": "ensure_workspace"},
            {"op": "mix_balance", "preset": "full_static"},
            {"op": "play_listen", "seconds": 4.0},
            {"op": "ears_check", "seconds": 2.5, "min_peak_db": -50.0, "optional": True},
            {"op": "export_mixdown", "optional": True},
            {"op": "save"},
            {"op": "report", "message": "autonomous mix+export pass done"},
        ],
    }
    path = song / "s1_jobs" / "current.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(job, indent=2), encoding="utf-8")
    runner = JobRunner(song, job, dry_run=False, no_prompt=True)
    result = runner.run()
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Full unattended Studio One produce pipeline")
    ap.add_argument("--name", default=None)
    ap.add_argument("--song-dir", type=Path, default=None)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--parts", default="drums,bass,lead,bed,color")
    ap.add_argument("--max-sec", type=float, default=40.0)
    ap.add_argument("--prefer-import", action="store_true")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--recompose", action="store_true")
    ap.add_argument("--skip-mix", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="Template+compose only; no stream")
    args = ap.parse_args()

    ensure_s1remote_on_path()
    out: dict = {"started_at": _utc(), "phases": []}

    if args.resume or args.song_dir or (os.environ.get("S1_SONG_DIR") and not args.name):
        song = resolve_song_dir(args.song_dir)
        out["phases"].append({"stage": "resume", "song_dir": str(song)})
    else:
        from start_from_template import start_new_song_from_template

        summary = start_new_song_from_template(name=args.name)
        out["phases"].append({"stage": "template", "data": summary})
        if not summary.get("ok"):
            print(json.dumps({**out, "ok": False}, indent=2))
            return 2
        song = Path(summary["song_dir"])

    vision = song / "_vision" / "autonomy"
    vision.mkdir(parents=True, exist_ok=True)
    set_log_file(vision / "autonomous_run.log")
    ensure_default_tracks(song)
    set_state(song, "autonomous_run", note="started")

    watch = CrashWatch()
    watch.start()
    try:
        comp = compose_if_needed(song, seed=args.seed, force=args.recompose)
        out["phases"].append({"stage": "compose", "data": comp})
        if not comp.get("ok"):
            out["ok"] = False
            out["error"] = "compose_failed"
            _write_out(song, out, watch)
            return 3

        if args.dry_run:
            out["ok"] = True
            out["dry_run"] = True
            _write_out(song, out, watch)
            print(json.dumps(out, indent=2))
            return 0

        produce = run_produce(song, args.parts, args.max_sec, args.prefer_import)
        out["phases"].append({"stage": "produce", "data": produce})

        # One retry if failed and crash not the cause
        if not produce.get("ok") and watch.crash_count == 0:
            log("  autonomy: produce failed — single retry with prefer_import")
            produce2 = run_produce(song, args.parts, args.max_sec, prefer_import=True)
            out["phases"].append({"stage": "produce_retry_import", "data": produce2})
            produce = produce2

        if not args.skip_mix and produce.get("ok"):
            try:
                mix = run_mix_export(song)
                out["phases"].append({"stage": "mix_export", "data": {
                    "ok": mix.get("ok"),
                    "job_id": mix.get("job_id"),
                    "steps": [
                        {"op": s.get("op"), "ok": s.get("ok")}
                        for s in (mix.get("steps") or [])
                    ],
                }})
            except Exception as e:
                out["phases"].append({"stage": "mix_export", "error": str(e)})

        out["ok"] = bool(produce.get("ok"))
        out["song_dir"] = str(song)
        out["crash_events"] = watch.events
        set_state(song, "autonomous_done" if out["ok"] else "autonomous_failed", note=f"ok={out['ok']}")
        _write_out(song, out, watch)
        print(json.dumps(out, indent=2))
        return 0 if out["ok"] else 1
    finally:
        watch.stop()


def _write_out(song: Path, out: dict, watch: CrashWatch) -> None:
    out["finished_at"] = _utc()
    out["crash_count"] = watch.crash_count
    path = song / "s1_jobs" / "autonomy_result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    log(f"autonomy_result → {path}")


if __name__ == "__main__":
    raise SystemExit(main())
