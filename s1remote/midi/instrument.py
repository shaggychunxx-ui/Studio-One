"""Standard MIDI note / program change I/O for instrument tracks."""

from __future__ import annotations

import time
from typing import Iterable, Optional

import mido

from .port import MidiBridge


class InstrumentMidi:
    """
    Send notes to Studio One instrument tracks.

    In Studio One: External Devices → New Keyboard → Receive From = this port,
    then assign the keyboard to instrument tracks (or record-enable + monitor).
    """

    def __init__(self, bridge: MidiBridge) -> None:
        self.bridge = bridge

    def note_on(self, note: int, velocity: int = 100, channel: int = 0) -> None:
        self.bridge.send(
            mido.Message(
                "note_on",
                channel=channel & 0x0F,
                note=max(0, min(127, note)),
                velocity=max(0, min(127, velocity)),
            )
        )

    def note_off(self, note: int, velocity: int = 0, channel: int = 0) -> None:
        self.bridge.send(
            mido.Message(
                "note_off",
                channel=channel & 0x0F,
                note=max(0, min(127, note)),
                velocity=max(0, min(127, velocity)),
            )
        )

    def play_note(
        self,
        note: int,
        duration: float = 0.25,
        velocity: int = 100,
        channel: int = 0,
    ) -> None:
        self.note_on(note, velocity, channel)
        time.sleep(max(0.01, duration))
        self.note_off(note, 0, channel)

    def play_chord(
        self,
        notes: Iterable[int],
        duration: float = 0.5,
        velocity: int = 100,
        channel: int = 0,
    ) -> None:
        notes = list(notes)
        for n in notes:
            self.note_on(n, velocity, channel)
        time.sleep(max(0.01, duration))
        for n in notes:
            self.note_off(n, 0, channel)

    def all_notes_off(self, channel: Optional[int] = None) -> None:
        channels = range(16) if channel is None else [channel & 0x0F]
        for ch in channels:
            self.bridge.send(mido.Message("control_change", channel=ch, control=123, value=0))

    def program_change(self, program: int, channel: int = 0) -> None:
        self.bridge.send(
            mido.Message("program_change", channel=channel & 0x0F, program=program & 0x7F)
        )

    def pitch_bend(self, value: int, channel: int = 0) -> None:
        """value: -8192 .. 8191"""
        self.bridge.send(
            mido.Message("pitchwheel", channel=channel & 0x0F, pitch=max(-8192, min(8191, value)))
        )

    def mod_wheel(self, value: int, channel: int = 0) -> None:
        self.bridge.send(
            mido.Message("control_change", channel=channel & 0x0F, control=1, value=value & 0x7F)
        )
