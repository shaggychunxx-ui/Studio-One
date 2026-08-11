"""
Hard UI availability gate for Studio One.

Before any arm/stream/save automation:
  1) S1 process running
  2) Song window focused (expected name if given)
  3) No blocking dialogs (New, Safety, Save As, Open, Import, etc.)
  4) Arrange screenshot is real S1 song UI

If unavailable: log structured failure, STOP. Never thrash keys that open
more dialogs or abandon the current song.

Policy: stay on the open production song (e.g. Meridian_Pulse). Do not
create new songs mid-session unless explicitly requested.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .logutil import log
from .eyes import is_studio_one_arrange_shot, Eyes
from .vision import (
    detect_safety_dialog_uia,
    dismiss_safety_dialog,
    hard_clear_safety,
)
from .failure_log import record_failure

# Dialog titles that block arrange work — cancel/dismiss, do not OK
BLOCKING_DIALOG_TITLES = (
    "New",
    "Save As",
    "Save Song As",
    "Open",
    "Open Song",
    "Import Files",
    "Import File",
    "Import",
    "Studio One Safety",
    "Missing Files",
    "Audio Device",
    "Options",
    "Preferences",
    "Export",
    "Mixdown",
)

# Never match these as S1 song windows
SKIP_WINDOW = (
    "grok",
    "connect studio one and producer",
    "windows terminal",
    "powershell",
    "chrome",
    "edge",
    "visual studio",
    "github desktop",
    "tightvnc",
    "program manager",
)


@dataclass
class UiGateReport:
    ok: bool
    available: bool
    reasons: List[str] = field(default_factory=list)
    s1_running: bool = False
    song_title: Optional[str] = None
    expected_song: Optional[str] = None
    title_match: bool = False
    blocking_dialogs: List[str] = field(default_factory=list)
    is_arrange: bool = False
    safety_present: bool = False
    shot: Optional[str] = None
    actions_taken: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _window_titles() -> List[str]:
    from pywinauto import Desktop

    out: List[str] = []
    for backend in ("uia", "win32"):
        try:
            for w in Desktop(backend=backend).windows():
                try:
                    t = (w.window_text() or "").strip()
                except Exception:
                    continue
                if not t or not w.is_visible():
                    continue
                low = t.lower()
                if any(s in low for s in SKIP_WINDOW):
                    continue
                if t not in out:
                    out.append(t)
        except Exception:
            continue
    return out


def list_blocking_dialogs() -> List[Tuple[str, Any]]:
    """Return (title, window) for visible blocking dialogs."""
    from pywinauto import Desktop

    found: List[Tuple[str, Any]] = []
    try:
        for w in Desktop(backend="uia").windows():
            try:
                t = (w.window_text() or "").strip()
            except Exception:
                continue
            if not t or not w.is_visible():
                continue
            low = t.lower()
            if any(s in low for s in SKIP_WINDOW):
                continue
            # Exact short titles (New, Open) — avoid matching OS "Settings" broadly
            exact = {"New", "Open", "Save As", "Import", "Export", "Options"}
            if t in exact or t in BLOCKING_DIALOG_TITLES:
                found.append((t, w))
                continue
            if "studio one safety" in low:
                found.append((t, w))
                continue
            if t.startswith("Import File") or t.startswith("Save Song"):
                found.append((t, w))
                continue
    except Exception:
        pass
    return found


def dismiss_blocking_dialogs(*, allow_ok_on_safety: bool = True) -> List[str]:
    """
    Close blocking dialogs that steal the song UI.
    - Safety: start normally (existing helper)
    - New / Open / Save As / Import: ESC / Cancel only (never OK — stays on current song)
    """
    from pywinauto.keyboard import send_keys
    from s1remote.hotkeys import focus_studio_one

    actions: List[str] = []
    # Safety first — multi-strategy (button / keys / bottom-right coords).
    # Do not ESC Safety (cancels wrong path); Start normally only.
    if detect_safety_dialog_uia():
        log("  ui_gate: Safety dialog — multi-strategy dismiss")
        ok = dismiss_safety_dialog(retries=4)
        actions.append("dismissed_safety_ok" if ok else "dismissed_safety_fail")
        time.sleep(0.8)
        # Second pass if ghost title / Qt lag
        if detect_safety_dialog_uia():
            log("  ui_gate: Safety still present — second dismiss pass")
            ok2 = dismiss_safety_dialog(retries=3)
            actions.append("dismissed_safety_pass2_ok" if ok2 else "dismissed_safety_pass2_fail")
            time.sleep(0.8)
        # Last resort: kill S1 + clear crash markers (caller must relaunch song)
        if detect_safety_dialog_uia():
            log("  ui_gate: Safety still blocking — hard_clear_safety (kill S1 + markers)")
            hard_clear_safety(kill_s1=True)
            actions.append("hard_clear_safety")
            time.sleep(1.0)

    for title, w in list_blocking_dialogs():
        low = title.lower()
        if "safety" in low:
            continue  # handled above
        log(f"  ui_gate: blocking dialog {title!r} — Cancel/ESC (stay on current song)")
        try:
            w.set_focus()
        except Exception:
            pass
        time.sleep(0.12)
        # Prefer Cancel button
        try:
            for btn_name in ("Cancel", "Close", "No"):
                try:
                    b = w.child_window(title=btn_name, control_type="Button")
                    if b.exists(timeout=0.3):
                        b.click_input()
                        actions.append(f"clicked_{btn_name}_on_{title}")
                        time.sleep(0.35)
                        break
                except Exception:
                    continue
            else:
                send_keys("{ESC}")
                actions.append(f"esc_on_{title}")
                time.sleep(0.35)
        except Exception:
            send_keys("{ESC}")
            actions.append(f"esc_fallback_{title}")
            time.sleep(0.3)

    # Focus song again
    try:
        focus_studio_one()
    except Exception:
        pass
    time.sleep(0.2)
    # One more ESC if New still up (never for Safety — already handled)
    still = [(t, w) for t, w in list_blocking_dialogs() if "safety" not in t.lower()]
    if still:
        send_keys("{ESC}")
        actions.append("final_esc")
        time.sleep(0.25)
    return actions


def check_ui_available(
    *,
    expected_song: Optional[str] = None,
    eyes: Optional[Eyes] = None,
    auto_dismiss: bool = True,
    song_dir: Optional[Path] = None,
    log_failure: bool = True,
) -> UiGateReport:
    """
    Full gate. If auto_dismiss, try once to clear Safety/New/etc., then re-check.
    """
    from s1remote.hotkeys import focus_studio_one, studio_one_running

    report = UiGateReport(ok=False, available=False, expected_song=expected_song)
    report.s1_running = studio_one_running()
    if not report.s1_running:
        report.reasons.append("studio_one_not_running")
        if log_failure and song_dir:
            record_failure(
                song_dir,
                domain="workspace",
                primary_cause="s1_not_running",
                remediations=[
                    f"Open song: {expected_song or 'current production song'}",
                    "Do not continue automation until S1 is running",
                ],
                next_action="relaunch_s1_open_song",
                evidence=report.to_dict(),
                also_named="workspace_failure",
            )
        log(f"  ui_gate UNAVAILABLE: {report.reasons}")
        return report

    if auto_dismiss:
        report.actions_taken = dismiss_blocking_dialogs()

    focus_studio_one()
    time.sleep(0.2)
    titles = _window_titles()
    song_titles = [t for t in titles if t.startswith("Studio One")]
    report.song_title = song_titles[0] if song_titles else None

    if expected_song:
        report.title_match = any(
            expected_song.lower() in t.lower() for t in song_titles
        )
        if not report.title_match:
            report.reasons.append(f"song_title_mismatch want={expected_song!r} have={song_titles}")

    blocking = list_blocking_dialogs()
    report.blocking_dialogs = [t for t, _ in blocking]
    report.safety_present = detect_safety_dialog_uia()
    if report.blocking_dialogs:
        report.reasons.append(f"blocking_dialogs={report.blocking_dialogs}")
    if report.safety_present:
        report.reasons.append("safety_dialog_present")

    shot_path = None
    if eyes is not None:
        shot_path = eyes.shot(
            "ui_gate",
            hud=f"gate {expected_song or ''} block={report.blocking_dialogs[:1]}",
        )
        report.shot = str(shot_path) if shot_path else None
        report.is_arrange = bool(shot_path and is_studio_one_arrange_shot(shot_path))
        if not report.is_arrange:
            report.reasons.append("screenshot_not_s1_arrange")
    else:
        # Without eyes, still require no blockers + title
        report.is_arrange = not report.blocking_dialogs and not report.safety_present

    report.available = (
        report.s1_running
        and not report.blocking_dialogs
        and not report.safety_present
        and (report.is_arrange if eyes is not None else True)
        and (report.title_match if expected_song else True)
    )
    report.ok = report.available

    if not report.available:
        log(f"  ui_gate UNAVAILABLE: {report.reasons}")
        if log_failure and song_dir:
            primary = (
                "safety_dialog_blocking"
                if report.safety_present
                else "blocking_dialog"
                if report.blocking_dialogs
                else "song_title_mismatch"
                if expected_song and not report.title_match
                else "not_s1_arrange_ui"
                if not report.is_arrange
                else "ui_unavailable"
            )
            remediations = [
                "Stay on production song; do not OK New/Open dialogs mid-session",
                "Cancel any New/Save As/Import dialogs (ESC)",
                "Dismiss Safety with Start if present",
                f"Focus window titled Studio One - {expected_song or '…'}",
            ]
            if "New" in report.blocking_dialogs:
                remediations.insert(
                    0,
                    "New dialog was open (often accidental Ctrl+N) — Cancel to keep Meridian_Pulse",
                )
            record_failure(
                song_dir,
                domain="workspace",
                primary_cause=primary,
                causes=list(report.reasons),
                remediations=remediations,
                next_action="clear_blockers_stay_on_song",
                evidence=report.to_dict(),
                also_named="workspace_failure",
            )
    else:
        log(
            f"  ui_gate OK title={report.song_title!r} "
            f"arrange={report.is_arrange} dismissed={report.actions_taken}"
        )
    return report


def require_ui(
    *,
    expected_song: Optional[str] = None,
    eyes: Optional[Eyes] = None,
    song_dir: Optional[Path] = None,
) -> UiGateReport:
    """
    Call before every production action. Raises RuntimeError if unavailable
    after one auto-dismiss pass (callers catch and stop).
    """
    rep = check_ui_available(
        expected_song=expected_song,
        eyes=eyes,
        auto_dismiss=True,
        song_dir=song_dir,
        log_failure=True,
    )
    if not rep.available:
        # Second pass after dismiss
        time.sleep(0.4)
        rep = check_ui_available(
            expected_song=expected_song,
            eyes=eyes,
            auto_dismiss=True,
            song_dir=song_dir,
            log_failure=True,
        )
    if not rep.available:
        raise RuntimeError(
            f"UI unavailable: {rep.reasons} dialogs={rep.blocking_dialogs}"
        )
    return rep
