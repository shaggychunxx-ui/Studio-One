"""
Studio One execution job schema.

Music-producer writes s1_jobs/current.json.
This module validates + documents ops. Creative gates stay in producer.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

JOB_VERSION = 1

KNOWN_OPS: Set[str] = {
    "check_setup",
    "ensure_workspace",
    "create_tracks",
    "browser_load",
    "stream_record",
    "import_midi",
    "play_listen",
    "save",
    "report",
    "shot",
    "rewind",
    "stop",
}

REQUIRED_TOP = ("version", "id", "steps")


def validate_job(job: Dict[str, Any]) -> List[str]:
    """Return list of validation errors (empty = ok)."""
    errs: List[str] = []
    if not isinstance(job, dict):
        return ["job must be a JSON object"]
    for k in REQUIRED_TOP:
        if k not in job:
            errs.append(f"missing field: {k}")
    ver = job.get("version")
    if ver is not None and int(ver) != JOB_VERSION:
        errs.append(f"unsupported version {ver} (want {JOB_VERSION})")
    steps = job.get("steps")
    if not isinstance(steps, list) or not steps:
        errs.append("steps must be a non-empty list")
        return errs
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            errs.append(f"step[{i}] not an object")
            continue
        op = step.get("op")
        if not op:
            errs.append(f"step[{i}] missing op")
        elif op not in KNOWN_OPS:
            errs.append(f"step[{i}] unknown op: {op!r}")
        if op == "stream_record":
            if not step.get("midi"):
                errs.append(f"step[{i}] stream_record needs midi")
            if step.get("track") is None:
                errs.append(f"step[{i}] stream_record needs track (1-based)")
        if op == "create_tracks" and step.get("count") is not None:
            try:
                if int(step["count"]) < 1:
                    errs.append(f"step[{i}] create_tracks count must be >= 1")
            except (TypeError, ValueError):
                errs.append(f"step[{i}] create_tracks count invalid")
        if op == "play_listen" and step.get("seconds") is not None:
            try:
                float(step["seconds"])
            except (TypeError, ValueError):
                errs.append(f"step[{i}] play_listen seconds invalid")
    return errs


def normalize_options(job: Dict[str, Any]) -> Dict[str, Any]:
    opts = dict(job.get("options") or {})
    defaults = {
        "user_armed": False,
        "no_prompt": False,
        "no_eyes": False,
        "no_ears": False,
        "max_sec": None,
        "save_after": True,
        "listen_sec": 4.0,
    }
    for k, v in defaults.items():
        opts.setdefault(k, v)
    return opts


def resolve_midi_path(song_dir, midi_field: str):
    from pathlib import Path

    song = Path(song_dir)
    rel = Path(midi_field)
    candidates = [
        song / rel,
        song / "MIDI" / rel.name,
        Path(midi_field),
    ]
    for c in candidates:
        if c.is_file():
            return c.resolve()
    return None
