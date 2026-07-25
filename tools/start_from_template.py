#!/usr/bin/env python3
"""
Start production from the standing Template song, then Save As a new song.

Policy (user requirement):
  1) Open  .../Songs/Template/Template.song
  2) Save As a **new** song (never write into Template)
  3) Only then begin production (MIDI stream, arm, mix, …)

Usage:
  set PYTHONPATH=%CD%;%CD%\\tools
  py -3.12 tools/start_from_template.py --name "MySong"
  py -3.12 tools/start_from_template.py --name "MySong" --scaffold
  py -3.12 tools/start_from_template.py   # auto name: YYYY-MM-DD_HHMM

Env:
  S1_TEMPLATE_SONG   path to Template.song (optional)
  S1_SONGS_ROOT      Songs parent folder (optional)
  S1_REMOTE          s1-remote root
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from pywinauto import Desktop
from pywinauto.keyboard import send_keys

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TOOLS))

from s1_tools.paths import (  # noqa: E402
    ensure_s1remote_on_path,
    default_songs_root,
    default_template_song,
)
from s1_tools.logutil import log, set_log_file  # noqa: E402
from s1_tools.eyes import Eyes, is_studio_one_arrange_shot  # noqa: E402
from s1_tools.vision import analyze_shot, detect_safety_dialog_uia, dismiss_safety_dialog  # noqa: E402


DEFAULT_EXE = Path(r"C:\Program Files\PreSonus\Studio One 6\Studio One.exe")


def songs_root() -> Path:
    return default_songs_root()


def template_song_path() -> Path:
    return default_template_song()


def studio_one_exe() -> Path:
    env = os.environ.get("S1_EXE", "").strip()
    if env:
        return Path(env)
    return DEFAULT_EXE


def sanitize_name(name: str) -> str:
    name = name.strip()
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name or name.lower() == "template":
        raise SystemExit("Invalid song name (empty or reserved 'Template')")
    return name


def auto_name() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H%M")


def scaffold_agent_dirs(song_dir: Path, name: str) -> None:
    """Create producer/agent folders next to the .song package."""
    for sub in (
        "MIDI",
        "MIDI_Parts",
        "s1_jobs",
        "_vision",
        "Audio",
        "Stems_MVP",
        "DRAG_THESE_INTO_STUDIO_ONE",
    ):
        (song_dir / sub).mkdir(parents=True, exist_ok=True)
    # Light stubs if missing
    notes = song_dir / "NOTES.txt"
    if not notes.is_file():
        notes.write_text(
            f"NOTES — {name}\nStarted from Template via start_from_template.py\n"
            f"When: {datetime.now().isoformat()}\n",
            encoding="utf-8",
        )
    gates = song_dir / "GATES.txt"
    if not gates.is_file():
        gates.write_text(
            f"GATES — {name}\n[ ] brief locked\n[ ] pocket locked\n[ ] lead locked\n",
            encoding="utf-8",
        )


def window_titles() -> list[str]:
    out: list[str] = []
    for backend in ("uia", "win32"):
        try:
            for w in Desktop(backend=backend).windows():
                try:
                    t = (w.window_text() or "").strip()
                except Exception:
                    continue
                if not t:
                    continue
                low = t.lower()
                if "studio one" in low or "safety" in low or "save" in low:
                    if t not in out:
                        out.append(t)
        except Exception:
            pass
    return out


def find_dialog(titles: tuple[str, ...], timeout: float = 6.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for backend in ("uia", "win32"):
            try:
                for w in Desktop(backend=backend).windows():
                    try:
                        t = (w.window_text() or "").strip()
                    except Exception:
                        continue
                    if not t or not w.is_visible():
                        continue
                    tl = t.lower()
                    for want in titles:
                        if want.lower() in tl:
                            return w, backend, t
            except Exception:
                continue
        time.sleep(0.12)
    return None, None, None


def _type_path(path: str) -> None:
    safe = (
        path.replace("{", "{{")
        .replace("}", "}}")
        .replace("+", "{+}")
        .replace("^", "{^}")
        .replace("%", "{%}")
        .replace("~", "{~}")
        .replace("(", "{(}")
        .replace(")", "{)}")
    )
    send_keys("%n")
    time.sleep(0.12)
    send_keys("^a")
    time.sleep(0.05)
    send_keys(safe, with_spaces=True, pause=0.015)
    time.sleep(0.2)


def wait_song_ui(eyes: Eyes, *, name_hint: str | None, timeout: float = 120.0) -> bool:
    from s1remote.hotkeys import focus_studio_one, studio_one_running

    deadline = time.time() + timeout
    n = 0
    while time.time() < deadline:
        if not studio_one_running():
            log("  S1 process gone")
            return False
        if detect_safety_dialog_uia():
            log("  dismiss Safety")
            dismiss_safety_dialog()
            time.sleep(1.0)
        focus_studio_one()
        titles = window_titles()
        shot = eyes.shot(f"wait_{n:02d}")
        n += 1
        is_arr = is_studio_one_arrange_shot(shot) if shot else False
        log(f"  wait titles={titles} arrange={is_arr}")
        if name_hint:
            if any(name_hint.lower() in t.lower() for t in titles) and is_arr:
                return True
        else:
            # any song title (not bare splash)
            if any(
                t.startswith("Studio One -") and "Template" not in t
                for t in titles
            ) and is_arr:
                return True
            if any("Template" in t for t in titles) and is_arr and name_hint is None:
                return True
            if is_arr and any(t.startswith("Studio One") for t in titles):
                # loaded something
                if any(" - " in t for t in titles):
                    return True
        time.sleep(2.5)
    return False


def open_template(template: Path, eyes: Eyes) -> bool:
    from s1remote.hotkeys import studio_one_running, focus_studio_one

    exe = studio_one_exe()
    if not template.is_file():
        log(f"FATAL: template missing: {template}")
        return False
    if not exe.is_file():
        log(f"FATAL: Studio One exe missing: {exe}")
        return False

    log(f"Opening template: {template}")
    if studio_one_running():
        # Open into existing process
        subprocess.Popen([str(exe), str(template)])
    else:
        subprocess.Popen([str(exe), str(template)])
        time.sleep(6)

    # Boot + safety
    for i in range(8):
        if detect_safety_dialog_uia():
            dismiss_safety_dialog()
            time.sleep(1.2)
        focus_studio_one()
        eyes.shot(f"boot_{i}")
        titles = window_titles()
        if any("Template" in t or "Studio One -" in t for t in titles):
            break
        time.sleep(2)

    ok = wait_song_ui(eyes, name_hint="Template", timeout=150)
    if ok:
        log("Template song UI ready")
    else:
        # Accept if arrange visible under any title
        shot = eyes.shot("template_fallback")
        ok = bool(shot and is_studio_one_arrange_shot(shot))
        log(f"Template wait fallback arrange={ok}")
    return ok


def save_as_new_song(dest_song_file: Path, eyes: Eyes) -> bool:
    """Ctrl+Shift+S → type path → Enter. dest_song_file ends with .song."""
    from s1remote.hotkeys import focus_studio_one, run_action

    dest_song_file = dest_song_file.resolve()
    dest_song_file.parent.mkdir(parents=True, exist_ok=True)

    focus_studio_one()
    time.sleep(0.25)
    send_keys("{ESC}")
    time.sleep(0.15)

    log(f"Save As → {dest_song_file}")
    try:
        run_action("save_as", focus=True)
    except Exception:
        send_keys("^+s")
    time.sleep(0.9)

    dlg, backend, title = find_dialog(
        ("Save As", "Save Song", "Save", "Name Song", "Song"),
        timeout=8.0,
    )
    if dlg is None:
        log("  Save As dialog not found — retry hotkey")
        focus_studio_one()
        send_keys("^+s")
        time.sleep(1.0)
        dlg, backend, title = find_dialog(
            ("Save As", "Save Song", "Save", "Name Song"),
            timeout=6.0,
        )
    if dlg is None:
        log("  FAIL: no Save As dialog")
        eyes.shot("save_as_no_dialog")
        return False

    log(f"  dialog: {title!r} backend={backend}")
    try:
        dlg.set_focus()
    except Exception:
        pass
    time.sleep(0.2)

    # Prefer full path in filename field
    _type_path(str(dest_song_file))
    send_keys("{ENTER}")
    time.sleep(1.2)
    # Confirm overwrite if prompted
    conf, _, ctitle = find_dialog(("Confirm", "Yes", "Replace", "already exists"), timeout=2.0)
    if conf is not None:
        log(f"  confirm dialog {ctitle!r} → Yes")
        send_keys("%y")
        time.sleep(0.5)
        send_keys("{ENTER}")
        time.sleep(0.8)
    # Extra enter for multi-page wizards
    send_keys("{ENTER}")
    time.sleep(1.5)
    eyes.shot("after_save_as")

    # Wait for file or title
    name = dest_song_file.stem
    deadline = time.time() + 60
    while time.time() < deadline:
        if dest_song_file.is_file():
            log(f"  song file exists: {dest_song_file}")
            return True
        # S1 sometimes creates folder then song with slight delay
        parent = dest_song_file.parent
        if parent.is_dir():
            songs = list(parent.glob("*.song"))
            if songs:
                log(f"  song package present: {songs[0]}")
                return True
        titles = window_titles()
        if any(name.lower() in t.lower() for t in titles):
            log(f"  title has new name: {titles}")
            return True
        time.sleep(1.0)

    log("  WARN: Save As finished but file/title not confirmed")
    return dest_song_file.parent.is_dir()


def start_new_song_from_template(
    *,
    name: str | None = None,
    template: Path | None = None,
    songs_root_path: Path | None = None,
    open_s1: bool = True,
) -> dict:
    """
    Open Template.song → Save As new song → set S1_SONG_DIR.

    Returns summary dict with ok, song_dir, song_file, etc.
    Raises SystemExit-style errors as dict ok=False + error.
    """
    ensure_s1remote_on_path()
    name = sanitize_name(name or auto_name())
    root = (songs_root_path or songs_root()).resolve()
    template_p = (template or template_song_path()).resolve()

    if name.lower() == "template":
        return {"ok": False, "error": "cannot Save As over Template"}

    song_dir = root / name
    song_file = song_dir / f"{name}.song"
    if song_file.is_file() or (song_dir.is_dir() and any(song_dir.glob("*.song"))):
        suffix = datetime.now().strftime("%H%M%S")
        name = f"{name}_{suffix}"
        song_dir = root / name
        song_file = song_dir / f"{name}.song"
        log(f"  name collision → {name}")

    song_dir.mkdir(parents=True, exist_ok=True)
    scaffold_agent_dirs(song_dir, name)
    try:
        from s1_tools.tracks_map import ensure_default_tracks
        from s1_tools.state import set_state

        ensure_default_tracks(song_dir)
        set_state(song_dir, "template_saved" if open_s1 else "none", note="start_from_template")
    except Exception as e:
        log(f"  tracks/state init warn: {e}")

    vision = song_dir / "_vision" / "start_template"
    vision.mkdir(parents=True, exist_ok=True)
    set_log_file(vision / "start_from_template.log")

    log("NEW SONG from template")
    log(f"  template: {template_p}")
    log(f"  new name: {name}")
    log(f"  song dir: {song_dir}")
    log(f"  song file: {song_file}")

    if not open_s1:
        summary = {
            "ok": True,
            "skipped_s1": True,
            "name": name,
            "song_dir": str(song_dir),
            "song_file": str(song_file),
            "template": str(template_p),
        }
        (song_dir / "s1_jobs" / "session.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        os.environ["S1_SONG_DIR"] = str(song_dir)
        os.environ["STUDIO_ONE_SONG"] = str(song_dir)
        return summary

    if not template_p.is_file():
        try:
            from s1_tools.failure_log import record_failure

            record_failure(
                song_dir,
                domain="template",
                primary_cause="template_song_missing",
                remediations=[
                    f"Create or restore {template_p}",
                    "Set S1_TEMPLATE_SONG env if Template lives elsewhere",
                ],
                next_action="restore_template_song",
                evidence={"template": str(template_p)},
                also_named="template_failure",
            )
        except Exception:
            pass
        return {"ok": False, "error": f"template missing: {template_p}", "primary_cause": "template_song_missing"}

    eyes = Eyes(vision)
    if not open_template(template_p, eyes):
        try:
            from s1_tools.failure_log import record_failure

            record_failure(
                song_dir,
                domain="template",
                primary_cause="not_s1_arrange_ui",
                remediations=[
                    "Wait for S1 to finish loading Template",
                    "Dismiss Safety dialog",
                    "Confirm Template.song opens manually",
                ],
                next_action="recover_s1_ui",
                evidence={"template": str(template_p)},
                also_named="template_failure",
            )
        except Exception:
            pass
        return {
            "ok": False,
            "error": "could not open Template song UI",
            "song_dir": str(song_dir),
            "primary_cause": "not_s1_arrange_ui",
        }

    if song_file.parent.resolve() == template_p.parent.resolve():
        return {"ok": False, "error": "refused to Save As into Template folder", "primary_cause": "save_as_into_template"}

    if not save_as_new_song(song_file, eyes):
        eyes.shot("save_as_failed")
        try:
            from s1_tools.failure_log import record_failure

            record_failure(
                song_dir,
                domain="template",
                primary_cause="save_as_failed",
                remediations=[
                    "Ctrl+Shift+S manually and save under Songs/<Name>/",
                    "Check Save As dialog focus / path permissions",
                    "Never save over Template folder",
                ],
                next_action="manual_save_as",
                evidence={"dest": str(song_file)},
                also_named="template_failure",
            )
        except Exception:
            pass
        return {
            "ok": False,
            "error": "Save As failed",
            "song_dir": str(song_dir),
            "primary_cause": "save_as_failed",
        }

    time.sleep(1.0)
    if detect_safety_dialog_uia():
        dismiss_safety_dialog()
        time.sleep(0.8)
    wait_song_ui(eyes, name_hint=name, timeout=45)
    final = eyes.shot("ready_production", hud=f"READY {name}")
    vis = analyze_shot(final).to_dict() if final else {}
    try:
        from s1_tools.tracks_map import ensure_default_tracks, load_tracks
        from s1_tools.state import set_state

        ensure_default_tracks(song_dir)
        set_state(song_dir, "tracks_ready", note="Save As complete; Template instruments assumed")
        tracks = load_tracks(song_dir)
    except Exception:
        tracks = {}

    os.environ["S1_SONG_DIR"] = str(song_dir)
    os.environ["STUDIO_ONE_SONG"] = str(song_dir)

    resolved_song = song_file if song_file.is_file() else next(iter(song_dir.glob("*.song")), song_file)
    summary = {
        "ok": True,
        "name": name,
        "song_dir": str(song_dir),
        "song_file": str(resolved_song),
        "template": str(template_p),
        "s1_song_dir_env": str(song_dir),
        "tracks": tracks,
        "final_vision": vis,
        "final_shot": str(final) if final else None,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "note": "Opened Template → Save As new song → ready for production",
    }
    out = song_dir / "s1_jobs" / "session.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (song_dir / "s1_jobs" / "set_song_env.cmd").write_text(
        f"@echo off\r\nset S1_SONG_DIR={song_dir}\r\nset STUDIO_ONE_SONG={song_dir}\r\n",
        encoding="utf-8",
    )
    (song_dir / "s1_jobs" / "set_song_env.ps1").write_text(
        f'$env:S1_SONG_DIR = "{song_dir}"\n$env:STUDIO_ONE_SONG = "{song_dir}"\n',
        encoding="utf-8",
    )
    log(f"READY for production → {song_dir}")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Open Template → Save As new song → ready for production"
    )
    ap.add_argument("--name", default=None, help="New song name (default: date_time)")
    ap.add_argument(
        "--template",
        type=Path,
        default=None,
        help=f"Template.song path (default: {default_template_song()})",
    )
    ap.add_argument(
        "--songs-root",
        type=Path,
        default=None,
        help=f"Songs parent (default: {default_songs_root()})",
    )
    ap.add_argument(
        "--scaffold",
        action="store_true",
        help="(always on) Create MIDI/, s1_jobs/, NOTES, GATES under new song dir",
    )
    ap.add_argument(
        "--no-open",
        action="store_true",
        help="Only scaffold folders; do not launch S1 (dev)",
    )
    args = ap.parse_args()

    summary = start_new_song_from_template(
        name=args.name,
        template=args.template,
        songs_root_path=args.songs_root,
        open_s1=not args.no_open,
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
