"""
MCU-based mix helpers for unattended production.

Hands only — levels by role via tracks.json. Not full EQ/comp automation
(needs Control Link maps or UCNET); provides static balance + export hotkey.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .tracks_map import load_tracks, resolve_track

# MCU strip is 0-based; arrange track is 1-based. Template default: strip ≈ track-1
# when bank starts at first instrument — best-effort.
DEFAULT_ROLE_DB: Dict[str, float] = {
    "drums": -6.0,
    "drums2": -10.0,
    "bass": -8.0,
    "bass2": -12.0,
    "lead": -9.0,
    "bed": -14.0,
    "bed2": -16.0,
    "color": -15.0,
    "sample": -12.0,
}

PRESETS: Dict[str, Dict[str, float]] = {
    "mvp_pocket": {"drums": -5.0, "bass": -7.5},
    "full_static": dict(DEFAULT_ROLE_DB),
    "lead_forward": {
        "drums": -7.0,
        "bass": -9.0,
        "lead": -5.5,
        "bed": -16.0,
        "color": -14.0,
    },
}


def role_to_mcu_channel(song_dir: Path, role: str) -> int:
    track = resolve_track(song_dir, role)
    return max(0, track - 1)


def apply_mix_balance(
    s1,
    song_dir: Path,
    *,
    levels: Optional[Dict[str, float]] = None,
    preset: Optional[str] = None,
) -> Dict[str, Any]:
    """Set MCU faders for known roles. Returns applied map."""
    if levels is None:
        levels = dict(PRESETS.get(preset or "full_static", DEFAULT_ROLE_DB))
    applied: Dict[str, Any] = {}
    tracks = load_tracks(song_dir).get("roles") or {}
    for role, db in levels.items():
        role_l = str(role).lower()
        if role_l not in tracks and role_l not in DEFAULT_ROLE_DB:
            continue
        try:
            ch = role_to_mcu_channel(song_dir, role_l)
            s1.fader(ch, float(db))
            applied[role_l] = {"channel": ch, "db": float(db), "ok": True}
        except Exception as e:
            applied[role_l] = {"ok": False, "error": str(e), "db": float(db)}
    return {"ok": any(v.get("ok") for v in applied.values()), "applied": applied, "preset": preset}


def export_mixdown_hotkey(run_action, *, focus: bool = True) -> Dict[str, Any]:
    """
    Trigger Studio One Export Mixdown dialog via Ctrl+E.
    Unattended fill of dialog is best-effort; user Template may set defaults.
    Returns intent only — full dialog automation is OS/version fragile.
    """
    try:
        # Prefer catalog action if present
        try:
            run_action("export_mixdown", focus=focus)
        except Exception:
            run_action("save", focus=focus)  # ensure song saved first
            from s1remote.hotkeys import send_hotkey

            send_hotkey("^e", focus=focus)
        return {
            "ok": True,
            "method": "hotkey_ctrl_e",
            "note": "Export dialog opened; Template/default export path recommended for zero-touch",
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
