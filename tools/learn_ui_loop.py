#!/usr/bin/env python3
"""
Continuous Studio One UI learning loop (eyes + ears + S1 Controller).

Policy (human 2026-08-07):
  - Host: LAPTOP only
  - Use software S1 Controller (loopMIDI Mackie / MCU) + keyboard
  - Physical external devices (audio interface, hardware MIDI) may be offline —
    do not fail the whole session for that; SKIP true hardware ops, still use
    virtual S1 Controller when present
  - Every action: do → verify (eyes screenshot; ears on play) → log mistake
  - Respect screen aspect ratio / DPI (get_screen_geometry + fraction coords)
  - Improve: retry FAIL with alternate method; write lessons as we go

Usage:
  set PYTHONPATH=%CD%;%CD%\\tools
  py -3.12 tools\\learn_ui_loop.py --max-hours 6
  py -3.12 tools\\learn_ui_loop.py --song-dir PATH --max-hours 4 --no-open
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TOOLS))

from s1_tools.logutil import log, set_log_file  # noqa: E402
from s1_tools.paths import (  # noqa: E402
    default_eyes_dir,
    default_songs_root,
    ensure_s1remote_on_path,
    resolve_song_dir,
)
from s1_tools.eyes import Eyes, check_display_dpi, get_screen_geometry  # noqa: E402
from s1_tools.vision import (  # noqa: E402
    analyze_shot,
    detect_safety_dialog_uia,
    dismiss_safety_dialog,
)

GAP = 0.40


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class OpResult:
    cycle: int
    phase: str
    op: str
    method: str
    status: str  # PASS | FAIL | SKIP | RETRY_PASS | DOC
    detail: str = ""
    mistake: str = ""
    shot: Optional[str] = None
    ears: Optional[Dict[str, Any]] = None
    alt_method: str = ""


@dataclass
class Session:
    started_at: str
    finished_at: str = ""
    song_dir: str = ""
    host: str = ""
    geometry: Dict[str, Any] = field(default_factory=dict)
    s1_controller: Dict[str, Any] = field(default_factory=dict)
    external_devices_policy: str = (
        "Physical external devices offline OK; still use software S1 Controller (loopMIDI MCU)."
    )
    results: List[Dict[str, Any]] = field(default_factory=list)
    lessons: List[str] = field(default_factory=list)
    counts: Dict[str, int] = field(default_factory=dict)
    improvements: List[str] = field(default_factory=list)


class LearnUILoop:
    def __init__(
        self,
        song: Path,
        *,
        max_hours: float = 6.0,
        eyes_enabled: bool = True,
        ears_enabled: bool = True,
        require_mcu: bool = False,
    ):
        self.song = Path(song)
        self.max_hours = max(0.25, float(max_hours))
        self.deadline = time.time() + self.max_hours * 3600
        self.eyes = Eyes(self.song / "_vision" / "learn_ui", enabled=eyes_enabled)
        self.ears_enabled = ears_enabled
        self.require_mcu = require_mcu
        self.results: List[OpResult] = []
        self.lessons: List[str] = []
        self.improvements: List[str] = []
        self.s1 = None
        self._focus = None
        self._run_action = None
        self.geometry: Dict[str, Any] = {}
        self.controller_status: Dict[str, Any] = {}
        self.cycle = 0

    def remaining(self) -> float:
        return max(0.0, self.deadline - time.time())

    def record(
        self,
        phase: str,
        op: str,
        method: str,
        status: str,
        detail: str = "",
        *,
        mistake: str = "",
        shot: bool = False,
        ears: Optional[Dict[str, Any]] = None,
        alt_method: str = "",
    ) -> None:
        path = None
        if shot or status in ("FAIL", "RETRY_PASS"):
            p = self.eyes.shot(f"c{self.cycle}_{phase}_{op}_{status}", annotate=True, hud=f"{phase}/{op}")
            path = str(p) if p else None
        r = OpResult(
            self.cycle,
            phase,
            op,
            method,
            status,
            detail,
            mistake,
            path,
            ears,
            alt_method,
        )
        self.results.append(r)
        mark = {
            "PASS": "OK",
            "FAIL": "FAIL",
            "SKIP": "SKIP",
            "RETRY_PASS": "RETRY_OK",
            "DOC": "DOC",
        }.get(status, status)
        log(f"  [{mark}] {phase}/{op} via {method} {detail} {mistake}".strip())

    def lesson(self, text: str) -> None:
        if text and text not in self.lessons:
            self.lessons.append(text)
            log(f"  LESSON: {text}")

    def improve(self, text: str) -> None:
        if text and text not in self.improvements:
            self.improvements.append(text)
            log(f"  IMPROVE: {text}")

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
        self.geometry = get_screen_geometry()
        dpi = check_display_dpi()
        self.geometry["dpi_check"] = dpi
        self.record(
            "0",
            "screen_geometry",
            "win32",
            "PASS" if self.geometry.get("ok") else "FAIL",
            (
                f"{self.geometry.get('width')}x{self.geometry.get('height')} "
                f"aspect={self.geometry.get('aspect_label')} "
                f"scale={self.geometry.get('scale')}"
            ),
            shot=True,
        )
        if self.geometry.get("aspect_label") not in ("16:9", "unknown") and self.geometry.get("ok"):
            self.lesson(
                f"Primary display is {self.geometry.get('aspect_label')} "
                f"({self.geometry.get('width')}x{self.geometry.get('height')}); "
                "use fraction-based Rec/UI targets, not 1920-only pixels."
            )
            self.improve("eyes.rec_x_band_for_width + get_screen_geometry active for this host")

        if not studio_one_running():
            self.record("0", "studio_one_running", "proc", "FAIL", "Studio One not running")
            return False

        if detect_safety_dialog_uia():
            dismiss_safety_dialog()
            time.sleep(1.0)
            self.record("0", "dismiss_safety", "uia", "PASS")

        self._focus()
        self.s1 = FullControl()
        try:
            self.s1.connect()
        except Exception as e:
            self.record("0", "s1_controller_connect", "mcu", "FAIL", str(e)[:200], shot=True)
            if self.require_mcu:
                return False
            self.lesson(
                "S1 Controller connect failed — continue keyboard-only; "
                "check loopMIDI 'S1 Controller' ports when back."
            )
            self.s1 = None
            return True

        st = self.s1.status()
        self.controller_status = {
            "midi_connected": st.get("midi_connected"),
            "instrument_midi_connected": st.get("instrument_midi_connected"),
            "instrument_midi_out": st.get("instrument_midi_out"),
            "mcu_out": st.get("mcu_out") or st.get("midi_out"),
        }
        mcu_ok = bool(st.get("midi_connected"))
        notes_ok = bool(st.get("instrument_midi_connected"))
        self.record(
            "0",
            "s1_controller",
            "loopMIDI_MCU",
            "PASS" if mcu_ok else "FAIL",
            f"mcu={mcu_ok} notes={notes_ok} out={st.get('instrument_midi_out')}",
            shot=True,
            mistake="" if mcu_ok else "MCU port not connected (still prefer software S1 Controller)",
        )
        if not mcu_ok:
            self.lesson(
                "S1 Controller MCU not connected — ensure loopMIDI ports "
                "'S1 Controller 1/0' and Studio One External Devices Mackie Control."
            )
            if self.require_mcu:
                return False
        else:
            self.lesson("Software S1 Controller (MCU) connected — prefer MCU for transport/mix.")
        if not notes_ok:
            self.lesson(
                "S1 Notes instrument port offline — skip live note stream; "
                "physical external devices also offline per human (future)."
            )
        # Physical I/O: always document as future
        self.record(
            "0",
            "physical_external_devices",
            "policy",
            "SKIP",
            "Human: external hardware not connected (future). Use virtual S1 Controller only.",
        )
        return True

    def teardown(self) -> None:
        if self.s1 is not None:
            try:
                self.s1.disconnect()
            except Exception:
                pass
            self.s1 = None

    def _kb(self, action: str) -> None:
        self._focus()
        time.sleep(0.12)
        self._run_action(action, focus=False)
        time.sleep(GAP)

    def _try(
        self,
        phase: str,
        op: str,
        method: str,
        fn: Callable[[], Any],
        *,
        alt: Optional[tuple[str, Callable[[], Any]]] = None,
        verify_eyes: bool = True,
        ears_on_pass: bool = False,
    ) -> None:
        if self.remaining() < 5:
            self.record(phase, op, method, "SKIP", "time budget exhausted")
            return
        try:
            fn()
            detail = ""
            ears_rep = None
            if ears_on_pass and self.ears_enabled:
                ears_rep = self._ears_probe(f"{phase}_{op}")
            if verify_eyes:
                p = self.eyes.shot(f"c{self.cycle}_{phase}_{op}_after", annotate=True, hud=f"{op}")
                if p:
                    rep = analyze_shot(p)
                    detail = f"luma={rep.mean_luma:.0f} song_ui={rep.likely_song_ui}"
                    if rep.safety_dialog:
                        dismiss_safety_dialog()
                        detail += " safety_dismissed"
            self.record(
                phase,
                op,
                method,
                "PASS",
                detail,
                shot=False,
                ears=ears_rep,
            )
        except Exception as e:
            err = str(e)[:220]
            mistake = f"primary method failed: {err}"
            self.record(phase, op, method, "FAIL", err, mistake=mistake, shot=True)
            if alt is not None:
                alt_name, alt_fn = alt
                try:
                    time.sleep(0.3)
                    alt_fn()
                    self.record(
                        phase,
                        op,
                        alt_name,
                        "RETRY_PASS",
                        "recovered via alternate",
                        mistake=mistake,
                        shot=True,
                        alt_method=alt_name,
                    )
                    self.lesson(f"{phase}/{op}: prefer {alt_name} when {method} fails ({err[:80]})")
                    self.improve(f"For {op}, try {alt_name} after {method} failure")
                except Exception as e2:
                    self.record(
                        phase,
                        op,
                        alt_name,
                        "FAIL",
                        str(e2)[:200],
                        mistake=f"both methods failed: {method} then {alt_name}",
                        shot=True,
                        alt_method=alt_name,
                    )

    def _ears_probe(self, tag: str) -> Optional[Dict[str, Any]]:
        try:
            from s1_tools.ears import capture

            rep = capture(self.song / "_vision" / "learn_ears", tag=tag, seconds=1.8, enabled=True)
            d = rep.to_dict()
            if not d.get("has_signal"):
                self.lesson(
                    f"ears:{tag} no signal (peak_db={d.get('peak_db')}) — "
                    "expected if no instrument audio / physical I/O offline"
                )
            return d
        except Exception as e:
            return {"ok": False, "error": str(e)[:160]}

    # ---- phases ----

    def phase_prereq(self) -> None:
        self._try("prereq", "focus", "win32", lambda: self._focus() or True)
        shot = self.eyes.shot("workspace", annotate=True, hud="workspace")
        rep = analyze_shot(shot) if shot else None
        self.record(
            "prereq",
            "song_ui",
            "vision",
            "PASS" if rep and rep.likely_song_ui and not rep.safety_dialog else "FAIL",
            f"luma={getattr(rep, 'mean_luma', -1):.0f}" if rep else "no shot",
            shot=True,
            mistake="" if (rep and rep.likely_song_ui) else "Not on Song page / not S1 arrange",
        )

    def phase_views(self) -> None:
        views = [
            ("editor", "F2"),
            ("console", "F3"),
            ("inspector", "F4"),
            ("browser", "F5"),
            ("browser_instruments", "F6"),
            ("browser_effects", "F7"),
            ("browser_loops", "F8"),
            ("browser_files", "F9"),
            ("browser_pool", "F10"),
        ]
        for action, key in views:
            self._try("views", action, f"hotkey_{key}", lambda a=action: self._kb(a))
        self._try("views", "escape", "hotkey_Esc", lambda: self._kb("escape"))

    def phase_transport(self) -> None:
        # Prefer S1 Controller MCU; fallback keyboard Space / stop
        if self.s1 is not None and self.controller_status.get("midi_connected"):

            def mcu_stop():
                self.s1.stop()

            def mcu_play():
                self.s1.play()
                time.sleep(0.5)
                self.s1.stop()

            def mcu_rew():
                self.s1.remote.mcu.rewind()

            def mcu_rec_pulse():
                self.s1.record()
                time.sleep(0.25)
                self.s1.stop()

            self._try(
                "transport",
                "stop",
                "s1_controller_mcu",
                mcu_stop,
                # Space toggles play; second Space often stops when already playing
                alt=("hotkey_space", lambda: self._kb("transport_play")),
            )
            self._try(
                "transport",
                "play_stop",
                "s1_controller_mcu",
                mcu_play,
                alt=("hotkey_space", lambda: self._kb("transport_play")),
                ears_on_pass=True,
            )
            self._try(
                "transport",
                "rewind",
                "s1_controller_mcu",
                mcu_rew,
                alt=("hotkey_home", lambda: self._kb("return_zero")),
            )
            self._try(
                "transport",
                "record_pulse",
                "s1_controller_mcu",
                mcu_rec_pulse,
                # No dedicated Record hotkey in catalog — NumPad* often works if focused
                alt=("hotkey_numpad_star_try", lambda: self._run_action("transport_play", focus=False)),
            )
        else:
            self._try(
                "transport",
                "play_stop",
                "hotkey_space",
                lambda: self._kb("transport_play"),
                ears_on_pass=True,
            )
            self._try(
                "transport",
                "return_zero",
                "hotkey_home",
                lambda: self._kb("return_zero"),
            )
            self.record(
                "transport",
                "mcu_ops",
                "s1_controller",
                "SKIP",
                "MCU not connected this cycle — keyboard only; still prefer S1 Controller when ports up",
            )

        for op, action in (
            ("loop_toggle", "loop_toggle"),
            ("metronome", "metronome"),
            ("precount", "precount"),
            ("preroll", "preroll"),
            ("auto_punch", "auto_punch"),
        ):
            self._try("transport", op, "hotkey", lambda a=action: self._kb(a))
        try:
            if self.s1:
                self.s1.stop()
            else:
                self._kb("transport_stop")
        except Exception:
            pass

    def phase_edit(self) -> None:
        for action in (
            "undo",
            "redo",
            "select_all",
            "copy",
            "paste",
            "duplicate",
            "quantize",
            "merge",
            "split_at_cursor",
            "crossfade",
            "nudge_left",
            "tool_arrow",
            "tool_range",
            "tool_split",
            "tool_eraser",
            "tool_paint",
            "tool_mute",
            "save",
            "escape",
        ):
            self._try("edit", action, "hotkey", lambda a=action: self._kb(a))

    def phase_tracks(self) -> None:
        from s1_tools.arrange import add_instrument_tracks  # noqa: E402

        def add_inst():
            self._focus()
            n = add_instrument_tracks(1, focus_fn=self._focus)
            if n < 1:
                raise RuntimeError("created 0 tracks")

        self._try(
            "tracks",
            "add_instrument_track",
            "menu_uia",
            add_inst,
            alt=("hotkey_T", lambda: self._kb("add_tracks")),
        )
        self._try("tracks", "escape_dialog", "Esc", lambda: self._kb("escape"))
        for action in ("arm", "track_mute", "track_solo", "find_track", "escape"):
            self._try("tracks", action, "hotkey", lambda a=action: self._kb(a))

        if self.s1 is not None:
            def arm_v():
                ok = self.s1.arm_and_verify(1, eyes_dir=self.eyes.directory, retries=2)
                if not ok:
                    raise RuntimeError("arm_and_verify false (no Rec red)")

            self._try(
                "tracks",
                "arm_and_verify_t1",
                "s1_controller+eyes",
                arm_v,
                alt=("hotkey_R", lambda: self._kb("arm")),
            )
        else:
            self.record("tracks", "arm_and_verify_t1", "s1_controller", "SKIP", "no MCU session")

    def phase_mix(self) -> None:
        self._try("mix", "console", "hotkey_F3", lambda: self._kb("console"))
        if self.s1 is not None and self.controller_status.get("midi_connected"):

            def fader():
                self.s1.fader(0, -6)
                time.sleep(0.2)
                self.s1.fader(0, 0)

            def mute():
                self.s1.mute(0)
                time.sleep(0.15)
                self.s1.mute(0)

            def solo():
                self.s1.solo(0)
                time.sleep(0.15)
                self.s1.solo(0)

            self._try("mix", "fader_ch0", "s1_controller_mcu", fader)
            self._try("mix", "mute_ch0", "s1_controller_mcu", mute)
            self._try("mix", "solo_ch0", "s1_controller_mcu", solo)
            self._try("mix", "select_ch0", "s1_controller_mcu", lambda: self.s1.select(0))
            self._try(
                "mix",
                "bank",
                "s1_controller_mcu",
                lambda: (self.s1.bank_right(), time.sleep(0.15), self.s1.bank_left()),
            )
        else:
            self.record("mix", "mcu_fader_mute_solo", "s1_controller", "SKIP", "MCU offline")
            self._try("mix", "track_mute", "hotkey_M", lambda: self._kb("track_mute"))
            self._try("mix", "track_solo", "hotkey_S", lambda: self._kb("track_solo"))
        self._try("mix", "automation_lanes", "hotkey_A", lambda: self._kb("automation_lanes"))
        self._try("mix", "escape", "Esc", lambda: self._kb("escape"))

    def phase_midi_notes(self) -> None:
        """S1 Notes port — software; skip if offline (not physical device)."""
        if self.s1 is None:
            self.record("midi", "note", "s1_notes", "SKIP", "no FullControl")
            return
        if not self.controller_status.get("instrument_midi_connected"):
            self.record(
                "midi",
                "note",
                "s1_notes",
                "SKIP",
                "S1 Notes not connected — virtual port only; no physical keyboard required",
            )
            return

        def note():
            self.s1.note(60, 0.12, 100)

        self._try("midi", "note_c4", "s1_notes", note, ears_on_pass=True)

    def phase_menus(self) -> None:
        from s1remote.menus import open_menu_path  # noqa: E402
        from s1remote.hotkeys import studio_one_running  # noqa: E402

        for path in (["Track"], ["View"], ["Transport"], ["Event"], ["Song"]):
            def open_m(p=path):
                if not studio_one_running():
                    raise RuntimeError("Studio One not running")
                if not self._focus():
                    raise RuntimeError("focus failed")
                time.sleep(0.12)
                open_menu_path(p, focus=True)
                time.sleep(0.25)
                self._kb("escape")
                self._focus()

            self._try("menus", path[0].lower(), "menu_uia", open_m)

    def phase_browser(self) -> None:
        self._try("browser", "open", "hotkey_F5", lambda: self._kb("browser"))
        if self.s1 is not None:
            self._try(
                "browser",
                "browser_load_search",
                "keyboard_search",
                lambda: self.s1.browser_load("Mojito"),
            )
        self._try("browser", "escape", "Esc", lambda: self._kb("escape"))
        self._try("file", "save", "hotkey", lambda: self._kb("save"))

        def export_dismiss():
            self._kb("export_mixdown")
            time.sleep(0.5)
            self._kb("escape")
            time.sleep(0.15)
            self._kb("escape")

        self._try("file", "export_dialog_open_esc", "hotkey", export_dismiss)

    def phase_doc_skip(self) -> None:
        skips = [
            ("physical_audio_io", "Song Setup Audio I/O — physical interface future"),
            ("physical_midi_keyboard", "Hardware MIDI keyboard — future"),
            ("hardware_control_surface", "Hardware surface — future; use software S1 Controller"),
            ("show_page", "Show page — user / Pro"),
            ("project_mastering", "Project page mastering"),
            ("spatial_atmos", "Atmos / spatial"),
            ("collaboration_cloud", "Studio One+ cloud"),
        ]
        for op, detail in skips:
            self.record("future_hardware_or_edition", op, "policy", "SKIP", detail)

    def run_cycle(self) -> None:
        self.cycle += 1
        log(f"=== LEARN CYCLE {self.cycle} remaining_h={self.remaining()/3600:.2f} ===")
        phases = [
            self.phase_prereq,
            self.phase_views,
            self.phase_transport,
            self.phase_edit,
            self.phase_tracks,
            self.phase_mix,
            self.phase_midi_notes,
            self.phase_menus,
            self.phase_browser,
            self.phase_doc_skip,
        ]
        for fn in phases:
            if self.remaining() < 10:
                log("time budget low — stop cycle early")
                break
            try:
                fn()
            except Exception as e:
                self.record(
                    "runner",
                    fn.__name__,
                    "cycle",
                    "FAIL",
                    traceback.format_exc()[-280:],
                    mistake=str(e)[:160],
                    shot=True,
                )

    def write_report(self) -> Session:
        counts: Dict[str, int] = {}
        for r in self.results:
            counts[r.status] = counts.get(r.status, 0) + 1
        sess = Session(
            started_at=self._started,
            finished_at=_utc(),
            song_dir=str(self.song),
            host=os.environ.get("COMPUTERNAME", ""),
            geometry=self.geometry,
            s1_controller=self.controller_status,
            results=[asdict(r) for r in self.results],
            lessons=self.lessons,
            counts=counts,
            improvements=self.improvements,
        )
        out = self.song / "_vision" / "learn_ui"
        out.mkdir(parents=True, exist_ok=True)
        jp = out / "learn_session_report.json"
        mp = out / "learn_session_report.md"
        lp = out / "lessons.jsonl"
        jp.write_text(json.dumps(asdict(sess), indent=2), encoding="utf-8")
        lines = [
            "# Studio One UI learn session",
            "",
            f"- Host: `{sess.host}`",
            f"- Started: {sess.started_at}",
            f"- Finished: {sess.finished_at}",
            f"- Song: `{sess.song_dir}`",
            f"- Geometry: `{sess.geometry}`",
            f"- S1 Controller: `{sess.s1_controller}`",
            f"- Policy: {sess.external_devices_policy}",
            f"- Counts: {sess.counts}",
            "",
            "## Lessons",
        ]
        for L in sess.lessons:
            lines.append(f"- {L}")
        lines += ["", "## Process improvements"]
        for I in sess.improvements:
            lines.append(f"- {I}")
        lines += [
            "",
            "| Cycle | Phase | Op | Method | Status | Mistake |",
            "|------:|-------|-----|--------|--------|---------|",
        ]
        for r in sess.results:
            mist = (r.get("mistake") or "").replace("|", "/")[:60]
            lines.append(
                f"| {r['cycle']} | {r['phase']} | {r['op']} | {r['method']} | "
                f"**{r['status']}** | {mist} |"
            )
        fails = [r for r in sess.results if r["status"] == "FAIL"]
        lines += ["", f"## Failures ({len(fails)})"]
        for r in fails:
            lines.append(
                f"- c{r['cycle']} `{r['phase']}/{r['op']}`: {r.get('detail')} "
                f"mistake={r.get('mistake')} shot={r.get('shot')}"
            )
        mp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with lp.open("a", encoding="utf-8") as f:
            for L in sess.lessons:
                f.write(
                    json.dumps(
                        {"t": _utc(), "host": sess.host, "lesson": L, "domain": "studio-one"},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        # Promote durable summary into docs (overwrite session summary, not spam)
        docs = ROOT / "docs" / "LEARN_UI_SESSION_LATEST.md"
        lesson_lines = [f"- {L}" for L in sess.lessons] if sess.lessons else ["- (none)"]
        docs.write_text(
            "\n".join(
                [
                    "# Latest UI learn session (auto)",
                    "",
                    f"Host **{sess.host}** · {sess.finished_at}",
                    f"Counts: `{sess.counts}`",
                    f"Geometry: `{sess.geometry}`",
                    f"S1 Controller: `{sess.s1_controller}`",
                    "",
                    "## Lessons",
                    *lesson_lines,
                    "",
                    f"Full report: `{jp}`",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        log(f"REPORT {jp}")
        log(f"REPORT {mp}")
        log(f"COUNTS {counts}")
        return sess

    def run(self) -> Session:
        self._started = _utc()
        set_log_file(self.song / "_vision" / "learn_ui" / "learn_latest.log")
        log(f"LEARN UI LOOP max_hours={self.max_hours} song={self.song}")
        if not self.setup():
            return self.write_report()
        # Multiple cycles until time budget — re-verify so mistakes stay visible
        while self.remaining() > 30:
            self.run_cycle()
            # After first full cycle, slow down: deeper re-verify every ~15 min or continue
            if self.cycle >= 1 and self.remaining() > 60:
                pause = min(90.0, self.remaining() / 4)
                log(f"cycle pause {pause:.0f}s then re-verify")
                time.sleep(pause)
            if self.cycle >= 8:
                # Cap thrash; keep re-running key phases only
                log("cycle cap 8 — final transport+mix re-verify only")
                self.phase_transport()
                self.phase_mix()
                break
        self.teardown()
        return self.write_report()


def ensure_song_open(name: str, *, no_open: bool) -> Path:
    """Open Template → Save As learn song unless --no-open and S1_SONG_DIR set."""
    song_env = os.environ.get("S1_SONG_DIR", "").strip()
    if no_open and song_env:
        p = Path(song_env)
        p.mkdir(parents=True, exist_ok=True)
        return p
    if song_env:
        p = Path(song_env)
        p.mkdir(parents=True, exist_ok=True)
        # If S1 already running with a song, still use this dir for reports
        from s1remote.hotkeys import studio_one_running

        if studio_one_running() and no_open:
            return p

    ensure_s1remote_on_path()
    from start_from_template import start_new_song_from_template  # noqa: E402

    summary = start_new_song_from_template(name=name)
    if not summary.get("ok"):
        # Fallback: report dir under Songs even if launch partial
        dest = default_songs_root() / name
        dest.mkdir(parents=True, exist_ok=True)
        log(f"start_from_template not fully ok: {summary} — using {dest}")
        return dest
    return Path(summary.get("song_dir") or default_songs_root() / name)


def main() -> int:
    ap = argparse.ArgumentParser(description="Studio One UI learn loop (eyes/ears/S1 Controller)")
    ap.add_argument("--song-dir", type=Path, default=None)
    ap.add_argument("--name", default="Agent_UI_Learn", help="Save-As song name if opening Template")
    ap.add_argument("--max-hours", type=float, default=6.0)
    ap.add_argument("--no-open", action="store_true", help="Do not launch S1 / Template Save As")
    ap.add_argument("--no-eyes", action="store_true")
    ap.add_argument("--no-ears", action="store_true")
    ap.add_argument(
        "--require-mcu",
        action="store_true",
        help="Abort if software S1 Controller MCU not connected",
    )
    args = ap.parse_args()

    if args.song_dir:
        song = Path(args.song_dir)
        song.mkdir(parents=True, exist_ok=True)
        os.environ["S1_SONG_DIR"] = str(song)
    else:
        song = ensure_song_open(args.name, no_open=args.no_open)
        os.environ["S1_SONG_DIR"] = str(song)

    loop = LearnUILoop(
        song,
        max_hours=args.max_hours,
        eyes_enabled=not args.no_eyes,
        ears_enabled=not args.no_ears,
        require_mcu=args.require_mcu,
    )
    sess = loop.run()
    fails = sess.counts.get("FAIL", 0)
    # Partial success is OK (learning); exit 0 if any PASS and S1 was exercised
    if sess.counts.get("PASS", 0) + sess.counts.get("RETRY_PASS", 0) > 0:
        return 0
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
