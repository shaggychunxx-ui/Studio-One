"""
Diagnose why Arrange Rec arm failed — so we fix root causes, not thrash.

Priority for control remains: keyboard → MIDI (MCU) → ask user.
Mouse is never required for diagnosis (vision only).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .logutil import log
from .eyes import (
    is_studio_one_arrange_shot,
    locate_track_rec_buttons,
    scan_rec_red,
    list_armed_visible_rows,
    annotate_rec_hud,
    check_display_dpi,
    REC_X_BAND,
)


# Machine-readable cause codes
CAUSE_S1_NOT_RUNNING = "s1_not_running"
CAUSE_NOT_ARRANGE_UI = "not_s1_arrange_ui"
CAUSE_FOCUS_LOST = "focus_lost_mid_arm"
CAUSE_WRONG_TRACK_ARMED = "wrong_track_armed"
CAUSE_NO_RED_ANYWHERE = "no_rec_red_anywhere"
CAUSE_RED_BUT_WRONG_ROW = "rec_red_not_on_target_row"
CAUSE_DOUBLE_TOGGLE = "likely_double_toggle_disarmed"
CAUSE_MCU_BANK_MISMATCH = "mcu_bank_vs_arrange_mismatch"
CAUSE_SELECT_FAILED = "track_select_likely_failed"
CAUSE_DPI_SCALE = "dpi_scale_may_break_vision_map"
CAUSE_FEW_REC_ROWS = "fewer_rec_rows_than_target"
CAUSE_SAFETY_DIALOG = "safety_dialog_blocking"
CAUSE_UNKNOWN = "unknown_arm_failure"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def diagnose_arm_failure(
    *,
    track: int,
    shots: Dict[str, Optional[Path]],
    attempts: List[Dict[str, Any]],
    status: Optional[Dict[str, Any]] = None,
    allow_mouse: bool = False,
    mcu_used: bool = False,
    keyboard_used: bool = True,
) -> Dict[str, Any]:
    """
    Build a structured diagnosis from arm attempt evidence.

    ``shots`` keys e.g. pre, after_kb, after_mcu, final
    ``attempts`` list of {method, shot, target_red, any_red, armed_rows}
    """
    causes: List[str] = []
    evidence: Dict[str, Any] = {
        "track": track,
        "attempts": attempts,
        "rec_x_band": list(REC_X_BAND),
        "allow_mouse": allow_mouse,
    }
    remediations: List[str] = []

    status = status or {}
    if status.get("studio_one_running") is False:
        causes.append(CAUSE_S1_NOT_RUNNING)
        remediations.append("Relaunch Studio One; open song from Template→Save As")

    dpi = check_display_dpi()
    evidence["dpi"] = dpi
    if not dpi.get("ok", True):
        causes.append(CAUSE_DPI_SCALE)
        remediations.append(
            f"Display scale={dpi.get('scale')} — set Windows scaling to 100% for S1 "
            "or rely on keyboard arm only (mouse coords unreliable)"
        )

    final = shots.get("final") or shots.get("pre")
    if final is None or not Path(final).exists():
        causes.append(CAUSE_FOCUS_LOST)
        remediations.append("Ensure S1 is focused; close Safety dialog; re-run arm")
    elif not is_studio_one_arrange_shot(final):
        causes.append(CAUSE_NOT_ARRANGE_UI)
        remediations.append(
            "Screenshot was not S1 arrange (hub/Safety/other app). "
            "Focus song window; dismiss Safety; avoid arm while loading"
        )

    pts: List = []
    armed_rows: List[int] = []
    target_red = False
    any_red = False
    if final and Path(final).exists() and is_studio_one_arrange_shot(final):
        pts = locate_track_rec_buttons(final)
        armed_rows = list_armed_visible_rows(final)
        target_red = scan_rec_red(final, track=track, allow_fallback=False)
        any_red = scan_rec_red(final, track=None)
        evidence["rec_pts"] = pts
        evidence["armed_rows"] = armed_rows
        evidence["target_red"] = target_red
        evidence["any_red"] = any_red
        try:
            annotate_rec_hud(
                final,
                pts,
                armed_row=armed_rows[0] if len(armed_rows) == 1 else None,
                label=f"DIAG fail t{track} armed={armed_rows}",
            )
        except Exception:
            pass

        if track > len(pts) and pts:
            causes.append(CAUSE_FEW_REC_ROWS)
            remediations.append(
                f"Only {len(pts)} Rec rows visible; target track={track}. "
                "Scroll arrange to show track 1 at top, or fix tracks.json role→index"
            )

        if any_red and not target_red:
            causes.append(CAUSE_WRONG_TRACK_ARMED)
            causes.append(CAUSE_RED_BUT_WRONG_ROW)
            remediations.append(
                f"Rec is red on row(s) {armed_rows}, not target {track}. "
                "Keyboard select landed on wrong track — improve select "
                "(Home/Up then Down count) or confirm tracks.json mapping"
            )
            remediations.append(
                "Do NOT press [R] again on wrong track (double-toggle chaos). "
                "Select correct track first, then one [R]"
            )

        if not any_red:
            causes.append(CAUSE_NO_RED_ANYWHERE)
            # Infer from attempt history
            saw_red_then_gone = any(
                a.get("any_red") or a.get("target_red") for a in attempts
            ) and not any_red
            if saw_red_then_gone:
                causes.append(CAUSE_DOUBLE_TOGGLE)
                remediations.append(
                    "Rec was red mid-attempt then grey — likely double [R] or "
                    "MCU+keyboard both toggled. Use ONE method per attempt"
                )
            if keyboard_used:
                causes.append(CAUSE_SELECT_FAILED)
                remediations.append(
                    "Keyboard select+ [R] never produced Rec red. "
                    "Causes: wrong track focused, [R] bound differently, "
                    "or Instrument Input Follows Selection off / no keyboard device"
                )
            if mcu_used:
                causes.append(CAUSE_MCU_BANK_MISMATCH)
                remediations.append(
                    "MCU rec_arm does not map 1:1 to arrange tracks. "
                    "Prefer keyboard select+[R]; use MCU only for transport/mix"
                )
            remediations.append(
                "Check External Devices: Keyboard Receive From = S1 Notes 1; "
                "track Input includes that Keyboard"
            )
            remediations.append(
                "Manual once: click target track header, confirm Rec goes red with [R], "
                "then re-run with --user-armed or fix select path"
            )

    # Attempt pattern: keyboard then still fail
    methods = [a.get("method") for a in attempts]
    evidence["methods_tried"] = methods

    if not causes:
        causes.append(CAUSE_UNKNOWN)
        remediations.append("Inspect arm_watch PNGs and arm_diagnosis.json; compare Rec column")

    # Dedupe preserve order
    def _uniq(xs: List[str]) -> List[str]:
        out: List[str] = []
        for x in xs:
            if x not in out:
                out.append(x)
        return out

    diagnosis = {
        "ok": False,
        "track": track,
        "causes": _uniq(causes),
        "primary_cause": _uniq(causes)[0],
        "remediations": _uniq(remediations),
        "evidence": evidence,
        "policy": "keyboard_then_midi_only; mouse disabled unless allow_mouse",
        "finished_at": _utc(),
    }
    log(f"  ARM DIAGNOSIS primary={diagnosis['primary_cause']} causes={diagnosis['causes']}")
    for r in diagnosis["remediations"][:5]:
        log(f"  → fix: {r}")
    return diagnosis


def write_diagnosis(song_or_eyes: Path, diagnosis: Dict[str, Any]) -> Path:
    """Write unified failure log + arm_diagnosis.json (same structured manner)."""
    from .failure_log import wrap_arm_diagnosis, resolve_jobs_dir

    p = Path(song_or_eyes)
    # Prefer song root for s1_jobs
    song = None
    for parent in [p, *p.parents]:
        if (parent / "s1_jobs").is_dir() or (parent / "MIDI").is_dir():
            song = parent
            break
    rec = wrap_arm_diagnosis(diagnosis, song or p)
    out = Path(rec.get("named_path") or rec.get("path") or resolve_jobs_dir(song or p) / "arm_diagnosis.json")
    return out


def suggest_next_action(diagnosis: Dict[str, Any]) -> str:
    """Single next action code for orchestrator."""
    c = set(diagnosis.get("causes") or [])
    if CAUSE_S1_NOT_RUNNING in c or CAUSE_NOT_ARRANGE_UI in c or CAUSE_SAFETY_DIALOG in c:
        return "recover_s1_ui"
    if CAUSE_WRONG_TRACK_ARMED in c or CAUSE_SELECT_FAILED in c:
        return "fix_track_select_or_tracks_json"
    if CAUSE_MCU_BANK_MISMATCH in c and CAUSE_NO_RED_ANYWHERE in c:
        return "keyboard_only_no_mcu"
    if CAUSE_DOUBLE_TOGGLE in c:
        return "single_toggle_only"
    if CAUSE_NO_RED_ANYWHERE in c:
        return "user_arm_once_then_user_armed_flag"
    return "inspect_arm_diagnosis_json"
