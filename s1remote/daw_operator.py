"""
DAW Operator — single entry-point that knows *all* information contained in
s1-remote about controlling Studio One 6.

Wraps FullControl and surfaces every catalog, policy, port wiring rule,
known failure, and agent guideline as structured data via ``info()``.

Usage (read-only, no MIDI)::

    from s1remote.daw_operator import DawOperator

    op = DawOperator()
    import json
    print(json.dumps(op.info(), indent=2))

Usage (live control)::

    with DawOperator() as op:
        op.play()
        op.fader(0, -6)
        op.note(60)
        op.do("view.browser")
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .commands_catalog import COMMANDS, coverage_summary, list_commands
from .full_control import FullControl
from .hotkeys import ACTIONS


# ---------------------------------------------------------------------------
# Static knowledge banks
# ---------------------------------------------------------------------------

_PORTS = {
    "mcu_out": "S1 Controller 1",
    "mcu_in": "S1 Controller 0",
    "notes_out_agent": "S1 Notes 2",
    "notes_in_s1": "S1 Notes 1",
    "config_keys": {
        "mcu_out": "midi_out_port",
        "mcu_in": "midi_in_port",
        "notes_out": "instrument_midi_out_port",
    },
    "rule": (
        "MCU and notes MUST use separate loopMIDI ports. "
        "Notes on the Mackie cable collide with surface note-numbers "
        "and do not record reliably."
    ),
}

_LAYERS: Dict[str, str] = {
    "mcu": "Mackie Control MIDI — transport, 8-ch faders, mute/solo/rec/select, banks, V-Pots, plugin mode",
    "link": "Control Link CC — named VST/stock params after map + optional learn",
    "note": "Instrument MIDI — notes + CC to live instrument tracks via S1 Notes port",
    "hotkey": "Hotkeys — views, file, edit via focused window keystrokes",
    "menu": "Alt-menu keyboard paths — full menu bar coverage (Windows only)",
    "browser": "Browser — F5 + type + Enter to search and load instruments/FX",
    "host": "In-host package queue — track/channel ops via Host.Objects inside Studio One",
    "ucnet": "UCNET (RE) — UDP discovery working; TCP param session framing incomplete",
}

_SETUP_STEPS: List[str] = [
    "Install loopMIDI — create port 'S1 Controller' (gives ports 0 and 1)",
    "Install loopMIDI — create port 'S1 Notes' (gives ports 1 and 2)",
    "Studio One → Options → External Devices → Add → Mackie Control",
    "  Receive From = S1 Controller 1 (MCU OUT from this tool)",
    "  Send To      = S1 Controller 0 (feedback LEDs/meters back)",
    "Studio One → Options → External Devices → New Keyboard",
    "  Receive From = S1 Notes 1 (instrument notes IN to S1)",
    "Build and install host package: py -3.12 -m s1remote full package",
    "  Then in S1: Scripts → S1 Full Control: Process Queue",
    "Optional: Control Link ON + Focus ON in S1 toolbar for permanent CC↔param binds",
]

_RECORD_PATH: List[str] = [
    "1. Song open; stay on Song/Arrange page (not Start page)",
    "2. Keyboard device: Receive From = S1 Notes 1 (not MCU port)",
    "3. Instrument on Arrange track — user drags from browser (agent cannot drag)",
    "4. Track Input = that Keyboard device",
    "5. Record Enable red ([R]) on that track — this is a TOGGLE",
    "6. Meter moves when notes arrive → confirms wiring",
    "7. Transport Record",
    "8. Stream notes via FullControl / instrument bridge",
    "9. Transport Stop",
    "10. Verify MIDI part visible on the correct track — never trust stream log alone",
]

_KNOWN_FAILURES: List[Dict[str, str]] = [
    {
        "issue": "MCU rec_arm(strip) does not arm Arrange instrument Rec",
        "cause": "MCU strip 0 is NOT guaranteed to map to Arrange Track 1",
        "fix": "Prefer user-confirmed Record Enable (Rec red); or agent presses [R] once after selecting correct track",
    },
    {
        "issue": "Double-toggle arms then disarms",
        "cause": "[R] and MCU rec_arm both toggle; calling both reverses the state",
        "fix": "Use only one arm method — keyboard [R] OR MCU rec_arm, never both",
    },
    {
        "issue": "Notes on MCU port do not record",
        "cause": "Mackie note-numbers collide with surface protocol",
        "fix": "Always use separate S1 Notes port for instrument MIDI",
    },
    {
        "issue": "browser_load does not assign VSTs to tracks",
        "cause": "Browser search triggers load but S1 does not route without drag target",
        "fix": "User drags instrument onto track; agent can assist with browser_load only for preset browsing",
    },
    {
        "issue": "Streaming notes counted but timeline empty",
        "cause": "Rec Enable was grey (not armed) during stream",
        "fix": "Take screenshots before/during/after; confirm Rec red AND MIDI part on track",
    },
    {
        "issue": "Import File dialog automation unreliable",
        "cause": "Studio One dialog is mostly custom-drawn UI, not standard Win32",
        "fix": "Use Song → Import File menu path or Browser Files drag; user confirms",
    },
]

_AGENT_POLICIES: Dict[str, Any] = {
    "control_split": {
        "agent": "Keyboard + MIDI (MCU transport/mix + S1 Notes for instrument notes)",
        "user": "Browser drag instruments/FX, External Devices confirm, taste locks, Rec red if arm won't stick",
    },
    "track_numbering": (
        "User language = Track 1/2/3 (1-based Arrange order). "
        "MCU strip = 0-based, NOT guaranteed equal to Arrange track index. "
        "Prefer user naming the track over blind strip numbers."
    ),
    "arm_policy": (
        "Preferred: user disarms all, arms ONLY target track (Rec red). "
        "Agent does NOT press [R] or MCU rec. "
        "If agent must arm: ONE [R] OR one MCU rec — never both. "
        "Screenshot after; if not red, stop and ask for mouse — do not thrash."
    ),
    "no_pixel_thrash": "Do not hunt UI knobs with cursor. No blind mouse clicking.",
    "no_auto_launch": "Do not auto-launch Studio One from scripts if already heavy; user opens Song first.",
    "eyes_policy": {
        "shots": ["01_home (after rewind)", "02_armed (after arm)", "03_recording (after Transport Record)", "04_stopped (after stop)"],
        "success_criteria": "Rec red on target row + blue MIDI parts on that lane",
    },
    "stream_vs_record": (
        "note_ons count in log ≠ UI proof. "
        "Status is 'attempted stream' until: instrument visible on track, "
        "Rec was red during stream (screenshot), MIDI part visible, user approved."
    ),
}

_HONEST_LIMITS: List[str] = [
    "No public 'control every S1 function via one host API'.",
    "UCNET TCP param session framing is incomplete — cannot yet set remote SurfaceData params over TCP.",
    "In-host Host.Objects requires running the package task once per queue (S1 does not expose continuous external IPC).",
    "Third-party VST param lists need Control Link learn, Channel Macros, or MCU plugin-mode focus — no public per-param dump.",
    "No pixel thrash — cursor is not used to hunt knobs.",
    "Browser drag cannot be automated (S1 custom browser UI).",
    "Studio One dialog automation unreliable (custom-drawn, limited UIA exposure).",
    "MCU strip 0 ≠ Arrange Track 1 — strip/track mapping is not guaranteed.",
]

_HOTKEYS: Dict[str, Any] = {
    name: {"modifiers": mods, "key": key}
    for name, (mods, key) in ACTIONS.items()
}


# ---------------------------------------------------------------------------
# DawOperator
# ---------------------------------------------------------------------------


class DawOperator:
    """
    DAW Operator for Studio One 6 (s1-remote).

    Knows all information contained in this system:
    capabilities, commands, ports, layers, hotkeys, record path,
    known failures, agent policies, and honest limits.

    Also delegates all live control operations to the underlying
    ``FullControl`` stack (MCU + Control Link + hotkeys + menus +
    host package + browser).
    """

    def __init__(self, out_port: Optional[str] = None) -> None:
        self._fc = FullControl(out_port=out_port)

    # ---- lifecycle --------------------------------------------------------

    def connect(self) -> "DawOperator":
        self._fc.connect()
        return self

    def disconnect(self) -> None:
        self._fc.disconnect()

    def __enter__(self) -> "DawOperator":
        return self.connect()

    def __exit__(self, *_) -> None:
        self.disconnect()

    # ---- knowledge --------------------------------------------------------

    def info(self) -> Dict[str, Any]:
        """
        Return the complete knowledge base of this DAW operator.

        Covers:
        - layers and what each does
        - port wiring
        - setup steps
        - record path (step-by-step)
        - all command IDs with layer + description
        - all hotkey actions
        - known failures and fixes
        - agent policies
        - honest limits
        - command coverage summary
        """
        return {
            "system": "s1-remote — external remote for PreSonus Studio One 6 on Windows",
            "layers": _LAYERS,
            "ports": _PORTS,
            "setup_steps": _SETUP_STEPS,
            "record_path": _RECORD_PATH,
            "commands": {
                "coverage": coverage_summary(),
                "catalog": {cid: {"layer": m["layer"], "description": m["description"]} for cid, m in sorted(COMMANDS.items())},
            },
            "hotkeys": _HOTKEYS,
            "known_failures": _KNOWN_FAILURES,
            "agent_policies": _AGENT_POLICIES,
            "honest_limits": _HONEST_LIMITS,
        }

    def commands(self, query: str = "") -> List[Dict[str, Any]]:
        """Search the command catalog. Empty query returns all commands."""
        return list_commands(query)

    def coverage(self) -> Dict[str, int]:
        """Return command count by layer + total."""
        return coverage_summary()

    # ---- live control (delegates to FullControl) --------------------------

    def status(self) -> Dict[str, Any]:
        return self._fc.status()

    def capabilities(self) -> Dict[str, Any]:
        return self._fc.capabilities()

    # Transport
    def play(self) -> None:
        self._fc.play()

    def stop(self) -> None:
        self._fc.stop()

    def record(self) -> None:
        self._fc.record()

    # Mixer
    def mute(self, ch: int) -> None:
        self._fc.mute(ch)

    def solo(self, ch: int) -> None:
        self._fc.solo(ch)

    def fader(self, ch: int, db: float) -> None:
        self._fc.fader(ch, db)

    def select(self, ch: int) -> None:
        self._fc.select(ch)

    def bank_left(self) -> None:
        self._fc.bank_left()

    def bank_right(self) -> None:
        self._fc.bank_right()

    def plugin_mode(self) -> None:
        self._fc.plugin_mode()

    def pan_mode(self) -> None:
        self._fc.pan_mode()

    def vpot(self, ch: int, delta: int = 1) -> None:
        self._fc.vpot(ch, delta)

    # VST / Control Link
    def cc(self, control: int, value: int, channel: int = 0) -> None:
        self._fc.cc(control, value, channel)

    def vst_param(self, plugin: str, param: str, value: Any) -> Dict[str, Any]:
        return self._fc.vst_param(plugin, param, value)

    # MIDI notes
    def note(
        self,
        note: int,
        duration: float = 0.25,
        velocity: int = 100,
        channel: int = 0,
    ) -> None:
        self._fc.note(note, duration, velocity, channel)

    # Views / hotkeys
    def hotkey(self, action: str) -> None:
        self._fc.hotkey(action)

    def console(self) -> None:
        self._fc.console()

    def browser(self) -> None:
        self._fc.browser()

    def save(self) -> None:
        self._fc.save()

    # Menus
    def menu(self, *path: str) -> None:
        self._fc.menu(*path)

    # Browser load
    def browser_load(self, search: str) -> None:
        self._fc.browser_load(search)

    # Host package
    def host(self, task: str, **params: Any) -> str:
        return self._fc.host(task, **params)

    def host_set_volume(self, index: int, db: float) -> str:
        return self._fc.host_set_volume(index, db)

    def host_set_mute(self, index: int, state: bool = True) -> str:
        return self._fc.host_set_mute(index, state)

    # Generic router
    def do(self, command_id: str, **kwargs: Any) -> Any:
        """Route any catalog command_id through the correct layer."""
        return self._fc.do(command_id, **kwargs)
