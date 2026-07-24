"""High-level facade: one object controls Studio One remotely."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from . import config
from .hotkeys import focus_studio_one, run_action, studio_one_running
from .midi.control_link import ControlLink
from .midi.instrument import InstrumentMidi
from .midi.mcu import MackieControl
from .midi.port import MidiBridge, list_ports


class S1Remote:
    """
    External remote for Studio One.

    Layers:
      mcu        — mixer, transport, banks, plugin mode (Mackie Control)
      link       — VST / any parameter via Control Link CCs
      instrument — note / CC MIDI to instrument tracks
      hotkeys    — menu / view shortcuts via focused window
    """

    def __init__(
        self,
        out_port: Optional[str] = None,
        in_port: Optional[str] = None,
        instrument_out_port: Optional[str] = None,
        auto_connect: bool = False,
    ) -> None:
        settings = config.load_settings()
        self.settings = settings
        # MCU + Control Link on Mackie cable
        self.bridge = MidiBridge(
            out_name=out_port or settings.get("midi_out_port", ""),
            in_name=in_port or settings.get("midi_in_port", ""),
            on_message=self._on_midi_in,
        )
        # Live notes for Instrument Tracks on a SEPARATE loopMIDI port
        notes_out = instrument_out_port or settings.get("instrument_midi_out_port") or ""
        if not notes_out:
            notes_out = out_port or settings.get("midi_out_port", "")
        self.notes_bridge = MidiBridge(out_name=notes_out, in_name="", on_message=None)
        self.mcu = MackieControl(self.bridge, channels=int(settings.get("mcu_channels", 8)))
        self.link = ControlLink(self.bridge, maps_path=config.MAPS_PATH)
        self.instrument = InstrumentMidi(self.notes_bridge)
        self._feedback: list[str] = []
        if auto_connect:
            self.connect()

    def _on_midi_in(self, msg) -> None:
        # Keep a small ring of feedback strings for status/debug
        self._feedback.append(str(msg))
        if len(self._feedback) > 64:
            self._feedback = self._feedback[-64:]

    # ---- connection -----------------------------------------------------

    def connect(
        self,
        out_port: Optional[str] = None,
        in_port: Optional[str] = None,
        instrument_out_port: Optional[str] = None,
        *,
        open_input: bool = True,
    ) -> None:
        self.bridge.connect(out_port, in_port, open_input=open_input)
        notes = instrument_out_port or self.settings.get("instrument_midi_out_port") or self.notes_bridge.out_name
        try:
            self.notes_bridge.connect(notes, "", open_input=False)
        except Exception:
            # Fall back to MCU out so notes still go somewhere
            self.notes_bridge.connect(self.bridge.out_name, "", open_input=False)
        self.settings["midi_out_port"] = self.bridge.out_name
        if self.bridge.in_name:
            self.settings["midi_in_port"] = self.bridge.in_name
        if self.notes_bridge.out_name:
            self.settings["instrument_midi_out_port"] = self.notes_bridge.out_name
        config.save_settings(self.settings)

    def disconnect(self) -> None:
        self.notes_bridge.disconnect()
        self.bridge.disconnect()

    @property
    def connected(self) -> bool:
        return self.bridge.connected

    @property
    def notes_connected(self) -> bool:
        return self.notes_bridge.connected

    def status(self) -> dict[str, Any]:
        ports = list_ports()
        return {
            "studio_one_running": studio_one_running(),
            "midi_connected": self.connected,
            "midi_out": self.bridge.out_name,
            "midi_in": self.bridge.in_name,
            "instrument_midi_out": self.notes_bridge.out_name,
            "instrument_midi_connected": self.notes_connected,
            "available_inputs": ports["inputs"],
            "available_outputs": ports["outputs"],
            "plugin_maps": self.link.list_plugins(),
            "recent_feedback": list(self._feedback[-8:]),
        }

    # ---- convenience wrappers -------------------------------------------

    def play(self) -> None:
        self.mcu.play()

    def stop(self) -> None:
        self.mcu.stop()

    def record(self) -> None:
        self.mcu.record()

    def fader(self, channel: int, db: float) -> None:
        self.mcu.fader(channel, db=db)

    def mute(self, channel: int) -> None:
        self.mcu.mute(channel)

    def solo(self, channel: int) -> None:
        self.mcu.solo(channel)

    def plugin_cc(self, control: int, value: int, channel: int = 0) -> None:
        self.link.cc(control, value, channel)

    def plugin_param(self, plugin: str, param: str, value: float | int) -> None:
        self.link.set_param(plugin, param, value)

    def note(self, note: int, duration: float = 0.25, velocity: int = 100, channel: int = 0) -> None:
        self.instrument.play_note(note, duration, velocity, channel)

    def hotkey(self, action: str) -> None:
        run_action(action, focus=True)

    def focus(self) -> bool:
        return focus_studio_one()

    def __enter__(self) -> "S1Remote":
        self.connect()
        return self

    def __exit__(self, *_) -> None:
        self.disconnect()
