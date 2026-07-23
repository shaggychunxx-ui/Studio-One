"""
S1 Full Control — one object that routes every capability through the best layer.

What this unlocks (practical maximum):
  • Mixer / transport / banks / plugin-mode VST params → MCU MIDI
  • Named VST params → Control Link CC maps (+ remoteservice catalog names)
  • MIDI notes / CC input → keyboard MIDI port
  • Views / file / edit → hotkeys
  • Menu bar paths → deliberate Alt-menu navigation
  • Channel volume/mute by index → in-host package queue
  • Browser load → F5 + type + enter (fixed path, not thrash)

Not magic: Studio One has no public “control all memory” API.
This stacks every supported surface into one program.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from . import host_bridge
from .commands_catalog import COMMANDS, coverage_summary, list_commands
from .controller import S1Remote
from .hotkeys import ACTIONS, focus_studio_one, run_action, send_hotkey, studio_one_running
from .menus import open_menu_path
from .vst_midi import VstMidiControl

ROOT = Path(__file__).resolve().parents[1]
REMOTE_CATALOG = ROOT / "re" / "plugin_param_catalog.json"


class FullControl:
    """
    Full Studio One remote surface.

    Usage:
        with FullControl() as s1:
            s1.play()
            s1.mute(0)
            s1.fader(0, -6)
            s1.vst_param("mai_tai", "Cutoff", 0.7)   # after Control Link map
            s1.plugin_mode()                          # V-Pots drive focused VST
            s1.vpot(0, +4)
            s1.note(60)
            s1.do("view.browser")
            s1.browser_load("Mojito")
            s1.host("set_channel_volume", index=0, db=-6)
    """

    def __init__(self, out_port: Optional[str] = None) -> None:
        self.remote = S1Remote(out_port=out_port, auto_connect=False)
        self.vst = VstMidiControl(out_port=out_port)
        self._connected = False
        self._remote_params: Optional[dict] = None

    # ---- lifecycle ----

    def connect(self) -> "FullControl":
        self.remote.connect(open_input=False)
        self.vst.connect()
        self._connected = True
        return self

    def disconnect(self) -> None:
        try:
            self.vst.disconnect()
        except Exception:
            pass
        try:
            self.remote.disconnect()
        except Exception:
            pass
        self._connected = False

    def __enter__(self) -> "FullControl":
        return self.connect()

    def __exit__(self, *_) -> None:
        self.disconnect()

    def status(self) -> Dict[str, Any]:
        st = self.remote.status()
        st["full_control_commands"] = coverage_summary()
        st["vst_maps"] = self.vst.list_plugins()
        st["host_queue"] = str(host_bridge.QUEUE_FILE)
        st["remote_param_devices"] = len(self.remote_catalog())
        return st

    def remote_catalog(self) -> dict:
        if self._remote_params is None:
            if REMOTE_CATALOG.exists():
                self._remote_params = json.loads(
                    REMOTE_CATALOG.read_text(encoding="utf-8")
                )
            else:
                self._remote_params = {}
        return self._remote_params

    # ---- transport ----

    def play(self) -> None:
        self.remote.play()

    def stop(self) -> None:
        self.remote.stop()

    def record(self) -> None:
        self.remote.record()

    # ---- mixer MCU ----

    def mute(self, ch: int) -> None:
        self.remote.mute(ch)

    def solo(self, ch: int) -> None:
        self.remote.solo(ch)

    def fader(self, ch: int, db: float) -> None:
        self.remote.fader(ch, db)

    def select(self, ch: int) -> None:
        self.remote.mcu.select(ch)

    def bank_left(self) -> None:
        self.remote.mcu.bank_left()

    def bank_right(self) -> None:
        self.remote.mcu.bank_right()

    def plugin_mode(self) -> None:
        """V-Pots control the focused plugin's parameters (official MCU path)."""
        self.remote.mcu.mode_plugin()

    def pan_mode(self) -> None:
        self.remote.mcu.mode_pan()

    def vpot(self, ch: int, delta: int = 1) -> None:
        self.remote.mcu.vpot(ch, delta)

    # ---- VST / Control Link ----

    def cc(self, control: int, value: int, channel: int = 0) -> None:
        self.vst.cc(control, value, channel)

    def vst_param(
        self, plugin: str, param: str, value: Union[float, int]
    ) -> Dict[str, Any]:
        return self.vst.set(plugin, param, value)

    def learn_wiggle(self, control: int = 20) -> None:
        self.vst.learn_wiggle(control)

    def program_all_maps(self) -> Dict[str, int]:
        """Pulse every CC in every map (Control Link ready). No mouse."""
        n_plug = 0
        n_param = 0
        for pid in self.vst.list_plugins():
            params = self.vst.list_params(pid)
            n_plug += 1
            for _name, entry in params.items():
                n_param += 1
                cc = int(entry["cc"])
                ch = int(entry.get("channel", 0))
                for v in (0, 96, 48, 64):
                    self.vst.cc(cc, v, ch)
                    time.sleep(0.004)
        return {"plugins": n_plug, "params": n_param}

    def list_vst_params(self, plugin: str) -> Dict[str, Any]:
        return self.vst.show(plugin)

    def list_remote_device_params(self, device_name: str) -> Dict[str, Any]:
        cat = self.remote_catalog()
        # case-insensitive match
        for k, v in cat.items():
            if k.lower() == device_name.lower() or device_name.lower() in k.lower():
                return {"device": k, "deviceID": v.get("deviceID"), "params": v.get("params") or {}}
        raise KeyError(f"Device not in remoteservice catalog: {device_name}")

    # ---- MIDI instrument input ----

    def note(
        self, note: int, duration: float = 0.25, velocity: int = 100, channel: int = 0
    ) -> None:
        self.remote.note(note, duration, velocity, channel)

    # ---- views / hotkeys ----

    def hotkey(self, action: str) -> None:
        run_action(action, focus=True)

    def console(self) -> None:
        self.hotkey("mixer")

    def browser(self) -> None:
        self.hotkey("browser")

    def save(self) -> None:
        self.hotkey("save")

    def new_song(self) -> None:
        self.hotkey("new_song")

    # ---- menus ----

    def menu(self, *path: str) -> None:
        open_menu_path(list(path), focus=True)

    # ---- browser load (deliberate, fixed coords relative via keys only) ----

    def browser_load(self, search: str) -> None:
        """
        Open Browser, type search, Enter twice to load.
        Keyboard-first (no multi-click thrash, no pynput dependency).
        """
        import ctypes

        user32 = ctypes.windll.user32
        focus_studio_one()
        run_action("browser", focus=False)
        time.sleep(0.45)
        try:
            send_hotkey(["ctrl"], "F")
            time.sleep(0.15)
        except Exception:
            pass
        send_hotkey(["ctrl"], "A")
        time.sleep(0.05)
        # Type ASCII via VkKeyScan (no pynput)
        for ch in search[:32]:
            vk = user32.VkKeyScanW(ord(ch))
            if vk == -1:
                continue
            code = vk & 0xFF
            shift = bool(vk & 0x100)
            if shift:
                user32.keybd_event(0x10, 0, 0, 0)
            user32.keybd_event(code, 0, 0, 0)
            user32.keybd_event(code, 0, 2, 0)
            if shift:
                user32.keybd_event(0x10, 0, 2, 0)
            time.sleep(0.02)
        time.sleep(0.35)
        send_hotkey([], "RETURN")
        time.sleep(0.3)
        send_hotkey([], "RETURN")
        time.sleep(0.4)

    # ---- host package queue ----

    def host(self, task: str, **params: Any) -> str:
        """
        Enqueue in-host task. Run in Studio One:
          Scripts → S1 Full Control: Process Queue
        """
        return host_bridge.enqueue(task, **params)

    def host_set_volume(self, index: int, db: float) -> str:
        return self.host("set_channel_volume", index=index, db=db)

    def host_set_mute(self, index: int, state: bool = True) -> str:
        return self.host("set_channel_mute", index=index, state=state)

    def host_interpret(self, category: str, name: str) -> str:
        return self.host("interpret_command", category=category, name=name)

    # ---- generic router ----

    def do(self, command_id: str, **override: Any) -> Any:
        """Route catalog command_id through the correct layer."""
        if command_id not in COMMANDS:
            raise KeyError(
                f"Unknown command {command_id!r}. "
                f"Use list_commands() — {len(COMMANDS)} available."
            )
        meta = {**COMMANDS[command_id], **override}
        layer = meta["layer"]

        if layer == "mcu":
            if "button" in meta:
                self.remote.mcu.click(meta["button"])
                return {"ok": True, "layer": "mcu", "button": meta["button"]}
            method = meta.get("method")
            ch = int(meta.get("channel", 0))
            if method == "mute":
                self.mute(ch)
            elif method == "solo":
                self.solo(ch)
            elif method == "select":
                self.select(ch)
            elif method == "rec_arm":
                self.remote.mcu.rec_arm(ch)
            elif method == "fader":
                self.fader(ch, float(meta.get("db", -6)))
            elif method == "mode_plugin":
                self.plugin_mode()
            elif method == "mode_pan":
                self.pan_mode()
            elif method == "mode_send":
                self.remote.mcu.mode_send()
            elif method == "mode_eq":
                self.remote.mcu.mode_eq()
            elif method == "mode_instrument":
                self.remote.mcu.mode_instrument()
            elif method == "vpot":
                self.vpot(ch, int(meta.get("delta", 1)))
            else:
                raise ValueError(f"mcu method {method}")
            return {"ok": True, "layer": "mcu", "method": method}

        if layer == "hotkey":
            action = meta.get("action")
            if not action or action not in ACTIONS:
                raise KeyError(f"Unknown hotkey action {action!r}; known: {sorted(ACTIONS)}")
            run_action(action, focus=True)
            return {"ok": True, "layer": "hotkey", "action": action}

        if layer == "link":
            if meta.get("plugin"):
                return {
                    "ok": True,
                    "layer": "link",
                    **self.vst_param(meta["plugin"], meta["param"], meta.get("value", 64)),
                }
            self.cc(int(meta.get("control", 0)), int(meta.get("value", 0)), int(meta.get("channel", 0)))
            return {"ok": True, "layer": "link"}

        if layer == "note":
            self.note(
                int(meta.get("note", 60)),
                float(meta.get("duration", 0.25)),
                int(meta.get("velocity", 100)),
                int(meta.get("channel", 0)),
            )
            return {"ok": True, "layer": "note"}

        if layer == "menu":
            path = meta.get("path") or []
            open_menu_path(path, focus=True)
            return {"ok": True, "layer": "menu", "path": path}

        if layer == "browser":
            self.browser_load(str(meta.get("search") or override.get("search") or ""))
            return {"ok": True, "layer": "browser"}

        if layer == "host":
            rid = self.host(meta.get("task", ""), **{k: v for k, v in meta.items() if k not in ("layer", "description", "task")})
            return {
                "ok": True,
                "layer": "host",
                "request_id": rid,
                "hint": host_bridge.package_install_hint(),
            }

        raise ValueError(f"Unknown layer {layer}")

    def list_commands(self, q: str = "") -> List[Dict[str, Any]]:
        return list_commands(q)

    def capabilities(self) -> Dict[str, Any]:
        """Honest capability matrix for the user."""
        cat = self.remote_catalog()
        remote_params = sum(len(v.get("params") or {}) for v in cat.values())
        return {
            "studio_one_running": studio_one_running(),
            "midi_connected": self._connected and self.remote.connected,
            "layers": {
                "mcu_mixer_transport_plugin_mode": True,
                "control_link_cc_maps": True,
                "instrument_midi_notes": True,
                "hotkeys_views_file_edit": True,
                "menu_bar_keyboard": True,
                "browser_search_load": True,
                "host_package_queue": True,
                "remoteservice_param_names": remote_params,
                "ucnet_session_params": False,  # RE incomplete
                "pixel_thrash_disabled": True,
            },
            "command_catalog": coverage_summary(),
            "vst_map_plugins": len(self.vst.list_plugins()),
            "how_vst_without_per_param_learn": (
                "1) Focus plugin editor in S1  2) s1.plugin_mode()  "
                "3) s1.vpot(i, delta) — MCU maps V-Pots to plugin params in order"
            ),
            "how_host_deep_mixer": host_bridge.package_install_hint(),
            "setup_once": [
                "loopMIDI port S1 Controller 1",
                "S1 Options → External Devices → Mackie Control (Receive=S1 Controller 1)",
                "S1 Options → External Devices → New Keyboard (Receive=S1 Controller 1) for notes/CC",
                "Install host_package → Scripts menu: S1 Full Control: Process Queue",
                "Control Link ON + Focus for permanent CC↔param binds (optional if using plugin mode)",
            ],
        }


def build_host_package(out_path: Optional[Path] = None) -> Path:
    """Zip host_package into a .package (zip) for Studio One Scripts install."""
    import zipfile

    src = ROOT / "host_package"
    out_path = out_path or (ROOT / "scripts" / "S1FullControl.package")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in src.iterdir():
            if f.is_file():
                zf.write(f, f.name)
    return out_path
