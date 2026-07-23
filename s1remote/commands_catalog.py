"""
Studio One command catalog — routes every high-level action to the best layer.

Layers:
  mcu      — Mackie Control MIDI (mixer/transport/plugin mode)
  link     — Control Link CC (VST params after map)
  note     — instrument MIDI notes
  hotkey   — focused window keystroke
  menu     — Alt-menu path (Windows)
  host     — in-host package request file (processed when package runs)
  browser  — Browser F5 + type + load
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# id → {layer, ...kwargs, description}
COMMANDS: Dict[str, Dict[str, Any]] = {}


def _c(
    id_: str,
    layer: str,
    description: str,
    **kwargs: Any,
) -> None:
    COMMANDS[id_] = {"layer": layer, "description": description, **kwargs}


# ---- Transport (MCU preferred) ----
for name, btn in [
    ("transport.play", "play"),
    ("transport.stop", "stop"),
    ("transport.record", "record"),
    ("transport.rewind", "rewind"),
    ("transport.ffwd", "ffwd"),
    ("transport.cycle", "cycle"),
    ("transport.click", "click"),
]:
    _c(name, "mcu", f"Transport {btn}", button=btn)

_c("transport.play_space", "hotkey", "Play toggle via Space", action="transport_play")

# ---- File / Song ----
_c("file.new", "hotkey", "New Song", action="new_song")
_c("file.open", "hotkey", "Open Song", action="open")
_c("file.save", "hotkey", "Save", action="save")
_c("file.save_as", "hotkey", "Save As", action="save_as")
_c("file.close", "hotkey", "Close song", action="close")
_c("file.export_mixdown", "menu", "Export Mixdown", path=["File", "Export Mixdown…"])

# ---- Edit ----
for a in ("undo", "redo", "cut", "copy", "paste", "select_all", "delete", "duplicate"):
    _c(f"edit.{a}", "hotkey", a.title(), action=a)

# ---- Views ----
_c("view.console", "hotkey", "Console / Mixer F3", action="mixer")
_c("view.browser", "hotkey", "Browser F5", action="browser")
_c("view.inspector", "hotkey", "Inspector F4", action="inspector")
_c("view.editor", "hotkey", "Editor", action="editor")
_c("view.fullscreen", "hotkey", "Full screen F11", action="fullscreen")

# ---- Tracks ----
_c("track.add", "hotkey", "Add Tracks dialog", action="add_tracks")
_c("track.arm", "hotkey", "Arm selected", action="arm")
_c("track.mute", "hotkey", "Mute selected (focus dependent)", action="track_mute")
_c("track.solo", "hotkey", "Solo selected", action="track_solo")
_c("track.duplicate", "hotkey", "Duplicate tracks", action="duplicate")
_c("track.add_instrument", "menu", "Add Instrument Track", path=["Track", "Add", "Instrument Track"])
_c("track.add_audio", "menu", "Add Audio Track", path=["Track", "Add", "Audio Track"])

# ---- Mixer MCU ----
for i in range(8):
    _c(f"mixer.mute.{i}", "mcu", f"Mute strip {i}", method="mute", channel=i)
    _c(f"mixer.solo.{i}", "mcu", f"Solo strip {i}", method="solo", channel=i)
    _c(f"mixer.select.{i}", "mcu", f"Select strip {i}", method="select", channel=i)
    _c(f"mixer.rec.{i}", "mcu", f"Rec arm strip {i}", method="rec_arm", channel=i)
    _c(f"mixer.fader.{i}", "mcu", f"Fader strip {i} (needs db=)", method="fader", channel=i)

_c("mixer.bank_left", "mcu", "Bank left", button="bank_left")
_c("mixer.bank_right", "mcu", "Bank right", button="bank_right")
_c("mixer.mode_plugin", "mcu", "V-Pots → focused plugin params", method="mode_plugin")
_c("mixer.mode_pan", "mcu", "V-Pots → pan", method="mode_pan")
_c("mixer.mode_send", "mcu", "V-Pots → sends", method="mode_send")
_c("mixer.mode_eq", "mcu", "Insert/EQ layer", method="mode_eq")
_c("mixer.mode_instrument", "mcu", "Instrument layer", method="mode_instrument")

# ---- Browser ----
_c("browser.open", "hotkey", "Open Browser", action="browser")
_c("browser.load", "browser", "Search and load instrument/FX", search="")

# ---- VST / Control Link ----
_c("vst.cc", "link", "Send raw CC", control=0, value=0)
_c("vst.param", "link", "Named param via map", plugin="", param="", value=0)
_c("vst.plugin_mode", "mcu", "Focus plugin params on V-Pots (no per-param learn)", method="mode_plugin")
_c("vst.vpot", "mcu", "Turn V-Pot (plugin param when in plugin mode)", method="vpot", channel=0, delta=1)
_c("vst.learn_wiggle", "link", "Wiggle CC for Control Link learn", control=20)

# ---- Instrument MIDI in ----
_c("midi.note", "note", "Play MIDI note", note=60, duration=0.25, velocity=100)
_c("midi.cc", "link", "Send CC on instrument/keyboard port", control=1, value=64)

# ---- Host package (in-process) ----
_c("host.mute_selected", "host", "Mute selected tracks (in-host)", task="mute_selected")
_c("host.solo_selected", "host", "Solo selected tracks", task="solo_selected")
_c("host.unmute_all", "host", "Unmute all tracks", task="unmute_all")
_c("host.faders_minus6", "host", "Selected faders -6 dB", task="faders_minus6")
_c("host.list_tracks", "host", "List tracks to S1 console", task="list_tracks")
_c("host.set_channel_volume", "host", "Set channel volume by index", task="set_channel_volume")
_c("host.set_channel_mute", "host", "Set channel mute by index", task="set_channel_mute")
_c("host.command", "host", "interpretCommand category+name", task="interpret_command")

# ---- Menus (full menu bar coverage via Alt paths) ----
MENU_ACTIONS = {
    "menu.file": ["File"],
    "menu.edit": ["Edit"],
    "menu.song": ["Song"],
    "menu.track": ["Track"],
    "menu.event": ["Event"],
    "menu.audio": ["Audio"],
    "menu.transport": ["Transport"],
    "menu.view": ["View"],
    "menu.studio_one": ["Studio One"],
    "menu.help": ["Help"],
    "menu.song_setup": ["Song", "Song Setup…"],
    "menu.external_devices": ["Studio One", "Options…"],  # then External Devices tab in UI
    "menu.keyboard_shortcuts": ["Studio One", "Keyboard Shortcuts…"],
    "menu.add_tracks": ["Track", "Add Tracks…"],
    "menu.import_files": ["File", "Import Files…"],
}
for mid, path in MENU_ACTIONS.items():
    _c(mid, "menu", f"Menu {' → '.join(path)}", path=path)


def list_commands(q: str = "") -> List[Dict[str, Any]]:
    q = (q or "").lower().strip()
    out = []
    for cid, meta in sorted(COMMANDS.items()):
        if q and q not in cid.lower() and q not in meta.get("description", "").lower():
            continue
        out.append({"id": cid, **meta})
    return out


def coverage_summary() -> Dict[str, int]:
    layers: Dict[str, int] = {}
    for meta in COMMANDS.values():
        layers[meta["layer"]] = layers.get(meta["layer"], 0) + 1
    layers["total"] = len(COMMANDS)
    return layers
