"""Resolve s1-remote and song directories without machine-specific hardcoding."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def resolve_s1_remote(explicit: Path | str | None = None) -> Path:
    """
    Order:
      1) explicit argument
      2) env S1_REMOTE
      3) this file's repo root (…/s1-remote) when tools live under tools/s1_tools/
    """
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.is_dir():
            raise FileNotFoundError(f"S1_REMOTE not a directory: {p}")
        return p
    env = os.environ.get("S1_REMOTE", "").strip()
    if env:
        p = Path(env).expanduser().resolve()
        if not p.is_dir():
            raise FileNotFoundError(f"S1_REMOTE env not a directory: {p}")
        return p
    # tools/s1_tools/paths.py → parents[0]=s1_tools, [1]=tools, [2]=s1-remote
    here = Path(__file__).resolve()
    candidate = here.parents[2]
    if (candidate / "s1remote").is_dir():
        return candidate
    raise RuntimeError(
        "Cannot find s1-remote. Set env S1_REMOTE or pass --s1-remote."
    )


def ensure_s1remote_on_path(explicit: Path | str | None = None) -> Path:
    root = resolve_s1_remote(explicit)
    s = str(root)
    if s not in sys.path:
        sys.path.insert(0, s)
    return root


def resolve_song_dir(explicit: Path | str | None = None, *, required: bool = True) -> Path | None:
    """
    Song folder containing MIDI/, optional _vision/, NOTES.txt.
    Order: explicit → S1_SONG_DIR → STUDIO_ONE_SONG → None/raise.
    """
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.is_dir():
            raise FileNotFoundError(f"Song dir not found: {p}")
        return p
    for key in ("S1_SONG_DIR", "STUDIO_ONE_SONG"):
        env = os.environ.get(key, "").strip()
        if env:
            p = Path(env).expanduser().resolve()
            if not p.is_dir():
                raise FileNotFoundError(f"{key} not a directory: {p}")
            return p
    if required:
        raise SystemExit(
            "Song directory required. Pass --song-dir PATH or set S1_SONG_DIR."
        )
    return None


def default_eyes_dir(song_dir: Path | None) -> Path:
    if song_dir is not None:
        return song_dir / "_vision" / "arm_watch"
    return Path.cwd() / "_vision" / "arm_watch"


def default_log_path(song_dir: Path | None, name: str) -> Path:
    if song_dir is not None:
        d = song_dir / "_vision"
    else:
        d = Path.cwd() / "_vision"
    d.mkdir(parents=True, exist_ok=True)
    return d / name
