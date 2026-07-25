"""
Unified structured failure log for all S1 / production failures.

Same shape as arm diagnosis so every failure is actionable:
  primary_cause, causes[], remediations[], next_action, evidence, context

Writes:
  <song>/s1_jobs/last_failure.json   — most recent
  <song>/s1_jobs/failures.jsonl      — append-only history
  optional domain file e.g. arm_diagnosis.json

Never thrash: diagnose → log → remediate suggestion → stop or single fallback.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .logutil import log

# ---- shared cause codes (domains may add more) ----
CAUSE_S1_NOT_RUNNING = "s1_not_running"
CAUSE_NOT_ARRANGE_UI = "not_s1_arrange_ui"
CAUSE_FOCUS_LOST = "focus_lost"
CAUSE_SAFETY_DIALOG = "safety_dialog_blocking"
CAUSE_MIDI_PORT = "instrument_midi_not_connected"
CAUSE_MCU_PORT = "mcu_midi_not_connected"
CAUSE_MIDI_FILE_MISSING = "midi_file_missing"
CAUSE_INVALID_JOB = "invalid_job"
CAUSE_UNKNOWN_OP = "unknown_job_op"
CAUSE_STREAM_NO_CLIPS = "stream_notes_without_clip_growth"
CAUSE_STREAM_NO_AUDIO = "stream_no_audio_signal"
CAUSE_STREAM_ARM_FAILED = "stream_arm_failed"
CAUSE_IMPORT_FAILED = "import_midi_failed"
CAUSE_SAVE_FAILED = "save_failed"
CAUSE_TEMPLATE_MISSING = "template_song_missing"
CAUSE_SAVE_AS_FAILED = "save_as_failed"
CAUSE_STEP_EXCEPTION = "step_exception"
CAUSE_UNKNOWN = "unknown_failure"
CAUSE_DPI_SCALE = "dpi_scale_may_break_vision_map"
CAUSE_TRACK_MAP = "track_role_unmapped"
CAUSE_MISSING_PART_MIDI = "missing_part_midi"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_failure(
    *,
    domain: str,
    primary_cause: str,
    causes: Optional[List[str]] = None,
    remediations: Optional[List[str]] = None,
    next_action: str = "inspect_last_failure_json",
    evidence: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a standard failure record (ok=False)."""
    clist = list(causes or [])
    if primary_cause not in clist:
        clist.insert(0, primary_cause)
    # dedupe
    seen = set()
    causes_u: List[str] = []
    for c in clist:
        if c and c not in seen:
            seen.add(c)
            causes_u.append(c)
    rems = list(remediations or [])
    # dedupe remediations
    rem_u: List[str] = []
    for r in rems:
        if r and r not in rem_u:
            rem_u.append(r)
    if not rem_u:
        rem_u.append("Open s1_jobs/last_failure.json and fix primary_cause")

    rec: Dict[str, Any] = {
        "ok": False,
        "domain": domain,
        "primary_cause": primary_cause or CAUSE_UNKNOWN,
        "causes": causes_u or [CAUSE_UNKNOWN],
        "remediations": rem_u,
        "next_action": next_action,
        "evidence": evidence or {},
        "context": context or {},
        "finished_at": _utc(),
        "policy": "diagnose_then_fix; no thrash; keyboard+MIDI preferred",
    }
    if error:
        rec["error"] = error
        rec["evidence"] = {**rec["evidence"], "error": error}
    return rec


def log_failure_console(rec: Dict[str, Any]) -> None:
    """Mirror arm-style console lines."""
    log(
        f"  FAILURE [{rec.get('domain')}] primary={rec.get('primary_cause')} "
        f"next={rec.get('next_action')}"
    )
    for c in (rec.get("causes") or [])[:6]:
        if c != rec.get("primary_cause"):
            log(f"  cause: {c}")
    for r in (rec.get("remediations") or [])[:5]:
        log(f"  → fix: {r}")


def resolve_jobs_dir(song_or_path: Optional[Path]) -> Path:
    """Find or create s1_jobs under a song directory."""
    if song_or_path is None:
        d = Path.cwd() / "s1_jobs"
        d.mkdir(parents=True, exist_ok=True)
        return d
    p = Path(song_or_path)
    if p.is_file():
        p = p.parent
    # walk up for song markers
    for cand in [p, *p.parents]:
        if (cand / "s1_jobs").is_dir() or (cand / "MIDI").is_dir():
            out = cand / "s1_jobs"
            out.mkdir(parents=True, exist_ok=True)
            return out
        if cand.name == "s1_jobs":
            return cand
    out = p / "s1_jobs"
    out.mkdir(parents=True, exist_ok=True)
    return out


def write_failure(
    song_or_path: Optional[Path],
    rec: Dict[str, Any],
    *,
    also_named: Optional[str] = None,
    console: bool = True,
) -> Dict[str, Any]:
    """
    Persist failure and return record with path fields filled.

    also_named: e.g. \"arm_diagnosis\" → also write arm_diagnosis.json
    """
    jobs = resolve_jobs_dir(song_or_path)
    last = jobs / "last_failure.json"
    hist = jobs / "failures.jsonl"
    rec = dict(rec)
    rec["ok"] = False
    rec.setdefault("finished_at", _utc())
    rec["path"] = str(last)

    last.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    try:
        with hist.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        log(f"  failures.jsonl append warn: {e}")

    if also_named:
        named = jobs / f"{also_named}.json"
        named.write_text(json.dumps(rec, indent=2), encoding="utf-8")
        rec["named_path"] = str(named)

    if console:
        log_failure_console(rec)
        log(f"  failure log → {last}")
    return rec


def record_failure(
    song_or_path: Optional[Path],
    *,
    domain: str,
    primary_cause: str,
    causes: Optional[List[str]] = None,
    remediations: Optional[List[str]] = None,
    next_action: str = "inspect_last_failure_json",
    evidence: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    also_named: Optional[str] = None,
) -> Dict[str, Any]:
    """One-shot: build + write + console log."""
    rec = make_failure(
        domain=domain,
        primary_cause=primary_cause,
        causes=causes,
        remediations=remediations,
        next_action=next_action,
        evidence=evidence,
        context=context,
        error=error,
    )
    return write_failure(song_or_path, rec, also_named=also_named)


# ---- domain helpers (common remediations) ----

def failure_s1_not_running(song: Optional[Path] = None, **ctx) -> Dict[str, Any]:
    return record_failure(
        song,
        domain="setup",
        primary_cause=CAUSE_S1_NOT_RUNNING,
        remediations=[
            "Start Studio One",
            "Run tools/start_from_template.py --name <Song> before production",
        ],
        next_action="relaunch_s1_from_template",
        context=ctx,
        also_named="setup_failure",
    )


def failure_midi_port(song: Optional[Path] = None, status: Optional[Dict] = None, **ctx) -> Dict[str, Any]:
    return record_failure(
        song,
        domain="setup",
        primary_cause=CAUSE_MIDI_PORT,
        causes=[CAUSE_MIDI_PORT],
        remediations=[
            "loopMIDI: S1 Notes pair running",
            "Studio One External Devices → Keyboard Receive From = S1 Notes 1",
            "config/settings.json instrument_midi_out_port = S1 Notes 2",
            "py -3.12 -m s1remote status",
        ],
        next_action="fix_s1_notes_ports",
        evidence={"status": status or {}},
        context=ctx,
        also_named="setup_failure",
    )


def failure_not_arrange(song: Optional[Path] = None, **ctx) -> Dict[str, Any]:
    return record_failure(
        song,
        domain="workspace",
        primary_cause=CAUSE_NOT_ARRANGE_UI,
        remediations=[
            "Focus Studio One song window (not Start/Hub)",
            "Dismiss Safety recovery dialog",
            "Wait for instruments to finish loading",
        ],
        next_action="recover_s1_ui",
        context=ctx,
        also_named="workspace_failure",
    )


def failure_midi_missing(song: Optional[Path] = None, midi: str = "", **ctx) -> Dict[str, Any]:
    return record_failure(
        song,
        domain="stream",
        primary_cause=CAUSE_MIDI_FILE_MISSING,
        remediations=[
            f"Create or copy MIDI file: {midi}",
            "Place under Song/MIDI/",
            "Producer: compose or export drums.mid / bass.mid / …",
        ],
        next_action="add_midi_files",
        evidence={"midi": midi},
        context=ctx,
        also_named="stream_failure",
    )


def failure_stream_no_evidence(
    song: Optional[Path] = None,
    *,
    note_ons: int = 0,
    clip_growth: bool = False,
    has_signal: bool = False,
    arm_diagnosis: Optional[Dict] = None,
    **ctx,
) -> Dict[str, Any]:
    causes = []
    if note_ons > 0 and not clip_growth:
        causes.append(CAUSE_STREAM_NO_CLIPS)
    if not has_signal:
        causes.append(CAUSE_STREAM_NO_AUDIO)
    primary = causes[0] if causes else CAUSE_UNKNOWN
    rems = [
        "Confirm Rec was red on the correct track during stream",
        "Check lane clips (blue/cyan/green) on that track after stop",
        "Check loopback / Stereo Mix for ears",
        "Prefer import_midi if live arm is flaky after arm_diagnosis fix",
    ]
    if arm_diagnosis:
        rems = list(arm_diagnosis.get("remediations") or []) + rems
        if arm_diagnosis.get("primary_cause"):
            causes.insert(0, f"arm:{arm_diagnosis['primary_cause']}")
            primary = CAUSE_STREAM_ARM_FAILED
    return record_failure(
        song,
        domain="stream",
        primary_cause=primary,
        causes=causes,
        remediations=rems,
        next_action=arm_diagnosis.get("next_action") if arm_diagnosis else "inspect_stream_eyes_and_ears",
        evidence={
            "note_ons": note_ons,
            "clip_growth": clip_growth,
            "has_signal": has_signal,
            "arm_diagnosis": arm_diagnosis,
        },
        context=ctx,
        also_named="stream_failure",
    )


def wrap_arm_diagnosis(arm_diag: Dict[str, Any], song: Optional[Path] = None) -> Dict[str, Any]:
    """Normalize arm diagnosis into unified failure log + keep arm_diagnosis.json."""
    rec = make_failure(
        domain="arm",
        primary_cause=str(arm_diag.get("primary_cause") or CAUSE_UNKNOWN),
        causes=list(arm_diag.get("causes") or []),
        remediations=list(arm_diag.get("remediations") or []),
        next_action=str(arm_diag.get("next_action") or "inspect_arm_diagnosis_json"),
        evidence=dict(arm_diag.get("evidence") or {}),
        context={"track": arm_diag.get("track"), **(arm_diag.get("context") or {})},
        error=arm_diag.get("error"),
    )
    # merge extra arm fields
    rec["track"] = arm_diag.get("track")
    rec["attempts"] = (arm_diag.get("evidence") or {}).get("attempts") or arm_diag.get("attempts")
    return write_failure(song, rec, also_named="arm_diagnosis")
