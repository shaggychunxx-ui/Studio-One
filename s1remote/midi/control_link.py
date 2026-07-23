"""
Studio One Control Link — map MIDI CCs to any plugin / mixer parameter.

Workflow in Studio One:
  1. Preferences → External Devices → add Keyboard or Control Surface on this port
     (or use the same MCU device — Control Link works with external MIDI).
  2. Enable Control Link (toolbar) and Focus.
  3. Click a parameter in a VST / stock plug-in.
  4. Move a CC from this class (learn), or right-click → Assign External Control.

Once learned, set_param(cc, value) drives that parameter in real time.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

import mido

from .port import MidiBridge


class ControlLink:
    def __init__(self, bridge: MidiBridge, maps_path: Optional[Path] = None) -> None:
        self.bridge = bridge
        self.maps_path = maps_path
        self.maps: dict[str, dict[str, Any]] = {}
        if maps_path and maps_path.is_file():
            self.load(maps_path)

    def cc(self, control: int, value: int, channel: int = 0) -> None:
        control = int(control) & 0x7F
        value = max(0, min(127, int(value)))
        channel = int(channel) & 0x0F
        self.bridge.send(
            mido.Message("control_change", channel=channel, control=control, value=value)
        )

    def sweep(self, control: int, start: int = 0, end: int = 127, steps: int = 32, channel: int = 0) -> None:
        """Useful while learning — wiggle a CC so Studio One can see it."""
        if steps < 2:
            steps = 2
        for i in range(steps + 1):
            v = int(start + (end - start) * (i / steps))
            self.cc(control, v, channel)
            time.sleep(0.01)
        self.cc(control, end, channel)

    def set_param(self, plugin: str, param: str, value: int | float) -> None:
        """
        Set a named parameter from a loaded map.
        value: 0..127 int, or 0.0..1.0 float (scaled to 0..127).
        """
        plugin_key = plugin.strip().lower().replace(" ", "_")
        if plugin_key not in self.maps:
            raise KeyError(f"No map for plugin {plugin!r}. Known: {list(self.maps)}")
        pmap = self.maps[plugin_key]
        params = pmap.get("params") or {}
        # case-insensitive param lookup
        entry = None
        for k, v in params.items():
            if k.lower() == param.lower() or k.lower().replace(" ", "_") == param.lower().replace(" ", "_"):
                entry = v
                break
        if entry is None:
            raise KeyError(f"Param {param!r} not in map {plugin_key}. Have: {list(params)}")
        cc_num = int(entry["cc"])
        ch = int(entry.get("channel", 0))
        if isinstance(value, float) and value <= 1.0:
            midi_val = int(round(max(0.0, min(1.0, value)) * 127))
        else:
            midi_val = int(value)
        self.cc(cc_num, midi_val, ch)

    def load(self, path: Path | str) -> None:
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "plugins" in data:
            self.maps = data["plugins"]
        elif isinstance(data, dict):
            self.maps = data
        else:
            raise ValueError("Map file must be a JSON object")
        self.maps_path = path

    def save(self, path: Optional[Path | str] = None) -> Path:
        path = Path(path or self.maps_path or "config/plugin_maps.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"plugins": self.maps}
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.maps_path = path
        return path

    def define(
        self,
        plugin: str,
        param: str,
        cc: int,
        channel: int = 0,
        *,
        note: str = "",
    ) -> None:
        key = plugin.strip().lower().replace(" ", "_")
        self.maps.setdefault(key, {"title": plugin, "params": {}})
        self.maps[key]["params"][param] = {
            "cc": int(cc) & 0x7F,
            "channel": int(channel) & 0x0F,
            "note": note,
        }

    def list_plugins(self) -> list[str]:
        return sorted(self.maps.keys())

    def list_params(self, plugin: str) -> list[str]:
        key = plugin.strip().lower().replace(" ", "_")
        if key not in self.maps:
            raise KeyError(key)
        return list((self.maps[key].get("params") or {}).keys())
