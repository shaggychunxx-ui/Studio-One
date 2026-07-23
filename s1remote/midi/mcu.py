"""
Mackie Control Universal (MCU) protocol for Studio One.

Matches PreSonus Studio One 6 MackieControl.surface.xml note/CC map:
  - Pitch bend ch 0-7 = channel faders (14-bit)
  - Pitch bend ch 8   = master fader
  - Note On 0x90 + address = buttons (vel 0x7F press, 0x00 release)
  - CC 0x10-0x17 = V-Pots (relative)
"""

from __future__ import annotations

from typing import Optional

import mido

from .port import MidiBridge


# Button note numbers from Studio One MackieControl.surface.xml
NOTE = {
    # Channel strip (per channel 0..7)
    "rec": 0x00,      # + ch
    "solo": 0x08,     # + ch
    "mute": 0x10,     # + ch
    "select": 0x18,   # + ch
    "vpot_push": 0x20,  # + ch
    # Assignment
    "track": 0x28,
    "send": 0x29,
    "pan": 0x2A,
    "plugin": 0x2B,
    "eq": 0x2C,
    "instrument": 0x2D,
    # Bank
    "bank_left": 0x2E,
    "bank_right": 0x2F,
    "chan_left": 0x30,
    "chan_right": 0x31,
    "flip": 0x32,
    "global_view": 0x33,
    "name_value": 0x34,
    "smpte_beats": 0x35,
    # F1-F8
    "f1": 0x36,
    "f2": 0x37,
    "f3": 0x38,
    "f4": 0x39,
    "f5": 0x3A,
    "f6": 0x3B,
    "f7": 0x3C,
    "f8": 0x3D,
    # Mixer bank filters
    "midi_tracks": 0x3E,
    "inputs": 0x3F,
    "audio_tracks": 0x40,
    "audio_instrument": 0x41,
    "aux": 0x42,
    "buses": 0x43,
    "outputs": 0x44,
    "user": 0x45,
    # Modifiers
    "shift": 0x46,
    "option": 0x47,
    "control": 0x48,
    "cmd_alt": 0x49,
    # Automation
    "read": 0x4A,
    "write": 0x4B,
    "trim": 0x4C,
    "touch": 0x4D,
    "latch": 0x4E,
    "group": 0x4F,
    # Utilities
    "save": 0x50,
    "undo": 0x51,
    "cancel": 0x52,
    "enter": 0x53,
    # Transport extras
    "marker": 0x54,
    "nudge": 0x55,
    "cycle": 0x56,
    "drop": 0x57,
    "replace": 0x58,
    "click": 0x59,
    "solo_master": 0x5A,
    # Transport
    "rewind": 0x5B,
    "ffwd": 0x5C,
    "stop": 0x5D,
    "play": 0x5E,
    "record": 0x5F,
    # Nav
    "up": 0x60,
    "down": 0x61,
    "left": 0x62,
    "right": 0x63,
    "zoom": 0x64,
    "scrub": 0x65,
    # Fader touch 0x68-0x6F, master touch 0x70
    "fader_touch": 0x68,  # + ch
    "master_touch": 0x70,
}


def _db_to_fader_14(db: float) -> int:
    """
    Approximate MCU fader position (0..16383) from dB.
    Unity (0 dB) ≈ 0xC000>>2 style mapping used by many MCU hosts;
    we use a practical curve: -inf→0, 0 dB→~12_288, +6 dB→16383.
    """
    if db <= -90:
        return 0
    # clamp
    db = max(-90.0, min(6.0, float(db)))
    # Piecewise: -90..0 maps to 0..0.75, 0..+6 maps to 0.75..1.0
    if db <= 0:
        norm = (db + 90.0) / 90.0 * 0.75
    else:
        norm = 0.75 + (db / 6.0) * 0.25
    return int(max(0, min(16383, round(norm * 16383))))


def _norm_to_fader_14(value: float) -> int:
    """0.0 .. 1.0 → 14-bit pitch bend."""
    value = max(0.0, min(1.0, float(value)))
    return int(round(value * 16383))


class MackieControl:
    """Send MCU messages into Studio One (configured as Mackie Control)."""

    def __init__(self, bridge: MidiBridge, channels: int = 8) -> None:
        self.bridge = bridge
        self.channels = max(1, min(8, channels))

    # ---- primitives -----------------------------------------------------

    def note(self, address: int, down: bool = True) -> None:
        vel = 0x7F if down else 0x00
        self.bridge.send(mido.Message("note_on", channel=0, note=address & 0x7F, velocity=vel))

    def press(self, address: int, hold_ms: float = 0.04) -> None:
        import time

        self.note(address, True)
        time.sleep(hold_ms)
        self.note(address, False)

    def button(self, name: str, down: bool = True) -> None:
        if name not in NOTE:
            raise KeyError(f"Unknown MCU button: {name}")
        self.note(NOTE[name], down)

    def click(self, name: str) -> None:
        import time

        self.button(name, True)
        time.sleep(0.04)
        self.button(name, False)

    def pitch_bend_14(self, channel: int, value_14: int) -> None:
        value_14 = max(0, min(16383, int(value_14)))
        # mido pitchwheel is -8192..8191 centered; MCU uses absolute 0..16383 as 14-bit
        # Convert: raw = (msb<<7)|lsb style. mido expects signed pitch.
        signed = value_14 - 8192
        self.bridge.send(mido.Message("pitchwheel", channel=channel & 0x0F, pitch=signed))

    def cc(self, control: int, value: int, channel: int = 0) -> None:
        self.bridge.send(
            mido.Message(
                "control_change",
                channel=channel & 0x0F,
                control=control & 0x7F,
                value=max(0, min(127, int(value))),
            )
        )

    # ---- transport ------------------------------------------------------

    def play(self) -> None:
        self.click("play")

    def stop(self) -> None:
        self.click("stop")

    def record(self) -> None:
        self.click("record")

    def rewind(self) -> None:
        self.click("rewind")

    def ffwd(self) -> None:
        self.click("ffwd")

    def cycle(self) -> None:
        self.click("cycle")

    def click_metronome(self) -> None:
        self.click("click")

    # ---- mixer channel strip --------------------------------------------

    def fader(self, channel: int, *, db: Optional[float] = None, norm: Optional[float] = None) -> None:
        if not 0 <= channel < self.channels:
            raise ValueError(f"channel must be 0..{self.channels - 1}")
        if db is not None:
            val = _db_to_fader_14(db)
        elif norm is not None:
            val = _norm_to_fader_14(norm)
        else:
            raise ValueError("Provide db= or norm=")
        # Touch → move → release (better automation behaviour)
        self.note(NOTE["fader_touch"] + channel, True)
        self.pitch_bend_14(channel, val)
        self.note(NOTE["fader_touch"] + channel, False)

    def master_fader(self, *, db: Optional[float] = None, norm: Optional[float] = None) -> None:
        if db is not None:
            val = _db_to_fader_14(db)
        elif norm is not None:
            val = _norm_to_fader_14(norm)
        else:
            raise ValueError("Provide db= or norm=")
        self.note(NOTE["master_touch"], True)
        self.pitch_bend_14(8, val)
        self.note(NOTE["master_touch"], False)

    def mute(self, channel: int) -> None:
        self._ch_button("mute", channel)

    def solo(self, channel: int) -> None:
        self._ch_button("solo", channel)

    def rec_arm(self, channel: int) -> None:
        self._ch_button("rec", channel)

    def select(self, channel: int) -> None:
        self._ch_button("select", channel)

    def _ch_button(self, kind: str, channel: int) -> None:
        if not 0 <= channel < self.channels:
            raise ValueError(f"channel must be 0..{self.channels - 1}")
        self.press(NOTE[kind] + channel)

    def vpot(self, channel: int, delta: int) -> None:
        """
        Relative V-Pot turn. MCU uses CC 0x10+ch with 7-bit two's complement ticks.
        Positive delta = clockwise.
        """
        if not 0 <= channel < self.channels:
            raise ValueError(f"channel must be 0..{self.channels - 1}")
        ticks = max(-63, min(63, int(delta)))
        if ticks == 0:
            return
        # Signed 7-bit: bit6 set means negative in MCU relative encoding often uses 0x01..0x3F up, 0x41..0x7F down
        if ticks > 0:
            value = ticks & 0x3F
        else:
            value = 0x40 | ((-ticks) & 0x3F)
        self.cc(0x10 + channel, value)

    def vpot_push(self, channel: int) -> None:
        if not 0 <= channel < self.channels:
            raise ValueError(f"channel must be 0..{self.channels - 1}")
        self.press(NOTE["vpot_push"] + channel)

    # ---- modes / banks --------------------------------------------------

    def mode_plugin(self) -> None:
        """V-Pots → Control Link / plug-in parameters."""
        self.click("plugin")

    def mode_pan(self) -> None:
        self.click("pan")

    def mode_send(self) -> None:
        self.click("send")

    def mode_track(self) -> None:
        self.click("track")

    def mode_eq(self) -> None:
        """Insert bypass layer (EQ button in MCU map)."""
        self.click("eq")

    def mode_instrument(self) -> None:
        """Instrument assignment layer."""
        self.click("instrument")

    def bank_left(self) -> None:
        self.click("bank_left")

    def bank_right(self) -> None:
        self.click("bank_right")

    def channel_left(self) -> None:
        self.click("chan_left")

    def channel_right(self) -> None:
        self.click("chan_right")

    def save(self) -> None:
        self.click("save")

    def undo(self) -> None:
        self.click("undo")

    def function(self, n: int) -> None:
        if not 1 <= n <= 8:
            raise ValueError("F-key must be 1..8")
        self.click(f"f{n}")
