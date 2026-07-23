"""Command-line interface for s1-remote."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__, config
from .controller import S1Remote
from .hotkeys import ACTIONS
from .midi.port import list_ports


def _remote(args) -> S1Remote:
    r = S1Remote(out_port=getattr(args, "port", None) or None, in_port=getattr(args, "in_port", None) or None)
    if getattr(args, "no_connect", False):
        return r
    # CLI one-shots only need outbound MIDI (skip feedback port — avoids Windows hang).
    need_midi = getattr(args, "_need_midi", True)
    if need_midi:
        r.connect(open_input=False)
    return r


def cmd_status(args) -> int:
    r = S1Remote()
    try:
        r.connect(open_input=False)
    except Exception as e:
        print(f"MIDI connect skipped: {e}")
    print(json.dumps(r.status(), indent=2))
    r.disconnect()
    return 0


def cmd_ports(args) -> int:
    print(json.dumps(list_ports(), indent=2))
    return 0


def cmd_connect(args) -> int:
    r = S1Remote(out_port=args.port or None, in_port=args.in_port or None)
    r.connect()
    print(f"Connected OUT={r.bridge.out_name!r} IN={r.bridge.in_name!r}")
    r.disconnect()
    return 0


def cmd_transport(args) -> int:
    r = _remote(args)
    try:
        getattr(r.mcu, args.action)()
        print(f"transport {args.action}")
    finally:
        r.disconnect()
    return 0


def cmd_fader(args) -> int:
    r = _remote(args)
    try:
        r.mcu.fader(args.channel, db=args.db)
        print(f"fader ch{args.channel} = {args.db} dB")
    finally:
        r.disconnect()
    return 0


def cmd_mute(args) -> int:
    r = _remote(args)
    try:
        r.mute(args.channel)
        print(f"mute ch{args.channel}")
    finally:
        r.disconnect()
    return 0


def cmd_solo(args) -> int:
    r = _remote(args)
    try:
        r.solo(args.channel)
        print(f"solo ch{args.channel}")
    finally:
        r.disconnect()
    return 0


def cmd_select(args) -> int:
    r = _remote(args)
    try:
        r.mcu.select(args.channel)
        print(f"select ch{args.channel}")
    finally:
        r.disconnect()
    return 0


def cmd_bank(args) -> int:
    r = _remote(args)
    try:
        if args.direction == "left":
            r.mcu.bank_left()
        else:
            r.mcu.bank_right()
        print(f"bank {args.direction}")
    finally:
        r.disconnect()
    return 0


def cmd_cc(args) -> int:
    r = _remote(args)
    try:
        r.plugin_cc(args.control, args.value, args.channel)
        print(f"CC ch{args.channel} #{args.control} = {args.value}")
    finally:
        r.disconnect()
    return 0


def cmd_learn_wiggle(args) -> int:
    r = _remote(args)
    try:
        r.link.sweep(args.control, channel=args.channel)
        print(f"wiggled CC {args.control} (Control Link learn)")
    finally:
        r.disconnect()
    return 0


def cmd_param(args) -> int:
    r = _remote(args)
    try:
        val: float | int
        if "." in args.value:
            val = float(args.value)
        else:
            val = int(args.value)
        r.plugin_param(args.plugin, args.param, val)
        print(f"{args.plugin}.{args.param} = {val}")
    finally:
        r.disconnect()
    return 0


def cmd_map_define(args) -> int:
    r = S1Remote()
    r.link.define(args.plugin, args.param, args.control, args.channel, note=args.note or "")
    path = r.link.save(config.MAPS_PATH)
    print(f"Saved {args.plugin}/{args.param} -> CC {args.control} in {path}")
    return 0


def cmd_map_list(args) -> int:
    r = S1Remote()
    if args.plugin:
        print(json.dumps(r.link.list_params(args.plugin), indent=2))
    else:
        print(json.dumps(r.link.list_plugins(), indent=2))
    return 0


def cmd_note(args) -> int:
    r = _remote(args)
    try:
        r.note(args.note, args.duration, args.velocity, args.channel)
        print(f"note {args.note} vel {args.velocity} {args.duration}s")
    finally:
        r.disconnect()
    return 0


def cmd_mcu(args) -> int:
    r = _remote(args)
    try:
        r.mcu.click(args.button)
        print(f"mcu {args.button}")
    finally:
        r.disconnect()
    return 0


def cmd_mode(args) -> int:
    r = _remote(args)
    try:
        getattr(r.mcu, f"mode_{args.mode}")()
        print(f"mode {args.mode}")
    finally:
        r.disconnect()
    return 0


def cmd_hotkey(args) -> int:
    r = S1Remote()
    r.hotkey(args.action)
    print(f"hotkey {args.action}")
    return 0


def cmd_hotkeys(args) -> int:
    print("\n".join(sorted(ACTIONS)))
    return 0


def cmd_api(args) -> int:
    from .api import run_server

    settings = config.load_settings()
    r = S1Remote(out_port=args.port or None, in_port=args.in_port or None)
    try:
        r.connect()
    except Exception as e:
        print(f"Warning: MIDI not connected ({e}). API will start anyway.")
    host = args.host or settings.get("api_host", "127.0.0.1")
    port = int(args.api_port or settings.get("api_port", 8765))
    print(f"s1-remote API on http://{host}:{port}  MIDI out={r.bridge.out_name!r}")
    run_server(r, host=host, port=port)
    return 0


def _parse_vst_value(raw: str) -> float | int:
    if "." in raw:
        return float(raw)
    return int(raw)


def cmd_vst(args) -> int:
    """VST / plugin MIDI (Control Link) commands."""
    from .vst_midi import VstMidiControl, setup_instructions

    action = args.vst_action
    if action == "setup":
        print(setup_instructions())
        return 0

    if action == "scan":
        from .vst_re import scan_and_save

        print("Reverse-engineering installed VSTs + stock SurfaceData catalog…")
        summary = scan_and_save(
            use_pedalboard=not getattr(args, "no_host", False),
            use_strings=not getattr(args, "no_strings", False),
            use_surface=not getattr(args, "no_surface", False),
        )
        print(json.dumps(summary, indent=2))
        print("\nNext: py -3.12 -m s1remote vst list")
        print("      py -3.12 -m s1remote vst show <plugin>")
        print("      py -3.12 -m s1remote vst learn-all <plugin>")
        return 0

    if action == "list":
        v = VstMidiControl()
        print(json.dumps(v.list_plugins(), indent=2))
        return 0

    if action == "show":
        v = VstMidiControl()
        print(json.dumps(v.show(args.plugin), indent=2))
        return 0

    if action == "define":
        v = VstMidiControl()
        path = v.define(args.plugin, args.param, args.control, args.channel)
        print(f"Saved {args.plugin}/{args.param} -> CC {args.control} in {path}")
        return 0

    # MIDI-needed actions
    with VstMidiControl(out_port=getattr(args, "port", None) or None) as v:
        print(f"MIDI OUT {v.bridge.out_name!r}")
        if action == "cc":
            v.cc(args.control, args.value, args.channel)
            print(f"CC ch{args.channel} #{args.control} = {args.value}")
        elif action == "set":
            val = _parse_vst_value(args.value)
            info = v.set(args.plugin, args.param, val)
            print(json.dumps(info, indent=2))
        elif action == "learn-wiggle":
            v.learn_wiggle(args.control, args.channel)
            print(f"Wiggled CC {args.control} (Control Link learn)")
        elif action == "learn":
            info = v.learn_param(args.plugin, args.param)
            print(json.dumps(info, indent=2))
        elif action == "learn-all":
            print(f"Learn-all {args.plugin} — Control Link + Focus ON, click each param when listed")
            results = v.learn_all(args.plugin, pause=args.pause, limit=args.limit)
            print(json.dumps({"learned": len(results), "params": results}, indent=2))
        else:
            print(f"Unknown vst action {action}", file=sys.stderr)
            return 1
    return 0


def cmd_ucnet_discover(args) -> int:
    from .ucnet import discover

    servers = discover(timeout=float(args.timeout), extra_hosts=args.host or None)
    if not servers:
        print("No UCNET servers found.")
        print("Check Studio One → Options → General → Network → Allow remote control apps…")
        return 1
    out = []
    for s in servers:
        out.append(
            {
                "name": s.name,
                "type": s.type,
                "id": s.server_id,
                "hostname": s.hostname,
                "host": s.host,
                "tcp_port": s.tcp_port,
                "udp_reply_port": s.udp_reply_port,
                "event_type": hex(s.event_type),
                "flags": hex(s.flags),
                "is_daw": s.is_daw,
                "source_ips": s.source_ips,
                "endpoint": s.endpoint(),
            }
        )
    print(json.dumps(out, indent=2))
    return 0


def cmd_ucnet_connect(args) -> int:
    """RE session connect — discovery + TCP handshake attempts."""
    from .ucnet.session import UCSession

    sess = UCSession(timeout=float(args.timeout))
    result = sess.connect()
    print(
        json.dumps(
            {
                "ok": result.ok,
                "note": result.note,
                "hits": result.probes_hit,
                "hello_bytes": len(result.hello),
                "server": None
                if not result.server
                else {
                    "name": result.server.name,
                    "endpoint": result.server.endpoint(),
                    "id": result.server.server_id,
                    "tcp": result.server.tcp_port,
                    "udp_reply": result.server.udp_reply_port,
                    "flags": result.server.flags,
                },
                "known_paths_sample": sess.known_paths(4)[:12],
                "protocol_doc": "re/UCNET_PROTOCOL.md",
            },
            indent=2,
        )
    )
    if args.try_param:
        print(json.dumps(sess.try_set_param(args.try_param, float(args.value)), indent=2))
    sess.close()
    return 0 if result.ok else 1


def cmd_ucnet_paths(args) -> int:
    from .ucnet.paths import all_core_paths, channel_paths, transport_paths

    if args.kind == "transport":
        paths = transport_paths()
    elif args.kind == "channel":
        paths = channel_paths("channel", int(args.index))
    else:
        paths = all_core_paths(int(args.channels))
    print(json.dumps({"count": len(paths), "paths": paths}, indent=2))
    return 0


def cmd_setup(args) -> int:
    settings = config.load_settings()
    out_p = settings.get("midi_out_port")
    in_p = settings.get("midi_in_port")
    print(
        f"""
Studio One setup (one time)
===========================

1. Virtual MIDI cable
   Install loopMIDI and create a port (e.g. "S1 Controller").
   Default config on this PC:
     OUT (this tool sends):     {out_p}
     IN  (this tool receives):  {in_p}

2. Studio One → Options → External Devices → Add
   • Mackie → Control
       Receive From = {out_p}   (must match what we send on)
       Send To      = {in_p}    (feedback LEDs / meters)
   • Optional: New Keyboard on the same cable for instrument notes

   If transport does nothing, swap Receive From / Send To (or swap
   midi_out_port / midi_in_port in config/settings.json).

3. Control Link for VST / any plug-in parameter
   • Control Link ON + Focus ON in Studio One toolbar
   • Click a parameter
   • py -3.12 -m s1remote learn-wiggle 20
   • Or right-click parameter → Assign External Control

4. Full control stack
   py -3.12 -m s1remote full package     # build in-host package
   py -3.12 -m s1remote full caps        # capability matrix
   py -3.12 -m s1remote full program-maps
   py -3.12 -m s1remote full do mixer.mode_plugin
   Install host package → run Scripts → S1 Full Control: Process Queue

5. Quick tests
   py -3.12 -m s1remote ports
   py -3.12 -m s1remote status
   py -3.12 -m s1remote transport play
   py -3.12 -m s1remote fader 0 --db -6
   py -3.12 -m s1remote mode plugin
   py -3.12 -m s1remote cc 20 100
   py -3.12 -m s1remote note 60 --duration 0.5
   py -3.12 -m s1remote api
"""
    )
    return 0


def cmd_full(args) -> int:
    """Full Control surface — all layers."""
    from .full_control import FullControl, build_host_package

    action = args.full_action

    if action == "package":
        path = build_host_package()
        print(f"Built host package: {path}")
        print("Install: Studio One → Scripts / drag package, or copy to user Scripts.")
        print("Then: Scripts menu → S1 Full Control: Process Queue")
        return 0

    if action == "commands":
        from .commands_catalog import list_commands, coverage_summary

        print(json.dumps({"coverage": coverage_summary(), "commands": list_commands(args.query or "")}, indent=2))
        return 0

    if action == "caps":
        with FullControl(out_port=getattr(args, "port", None)) as fc:
            print(json.dumps(fc.capabilities(), indent=2))
        return 0

    if action == "status":
        with FullControl(out_port=getattr(args, "port", None)) as fc:
            print(json.dumps(fc.status(), indent=2))
        return 0

    if action == "program-maps":
        with FullControl(out_port=getattr(args, "port", None)) as fc:
            info = fc.program_all_maps()
            print(json.dumps(info, indent=2))
        return 0

    if action == "do":
        with FullControl(out_port=getattr(args, "port", None)) as fc:
            kwargs = {}
            if args.db is not None:
                kwargs["db"] = args.db
            if args.search:
                kwargs["search"] = args.search
            if args.value is not None:
                kwargs["value"] = args.value
            if args.channel is not None:
                kwargs["channel"] = args.channel
            if args.delta is not None:
                kwargs["delta"] = args.delta
            result = fc.do(args.command_id, **kwargs)
            print(json.dumps(result, indent=2, default=str))
        return 0

    if action == "host":
        with FullControl(out_port=getattr(args, "port", None)) as fc:
            rid = fc.host(args.task, **(json.loads(args.params) if args.params else {}))
            print(json.dumps({"request_id": rid, "task": args.task}, indent=2))
            print("Run in S1: Scripts → S1 Full Control: Process Queue")
        return 0

    if action == "browser-load":
        with FullControl(out_port=getattr(args, "port", None)) as fc:
            fc.browser_load(args.search)
            print(f"browser load {args.search!r}")
        return 0

    if action == "plugin-mode":
        with FullControl(out_port=getattr(args, "port", None)) as fc:
            fc.plugin_mode()
            print("MCU plugin mode — V-Pots drive focused plugin params")
        return 0

    if action == "vpot":
        with FullControl(out_port=getattr(args, "port", None)) as fc:
            fc.vpot(args.channel, args.delta)
            print(f"vpot ch{args.channel} delta={args.delta}")
        return 0

    print(f"Unknown full action {action}", file=sys.stderr)
    return 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="s1remote",
        description="Remote-control PreSonus Studio One (MCU + Control Link + MIDI I/O)",
    )
    p.add_argument("--version", action="version", version=f"s1-remote {__version__}")
    p.add_argument("--port", help="MIDI output port name (we send on this)")
    p.add_argument("--in-port", dest="in_port", help="MIDI input port name (feedback)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status", help="Connection + Studio One status")
    s.set_defaults(func=cmd_status, _need_midi=False)

    s = sub.add_parser("ports", help="List MIDI ports")
    s.set_defaults(func=cmd_ports, _need_midi=False)

    s = sub.add_parser("setup", help="Print Studio One wiring instructions")
    s.set_defaults(func=cmd_setup, _need_midi=False)

    s = sub.add_parser("connect", help="Open MIDI and save port choice")
    s.set_defaults(func=cmd_connect)

    s = sub.add_parser("transport", help="play|stop|record|rewind|ffwd|cycle|click_metronome")
    s.add_argument("action", choices=["play", "stop", "record", "rewind", "ffwd", "cycle", "click_metronome"])
    s.set_defaults(func=cmd_transport)

    s = sub.add_parser("fader", help="Set channel fader in dB")
    s.add_argument("channel", type=int)
    s.add_argument("--db", type=float, required=True)
    s.set_defaults(func=cmd_fader)

    s = sub.add_parser("mute", help="Toggle mute")
    s.add_argument("channel", type=int)
    s.set_defaults(func=cmd_mute)

    s = sub.add_parser("solo", help="Toggle solo")
    s.add_argument("channel", type=int)
    s.set_defaults(func=cmd_solo)

    s = sub.add_parser("select", help="Select mixer channel")
    s.add_argument("channel", type=int)
    s.set_defaults(func=cmd_select)

    s = sub.add_parser("bank", help="Bank mixer left/right")
    s.add_argument("direction", choices=["left", "right"])
    s.set_defaults(func=cmd_bank)

    s = sub.add_parser("cc", help="Send Control Link CC")
    s.add_argument("control", type=int)
    s.add_argument("value", type=int)
    s.add_argument("--channel", type=int, default=0)
    s.set_defaults(func=cmd_cc)

    s = sub.add_parser("learn-wiggle", help="Sweep a CC for Control Link learn")
    s.add_argument("control", type=int)
    s.add_argument("--channel", type=int, default=0)
    s.set_defaults(func=cmd_learn_wiggle)

    s = sub.add_parser("param", help="Set mapped plugin param")
    s.add_argument("plugin")
    s.add_argument("param")
    s.add_argument("value")
    s.set_defaults(func=cmd_param)

    s = sub.add_parser("map-define", help="Bind plugin param → CC in local map")
    s.add_argument("plugin")
    s.add_argument("param")
    s.add_argument("control", type=int)
    s.add_argument("--channel", type=int, default=0)
    s.add_argument("--note", default="")
    s.set_defaults(func=cmd_map_define, _need_midi=False)

    s = sub.add_parser("map-list", help="List plugin maps")
    s.add_argument("plugin", nargs="?")
    s.set_defaults(func=cmd_map_list, _need_midi=False)

    s = sub.add_parser("note", help="Play a MIDI note")
    s.add_argument("note", type=int)
    s.add_argument("--duration", type=float, default=0.25)
    s.add_argument("--velocity", type=int, default=100)
    s.add_argument("--channel", type=int, default=0)
    s.set_defaults(func=cmd_note)

    s = sub.add_parser("mcu", help="Click any MCU button by name (play, plugin, f1, ...)")
    s.add_argument("button")
    s.set_defaults(func=cmd_mcu)

    s = sub.add_parser("mode", help="MCU assign mode")
    s.add_argument("mode", choices=["plugin", "pan", "send", "track", "eq"])
    s.set_defaults(func=cmd_mode)

    s = sub.add_parser("hotkey", help="Send Studio One keyboard shortcut")
    s.add_argument("action")
    s.set_defaults(func=cmd_hotkey, _need_midi=False)

    s = sub.add_parser("hotkeys", help="List hotkey action names")
    s.set_defaults(func=cmd_hotkeys, _need_midi=False)

    # ---- Full Control (all layers) ----
    s = sub.add_parser("full", help="Full Control: MCU + VST + menus + host + browser")
    full_sub = s.add_subparsers(dest="full_action", required=True)

    fs = full_sub.add_parser("caps", help="Capability matrix (honest)")
    fs.set_defaults(func=cmd_full, full_action="caps", _need_midi=False)

    fs = full_sub.add_parser("status", help="Full control status")
    fs.set_defaults(func=cmd_full, full_action="status")

    fs = full_sub.add_parser("commands", help="List routed commands")
    fs.add_argument("query", nargs="?", default="")
    fs.set_defaults(func=cmd_full, full_action="commands", _need_midi=False)

    fs = full_sub.add_parser("package", help="Build in-host S1 Full Control package")
    fs.set_defaults(func=cmd_full, full_action="package", _need_midi=False)

    fs = full_sub.add_parser("program-maps", help="Pulse all VST map CCs (no mouse)")
    fs.set_defaults(func=cmd_full, full_action="program-maps")

    fs = full_sub.add_parser("do", help="Run catalog command id")
    fs.add_argument("command_id")
    fs.add_argument("--db", type=float, default=None)
    fs.add_argument("--search", default="")
    fs.add_argument("--value", type=float, default=None)
    fs.add_argument("--channel", type=int, default=None)
    fs.add_argument("--delta", type=int, default=None)
    fs.set_defaults(func=cmd_full, full_action="do")

    fs = full_sub.add_parser("host", help="Enqueue in-host task")
    fs.add_argument("task")
    fs.add_argument("--params", default="{}", help="JSON object of params")
    fs.set_defaults(func=cmd_full, full_action="host")

    fs = full_sub.add_parser("browser-load", help="Browser search + load (keyboard)")
    fs.add_argument("search")
    fs.set_defaults(func=cmd_full, full_action="browser-load")

    fs = full_sub.add_parser("plugin-mode", help="MCU V-Pots → focused plugin params")
    fs.set_defaults(func=cmd_full, full_action="plugin-mode")

    fs = full_sub.add_parser("vpot", help="Turn V-Pot (plugin param in plugin mode)")
    fs.add_argument("channel", type=int)
    fs.add_argument("--delta", type=int, default=4)
    fs.set_defaults(func=cmd_full, full_action="vpot")

    s = sub.add_parser("api", help="Start HTTP API server")
    s.add_argument("--host", default=None)
    s.add_argument("--api-port", type=int, default=None)
    s.set_defaults(func=cmd_api)

    # ---- VST MIDI (Control Link) ----
    s = sub.add_parser("vst", help="VST / plugin MIDI control via Control Link")
    vst_sub = s.add_subparsers(dest="vst_action", required=True)

    vs = vst_sub.add_parser("setup", help="Print Studio One Control Link setup")
    vs.set_defaults(func=cmd_vst, _need_midi=False)

    vs = vst_sub.add_parser(
        "scan",
        help="RE all installed VST/VST3 + stock catalog → maps",
    )
    vs.add_argument("--no-host", action="store_true", help="Skip pedalboard host load")
    vs.add_argument("--no-strings", action="store_true", help="Skip binary string scrape")
    vs.add_argument("--no-surface", action="store_true", help="Skip Studio One SurfaceData")
    vs.set_defaults(func=cmd_vst, _need_midi=False)

    vs = vst_sub.add_parser("list", help="List plugin maps")
    vs.set_defaults(func=cmd_vst, _need_midi=False)

    vs = vst_sub.add_parser("show", help="Show params + CC numbers for a map")
    vs.add_argument("plugin")
    vs.set_defaults(func=cmd_vst, _need_midi=False)

    vs = vst_sub.add_parser("cc", help="Send raw MIDI CC")
    vs.add_argument("control", type=int)
    vs.add_argument("value", type=int)
    vs.add_argument("--channel", type=int, default=0)
    vs.set_defaults(func=cmd_vst)

    vs = vst_sub.add_parser("set", help="Set named mapped param (0-127 or 0.0-1.0)")
    vs.add_argument("plugin")
    vs.add_argument("param")
    vs.add_argument("value")
    vs.set_defaults(func=cmd_vst)

    vs = vst_sub.add_parser("learn-wiggle", help="Wiggle a CC for Control Link learn")
    vs.add_argument("control", type=int)
    vs.add_argument("--channel", type=int, default=0)
    vs.set_defaults(func=cmd_vst)

    vs = vst_sub.add_parser("learn", help="Wiggle CC for one named param in a map")
    vs.add_argument("plugin")
    vs.add_argument("param")
    vs.set_defaults(func=cmd_vst)

    vs = vst_sub.add_parser("learn-all", help="Walk all params in a map (click each in S1)")
    vs.add_argument("plugin")
    vs.add_argument("--pause", type=float, default=1.2, help="Seconds between params")
    vs.add_argument("--limit", type=int, default=None, help="Only first N params")
    vs.set_defaults(func=cmd_vst)

    vs = vst_sub.add_parser("define", help="Save plugin/param → CC mapping")
    vs.add_argument("plugin")
    vs.add_argument("param")
    vs.add_argument("control", type=int)
    vs.add_argument("--channel", type=int, default=0)
    vs.set_defaults(func=cmd_vst, _need_midi=False)

    s = sub.add_parser("ucnet-discover", help="UCNET UDP discovery (Studio One Remote protocol)")
    s.add_argument("--timeout", type=float, default=2.0)
    s.add_argument("--host", action="append", default=[], help="Extra unicast host to query")
    s.set_defaults(func=cmd_ucnet_discover, _need_midi=False)

    s = sub.add_parser("ucnet-connect", help="Discover + open TCP session (RE framing)")
    s.add_argument("--timeout", type=float, default=2.0)
    s.add_argument("--try-param", default="", help="Best-effort ParamValue path after connect")
    s.add_argument("--value", type=float, default=1.0)
    s.set_defaults(func=cmd_ucnet_connect, _need_midi=False)

    s = sub.add_parser("ucnet-paths", help="List reverse-engineered DAWRemote param paths")
    s.add_argument("--kind", choices=["all", "transport", "channel"], default="all")
    s.add_argument("--channels", type=int, default=8)
    s.add_argument("--index", type=int, default=1)
    s.set_defaults(func=cmd_ucnet_paths, _need_midi=False)

    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except BrokenPipeError:
        return 0
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
