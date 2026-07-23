"""
VST / plugin MIDI control for Studio One via Control Link.

Studio One does not expose a free “set any VST float by name” API.
The supported path is MIDI CC → Control Link assignment.

This module:
  - Sends CCs on your virtual MIDI port (S1 Controller)
  - Keeps named maps (stock plugins + generic banks)
  - Helps you learn params quickly (wiggle / bank learn)
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

from . import config
from .midi.control_link import ControlLink
from .midi.port import MidiBridge, list_ports


# Generic banks for any third-party VST (assign via Control Link once)
GENERIC_BANKS: dict[str, dict[str, Any]] = {
    "generic_16": {
        "title": "Generic VST — 16 knobs (CC 20–35)",
        "params": {f"knob_{i+1}": {"cc": 20 + i, "channel": 0} for i in range(16)},
    },
    "generic_32": {
        "title": "Generic VST — 32 knobs (CC 20–51)",
        "params": {f"knob_{i+1}": {"cc": 20 + i, "channel": 0} for i in range(32)},
    },
    "channel_macros": {
        "title": "Channel Macro Controls (8 knobs + 8 buttons)",
        "params": {
            **{f"macro_{i+1}": {"cc": 20 + i, "channel": 0} for i in range(8)},
            **{f"button_{i+1}": {"cc": 28 + i, "channel": 0} for i in range(8)},
        },
    },
}


class VstMidiControl:
    def __init__(
        self,
        out_port: Optional[str] = None,
        maps_path: Optional[Path] = None,
    ) -> None:
        settings = config.load_settings()
        self.bridge = MidiBridge(
            out_name=out_port or settings.get("midi_out_port", "S1 Controller 1"),
            in_name="",
        )
        self.maps_path = Path(maps_path or config.MAPS_PATH)
        self.link = ControlLink(self.bridge, maps_path=self.maps_path if self.maps_path.is_file() else None)
        # Ensure generic banks always available
        for key, bank in GENERIC_BANKS.items():
            if key not in self.link.maps:
                self.link.maps[key] = bank

    def connect(self) -> str:
        self.bridge.connect(open_input=False)
        return self.bridge.out_name

    def disconnect(self) -> None:
        self.bridge.disconnect()

    def __enter__(self) -> "VstMidiControl":
        self.connect()
        return self

    def __exit__(self, *_) -> None:
        self.disconnect()

    # ---- list / inspect -------------------------------------------------

    def list_plugins(self) -> list[str]:
        return sorted(self.link.maps.keys())

    def list_params(self, plugin: str) -> dict[str, Any]:
        key = self._key(plugin)
        if key not in self.link.maps:
            raise KeyError(f"Unknown plugin map {plugin!r}. Try: {self.list_plugins()[:12]}…")
        return dict(self.link.maps[key].get("params") or {})

    def show(self, plugin: str) -> dict[str, Any]:
        key = self._key(plugin)
        entry = self.link.maps.get(key)
        if not entry:
            raise KeyError(plugin)
        return {
            "id": key,
            "title": entry.get("title", key),
            "deviceID": entry.get("deviceID"),
            "params": entry.get("params") or {},
        }

    # ---- control --------------------------------------------------------

    def cc(self, control: int, value: int, channel: int = 0) -> None:
        self.link.cc(control, value, channel)

    def set(self, plugin: str, param: str, value: float | int) -> dict[str, Any]:
        """Set named param. value: 0–127 or 0.0–1.0."""
        self.link.set_param(plugin, param, value)
        params = self.list_params(plugin)
        entry = None
        for k, v in params.items():
            if k.lower() == param.lower() or k.lower().replace(" ", "_") == param.lower().replace(" ", "_"):
                entry = {"name": k, **v}
                break
        return {"plugin": self._key(plugin), "param": entry, "value": value}

    def learn_wiggle(self, control: int, channel: int = 0) -> None:
        """Wiggle one CC so Studio One Control Link can learn it."""
        self.link.sweep(control, 0, 127, steps=40, channel=channel)
        time.sleep(0.05)
        self.link.sweep(control, 127, 0, steps=20, channel=channel)

    def learn_param(self, plugin: str, param: str) -> dict[str, Any]:
        """Wiggle the CC assigned to this named param in the map."""
        params = self.list_params(plugin)
        entry = None
        name = None
        for k, v in params.items():
            if k.lower() == param.lower() or k.lower().replace(" ", "_") == param.lower().replace(" ", "_"):
                entry = v
                name = k
                break
        if not entry:
            raise KeyError(f"Param {param!r} not in {plugin}")
        cc_num = int(entry["cc"])
        ch = int(entry.get("channel", 0))
        self.learn_wiggle(cc_num, ch)
        return {"plugin": self._key(plugin), "param": name, "cc": cc_num, "channel": ch}

    def learn_all(
        self,
        plugin: str,
        pause: float = 1.2,
        limit: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """
        Walk every mapped param: wiggle its CC, pause so you can click the
        next knob in Studio One with Control Link Focus ON.
        """
        params = self.list_params(plugin)
        results = []
        items = list(params.items())
        if limit is not None:
            items = items[: max(0, int(limit))]
        for name, entry in items:
            cc_num = int(entry["cc"])
            ch = int(entry.get("channel", 0))
            print(f"  LEARN  {name:30s}  CC {cc_num:3d}  — click param in S1 now…")
            self.learn_wiggle(cc_num, ch)
            results.append({"param": name, "cc": cc_num, "channel": ch})
            time.sleep(max(0.2, pause))
        return results

    def define(self, plugin: str, param: str, cc: int, channel: int = 0) -> Path:
        self.link.define(plugin, param, cc, channel, note="user map")
        return self.link.save(self.maps_path)

    def save(self) -> Path:
        return self.link.save(self.maps_path)

    @staticmethod
    def _key(plugin: str) -> str:
        return plugin.strip().lower().replace(" ", "_").replace("-", "_")


def setup_instructions() -> str:
    ports = list_ports()
    settings = config.load_settings()
    out = settings.get("midi_out_port", "S1 Controller 1")
    return f"""
VST MIDI control setup (Studio One)
===================================

How it works
  This tool sends MIDI Control Change (CC) messages.
  Studio One Control Link binds those CCs to any plugin knob (stock or VST).

1) Virtual MIDI cable
   You already have: OUT {out!r}
   Available outputs: {ports.get('outputs')}

2) Studio One external device
   Options → External Devices → Add
   • New Keyboard  OR  New Control Surface
   • Receive From = {out!r}   (the port THIS tool sends on)
   Optional: also add Mackie Control on the same port for mixer/transport.

3) Learn one VST parameter
   a. Open your plugin in Studio One
   b. Toolbar: Control Link ON + Focus ON
   c. Click the knob you want
   d. Run:
        py -3.12 -m s1remote vst learn-wiggle 20
      (or right-click param → Assign External Control → move CC 20)

4) Drive it forever
        py -3.12 -m s1remote vst cc 20 100
        py -3.12 -m s1remote vst set generic_16 knob_1 0.75

5) Map a whole bank (third-party VST)
        py -3.12 -m s1remote vst learn-all generic_16 --pause 1.5
      Click each plugin knob when prompted (Focus stays on).

6) Stock plugins (named maps already generated)
        py -3.12 -m s1remote vst list
        py -3.12 -m s1remote vst show pro_eq
        py -3.12 -m s1remote vst set pro_eq lcfreq 80

Tips
  • Channel Macro Controls: map 8 key knobs on the channel, then learn
    only `channel_macros` (fastest for any VST).
  • MIDI channel defaults to 0 (MIDI ch 1). Use --channel if needed.
  • Value: 0–127 integer, or 0.0–1.0 float.
"""
