#!/usr/bin/env python3
"""Create the software S1 Controller on this PC.

What this installs
------------------
1. loopMIDI ports:
     S1 Controller  — Mackie Control Universal (mixer / transport / V-Pots)
     S1 Notes       — Keyboard (instrument notes; never share the MCU cable)
2. Studio One External Devices (MusicDevices.settings, S1 must be closed):
     Mackie Control  Receive/Send = S1 Controller
     S1 Notes        Keyboard Receive = S1 Notes
3. User Devices\\S1 Notes.device (+ surface with CC 20–35 for Control Link)
4. s1-remote config/settings.json port names

Idempotent. Does not start Studio One.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(ROOT))

from _setup_loopmidi_ports import (  # noqa: E402
    enable_autostart,
    has_named_port,
    list_midi_ports,
    restart_loopmidi,
    write_ports_registry,
)

MACKIE_MODEL_ID = "{EE428900-E2B0-477a-B27C-2730D0F373B7}"
# Stable IDs so re-runs do not spawn extra devices
NOTES_MODEL_ID = "{A7C3E1B2-9D4F-4A18-8E6C-2B1F0D5A7C91}"
NOTES_INSTANCE_ID = "{B8D4F2C3-0E5A-4B29-9F7D-3C2E1E6B8D02}"
MACKIE_INSTANCE_ID = "{C9E5A3D4-1F6B-4C3A-A08E-4D3F2F7C9E13}"

PORT_MCU = "S1 Controller"
PORT_NOTES = "S1 Notes"
MACKIE_NAME = "Mackie Control"
NOTES_NAME = "S1 Notes"

S1_APPDATA = Path(os.environ.get("APPDATA", "")) / "PreSonus" / "Studio One 6"
MUSIC_DEVICES = S1_APPDATA / "MusicDevices.settings"
USER_DEVICES = S1_APPDATA / "User Devices"
TEMPLATE_DIR = ROOT / "config" / "s1_controller"

MACKIE_XML = (
    f'\t\t\t<MusicDeviceDescription name="{MACKIE_NAME}" '
    f'receivePortID="WinMidi/Receive/{PORT_MCU}" '
    f'sendPortID="WinMidi/Send/{PORT_MCU}">\n'
    f'\t\t\t\t<UID x:id="modelID" uid="{MACKIE_MODEL_ID}"/>\n'
    f'\t\t\t\t<UID x:id="instanceID" uid="{MACKIE_INSTANCE_ID}"/>\n'
    f"\t\t\t</MusicDeviceDescription>\n"
)
NOTES_XML = (
    f'\t\t\t<MusicDeviceDescription name="{NOTES_NAME}" '
    f'receivePortID="WinMidi/Receive/{PORT_NOTES}" '
    f'midiReceiveMask="65535">\n'
    f'\t\t\t\t<UID x:id="modelID" uid="{NOTES_MODEL_ID}"/>\n'
    f'\t\t\t\t<UID x:id="instanceID" uid="{NOTES_INSTANCE_ID}"/>\n'
    f"\t\t\t</MusicDeviceDescription>\n"
)


def studio_one_running() -> bool:
    try:
        from s1remote.hotkeys import studio_one_running as _running

        return bool(_running())
    except Exception:
        pass
    if sys.platform == "win32":
        import subprocess

        r = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Studio One.exe"],
            capture_output=True,
            text=True,
        )
        return "Studio One.exe" in (r.stdout or "")
    return False


def copy_user_devices() -> list[str]:
    USER_DEVICES.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for name in ("S1 Notes.device", "S1 Notes.surface.xml"):
        src = TEMPLATE_DIR / name
        dst = USER_DEVICES / name
        if not src.is_file():
            raise FileNotFoundError(f"missing template {src}")
        shutil.copy2(src, dst)
        copied.append(str(dst))
    return copied


def _already_has(text: str, *needles: str) -> bool:
    low = text.lower()
    return any(n.lower() in low for n in needles)


def patch_music_devices(dry_run: bool = False) -> dict:
    if not MUSIC_DEVICES.is_file():
        raise FileNotFoundError(f"Studio One MusicDevices.settings not found: {MUSIC_DEVICES}")
    raw = MUSIC_DEVICES.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    added: list[str] = []
    skipped: list[str] = []

    def insert(block: str, label: str, *markers: str) -> str:
        nonlocal text
        if _already_has(text, *markers):
            skipped.append(label)
            return text
        needle = "</Attributes>"
        idx = text.rfind(needle)
        if idx < 0:
            raise RuntimeError("MusicDevices.settings missing </Attributes>")
        text = text[:idx] + block + text[idx:]
        added.append(label)
        return text

    insert(
        MACKIE_XML,
        MACKIE_NAME,
        f'name="{MACKIE_NAME}"',
        f"WinMidi/Receive/{PORT_MCU}",
        MACKIE_MODEL_ID,
        MACKIE_INSTANCE_ID,
    )
    insert(
        NOTES_XML,
        NOTES_NAME,
        f'name="{NOTES_NAME}"',
        f"WinMidi/Receive/{PORT_NOTES}",
        NOTES_MODEL_ID,
        NOTES_INSTANCE_ID,
    )

    if not dry_run and added:
        out = text.encode("utf-8")
        if bom:
            out = b"\xef\xbb\xbf" + out
        bak = MUSIC_DEVICES.with_suffix(".settings.bak-s1controller")
        if not bak.is_file():
            shutil.copy2(MUSIC_DEVICES, bak)
        MUSIC_DEVICES.write_bytes(out)

    return {"path": str(MUSIC_DEVICES), "added": added, "skipped": skipped, "dry_run": dry_run}


def _pick_port(names: list[str], base: str) -> str:
    from s1remote.midi.port import _match_port

    return _match_port(names, base) or base


def write_s1remote_settings(ports: dict | None = None) -> Path:
    from s1remote import config

    settings = config.load_settings()
    ins = list((ports or {}).get("inputs") or [])
    outs = list((ports or {}).get("outputs") or [])
    settings["midi_out_port"] = _pick_port(outs, PORT_MCU)
    settings["midi_in_port"] = _pick_port(ins, PORT_MCU)
    settings["instrument_midi_out_port"] = _pick_port(outs, PORT_NOTES)
    settings["mcu_channels"] = 8
    config.save_settings(settings)
    return config.SETTINGS_PATH


def setup_loopmidi() -> dict:
    before = list_midi_ports()
    write_ports_registry()
    restart_loopmidi()
    after = list_midi_ports()
    enable_autostart()
    ok = all(has_named_port(n) for n in (PORT_MCU, PORT_NOTES))
    return {
        "ok": ok,
        "before": before,
        "after": after,
        "mcu_out": "S1 Controller 1",
        "mcu_in": "S1 Controller 0",
        "notes_out": "S1 Notes 2",
        "notes_in": "S1 Notes 1",
    }


def run(dry_run: bool = False, skip_midi: bool = False) -> dict:
    report: dict = {
        "host": os.environ.get("COMPUTERNAME"),
        "ok": True,
        "failures": [],
        "steps": {},
    }

    if studio_one_running():
        msg = (
            "Studio One is running. Close it, then re-run so MusicDevices.settings "
            "is not overwritten on exit."
        )
        report["ok"] = False
        report["failures"].append(msg)
        report["steps"]["studio_one_running"] = True
        return report
    report["steps"]["studio_one_running"] = False

    if dry_run:
        report["steps"]["user_devices"] = {
            "would_copy": [str(USER_DEVICES / n) for n in ("S1 Notes.device", "S1 Notes.surface.xml")]
        }
        report["steps"]["music_devices"] = patch_music_devices(dry_run=True)
        return report

    try:
        copied = copy_user_devices()
        report["steps"]["user_devices"] = copied
    except Exception as e:
        report["ok"] = False
        report["failures"].append(f"user devices: {e}")

    try:
        report["steps"]["music_devices"] = patch_music_devices(dry_run=False)
    except Exception as e:
        report["ok"] = False
        report["failures"].append(f"MusicDevices: {e}")

    if not skip_midi:
        try:
            midi = setup_loopmidi()
            report["steps"]["loopmidi"] = midi
            if not midi.get("ok"):
                report["ok"] = False
                report["failures"].append("loopMIDI ports not visible after restart")
        except Exception as e:
            report["ok"] = False
            report["failures"].append(f"loopMIDI: {e}")
            report["steps"]["loopmidi"] = {"error": str(e)}

    try:
        midi_after = (report.get("steps") or {}).get("loopmidi") or {}
        report["steps"]["s1remote_settings"] = str(
            write_s1remote_settings(midi_after.get("after") if isinstance(midi_after, dict) else None)
        )
        from s1remote import config as _cfg

        report["steps"]["s1remote_ports"] = {
            k: _cfg.load_settings().get(k)
            for k in ("midi_out_port", "midi_in_port", "instrument_midi_out_port")
        }
    except Exception as e:
        report["ok"] = False
        report["failures"].append(f"settings.json: {e}")

    report["how_to_use"] = {
        "mcu": "py -3.12 -m s1remote transport play  /  fader 0 --db -6",
        "notes": "py -3.12 -m s1remote note 60 --duration 0.4",
        "status": "py -3.12 -m s1remote status",
        "s1": "Restart Studio One so External Devices loads Mackie Control + S1 Notes",
    }
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Install software S1 Controller (loopMIDI + External Devices)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-midi", action="store_true", help="Only write S1 device files, do not restart loopMIDI")
    args = ap.parse_args()
    report = run(dry_run=args.dry_run, skip_midi=args.skip_midi)
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
