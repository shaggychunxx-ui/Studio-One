"""
Studio One 6.6 UI command catalog.

Each entry is something an agent can fire against the live UI:

  layer  how it is invoked
  ------ -----------------
  hotkey named action in s1remote.hotkeys.ACTIONS
  find   Find Command (Ctrl+K) using `name`
  menu   Alt-menu path
  region named layout region click
  host   Host.GUI.Commands.interpretCommand(category, name)

`do()` prefers hotkey → find → menu → region. MCU/MIDI stay in FullControl.
Names match Keyboard Shortcuts / Find Command as closely as the 6.6 manual.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

UI_COMMANDS: Dict[str, Dict[str, Any]] = {}


def _u(
    id_: str,
    name: str,
    *,
    category: str = "",
    hotkey: str = "",
    menu: Optional[List[str]] = None,
    region: str = "",
    description: str = "",
    page: str = "song",
) -> None:
    UI_COMMANDS[id_] = {
        "name": name,
        "category": category,
        "hotkey": hotkey,
        "menu": list(menu or []),
        "region": region,
        "description": description or name,
        "page": page,
    }


# ---- File ----
_u("file.new", "New", category="File", hotkey="new_song", menu=["File", "New…"], page="any")
_u("file.open", "Open", category="File", hotkey="open", menu=["File", "Open…"], page="any")
_u("file.close", "Close", category="File", hotkey="close", menu=["File", "Close"])
_u("file.save", "Save", category="File", hotkey="save", menu=["File", "Save"])
_u("file.save_as", "Save As...", category="File", menu=["File", "Save As..."])
_u("file.exit", "Exit", category="File", menu=["File", "Exit"], page="any")

# ---- Song / export / import ----
_u("song.setup", "Song Setup", category="Song", menu=["Song", "Song Setup…"])
_u("song.import_file", "Import File", category="Song", hotkey="import_file", menu=["Song", "Import File…"])
_u("song.export_mixdown", "Export Mixdown", category="Song", hotkey="export_mixdown", menu=["Song", "Export Mixdown…"])
_u("song.export_stems", "Export Stems", category="Song", menu=["Song", "Export Stems…"])
_u("song.add_to_project", "Add to Project", category="Song", menu=["Song", "Add to Project"])
_u("song.add_to_show", "Add to Show", category="Song", menu=["Song", "Add to Show"])

# ---- Edit ----
_u("edit.undo", "Undo", category="Edit", hotkey="undo", menu=["Edit", "Undo"])
_u("edit.redo", "Redo", category="Edit", hotkey="redo", menu=["Edit", "Redo"])
_u("edit.cut", "Cut", category="Edit", hotkey="cut", menu=["Edit", "Cut"])
_u("edit.copy", "Copy", category="Edit", hotkey="copy", menu=["Edit", "Copy"])
_u("edit.paste", "Paste", category="Edit", hotkey="paste", menu=["Edit", "Paste"])
_u("edit.delete", "Delete", category="Edit", hotkey="delete", menu=["Edit", "Delete"])
_u("edit.select_all", "Select All", category="Edit", hotkey="select_all", menu=["Edit", "Select All"])
_u("edit.duplicate", "Duplicate", category="Edit", hotkey="duplicate", menu=["Edit", "Duplicate"])
_u("edit.duplicate_shared", "Duplicate Shared", category="Edit")
_u("edit.split", "Split", category="Edit", hotkey="split")
_u("edit.split_at_cursor", "Split at Cursor", category="Event", hotkey="split_at_cursor")
_u("edit.merge", "Merge", category="Event", hotkey="merge")
_u("edit.quantize", "Quantize", category="Event", hotkey="quantize")
_u("edit.quantize_selection", "Quantize Selection", category="Event", hotkey="quantize_selection")
_u("edit.crossfade", "Crossfade", category="Event", hotkey="crossfade")
_u("edit.bounce_selection", "Bounce Selection", category="Event", hotkey="bounce_selection")
_u("edit.nudge_left", "Nudge Left", category="Event", hotkey="nudge_left")
_u("edit.nudge_right", "Nudge Right", category="Event", hotkey="nudge_right")

# ---- Track ----
_u("track.add", "Add Tracks", category="Track", hotkey="add_tracks", menu=["Track", "Add Tracks…"])
_u("track.add_instrument", "Add Instrument Track", category="Track", menu=["Track", "Add", "Instrument Track"])
_u("track.add_audio", "Add Audio Track", category="Track", menu=["Track", "Add", "Audio Track"])
_u("track.add_folder", "Add Folder Track", category="Track", menu=["Track", "Add", "Folder Track"])
_u("track.duplicate", "Duplicate Tracks", category="Track")
_u("track.delete", "Delete Tracks", category="Track")
_u("track.arm", "Record Enable", category="Track", hotkey="arm")
_u("track.mute", "Mute", category="Track", hotkey="track_mute")
_u("track.solo", "Solo", category="Track", hotkey="track_solo")
_u("track.monitor", "Monitor", category="Track")
_u("track.group", "Group Tracks", category="Track", hotkey="group_tracks")
_u("track.dissolve_group", "Dissolve Group", category="Track", hotkey="dissolve_group")
_u("track.freeze", "Freeze Track", category="Track")
_u("track.transform_audio", "Transform to Rendered Audio", category="Track")
_u("track.pack_folder", "Pack Folder", category="Track")
_u("track.find", "Find Track", category="Track", hotkey="find_track")
_u("track.hide", "Hide Track", category="Track")
_u("track.show_all", "Show All Tracks", category="Track")

# ---- Event / audio ----
_u("event.normalize", "Normalize", category="Event")
_u("event.reverse", "Reverse", category="Audio")
_u("event.strip_silence", "Strip Silence", category="Audio")
_u("event.audio_bend", "Audio Bend", category="Audio")
_u("event.detect_tempo", "Detect Tempo", category="Audio")
_u("event.stretch", "Audio Stretch", category="Audio")

# ---- Transport ----
_u("transport.play", "Play", category="Transport", hotkey="transport_play", region="transport.play")
_u("transport.stop", "Stop", category="Transport", region="transport.stop")
_u("transport.record", "Record", category="Transport", region="transport.record")
_u("transport.loop", "Loop", category="Transport", hotkey="loop_toggle", region="transport.loop")
_u("transport.metronome", "Metronome", category="Transport", hotkey="metronome", region="transport.metronome")
_u("transport.precount", "Precount", category="Transport", hotkey="precount")
_u("transport.preroll", "Preroll", category="Transport", hotkey="preroll")
_u("transport.auto_punch", "Auto Punch", category="Transport", hotkey="auto_punch")
_u("transport.return_zero", "Return to Zero", category="Transport", hotkey="return_zero")
_u("transport.rewind", "Rewind", category="Transport", region="transport.rewind")
_u("transport.retrospective", "Recall Retrospective Recording", category="Transport")

# ---- Views / pages ----
_u("view.editor", "Editor", category="View", hotkey="editor", region="editor")
_u("view.console", "Console", category="View", hotkey="console", region="console")
_u("view.inspector", "Inspector", category="View", hotkey="inspector", region="inspector")
_u("view.browser", "Browser", category="View", hotkey="browser", region="browser")
_u("view.fullscreen", "Full Screen", category="View", hotkey="fullscreen")
_u("view.start", "Start Page", category="View", region="page.start", page="any")
_u("view.song", "Song Page", category="View", region="page.song", page="any")
_u("view.project", "Project Page", category="View", region="page.project", page="any")
_u("view.show", "Show Page", category="View", region="page.show", page="any")
_u("view.channel_editor", "Channel Editor", category="View", hotkey="channel_editor")
_u("view.instrument_editor", "Instrument Editor", category="View", hotkey="instrument_editor")
_u("view.zoom_in", "Zoom In", category="View", hotkey="zoom_in")
_u("view.zoom_out", "Zoom Out", category="View", hotkey="zoom_out")
_u("view.automation_lanes", "Automation Lanes", category="View", hotkey="automation_lanes")
_u("view.arranger", "Arranger Track", category="View")
_u("view.chord_track", "Chord Track", category="View")
_u("view.marker_track", "Marker Track", category="View")
_u("view.tempo_track", "Tempo Track", category="View")
_u("view.signature_track", "Signature Track", category="View")
_u("view.small_console", "Small Console", category="View")
_u("view.info", "Info View", category="View")
_u("view.find_command", "Find Command", category="View", hotkey="command_search")
_u("view.find_channel", "Find Channel", category="View", hotkey="find_channel")

# ---- Browser tabs ----
_u("browser.instruments", "Instruments", category="Browser", hotkey="browser_instruments", region="browser.instruments")
_u("browser.effects", "Effects", category="Browser", hotkey="browser_effects", region="browser.effects")
_u("browser.loops", "Loops", category="Browser", hotkey="browser_loops")
_u("browser.files", "Files", category="Browser", hotkey="browser_files")
_u("browser.pool", "Pool", category="Browser", hotkey="browser_pool")

# ---- Tools ----
_u("tool.arrow", "Arrow Tool", category="Edit", hotkey="tool_arrow")
_u("tool.range", "Range Tool", category="Edit", hotkey="tool_range")
_u("tool.split", "Split Tool", category="Edit", hotkey="tool_split")
_u("tool.eraser", "Eraser Tool", category="Edit", hotkey="tool_eraser")
_u("tool.paint", "Paint Tool", category="Edit", hotkey="tool_paint")
_u("tool.mute", "Mute Tool", category="Edit", hotkey="tool_mute")

# ---- Mix / console ----
_u("mix.find_channel", "Find Channel", category="Console", hotkey="find_channel")
_u("mix.scenes", "Scenes", category="Console")
_u("mix.vca", "VCA", category="Console")
_u("mix.cue", "Cue Mix", category="Console")
_u("mix.inserts", "Show Inserts", category="Console")
_u("mix.sends", "Show Sends", category="Console")

# ---- Automation ----
_u("auto.read", "Automation Read", category="Automation")
_u("auto.touch", "Automation Touch", category="Automation")
_u("auto.latch", "Automation Latch", category="Automation")
_u("auto.write", "Automation Write", category="Automation")
_u("auto.trim", "Automation Trim", category="Automation")
_u("auto.apply", "Apply Current Automation", category="Automation")

# ---- Studio One / Help ----
_u("app.options", "Options", category="Application", hotkey="options", menu=["Studio One", "Options…"], page="any")
_u("app.keyboard_shortcuts", "Keyboard Shortcuts", category="Application", menu=["Studio One", "Keyboard Shortcuts…"], page="any")
_u("app.external_devices", "External Devices", category="Application", menu=["Studio One", "Options…"], page="any")
_u("app.macros", "Macro Organizer", category="Gadgets", page="any")
_u("help.manual", "Studio One Reference Manual", category="Help", menu=["Help", "Studio One Reference Manual"], page="any")
_u("help.shortcuts", "Keyboard Shortcuts", category="Help", menu=["Help", "Keyboard Shortcuts"], page="any")
_u("help.about", "About Studio One", category="Help", menu=["Help", "About Studio One"], page="any")

# ---- Control Link ----
_u("link.assign", "Assign External Control", category="Studio One", hotkey="control_link_assign")

# ---- Show / Project (page switch + common) ----
_u("show.setlist", "Setlist", category="Show", page="show")
_u("project.add_song", "Add Song", category="Project", page="project")


def get(id_: str) -> Dict[str, Any]:
    if id_ not in UI_COMMANDS:
        raise KeyError(f"Unknown UI command {id_!r}")
    return UI_COMMANDS[id_]


def search(q: str = "") -> List[Dict[str, Any]]:
    q = (q or "").lower().strip()
    out = []
    for cid, meta in sorted(UI_COMMANDS.items()):
        blob = " ".join(
            [
                cid,
                meta.get("name", ""),
                meta.get("category", ""),
                meta.get("description", ""),
                " ".join(meta.get("menu") or []),
                meta.get("hotkey", ""),
                meta.get("region", ""),
            ]
        ).lower()
        if q and q not in blob:
            continue
        out.append({"id": cid, **meta})
    return out


def coverage() -> Dict[str, int]:
    by: Dict[str, int] = {}
    for m in UI_COMMANDS.values():
        cat = m.get("category") or "other"
        by[cat] = by.get(cat, 0) + 1
    by["total"] = len(UI_COMMANDS)
    by["with_hotkey"] = sum(1 for m in UI_COMMANDS.values() if m.get("hotkey"))
    by["with_menu"] = sum(1 for m in UI_COMMANDS.values() if m.get("menu"))
    by["with_region"] = sum(1 for m in UI_COMMANDS.values() if m.get("region"))
    return by
