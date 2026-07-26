#!/usr/bin/env python3
"""Preflight: ports, S1 running, Template, required MIDI — hands only."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS.parent))

from s1_tools.paths import (  # noqa: E402
    default_template_song,
    ensure_s1remote_on_path,
    resolve_song_dir,
)
from s1_tools.logutil import log  # noqa: E402


def run_checks(
    s1_remote: Path | None = None,
    song_dir: Path | None = None,
    *,
    connect: bool = True,
    require_files: list[str] | None = None,
) -> dict:
    ensure_s1remote_on_path(s1_remote)
    from s1remote.hotkeys import studio_one_running
    from s1remote.full_control import FullControl

    report: dict = {
        "ready": True,
        "checks": {},
        "failures": [],
    }

    running = studio_one_running()
    report["checks"]["studio_one_running"] = running
    if not running:
        report["ready"] = False
        report["failures"].append("Studio One not running")

    tpl = default_template_song()
    report["checks"]["template_exists"] = tpl.is_file()
    report["checks"]["template_path"] = str(tpl)
    if not tpl.is_file():
        report["ready"] = False
        report["failures"].append(f"Template missing: {tpl}")

    if song_dir is not None:
        song = Path(song_dir)
        report["checks"]["song_dir"] = str(song)
        midi = song / "MIDI"
        report["checks"]["midi_dir"] = midi.is_dir()
        if require_files:
            missing = []
            for rel in require_files:
                p = song / rel
                p2 = song / "MIDI" / Path(rel).name
                if not p.is_file() and not p2.is_file():
                    missing.append(rel)
            report["checks"]["required_files_missing"] = missing
            if missing:
                report["ready"] = False
                report["failures"].append(f"missing MIDI: {missing}")

    if connect and running:
        try:
            with FullControl() as s1:
                st = s1.status()
            report["checks"]["status"] = {
                k: st.get(k)
                for k in (
                    "midi_connected",
                    "instrument_midi_connected",
                    "instrument_midi_out",
                )
            }
            if not st.get("instrument_midi_connected"):
                report["ready"] = False
                report["failures"].append("S1 Notes instrument port not connected")
        except Exception as e:
            report["ready"] = False
            report["failures"].append(f"FullControl connect: {e}")
            report["checks"]["connect_error"] = str(e)

    return report


def print_report(report: dict) -> None:
    log(f"setup_check ready={report.get('ready')}")
    for k, v in (report.get("checks") or {}).items():
        log(f"  {k}: {v}")
    for f in report.get("failures") or []:
        log(f"  FAIL: {f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--song-dir", type=Path, default=None)
    ap.add_argument("--no-connect", action="store_true")
    args = ap.parse_args()
    song = None
    try:
        if args.song_dir or __import__("os").environ.get("S1_SONG_DIR"):
            song = resolve_song_dir(args.song_dir)
    except Exception:
        song = args.song_dir
    report = run_checks(song_dir=song, connect=not args.no_connect)
    print_report(report)
    print(json.dumps(report, indent=2))
    return 0 if report.get("ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
