#!/usr/bin/env python3
"""
Eyes-first unblock + diagnose for Studio One on LAPTOP.

Use when automation is stuck on a prompt/dialog:
  1) Screenshot (eyes) + list visible windows/dialogs
  2) Safe dismiss (Safety Start; Cancel/Esc on New/Save/Open/Import/device prompts)
  3) Re-shot + gate report
  4) Write JSON/MD for GROMIT comms bus

Usage:
  set PYTHONPATH=%CD%;%CD%\\tools
  py -3.12 tools\\unblock_and_diagnose.py
  py -3.12 tools\\unblock_and_diagnose.py --out-dir PATH
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TOOLS))

from s1_tools.logutil import log, set_log_file  # noqa: E402
from s1_tools.eyes import Eyes, get_screen_geometry  # noqa: E402
from s1_tools.vision import (  # noqa: E402
    analyze_shot,
    detect_safety_dialog_uia,
    dismiss_safety_dialog,
)
from s1_tools.ui_gate import (  # noqa: E402
    check_ui_available,
    dismiss_blocking_dialogs,
    list_blocking_dialogs,
    _window_titles,
)
from s1_tools.paths import ensure_s1remote_on_path, default_songs_root  # noqa: E402


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def list_all_visible_windows() -> List[Dict[str, Any]]:
    """Broader inventory than blocking-only (for diagnose)."""
    out: List[Dict[str, Any]] = []
    try:
        from pywinauto import Desktop

        for backend in ("uia", "win32"):
            try:
                for w in Desktop(backend=backend).windows():
                    try:
                        if not w.is_visible():
                            continue
                        t = (w.window_text() or "").strip()
                        if not t:
                            continue
                        rect = None
                        try:
                            r = w.rectangle()
                            rect = {
                                "left": int(r.left),
                                "top": int(r.top),
                                "right": int(r.right),
                                "bottom": int(r.bottom),
                            }
                        except Exception:
                            pass
                        item = {
                            "title": t,
                            "backend": backend,
                            "rect": rect,
                        }
                        # de-dupe by title+backend
                        if not any(
                            x["title"] == t and x["backend"] == backend for x in out
                        ):
                            out.append(item)
                    except Exception:
                        continue
            except Exception:
                continue
    except Exception as e:
        out.append({"error": str(e)})
    return out[:80]


def try_extra_device_prompts() -> List[str]:
    """
    Physical audio/MIDI offline often leaves device / missing-driver prompts.
    Prefer Cancel / No / Close / Esc — never OK through destructive dialogs.
    """
    actions: List[str] = []
    try:
        from pywinauto import Desktop
        from pywinauto.keyboard import send_keys

        keywords = (
            "audio",
            "device",
            "asio",
            "missing",
            "plugin",
            "license",
            "activation",
            "update",
            "crash",
            "safety",
            "not found",
            "error",
            "warning",
            "presonus",
            "studio one",
            "save",
            "don't save",
            "dont save",
        )
        safe_buttons = (
            "cancel",
            "close",
            "no",
            "don't save",
            "dont save",
            "later",
            "not now",
            "skip",
            "ignore",
            "start",  # Safety Start
            "ok",  # only after we classify as non-destructive below
        )
        for w in Desktop(backend="uia").windows():
            try:
                if not w.is_visible():
                    continue
                t = (w.window_text() or "").strip()
            except Exception:
                continue
            if not t:
                continue
            low = t.lower()
            if not any(k in low for k in keywords):
                # also catch bare Dialog with buttons under S1 parent
                if "dialog" not in low and len(t) > 40:
                    continue
            # Skip pure main song window
            if low.startswith("studio one") and " - " in low and "safety" not in low:
                continue
            try:
                w.set_focus()
            except Exception:
                pass
            time.sleep(0.15)
            clicked = False
            # Prefer non-destructive
            prefer = ("Cancel", "No", "Don't Save", "Close", "Later", "Not Now", "Skip")
            if "safety" in low:
                prefer = ("Start",) + prefer
            try:
                for btn in w.descendants(control_type="Button"):
                    try:
                        name = (btn.window_text() or "").strip()
                    except Exception:
                        continue
                    if not name:
                        continue
                    if any(name.lower() == p.lower() or name.lower().startswith(p.lower()) for p in prefer):
                        try:
                            btn.click_input()
                        except Exception:
                            try:
                                btn.invoke()
                            except Exception:
                                continue
                        actions.append(f"clicked:{name!r}_on:{t[:60]}")
                        clicked = True
                        time.sleep(0.4)
                        break
            except Exception:
                pass
            if not clicked:
                send_keys("{ESC}")
                actions.append(f"esc_on:{t[:60]}")
                time.sleep(0.3)
    except Exception as e:
        actions.append(f"extra_prompt_err:{e}")
    return actions


def run(out_dir: Path, *, song_hint: Optional[str] = None) -> Dict[str, Any]:
    ensure_s1remote_on_path()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    set_log_file(out_dir / "unblock_diagnose.log")
    eyes = Eyes(out_dir / "shots", enabled=True)
    report: Dict[str, Any] = {
        "when": _utc(),
        "host": os.environ.get("COMPUTERNAME", ""),
        "geometry": get_screen_geometry(),
        "phases": [],
    }

    from s1remote.hotkeys import studio_one_running, focus_studio_one

    running = studio_one_running()
    report["studio_one_running"] = running
    report["phases"].append({"step": "proc", "running": running})

    # Phase A: eyes BEFORE any dismiss (see the stuck prompt)
    shot_before = eyes.shot("before_unblock", annotate=True, hud="STUCK? before")
    report["shot_before"] = str(shot_before) if shot_before else None
    if shot_before:
        rep_b = analyze_shot(shot_before)
        report["vision_before"] = rep_b.to_dict()

    report["windows_before"] = list_all_visible_windows()
    report["blocking_before"] = [t for t, _ in list_blocking_dialogs()]
    report["safety_before"] = detect_safety_dialog_uia()

    actions: List[str] = []
    if report["safety_before"]:
        dismiss_safety_dialog()
        actions.append("dismissed_safety")
        time.sleep(0.8)

    actions.extend(dismiss_blocking_dialogs())
    actions.extend(try_extra_device_prompts())
    # Generic Esc sweep if still blocked
    try:
        from pywinauto.keyboard import send_keys

        focus_studio_one()
        for _ in range(3):
            if not list_blocking_dialogs() and not detect_safety_dialog_uia():
                break
            send_keys("{ESC}")
            actions.append("esc_sweep")
            time.sleep(0.25)
    except Exception as e:
        actions.append(f"esc_sweep_err:{e}")

    report["actions"] = actions
    time.sleep(0.5)

    shot_after = eyes.shot("after_unblock", annotate=True, hud="after dismiss")
    report["shot_after"] = str(shot_after) if shot_after else None
    if shot_after:
        rep_a = analyze_shot(shot_after)
        report["vision_after"] = rep_a.to_dict()

    report["windows_after"] = list_all_visible_windows()
    report["blocking_after"] = [t for t, _ in list_blocking_dialogs()]
    report["safety_after"] = detect_safety_dialog_uia()

    gate = check_ui_available(
        expected_song=song_hint,
        eyes=eyes,
        auto_dismiss=True,
        song_dir=out_dir,
        log_failure=False,
    )
    report["ui_gate"] = gate.to_dict()
    report["ok"] = bool(
        running
        and not report["blocking_after"]
        and not report["safety_after"]
        and (gate.available or (report.get("vision_after") or {}).get("likely_song_ui"))
    )
    report["still_stuck"] = bool(report["blocking_after"] or report["safety_after"])
    if report["still_stuck"]:
        report["diagnosis"] = (
            f"Still blocked after dismiss. blocking={report['blocking_after']} "
            f"safety={report['safety_after']}. See shot_after + windows_after."
        )
    elif not running:
        report["diagnosis"] = "Studio One process not running — need relaunch."
    else:
        report["diagnosis"] = "Prompt likely cleared; Song UI available or closer to available."

    jp = out_dir / "unblock_diagnose_latest.json"
    mp = out_dir / "unblock_diagnose_latest.md"
    jp.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# Studio One unblock + diagnose",
        "",
        f"- When: {report['when']}",
        f"- Host: `{report['host']}`",
        f"- S1 running: {running}",
        f"- OK: **{report['ok']}** still_stuck={report['still_stuck']}",
        f"- Geometry: `{report['geometry']}`",
        f"- Diagnosis: {report['diagnosis']}",
        "",
        "## Before",
        f"- Blocking: {report['blocking_before']}",
        f"- Safety: {report['safety_before']}",
        f"- Shot: `{report['shot_before']}`",
        "",
        "## Actions",
        *([f"- {a}" for a in actions] if actions else ["- (none)"]),
        "",
        "## After",
        f"- Blocking: {report['blocking_after']}",
        f"- Safety: {report['safety_after']}",
        f"- Shot: `{report['shot_after']}`",
        "",
        "## Window titles (after, sample)",
    ]
    for w in report["windows_after"][:25]:
        lines.append(f"- [{w.get('backend')}] {w.get('title', '')[:100]}")
    mp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"REPORT {jp}")
    log(f"REPORT {mp}")
    log(f"ok={report['ok']} still_stuck={report['still_stuck']} {report['diagnosis']}")
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Report dir (default: Songs/Agent_UI_Learn/_vision/unblock)",
    )
    ap.add_argument("--song-hint", default="Agent_UI_Learn")
    args = ap.parse_args()
    if args.out_dir:
        out = args.out_dir
    else:
        out = default_songs_root() / "Agent_UI_Learn" / "_vision" / "unblock"
    rep = run(out, song_hint=args.song_hint)
    return 0 if rep.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
