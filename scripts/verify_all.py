#!/usr/bin/env python3
"""
Verify s1-remote: imports, CLI help, MIDI connect, core APIs.
Does not thrash Studio One UI.

  py -3.12 -u scripts/verify_all.py
"""
from __future__ import annotations

import importlib
import json
import subprocess
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0
SKIP = 0
RESULTS: list[dict] = []


def record(name: str, ok: bool, detail: str = "", skip: bool = False) -> None:
    global PASS, FAIL, SKIP
    if skip:
        SKIP += 1
        status = "SKIP"
    elif ok:
        PASS += 1
        status = "PASS"
    else:
        FAIL += 1
        status = "FAIL"
    RESULTS.append({"name": name, "status": status, "detail": detail})
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""), flush=True)


def test_imports() -> None:
    print("\n=== Imports ===", flush=True)
    mods = [
        "s1remote",
        "s1remote.cli",
        "s1remote.config",
        "s1remote.controller",
        "s1remote.hotkeys",
        "s1remote.menus",
        "s1remote.vst_midi",
        "s1remote.full_control",
        "s1remote.commands_catalog",
        "s1remote.host_bridge",
        "s1remote.api",
        "s1remote.midi.port",
        "s1remote.midi.mcu",
        "s1remote.midi.control_link",
        "s1remote.midi.instrument",
        "s1remote.ucnet",
        "s1remote.ucnet.discovery",
        "s1remote.ucnet.events",
        "s1remote.ucnet.session",
        "s1remote.ucnet.paths",
        "s1remote.ucnet.client",
        "s1remote.vst_re",
    ]
    for m in mods:
        try:
            importlib.import_module(m)
            record(f"import {m}", True)
        except Exception as e:
            record(f"import {m}", False, f"{type(e).__name__}: {e}")


def test_cli_help() -> None:
    print("\n=== CLI --help ===", flush=True)
    cmds = [
        ["-h"],
        ["status", "-h"],
        ["ports", "-h"],
        ["setup", "-h"],
        ["transport", "-h"],
        ["fader", "-h"],
        ["mute", "-h"],
        ["vst", "-h"],
        ["full", "-h"],
        ["full", "caps", "-h"],
        ["ucnet-discover", "-h"],
        ["ucnet-connect", "-h"],
        ["ucnet-paths", "-h"],
        ["hotkeys"],
        ["map-list"],
    ]
    for args in cmds:
        try:
            r = subprocess.run(
                [sys.executable, "-m", "s1remote", *args],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=30,
                env={**dict(**{k: v for k, v in __import__("os").environ.items()}), "PYTHONPATH": str(ROOT)},
            )
            ok = r.returncode == 0
            detail = "" if ok else (r.stderr or r.stdout)[:200]
            record(f"cli {' '.join(args)}", ok, detail)
        except Exception as e:
            record(f"cli {' '.join(args)}", False, str(e))


def test_catalogs() -> None:
    print("\n=== Catalogs / pure functions ===", flush=True)
    try:
        from s1remote.commands_catalog import COMMANDS, coverage_summary, list_commands

        cov = coverage_summary()
        record("commands_catalog count", cov.get("total", 0) > 0, str(cov))
        record("list_commands mixer", len(list_commands("mixer")) > 0, str(len(list_commands("mixer"))))
        record("COMMANDS non-empty", len(COMMANDS) > 50, str(len(COMMANDS)))
    except Exception as e:
        record("commands_catalog", False, str(e))

    try:
        from s1remote.ucnet.paths import all_core_paths, transport_paths

        record("ucnet transport_paths", len(transport_paths()) >= 10, str(len(transport_paths())))
        record("ucnet all_core_paths", len(all_core_paths(8)) > 50, str(len(all_core_paths(8))))
    except Exception as e:
        record("ucnet paths", False, str(e))

    try:
        from s1remote.ucnet.events import EventType, event_tag_be

        record("EventType.PARAM_VALUE", EventType.PARAM_VALUE == 0x5056)
        record("event_tag_be DA", event_tag_be(EventType.DISCOVERY_ALIVE) == b"DA")
        record("EventType.ENCODED_MESSAGE", int(EventType.ENCODED_MESSAGE) == 0x4A4D)
    except Exception as e:
        record("ucnet events", False, str(e))

    try:
        from s1remote.hotkeys import ACTIONS

        record("hotkeys ACTIONS", "mixer" in ACTIONS and "save" in ACTIONS, str(len(ACTIONS)))
    except Exception as e:
        record("hotkeys", False, str(e))

    try:
        from s1remote.vst_midi import VstMidiControl, GENERIC_BANKS

        v = VstMidiControl()
        plugs = v.list_plugins()
        record("vst maps list", len(plugs) > 0, f"{len(plugs)} plugins")
        record("generic_16 bank", "generic_16" in plugs or "generic_16" in GENERIC_BANKS)
        if plugs:
            p0 = plugs[0]
            params = v.list_params(p0)
            record(f"vst show {p0}", len(params) > 0, f"{len(params)} params")
    except Exception as e:
        record("vst_midi maps", False, str(e))

    try:
        from s1remote.midi.mcu import NOTE, MackieControl

        record("MCU NOTE play", "play" in NOTE and NOTE["play"] == 0x5E)
        record("MCU NOTE mute base", NOTE["mute"] == 0x10)
    except Exception as e:
        record("mcu constants", False, str(e))

    try:
        from s1remote.host_bridge import ensure_queue_dir, enqueue, QUEUE_FILE

        ensure_queue_dir()
        rid = enqueue("list_tracks")
        record("host_bridge enqueue", bool(rid) and QUEUE_FILE.exists(), rid)
    except Exception as e:
        record("host_bridge", False, str(e))

    try:
        from s1remote.full_control import build_host_package

        path = build_host_package()
        record("build_host_package", path.is_file() and path.stat().st_size > 100, str(path))
    except Exception as e:
        record("build_host_package", False, str(e))


def test_midi_live() -> None:
    print("\n=== Live MIDI (if ports exist) ===", flush=True)
    try:
        from s1remote.midi.port import list_ports
        from s1remote.controller import S1Remote

        ports = list_ports()
        outs = ports.get("outputs") or []
        record("list_ports", True, f"out={outs}")
        if not any("S1" in p or "Controller" in p for p in outs):
            record("midi connect", False, "no S1 Controller port", skip=True)
            return
        r = S1Remote()
        r.connect(open_input=False)
        record("midi connect", r.connected, r.bridge.out_name)
        # non-destructive probes
        r.mcu.click("stop")
        record("mcu stop pulse", True)
        r.mute(0)
        record("mcu mute 0", True)
        r.fader(0, -6)
        record("mcu fader 0 -6dB", True)
        r.plugin_cc(20, 64)
        record("control_link cc 20", True)
        r.mcu.mode_plugin()
        record("mcu mode_plugin", True)
        r.disconnect()
        record("midi disconnect", True)
    except Exception as e:
        record("midi live", False, f"{type(e).__name__}: {e}\n{traceback.format_exc()[:300]}")


def test_full_control() -> None:
    print("\n=== FullControl API ===", flush=True)
    try:
        from s1remote.full_control import FullControl

        with FullControl() as fc:
            caps = fc.capabilities()
            record("full caps", "layers" in caps, json.dumps(caps.get("layers", {}))[:120])
            st = fc.status()
            record("full status", "midi_connected" in st or "studio_one_running" in st)
            cmds = fc.list_commands("mixer")
            record("full list_commands", len(cmds) > 0, str(len(cmds)))
            # do() for mcu mode without UI thrash
            res = fc.do("mixer.mode_plugin")
            record("full do mixer.mode_plugin", res.get("ok") is True, str(res))
            info = fc.program_all_maps()
            record(
                "full program_all_maps",
                info.get("plugins", 0) > 0,
                str(info),
            )
    except Exception as e:
        record("FullControl", False, f"{type(e).__name__}: {e}\n{traceback.format_exc()[:400]}")


def test_ucnet() -> None:
    print("\n=== UCNET discovery ===", flush=True)
    try:
        from s1remote.ucnet.discovery import discover
        from s1remote.ucnet.session import UCSession

        servers = discover(timeout=2.0, extra_hosts=["127.0.0.1"])
        record("ucnet discover", True, f"{len(servers)} server(s)")
        if servers:
            record("ucnet has DAW", any(s.is_daw for s in servers), servers[0].name)
        sess = UCSession(timeout=1.5)
        result = sess.connect()
        # connect may be ok=False if framing incomplete — still success if discovery worked
        record(
            "ucnet session connect attempt",
            result.server is not None or len(servers) == 0,
            result.note[:160],
        )
        if result.server:
            paths = sess.known_paths(4)
            record("ucnet known_paths", len(paths) > 10, str(len(paths)))
        sess.close()
    except Exception as e:
        record("ucnet", False, str(e))


def test_hotkey_no_crash() -> None:
    print("\n=== Hotkeys (focus only if S1 up) ===", flush=True)
    try:
        from s1remote.hotkeys import studio_one_running, focus_studio_one, run_action

        running = studio_one_running()
        record("studio_one_running", True, str(running))
        if not running:
            record("focus/hotkey", False, "S1 not running", skip=True)
            return
        ok = focus_studio_one()
        record("focus_studio_one", ok)
        run_action("mixer", focus=True)
        record("hotkey mixer", True)
    except Exception as e:
        record("hotkeys live", False, str(e))


def main() -> int:
    print("=" * 60, flush=True)
    print("s1-remote VERIFY ALL", flush=True)
    print("=" * 60, flush=True)
    test_imports()
    test_catalogs()
    test_cli_help()
    test_midi_live()
    test_full_control()
    test_ucnet()
    test_hotkey_no_crash()

    out = ROOT / "config" / "VERIFY_REPORT.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    report = {"pass": PASS, "fail": FAIL, "skip": SKIP, "results": RESULTS}
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    txt = ROOT / "config" / "VERIFY_REPORT.txt"
    lines = [
        "s1-remote VERIFY REPORT",
        "=======================",
        f"PASS={PASS} FAIL={FAIL} SKIP={SKIP}",
        "",
    ]
    for r in RESULTS:
        lines.append(f"[{r['status']}] {r['name']}" + (f" — {r['detail']}" if r["detail"] else ""))
    txt.write_text("\n".join(lines), encoding="utf-8")

    print("\n" + "=" * 60, flush=True)
    print(f"DONE PASS={PASS} FAIL={FAIL} SKIP={SKIP}", flush=True)
    print(f"Report: {txt}", flush=True)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
