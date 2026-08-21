"""Ensure loopMIDI ports 'S1 Controller' and 'S1 Notes' exist on this PC.

Ports only exist while loopMIDI.exe is running. Config is stored at:
  HKCU\\Software\\Tobias Erichsen\\loopMIDI\\Ports
  value name = port name, REG_DWORD = 1
"""
from __future__ import annotations

import subprocess
import sys
import time
import winreg
from pathlib import Path

LOOP_MIDI = Path(r"C:\Program Files (x86)\Tobias Erichsen\loopMIDI\loopMIDI.exe")
PORT_NAMES = ["S1 Controller", "S1 Notes"]
PORTS_KEY = r"Software\Tobias Erichsen\loopMIDI\Ports"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def list_midi_ports() -> dict:
    import mido

    return {"inputs": mido.get_input_names(), "outputs": mido.get_output_names()}


def has_named_port(base: str) -> bool:
    p = list_midi_ports()
    blob = p["inputs"] + p["outputs"]
    return any(base in n for n in blob)


def write_ports_registry() -> None:
    # Replace key so only desired ports remain
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, PORTS_KEY)
    except FileNotFoundError:
        pass
    except OSError:
        # Delete values then continue
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, PORTS_KEY, 0, winreg.KEY_ALL_ACCESS)
            while True:
                try:
                    name, _, _ = winreg.EnumValue(key, 0)
                    winreg.DeleteValue(key, name)
                except OSError:
                    break
            winreg.CloseKey(key)
        except OSError:
            pass

    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, PORTS_KEY)
    for name in PORT_NAMES:
        winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, 1)
    winreg.CloseKey(key)
    print(f"Wrote {PORTS_KEY}: {PORT_NAMES}")


def enable_autostart() -> None:
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE)
    winreg.SetValueEx(key, "loopMIDI", 0, winreg.REG_SZ, f'"{LOOP_MIDI}"')
    winreg.CloseKey(key)
    print("Enabled loopMIDI autostart (HKCU Run)")


def restart_loopmidi() -> None:
    if not LOOP_MIDI.is_file():
        raise SystemExit(f"loopMIDI not found at {LOOP_MIDI}. Install TobiasErichsen.loopMIDI via winget.")
    subprocess.run(["taskkill", "/IM", "loopMIDI.exe", "/F"], capture_output=True)
    time.sleep(1.5)
    # Start outside the parent Job Object so the process survives agent shells.
    ps = (
        f"$r = ([wmiclass]'Win32_Process').Create('{LOOP_MIDI}'); "
        f"if ($r.ReturnValue -ne 0) {{ exit $r.ReturnValue }}"
    )
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        # Last resort (may die with parent shell job)
        subprocess.Popen([str(LOOP_MIDI)])
    time.sleep(2.5)


def main() -> int:
    print("MIDI before:", list_midi_ports())
    write_ports_registry()
    restart_loopmidi()
    print("MIDI after:", list_midi_ports())

    ok = all(has_named_port(n) for n in PORT_NAMES)
    if not ok:
        print("FAILED: ports not visible. Is teVirtualMIDI driver installed?")
        return 1

    enable_autostart()
    print("SUCCESS: S1 Controller + S1 Notes ready")
    print("  MCU out (agent -> S1):  S1 Controller 1")
    print("  MCU in  (S1 feedback):  S1 Controller 0")
    print("  Notes out (agent):      S1 Notes 2")
    print("  Notes in  (S1 Keyboard): S1 Notes 1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
