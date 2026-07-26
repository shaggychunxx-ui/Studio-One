#!/usr/bin/env python3
"""
Original studio-quality track with crash watchdog + visual eyes.

Policy:
  1) Template → Save As new song
  2) Compose 32-bar professional MIDI
  3) Produce parts one-at-a-time with live eyes
  4) Crash monitor: process death + new .dmp files
  5) Screenshot + analyze before/after every major step

Usage:
  set PYTHONPATH=%CD%;%CD%\\tools
  py -3.12 tools/produce_original_watched.py --name Velvet_Circuit
"""

from __future__ import annotations

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

from s1remote.hotkeys import focus_studio_one, studio_one_running  # noqa: E402
from s1_tools.eyes import Eyes, is_studio_one_arrange_shot, check_display_dpi  # noqa: E402
from s1_tools.vision import analyze_shot, detect_safety_dialog_uia, dismiss_safety_dialog  # noqa: E402
from s1_tools.logutil import log, set_log_file  # noqa: E402

EXE = Path(r"C:\Program Files\PreSonus\Studio One 6\Studio One.exe")
DUMP_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "PreSonus"
DEFAULT_PARTS = "drums,bass,lead,bed,color"


class CrashWatch:
    """Background monitor: S1 process death + new crash dumps."""

    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.events: list[dict] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._known_dumps = self._list_dumps()
        self._was_running = studio_one_running()
        self.crash_count = 0

    def _list_dumps(self) -> set[str]:
        out: set[str] = set()
        if not DUMP_DIR.is_dir():
            return out
        try:
            for p in DUMP_DIR.glob("Studio One*.dmp"):
                out.add(p.name)
        except Exception:
            pass
        return out

    def _emit(self, kind: str, detail: str) -> None:
        ev = {
            "t": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "kind": kind,
            "detail": detail,
        }
        self.events.append(ev)
        line = f"[CRASHWATCH] {kind}: {detail}"
        log(line)
        try:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def _loop(self) -> None:
        while not self._stop.wait(1.5):
            running = studio_one_running()
            if self._was_running and not running:
                self.crash_count += 1
                self._emit("PROCESS_DIED", f"Studio One exited (count={self.crash_count})")
            elif not self._was_running and running:
                self._emit("PROCESS_ALIVE", "Studio One is running again")
            self._was_running = running

            dumps = self._list_dumps()
            new = dumps - self._known_dumps
            if new:
                for name in sorted(new):
                    self._emit("NEW_DUMP", name)
                    self.crash_count += 1
                self._known_dumps = dumps

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="s1-crash-watch", daemon=True)
        self._thread.start()
        self._emit("START", f"watching process + dumps in {DUMP_DIR}")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3.0)
        self._emit("STOP", f"events={len(self.events)} crash_count={self.crash_count}")

    def ok(self) -> bool:
        return self.crash_count == 0


def titles() -> list[str]:
    from pywinauto import Desktop

    out: list[str] = []
    for backend in ("uia", "win32"):
        try:
            for w in Desktop(backend=backend).windows():
                try:
                    t = (w.window_text() or "").strip()
                except Exception:
                    continue
                if not t:
                    continue
                low = t.lower()
                if any(s in low for s in ("grok", "connect studio one", "powershell", "windows terminal")):
                    continue
                if any(k in low for k in ("studio one", "safety", "save as", "save", "template")):
                    if t not in out:
                        out.append(t)
        except Exception:
            pass
    return out


def visual_status(eyes: Eyes, tag: str, hud: str) -> dict:
    """Grab shot, analyze, log human-readable status."""
    if detect_safety_dialog_uia():
        log(f"  [{tag}] Safety dialog — dismissing")
        dismiss_safety_dialog()
        time.sleep(1.0)
    if studio_one_running():
        focus_studio_one()
        time.sleep(0.2)
    path = eyes.shot(tag, annotate=True, hud=hud)
    running = studio_one_running()
    ts = titles()
    arr = bool(path and is_studio_one_arrange_shot(path))
    blue = luma = rec = None
    if path:
        v = analyze_shot(path)
        blue = getattr(v, "blue_pixel_hits", None)
        luma = round(getattr(v, "mean_luma", 0) or 0, 1)
        rec = getattr(v, "rec_red", None)
    status = {
        "tag": tag,
        "shot": str(path) if path else None,
        "running": running,
        "titles": ts,
        "arrange": arr,
        "blue_pixels": blue,
        "luma": luma,
        "rec_red": rec,
        "hud": hud,
    }
    log(
        f"  👁 [{tag}] run={running} arrange={arr} rec={rec} "
        f"blue={blue} luma={luma} titles={ts[:3]}"
    )
    return status


def wait_ready(eyes: Eyes, name_hint: str | None, timeout: float = 180.0) -> bool:
    deadline = time.time() + timeout
    i = 0
    while time.time() < deadline:
        if not studio_one_running():
            log(f"  wait[{i}]: S1 not running")
            visual_status(eyes, f"wait_dead_{i:02d}", f"DEAD wait {i}")
            time.sleep(2.0)
            i += 1
            continue
        st = visual_status(eyes, f"wait_{i:02d}", f"wait ready {i}")
        if st["arrange"] and any(
            (name_hint and name_hint.lower() in t.lower())
            or t.startswith("Studio One -")
            or "Template" in t
            for t in st["titles"]
        ):
            # settle one more frame
            time.sleep(2.5)
            if detect_safety_dialog_uia():
                dismiss_safety_dialog()
            visual_status(eyes, "ready", f"READY {name_hint or 'song'}")
            return True
        i += 1
        time.sleep(2.5)
    return False


def ensure_running_or_fail(watch: CrashWatch, eyes: Eyes, tag: str) -> bool:
    if studio_one_running():
        return True
    visual_status(eyes, f"crash_{tag}", f"CRASH at {tag}")
    log(f"FATAL: Studio One not running at step '{tag}' (crashes={watch.crash_count})")
    return False


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="Velvet_Circuit", help="New song name")
    ap.add_argument("--parts", default=DEFAULT_PARTS)
    ap.add_argument("--max-sec", type=float, default=22.0)
    ap.add_argument("--prefer-import", action="store_true", default=True)
    ap.add_argument("--resume-dir", type=Path, default=None, help="Skip template; use existing song")
    ap.add_argument("--seed", type=int, default=250726)
    args = ap.parse_args()

    song_name = args.name
    # Vision root before song exists — use temp then migrate
    pre_vis = ROOT / "_vision_runs" / f"{song_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    pre_vis.mkdir(parents=True, exist_ok=True)
    set_log_file(pre_vis / "watched_produce.log")
    check_display_dpi()

    watch = CrashWatch(pre_vis / "crash_watch.log")
    watch.start()
    eyes = Eyes(pre_vis, live=True)
    timeline: list[dict] = []

    def note(step: str, **extra):
        st = visual_status(eyes, step, step.replace("_", " ")[:70])
        st["step"] = step
        st["crashes"] = watch.crash_count
        st.update(extra)
        timeline.append(st)
        return st

    result: dict = {
        "ok": False,
        "song_name": song_name,
        "started": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    try:
        note("00_start", msg="begin original watched produce")

        # --- 1) Template → Save As ---
        if args.resume_dir:
            song = Path(args.resume_dir)
            log(f"RESUME song={song}")
            if not studio_one_running():
                song_file = song / f"{song.name}.song"
                if song_file.is_file():
                    subprocess.Popen([str(EXE), str(song_file)])
                    time.sleep(5)
            if not wait_ready(eyes, song.name, 180):
                result["error"] = "resume_ui_not_ready"
                return 3
        else:
            log(f"=== TEMPLATE → Save As '{song_name}' ===")
            from start_from_template import start_new_song_from_template

            note("01_before_template")
            summary = start_new_song_from_template(name=song_name)
            timeline.append({"step": "template_summary", **summary})
            if not summary.get("ok"):
                note("01_template_fail", error=summary.get("error"))
                result["error"] = "template_start_failed"
                result["template"] = summary
                return 2
            song = Path(summary["song_dir"])
            log(f"  new song: {song}")
            note("02_after_template", song_dir=str(song))

        # Move eyes into song vision folder for permanence
        vis = song / "_vision" / "watched"
        vis.mkdir(parents=True, exist_ok=True)
        eyes.directory = vis
        set_log_file(vis / "watched_produce.log")
        # keep crash log too
        try:
            (vis / "crash_watch.log").write_text(
                (pre_vis / "crash_watch.log").read_text(encoding="utf-8", errors="ignore"),
                encoding="utf-8",
            )
        except Exception:
            pass

        if not ensure_running_or_fail(watch, eyes, "post_template"):
            result["error"] = "crash_after_template"
            result["crashes"] = watch.events
            return 4

        # --- 2) Compose professional MIDI ---
        log("=== COMPOSE professional 32-bar MIDI ===")
        note("10_before_compose")
        from compose_professional import main as compose_main

        old_argv = sys.argv
        sys.argv = [
            "compose_professional.py",
            "--song-dir",
            str(song),
            "--seed",
            str(args.seed),
        ]
        try:
            crc = compose_main()
        finally:
            sys.argv = old_argv
        if crc != 0:
            note("10_compose_fail", rc=crc)
            result["error"] = "compose_failed"
            return 5
        midi_files = sorted((song / "MIDI").glob("*.mid"))
        note("11_after_compose", midi=[p.name for p in midi_files], seed=args.seed)

        if not ensure_running_or_fail(watch, eyes, "post_compose"):
            result["error"] = "crash_after_compose"
            return 4

        # --- 3) Produce parts ---
        log(f"=== PRODUCE parts={args.parts} max_sec={args.max_sec} ===")
        note("20_before_produce", parts=args.parts)
        from produce import main as produce_main

        argv = [
            "produce.py",
            "--resume",
            "--song-dir",
            str(song),
            "--parts",
            args.parts,
            "--max-sec",
            str(args.max_sec),
        ]
        if args.prefer_import:
            argv.append("--prefer-import")
        sys.argv = argv
        try:
            # Mid-produce eyes snapshot
            note("21_produce_start")
            prc = produce_main()
        finally:
            sys.argv = old_argv

        if not studio_one_running():
            note("22_crash_during_produce")
            result["error"] = "crash_during_produce"
            result["produce_rc"] = prc
            result["crashes"] = watch.events
            return 4

        note("22_after_produce", produce_rc=prc)

        # Load produce result if present
        pr_path = song / "s1_jobs" / "produce_result.json"
        produce_result = None
        if pr_path.is_file():
            try:
                produce_result = json.loads(pr_path.read_text(encoding="utf-8"))
            except Exception:
                produce_result = None

        # --- 4) Final visual verify ---
        focus_studio_one()
        time.sleep(0.4)
        final = note("99_final", produce_rc=prc)

        result.update(
            {
                "ok": prc == 0 and watch.ok(),
                "song_dir": str(song),
                "song_file": str(song / f"{song.name}.song"),
                "produce_rc": prc,
                "produce_result": produce_result,
                "crash_count": watch.crash_count,
                "crash_events": watch.events,
                "vision_dir": str(vis),
                "final_shot": final.get("shot"),
                "timeline_steps": [t.get("step") for t in timeline],
                "finished": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
        out_path = song / "s1_jobs" / "watched_result.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        (vis / "timeline.json").write_text(json.dumps(timeline, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1

    except Exception as e:
        log(f"FATAL exception: {e}")
        try:
            note("xx_exception", error=str(e))
        except Exception:
            pass
        result["error"] = str(e)
        result["crashes"] = watch.events
        print(json.dumps(result, indent=2))
        return 9
    finally:
        watch.stop()


if __name__ == "__main__":
    raise SystemExit(main())
