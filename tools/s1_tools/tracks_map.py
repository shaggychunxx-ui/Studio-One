"""
Stable track registry for a song — names → 1-based arrange track numbers.

Written at Template → Save As (defaults) and optionally refined by vision.
All jobs should resolve ``drums`` / ``bass`` / … via this file, not magic indices.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

# Default map matching standing Template instrument order (Impact first).
DEFAULT_TRACKS: Dict[str, int] = {
    "drums": 1,
    "drums2": 2,
    "lead": 3,
    "color": 4,
    "bass": 5,
    "bass2": 6,
    "bed": 7,
    "bed2": 8,
    "sample": 9,
}

ROLE_MIDI = {
    "drums": "drums.mid",
    "bass": "bass.mid",
    "lead": "lead.mid",
    "color": "color.mid",
    "bed": "bed.mid",
}


def tracks_path(song_dir: Path) -> Path:
    return Path(song_dir) / "tracks.json"


def load_tracks(song_dir: Path) -> Dict[str, Any]:
    p = tracks_path(song_dir)
    if p.is_file():
        data = json.loads(p.read_text(encoding="utf-8-sig"))
        if isinstance(data, dict) and "roles" in data:
            return data
        if isinstance(data, dict):
            return {"roles": data, "source": "legacy"}
    return {
        "roles": dict(DEFAULT_TRACKS),
        "source": "default_template",
        "midi": dict(ROLE_MIDI),
    }


def save_tracks(song_dir: Path, data: Dict[str, Any]) -> Path:
    p = tracks_path(song_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return p


def ensure_default_tracks(song_dir: Path) -> Dict[str, Any]:
    p = tracks_path(song_dir)
    if p.is_file():
        return load_tracks(song_dir)
    data = {
        "roles": dict(DEFAULT_TRACKS),
        "midi": dict(ROLE_MIDI),
        "source": "template_default",
        "note": "1-based arrange indices for standing Template; refine after Save As if needed",
    }
    save_tracks(song_dir, data)
    return data


def resolve_track(song_dir: Path, role_or_number: Any) -> int:
    """Accept int track, or role name string (drums/bass/lead/…)."""
    if isinstance(role_or_number, int):
        return max(1, role_or_number)
    if isinstance(role_or_number, float):
        return max(1, int(role_or_number))
    s = str(role_or_number).strip().lower()
    if s.isdigit():
        return max(1, int(s))
    roles = load_tracks(song_dir).get("roles") or DEFAULT_TRACKS
    if s in roles:
        return int(roles[s])
    # aliases
    aliases = {"kick": "drums", "groove": "drums", "pad": "bed", "synth": "lead"}
    if s in aliases and aliases[s] in roles:
        return int(roles[aliases[s]])
    raise KeyError(f"Unknown track role {role_or_number!r}; known={list(roles)}")
