#!/usr/bin/env python3
"""
Import .mid files into the open Studio One Song (no live arm required).

Preferred non-realtime handoff when live record/arm is flaky.

Studio One 6.x (Windows) primary path:
  Song → Import File…   shortcut: Ctrl+Shift+O

Legacy / other builds may expose File → Import Files…

Env:
  S1_SONG_DIR / --song-dir   song folder (MIDI/ default subdir)
  S1_REMOTE                  s1-remote root

Usage:
  py -3.12 tools/import_and_verify_midi.py --song-dir "D:\\Songs\\MySong"
  py -3.12 tools/import_and_verify_midi.py --song-dir ... --files drums.mid bass.mid
  py -3.12 tools/import_and_verify_midi.py --paths path\\a.mid path\\b.mid
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

from pywinauto import Desktop
from pywinauto.keyboard import send_keys

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from s1_tools.paths import ensure_s1remote_on_path, resolve_song_dir  # noqa: E402
from s1_tools.logutil import log, set_log_file  # noqa: E402
from s1_tools.eyes import Eyes  # noqa: E402
from s1_tools.paths import default_eyes_dir, default_log_path  # noqa: E402


DIALOG_TITLES = (
    "Import File",
    "Import Files",
    "Open",
    "Import",
    "Select files",
    "Select Files",
)


def find_file_dialog(timeout: float = 6.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for backend in ("uia", "win32"):
            desk = Desktop(backend=backend)
            for w in desk.windows():
                try:
                    t = (w.window_text() or "").strip()
                except Exception:
                    continue
                if not t:
                    continue
                for want in DIALOG_TITLES:
                    if want.lower() in t.lower() and w.is_visible():
                        return w, backend, t
        time.sleep(0.12)
    return None, None, None


def _dismiss_overlays() -> None:
    try:
        send_keys("{ESC}")
    except Exception:
        pass
    time.sleep(0.12)
    try:
        send_keys("{ESC}")
    except Exception:
        pass
    time.sleep(0.15)


def _open_import_dialog(open_menu_path, focus_studio_one) -> bool:
    """
    Try several open strategies until a file dialog appears.

    Order (Studio One 6.6 agent knowledge):
      1) Ctrl+Shift+O  (Song → Import File…)
      2) Menu Song → Import File…
      3) Menu File → Import Files… (legacy label)
      4) Alt+S then I / Enter
      5) Alt+F then I / Enter
    """
    strategies = []

    def via_hotkey_ctrl_shift_o() -> None:
        focus_studio_one()
        time.sleep(0.15)
        _dismiss_overlays()
        try:
            from s1remote.hotkeys import send_hotkey  # type: ignore

            send_hotkey(["ctrl", "shift"], "O")
        except Exception:
            send_keys("^+o")

    def via_song_menu() -> None:
        focus_studio_one()
        time.sleep(0.12)
        _dismiss_overlays()
        open_menu_path(["Song", "Import File…"], focus=True)

    def via_file_menu() -> None:
        focus_studio_one()
        time.sleep(0.12)
        _dismiss_overlays()
        open_menu_path(["File", "Import Files…"], focus=True)

    def via_alt_song_i() -> None:
        focus_studio_one()
        time.sleep(0.12)
        _dismiss_overlays()
        send_keys("%s")
        time.sleep(0.35)
        send_keys("i")
        time.sleep(0.2)
        send_keys("{ENTER}")

    def via_alt_file_i() -> None:
        focus_studio_one()
        time.sleep(0.12)
        _dismiss_overlays()
        send_keys("%f")
        time.sleep(0.35)
        send_keys("i")
        time.sleep(0.2)
        send_keys("{ENTER}")

    strategies = [
        ("Ctrl+Shift+O", via_hotkey_ctrl_shift_o),
        ("Song → Import File…", via_song_menu),
        ("File → Import Files…", via_file_menu),
        ("Alt+S I", via_alt_song_i),
        ("Alt+F I", via_alt_file_i),
    ]

    for name, fn in strategies:
        try:
            log(f"  import open try: {name}")
            fn()
        except Exception as e:
            log(f"  import open {name} exception: {e}")
            continue
        time.sleep(0.75)
        dlg, backend, title = find_file_dialog(timeout=3.5)
        if dlg is not None:
            log(f"  dialog open via {name}: {title!r} backend={backend}")
            return True
        # Close any partial menu before next try
        _dismiss_overlays()
        time.sleep(0.2)

    log("  FAIL: no import/open dialog after all open strategies")
    return False


def _type_path_into_dialog(path: Path) -> None:
    """Focus filename field and type absolute path (pywinauto-safe escaping)."""
    time.sleep(0.2)
    # Alt+N = File name field on standard Windows common dialogs
    send_keys("%n")
    time.sleep(0.15)
    pstr = str(path.resolve())
    send_keys("^a")
    time.sleep(0.05)
    safe = (
        pstr.replace("{", "{{")
        .replace("}", "}}")
        .replace("+", "{+}")
        .replace("^", "{^}")
        .replace("%", "{%}")
        .replace("~", "{~}")
        .replace("(", "{(}")
        .replace(")", "{)}")
    )
    send_keys(safe, with_spaces=True, pause=0.015)
    time.sleep(0.25)
    send_keys("{ENTER}")
    time.sleep(0.9)
    # Confirm any follow-up import options dialog
    send_keys("{ENTER}")
    time.sleep(0.5)
    send_keys("{ESC}")
    time.sleep(0.2)


def import_one_file(path: Path, *, open_menu_path, focus_studio_one) -> bool:
    path = Path(path).resolve()
    if not path.is_file():
        log(f"  missing file {path}")
        return False

    focus_studio_one()
    time.sleep(0.2)
    _dismiss_overlays()

    log(f"  Song → Import File… for {path.name}")
    if not _open_import_dialog(open_menu_path, focus_studio_one):
        return False

    dlg, backend, title = find_file_dialog(timeout=2.0)
    if dlg is None:
        log("  FAIL: dialog vanished before type")
        return False
    log(f"  dialog: {title!r} backend={backend}")

    try:
        dlg.set_focus()
    except Exception:
        pass

    try:
        _type_path_into_dialog(path)
    except Exception as e:
        log(f"  type path fail: {e}")
        _dismiss_overlays()
        return False

    log(f"  import attempted: {path.name}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Import MIDI into open S1 Song")
    ap.add_argument("--song-dir", type=Path, default=None)
    ap.add_argument("--midi-dir", type=Path, default=None, help="default: <song>/MIDI")
    ap.add_argument("--files", nargs="*", default=["drums.mid", "bass.mid"])
    ap.add_argument("--paths", nargs="*", default=[], help="Absolute/relative .mid paths")
    ap.add_argument("--s1-remote", type=Path, default=None)
    ap.add_argument("--no-eyes", action="store_true")
    args = ap.parse_args()

    song = resolve_song_dir(args.song_dir, required=not args.paths)
    ensure_s1remote_on_path(args.s1_remote)

    from s1remote.hotkeys import focus_studio_one  # noqa: E402
    from s1remote.menus import open_menu_path  # noqa: E402

    set_log_file(default_log_path(song, "midi_import_latest.log") if song else None)
    eyes = Eyes(default_eyes_dir(song) if song else Path.cwd() / "_vision" / "import", enabled=not args.no_eyes)

    paths: list[Path] = []
    for p in args.paths:
        paths.append(Path(p).expanduser().resolve())
    if song is not None:
        midi_dir = args.midi_dir or (song / "MIDI")
        for name in args.files:
            paths.append((midi_dir / name).resolve())

    # unique preserve order
    seen = set()
    uniq = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            uniq.append(p)

    log(f"Import MIDI into open Song  n={len(uniq)}")
    eyes.shot("import_start")
    ok = []
    for p in uniq:
        good = import_one_file(p, open_menu_path=open_menu_path, focus_studio_one=focus_studio_one)
        ok.append(good)
        eyes.shot(f"after_{p.stem}")
        time.sleep(0.3)

    report_path = (song / "MIDI_IMPORT_MONITOR_REPORT.md") if song else Path.cwd() / "MIDI_IMPORT_MONITOR_REPORT.md"
    lines = [
        f"# MIDI import monitor",
        f"- When: {datetime.now().isoformat()}",
        f"- Song: {song}",
        "",
    ]
    for p, g in zip(uniq, ok):
        lines.append(f"- {'OK' if g else 'FAIL'}: `{p}`")
    lines.append("")
    lines.append("Verify in Arrange: parts landed on intended instrument tracks.")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"report {report_path}")
    return 0 if all(ok) and ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
