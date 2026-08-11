#!/usr/bin/env python3
"""
Single orchestrator: Template → Save As → plan-sized jobs → execute → observe cues.

Human-like hands, live eyes/ears, no thrash, one part at a time by default.

Usage:
  set PYTHONPATH=%CD%;%CD%\\tools
  py -3.12 tools/produce.py --name MySong --parts drums,bass --max-sec 15
  py -3.12 tools/produce.py --resume --song-dir PATH --parts lead
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS.parent))
sys.path.insert(0, str(TOOLS))

from s1_tools.paths import ensure_s1remote_on_path, resolve_song_dir  # noqa: E402
from s1_tools.logutil import log, set_log_file  # noqa: E402
from s1_tools.tracks_map import ensure_default_tracks, load_tracks, ROLE_MIDI  # noqa: E402
from s1_tools.state import set_state, load_state  # noqa: E402


def _write_one_part_job(
    song: Path,
    role: str,
    track: int,
    midi_name: str,
    max_sec: float,
    *,
    prefer_import: bool = False,
    allow_mouse: bool = False,
) -> Path:
    job = {
        "version": 1,
        "id": f"produce_{role}_{datetime.now(timezone.utc).strftime('%H%M%S')}",
        "source": "produce.py",
        "options": {
            "no_prompt": True,
            "probe_first": True,
            "probe_sec": max_sec,
            "import_on_arm_fail": True,
            "prefer_import": bool(prefer_import),
            # Vision Rec click as last arm attempt when keyboard select fails
            "allow_mouse": bool(allow_mouse),
            "save_after": True,
        },
        "steps": [
            {"op": "check_setup"},
            {"op": "ensure_workspace"},
            {
                "op": "stream_record",
                "label": role.upper(),
                "role": role,
                "track": track,
                "midi": midi_name,
                "max_sec": max_sec,
                "listen_sec": 3.0,
            },
            {"op": "save"},
            {"op": "report"},
        ],
    }
    path = song / "s1_jobs" / "current.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(job, indent=2), encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description="Orchestrate production: template → parts → live verify")
    ap.add_argument("--name", default=None, help="New song name (from Template)")
    ap.add_argument("--song-dir", type=Path, default=None, help="Resume existing song")
    ap.add_argument("--resume", action="store_true", help="Skip Template; use --song-dir or S1_SONG_DIR")
    ap.add_argument(
        "--parts",
        default="drums,bass",
        help="Comma roles: drums,bass,lead,color,bed (one job each)",
    )
    ap.add_argument("--max-sec", type=float, default=15.0, help="Per-part stream probe cap")
    ap.add_argument("--prefer-import", action="store_true", help="Import MIDI instead of live arm")
    ap.add_argument(
        "--allow-mouse",
        action="store_true",
        help="Allow one vision Rec click after keyboard/MCU arm fail",
    )
    args = ap.parse_args()

    ensure_s1remote_on_path()

    if args.resume or args.song_dir or (
        os.environ.get("S1_SONG_DIR") and not args.name
    ):
        song = resolve_song_dir(args.song_dir)
        log(f"RESUME production song={song}")
    else:
        from start_from_template import start_new_song_from_template

        summary = start_new_song_from_template(name=args.name)
        if not summary.get("ok"):
            print(json.dumps(summary, indent=2))
            return 2
        song = Path(summary["song_dir"])
        log(f"NEW song from template: {song}")

    vision = song / "_vision" / "produce"
    vision.mkdir(parents=True, exist_ok=True)
    set_log_file(vision / "produce.log")

    tracks = ensure_default_tracks(song)
    roles_map = tracks.get("roles") or {}
    midi_map = tracks.get("midi") or ROLE_MIDI

    parts = [p.strip().lower() for p in args.parts.split(",") if p.strip()]
    if not parts:
        log("FATAL: no parts")
        return 2

    set_state(song, "pocket_streaming", note=f"parts={parts}")

    # Ensure minimal MIDI exists (tiny silence-proof stubs if missing — live_make compose better)
    midi_dir = song / "MIDI"
    midi_dir.mkdir(exist_ok=True)

    from execute_job import JobRunner, load_job
    from s1remote.hotkeys import studio_one_running

    if not studio_one_running():
        log("FATAL: Studio One not running after template start")
        return 3

    results = []
    for role in parts:
        track = int(roles_map.get(role, 0) or 0)
        if track < 1:
            log(f"  SKIP {role}: no track mapping")
            try:
                from s1_tools.failure_log import record_failure

                rec = record_failure(
                    song,
                    domain="produce",
                    primary_cause="track_role_unmapped",
                    remediations=[
                        f"Add \"{role}\" to tracks.json roles",
                        "Default Template map: drums=1 bass=5 lead=3 bed=7",
                    ],
                    next_action="fix_tracks_json",
                    evidence={"role": role, "roles": roles_map},
                    also_named="produce_failure",
                )
            except Exception:
                rec = None
            results.append(
                {"role": role, "ok": False, "error": "no_track_map", "failure": rec}
            )
            continue
        midi_name = midi_map.get(role) or f"{role}.mid"
        midi_path = midi_dir / midi_name
        if not midi_path.is_file():
            log(f"  SKIP {role}: missing {midi_path} — compose MIDI first")
            try:
                from s1_tools.failure_log import record_failure

                rec = record_failure(
                    song,
                    domain="produce",
                    primary_cause="missing_part_midi",
                    remediations=[
                        f"Add {midi_name} under MIDI/",
                        "Run live_make_song compose or producer MIDI export",
                    ],
                    next_action="add_midi_files",
                    evidence={"role": role, "midi": str(midi_path)},
                    context={"role": role, "track": track},
                    also_named="produce_failure",
                )
            except Exception:
                rec = None
            results.append(
                {
                    "role": role,
                    "ok": False,
                    "error": "missing_midi",
                    "primary_cause": "missing_part_midi",
                    "failure": rec,
                }
            )
            continue

        log(f"######## PART {role} → track {track} (live eyes/ears, no thrash) ########")
        # Default allow_mouse when prefer_import: arm path still used if import
        # dialog fails; vision Rec click is last non-thrash attempt.
        allow_mouse = bool(args.allow_mouse or args.prefer_import)
        job_path = _write_one_part_job(
            song,
            role,
            track,
            midi_name,
            args.max_sec,
            prefer_import=bool(args.prefer_import),
            allow_mouse=allow_mouse,
        )
        job = load_job(job_path)
        runner = JobRunner(song, job, dry_run=False, force_max_sec=args.max_sec, no_prompt=True)
        result = runner.run()
        ok = bool(result.get("ok"))
        results.append(
            {
                "role": role,
                "track": track,
                "ok": ok,
                "job_id": result.get("job_id"),
                "steps": [
                    {
                        "op": s.get("op"),
                        "ok": s.get("ok"),
                        "clip_growth": s.get("clip_growth"),
                        "note_ons": s.get("note_ons"),
                        "method": s.get("method"),
                        "lane": s.get("lane"),
                    }
                    for s in (result.get("steps") or [])
                    if s.get("op") == "stream_record"
                ],
            }
        )
        # Human-like pause between parts
        time.sleep(0.8)

    n_ok = sum(1 for r in results if r.get("ok"))
    if n_ok >= 1 and "drums" in parts and "bass" in parts:
        # Do not auto-lock pocket — only mark streaming done
        set_state(song, "pocket_streaming", note=f"finished parts ok={n_ok}/{len(parts)}")
    out = {
        "ok": n_ok >= max(1, len(parts) // 2),
        "song_dir": str(song),
        "state": load_state(song),
        "parts": results,
        "n_ok": n_ok,
        "finished_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "policy": "one_part_per_job, live eyes 2.5s, human arm max 3, import on arm fail",
    }
    (song / "s1_jobs" / "produce_result.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
