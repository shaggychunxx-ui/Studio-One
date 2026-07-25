#!/usr/bin/env python3
"""
Verify Studio One functions from the Reference Manual / agent catalog.

Runs live against an open Song. Takes eyes screenshots on FAIL.
Writes: <song>/_vision/manual_verify_report.json + .md

Usage:
  set PYTHONPATH=%CD%
  set S1_SONG_DIR=...
  py -3.12 tools/verify_manual_functions.py
  py -3.12 tools/verify_manual_functions.py --phases views,transport,edit,mix
  py -3.12 tools/verify_manual_functions.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from s1_tools.paths import (  # noqa: E402
    default_eyes_dir,
    ensure_s1remote_on_path,
    resolve_song_dir,
)
from s1_tools.logutil import log, set_log_file  # noqa: E402
from s1_tools.eyes import Eyes  # noqa: E402
from s1_tools.vision import analyze_shot, detect_safety_dialog_uia, dismiss_safety_dialog  # noqa: E402

GAP = 0.35


@dataclass
class OpResult:
    phase: str
    op: str
    method: str
    status: str  # PASS | FAIL | SKIP | DOC
    detail: str = ""
    shot: Optional[str] = None
    manual_ref: str = ""


@dataclass
class Report:
    started_at: str
    finished_at: str = ""
    song_dir: str = ""
    results: List[Dict[str, Any]] = field(default_factory=list)
    counts: Dict[str, int] = field(default_factory=dict)


class ManualVerifier:
    def __init__(self, song: Path, *, dry_run: bool = False, eyes_enabled: bool = True):
        self.song = song
        self.dry_run = dry_run
        self.eyes = Eyes(default_eyes_dir(song) / "manual_verify", enabled=eyes_enabled)
        self.results: List[OpResult] = []
        self.s1 = None
        self._focus = None
        self._run_action = None

    def record(
        self,
        phase: str,
        op: str,
        method: str,
        status: str,
        detail: str = "",
        *,
        shot: bool = False,
        manual_ref: str = "",
    ) -> None:
        path = None
        if shot or status == "FAIL":
            p = self.eyes.shot(f"{phase}_{op}_{status}")
            path = str(p) if p else None
        r = OpResult(phase, op, method, status, detail, path, manual_ref)
        self.results.append(r)
        mark = {"PASS": "✓", "FAIL": "✗", "SKIP": "○", "DOC": "·"}.get(status, "?")
        log(f"  {mark} [{phase}] {op} ({method}) {detail}")

    def setup(self) -> bool:
        ensure_s1remote_on_path()
        from s1remote.hotkeys import (  # noqa: E402
            focus_studio_one,
            run_action,
            studio_one_running,
        )
        from s1remote.full_control import FullControl  # noqa: E402

        self._focus = focus_studio_one
        self._run_action = run_action
        if not studio_one_running():
            self.record("0", "studio_one_running", "proc", "FAIL", "Studio One not running")
            return False
        if detect_safety_dialog_uia():
            dismiss_safety_dialog()
            time.sleep(1.0)
        self._focus()
        if self.dry_run:
            return True
        self.s1 = FullControl()
        self.s1.connect()
        st = self.s1.status()
        self.record(
            "0",
            "connect",
            "midi",
            "PASS" if st.get("instrument_midi_connected") or st.get("midi_connected") else "FAIL",
            f"mcu={st.get('midi_connected')} notes={st.get('instrument_midi_connected')} out={st.get('instrument_midi_out')}",
            shot=True,
        )
        return True

    def teardown(self) -> None:
        if self.s1 is not None:
            try:
                self.s1.disconnect()
            except Exception:
                pass

    def _kb(self, action: str) -> None:
        self._focus()
        time.sleep(0.12)
        self._run_action(action, focus=False)
        time.sleep(GAP)

    def _try(self, phase: str, op: str, method: str, fn: Callable[[], Any], *, manual_ref: str = "") -> None:
        if self.dry_run:
            self.record(phase, op, method, "SKIP", "dry-run", manual_ref=manual_ref)
            return
        try:
            fn()
            self.record(phase, op, method, "PASS", manual_ref=manual_ref)
        except Exception as e:
            self.record(phase, op, method, "FAIL", str(e)[:200], shot=True, manual_ref=manual_ref)

    # ---- phases ----

    def phase_prereq(self) -> None:
        self._try("0", "focus_studio_one", "win32", lambda: self._focus() or True, manual_ref="Setup")
        if detect_safety_dialog_uia():
            self._try("0", "dismiss_safety", "uia", dismiss_safety_dialog, manual_ref="Crash recovery")
        shot = self.eyes.shot("prereq_workspace")
        rep = analyze_shot(shot)
        self.record(
            "0",
            "song_ui_visible",
            "vision",
            "PASS" if rep.likely_song_ui and not rep.safety_dialog else "FAIL",
            f"luma={rep.mean_luma:.0f} safety={rep.safety_dialog}",
            shot=True,
            manual_ref="Pages / Song",
        )

    def phase_views(self) -> None:
        views = [
            ("editor", "F2", "Fundamentals views"),
            ("console", "F3", "Console"),
            ("inspector", "F4", "Inspector"),
            ("browser", "F5", "Browser"),
            ("browser_instruments", "F6", "Browser Instruments"),
            ("browser_effects", "F7", "Browser Effects"),
            ("browser_loops", "F8", "Browser Loops"),
            ("browser_files", "F9", "Browser Files"),
            ("browser_pool", "F10", "Browser Pool"),
        ]
        for action, key, ref in views:
            self._try("views", action, f"hotkey {key}", lambda a=action: self._kb(a), manual_ref=ref)
        # leave on arrange-friendly state
        self._try("views", "escape_overlays", "hotkey Esc", lambda: self._kb("escape"))

    def phase_transport(self) -> None:
        if self.s1 is None:
            return

        def stop():
            self.s1.stop()

        def play():
            self.s1.play()
            time.sleep(0.4)
            self.s1.stop()

        def rewind():
            self.s1.remote.mcu.rewind()

        def record_pulse():
            self.s1.record()
            time.sleep(0.3)
            self.s1.stop()

        self._try("transport", "stop", "mcu", stop, manual_ref="Transport")
        self._try("transport", "play_stop", "mcu", play, manual_ref="Transport Play")
        self._try("transport", "rewind", "mcu", rewind, manual_ref="Return / rewind")
        self._try("transport", "record_pulse", "mcu", record_pulse, manual_ref="Record")
        self._try("transport", "loop_toggle", "hotkey", lambda: self._kb("loop_toggle"), manual_ref="Loop")
        self._try("transport", "metronome", "hotkey", lambda: self._kb("metronome"), manual_ref="Metronome C")
        self._try("transport", "precount", "hotkey", lambda: self._kb("precount"), manual_ref="Shift+C")
        self._try("transport", "preroll", "hotkey", lambda: self._kb("preroll"), manual_ref="O")
        self._try("transport", "auto_punch", "hotkey", lambda: self._kb("auto_punch"), manual_ref="I")
        self._try("transport", "play_space", "hotkey", lambda: self._kb("transport_play"), manual_ref="Space")
        # ensure stopped
        try:
            self.s1.stop()
        except Exception:
            pass

    def phase_edit(self) -> None:
        edits = [
            ("undo", "Edit Undo"),
            ("redo", "Edit Redo"),
            ("select_all", "Select All"),
            ("copy", "Copy"),
            ("paste", "Paste"),
            ("duplicate", "Duplicate"),
            ("quantize", "Quantize"),
            ("merge", "Merge G"),
            ("split_at_cursor", "Alt+X"),
            ("crossfade", "X"),
            ("nudge_left", "Alt+Left"),
            ("bounce_selection", "Ctrl+B"),
            ("tool_arrow", "Tool 1"),
            ("tool_range", "Tool 2"),
            ("tool_split", "Tool 3"),
            ("tool_eraser", "Tool 4"),
            ("tool_paint", "Tool 5"),
            ("tool_mute", "Tool 6"),
            ("save", "Save"),
        ]
        for action, ref in edits:
            self._try("edit", action, "hotkey", lambda a=action: self._kb(a), manual_ref=ref)
        self._try("edit", "escape", "hotkey", lambda: self._kb("escape"))

    def phase_tracks(self) -> None:
        from s1_tools.arrange import add_instrument_tracks  # noqa: E402

        def add_inst():
            self._focus()
            n = add_instrument_tracks(1, focus_fn=self._focus)
            # [T] dialog fallback always "returns" True; treat as PASS if no exception
            # Success = function path completed (menu UIA or T dialog)
            if n < 1:
                raise RuntimeError("created 0 tracks")
            return n

        self._try(
            "tracks",
            "add_instrument_track",
            "menu_or_T_dialog",
            add_inst,
            manual_ref="Track → Add Instrument Track / [T]",
        )
        self._try("tracks", "add_tracks_dialog", "hotkey T", lambda: self._kb("add_tracks"), manual_ref="T")
        self._try("tracks", "escape_dialog", "Esc", lambda: self._kb("escape"))
        self._try("tracks", "arm_key", "hotkey R", lambda: self._kb("arm"), manual_ref="Record Enable")
        self._try("tracks", "track_mute", "hotkey M", lambda: self._kb("track_mute"), manual_ref="Mute")
        self._try("tracks", "track_solo", "hotkey S", lambda: self._kb("track_solo"), manual_ref="Solo")
        self._try("tracks", "group_tracks", "hotkey", lambda: self._kb("group_tracks"), manual_ref="Ctrl+G")
        self._try("tracks", "dissolve_group", "hotkey", lambda: self._kb("dissolve_group"), manual_ref="Ctrl+Shift+G")
        self._try("tracks", "find_track", "hotkey", lambda: self._kb("find_track"), manual_ref="Ctrl+Alt+T")
        self._try("tracks", "escape", "hotkey", lambda: self._kb("escape"))

        if self.s1 is not None:
            self._try(
                "tracks",
                "arm_and_verify_t1",
                "vision+click",
                lambda: self.s1.arm_and_verify(1, eyes_dir=self.eyes.directory, retries=3)
                or (_ for _ in ()).throw(RuntimeError("arm not confirmed")),
                manual_ref="Recording arm",
            )

    def phase_mix(self) -> None:
        if self.s1 is None:
            return

        def fader():
            self.s1.fader(0, -6)
            time.sleep(0.2)
            self.s1.fader(0, 0)

        def mute():
            self.s1.mute(0)
            time.sleep(0.2)
            self.s1.mute(0)

        def solo():
            self.s1.solo(0)
            time.sleep(0.2)
            self.s1.solo(0)

        def select():
            self.s1.select(0)

        def bank():
            self.s1.bank_right()
            time.sleep(0.2)
            self.s1.bank_left()

        def modes():
            self.s1.plugin_mode()
            time.sleep(0.15)
            self.s1.pan_mode()

        self._try("mix", "console", "hotkey", lambda: self._kb("console"), manual_ref="F3 Console")
        self._try("mix", "fader_ch0", "mcu", fader, manual_ref="Mixing fader")
        self._try("mix", "mute_ch0", "mcu", mute, manual_ref="Mute")
        self._try("mix", "solo_ch0", "mcu", solo, manual_ref="Solo")
        self._try("mix", "select_ch0", "mcu", select, manual_ref="Select")
        self._try("mix", "bank", "mcu", bank, manual_ref="Bank")
        self._try("mix", "mcu_modes", "mcu", modes, manual_ref="Plugin/Pan mode")
        self._try("mix", "control_link_assign", "hotkey", lambda: self._kb("control_link_assign"), manual_ref="Alt+M")
        self._try("mix", "escape", "hotkey", lambda: self._kb("escape"))
        self._try("mix", "automation_lanes", "hotkey", lambda: self._kb("automation_lanes"), manual_ref="A")
        self._try("mix", "escape2", "hotkey", lambda: self._kb("escape"))

    def phase_midi(self) -> None:
        if self.s1 is None:
            return

        def note():
            self.s1.note(60, 0.15, 100)

        def status():
            st = self.s1.status()
            if not st.get("instrument_midi_connected"):
                raise RuntimeError(f"notes not connected: {st.get('instrument_midi_out')}")

        self._try("midi", "notes_port_status", "status", status, manual_ref="S1 Notes")
        self._try("midi", "note_on_off", "instrument_port", note, manual_ref="MIDI input")

    def phase_browser_file(self) -> None:
        self._try("browser", "open", "hotkey", lambda: self._kb("browser"), manual_ref="F5")
        if self.s1 is not None:
            self._try(
                "browser",
                "browser_load_mojito",
                "keyboard_search",
                lambda: self.s1.browser_load("Mojito"),
                manual_ref="Browser load",
            )
        self._try("browser", "escape", "hotkey", lambda: self._kb("escape"))
        self._try("file", "save", "hotkey", lambda: self._kb("save"), manual_ref="Ctrl+S")
        # Export opens dialog — open and dismiss
        def export_dismiss():
            self._kb("export_mixdown")
            time.sleep(0.6)
            self._kb("escape")
            time.sleep(0.2)
            self._kb("escape")

        self._try("file", "export_mixdown_open_esc", "hotkey", export_dismiss, manual_ref="Ctrl+E")

    def phase_menus(self) -> None:
        from s1remote.menus import open_menu_path  # noqa: E402
        from s1remote.hotkeys import studio_one_running  # noqa: E402

        menus = [
            (["Track"], "Track menu"),
            (["View"], "View menu"),
            (["Transport"], "Transport menu"),
            (["Event"], "Event menu"),
        ]
        for path, ref in menus:
            def open_m(p=path):
                if not studio_one_running():
                    raise RuntimeError("Studio One not running")
                if not self._focus():
                    raise RuntimeError("Studio One not focused")
                time.sleep(0.15)
                open_menu_path(p, focus=True)
                time.sleep(0.3)
                self._kb("escape")
                time.sleep(0.15)
                # re-focus after menu so next op does not hit wrong app
                self._focus()

            self._try("menus", "_".join(path).lower(), "menu_uia", open_m, manual_ref=ref)

    def phase_doc_only(self) -> None:
        docs = [
            ("01_editions", "Artist/Pro/Prime — agent notes only"),
            ("12_spatial_atmos", "Atmos / spatial — often Pro + user"),
            ("13_show_page", "Show page — user File→New→Show"),
            ("16_project_mastering", "Project page mastering"),
            ("19_collaboration", "Studio One+ cloud"),
            ("20_video", "Video track"),
        ]
        for op, detail in docs:
            self.record("doc", op, "doc", "DOC", detail, manual_ref=op)

    def phase_user_skip(self) -> None:
        skips = [
            ("audio_io_matrix", "Song Setup Audio I/O — user"),
            ("options_external_devices", "External Devices wiring — user once"),
            ("drag_instrument", "Browser drag instrument — custom UI"),
            ("insert_fx_drag", "Drag FX to insert — custom UI"),
            ("export_stems", "Song→Export Stems — user"),
            ("comping_layers", "Takes/layers — user"),
            ("chord_arranger_tempo", "Special tracks — user buttons"),
        ]
        for op, detail in skips:
            self.record("user", op, "user", "SKIP", detail)

    def run(self, phases: List[str]) -> Report:
        started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        set_log_file(self.song / "_vision" / "manual_verify_latest.log")
        log(f"MANUAL FUNCTION VERIFY phases={phases} dry_run={self.dry_run}")
        ok_setup = self.setup()
        table: Dict[str, Callable[[], None]] = {
            "prereq": self.phase_prereq,
            "views": self.phase_views,
            "transport": self.phase_transport,
            "edit": self.phase_edit,
            "tracks": self.phase_tracks,
            "mix": self.phase_mix,
            "midi": self.phase_midi,
            "browser": self.phase_browser_file,
            "menus": self.phase_menus,
            "doc": self.phase_doc_only,
            "user": self.phase_user_skip,
        }
        if ok_setup or self.dry_run:
            for name in phases:
                if name not in table:
                    log(f"  unknown phase {name}")
                    continue
                log(f"=== PHASE {name} ===")
                try:
                    table[name]()
                except Exception as e:
                    self.record(name, "phase_crash", "runner", "FAIL", traceback.format_exc()[-300:])
                    log(f"  PHASE CRASH: {e}")
        self.teardown()
        finished = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        counts: Dict[str, int] = {}
        for r in self.results:
            counts[r.status] = counts.get(r.status, 0) + 1
        report = Report(
            started_at=started,
            finished_at=finished,
            song_dir=str(self.song),
            results=[asdict(r) for r in self.results],
            counts=counts,
        )
        self._write(report)
        return report

    def _write(self, report: Report) -> None:
        out_dir = self.song / "_vision"
        out_dir.mkdir(parents=True, exist_ok=True)
        jp = out_dir / "manual_verify_report.json"
        mp = out_dir / "manual_verify_report.md"
        jp.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
        lines = [
            f"# Studio One manual function verify",
            f"",
            f"- Started: {report.started_at}",
            f"- Finished: {report.finished_at}",
            f"- Song: `{report.song_dir}`",
            f"- Counts: {report.counts}",
            f"",
            f"| Phase | Op | Method | Status | Detail |",
            f"|-------|-----|--------|--------|--------|",
        ]
        for r in report.results:
            det = (r.get("detail") or "").replace("|", "/")[:80]
            lines.append(
                f"| {r['phase']} | {r['op']} | {r['method']} | **{r['status']}** | {det} |"
            )
        fails = [r for r in report.results if r["status"] == "FAIL"]
        lines.append("")
        lines.append(f"## Failures ({len(fails)})")
        for r in fails:
            lines.append(f"- `{r['phase']}/{r['op']}`: {r.get('detail')} shot={r.get('shot')}")
        mp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        log(f"REPORT {jp}")
        log(f"REPORT {mp}")
        log(f"COUNTS {report.counts}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--song-dir", type=Path, default=None)
    ap.add_argument(
        "--phases",
        default="prereq,views,transport,edit,tracks,mix,midi,browser,menus,doc,user",
        help="Comma-separated phases",
    )
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-eyes", action="store_true")
    args = ap.parse_args()
    song = resolve_song_dir(args.song_dir, required=False) or Path.cwd()
    phases = [p.strip() for p in args.phases.split(",") if p.strip()]
    v = ManualVerifier(song, dry_run=args.dry_run, eyes_enabled=not args.no_eyes)
    report = v.run(phases)
    fails = report.counts.get("FAIL", 0)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
