"""
Song production state machine on disk (s1_jobs/state.json).

States:
  none → template_saved → tracks_ready → pocket_streaming → pocket_locked
       → lead_streaming → lead_locked → form_building → done
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

STATES = (
    "none",
    "template_saved",
    "tracks_ready",
    "pocket_streaming",
    "pocket_locked",
    "lead_streaming",
    "lead_locked",
    "form_building",
    "done",
    # autonomy pipeline (autonomous_run.py)
    "autonomous_run",
    "autonomous_done",
    "autonomous_failed",
)


def state_path(song_dir: Path) -> Path:
    return Path(song_dir) / "s1_jobs" / "state.json"


def load_state(song_dir: Path) -> Dict[str, Any]:
    p = state_path(song_dir)
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return {
        "state": "none",
        "history": [],
        "updated_at": None,
    }


def set_state(song_dir: Path, state: str, *, note: str = "") -> Dict[str, Any]:
    if state not in STATES:
        raise ValueError(f"unknown state {state}")
    data = load_state(song_dir)
    prev = data.get("state")
    data["state"] = state
    data["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    hist: List[Dict[str, Any]] = list(data.get("history") or [])
    hist.append({"from": prev, "to": state, "at": data["updated_at"], "note": note})
    data["history"] = hist[-40:]
    p = state_path(song_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def can_stream_pocket(song_dir: Path) -> bool:
    st = load_state(song_dir).get("state") or "none"
    return st in ("template_saved", "tracks_ready", "pocket_streaming")


def can_stream_lead(song_dir: Path) -> bool:
    st = load_state(song_dir).get("state") or "none"
    return st in ("pocket_locked", "lead_streaming", "lead_locked", "form_building")
