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

    # ---- arm + verify ----

    def arm_and_verify(
        self,
        track: int,
        eyes_dir: Optional[Path] = None,
        retries: int = 3,
        *,
        allow_mouse: bool = False,
        song_dir: Optional[Path] = None,
    ) -> bool:
        """
        Arm Arrange track N; confirm Rec red via screenshot.

        **Control priority (default): keyboard → MIDI (MCU) → fail + diagnose.**
        Mouse is **off unless** ``allow_mouse=True``.

        On failure: writes structured diagnosis (causes + remediations) so the
        next fix addresses *why*, not more thrash. See ``last_arm_result``.

        ``track`` is 1-based arrange index (from tracks.json / Template order).
        """
        import sys as _sys

        _sys.path.insert(0, str(ROOT / "tools"))
        self.last_arm_result: Dict[str, Any] = {"ok": False, "track": track}

        try:
            from s1_tools.eyes import (  # type: ignore[import]
                Eyes,
                scan_rec_red,
                is_studio_one_arrange_shot,
                locate_track_rec_buttons,
                list_armed_visible_rows,
                annotate_rec_hud,
            )
            from s1_tools.logutil import log  # type: ignore[import]
            from s1_tools.arm_diagnose import (  # type: ignore[import]
                diagnose_arm_failure,
                write_diagnosis,
                suggest_next_action,
            )
        except ImportError:
            self._arm_once_keyboard(track)
            self.last_arm_result = {
                "ok": False,
                "error": "s1_tools_import_failed",
                "track": track,
            }
            return False

        from .hotkeys import focus_studio_one, studio_one_running

        # Hard cap — keyboard + MCU only (no thrash)
        retries = min(max(1, int(retries)), 3)
        eyes_path = Path(eyes_dir) if eyes_dir else (Path.cwd() / "_vision" / "arm_watch")
        eyes = Eyes(eyes_path, enabled=True, live=True)
        strip = max(0, track - 1)
        shots: Dict[str, Any] = {}
        attempts: List[Dict[str, Any]] = []
        mcu_used = False
        keyboard_used = False

        def _snapshot(tag: str, method: str) -> Path | None:
            shot = eyes.shot(tag, hud=f"{method} t{track}")
            if shot is None:
                return None
            target_red = scan_rec_red(shot, track=track, allow_fallback=False)
            any_red = scan_rec_red(shot, track=None)
            armed_rows = (
                list_armed_visible_rows(shot)
                if is_studio_one_arrange_shot(shot)
                else []
            )
            attempts.append(
                {
                    "method": method,
                    "shot": str(shot),
                    "target_red": target_red,
                    "any_red": any_red,
                    "armed_rows": armed_rows,
                    "is_arrange": is_studio_one_arrange_shot(shot),
                }
            )
            return shot

        def _fail(early_cause: Optional[str] = None) -> bool:
            st = {}
            try:
                st = self.status()
            except Exception:
                st = {"studio_one_running": studio_one_running()}
            shots["final"] = shots.get("final") or eyes.shot(f"arm_fail_final_t{track}")
            diag = diagnose_arm_failure(
                track=track,
                shots=shots,
                attempts=attempts,
                status=st,
                allow_mouse=allow_mouse,
                mcu_used=mcu_used,
                keyboard_used=keyboard_used,
            )
            if early_cause:
                diag["causes"] = [early_cause] + [
                    c for c in diag.get("causes", []) if c != early_cause
                ]
                diag["primary_cause"] = early_cause
            diag["next_action"] = suggest_next_action(diag)
            # Persist
            write_to = Path(song_dir) if song_dir else eyes_path
            try:
                path = write_diagnosis(write_to, diag)
                diag["path"] = str(path)
            except Exception as e:
                log(f"  arm diagnosis write fail: {e}")
            self.last_arm_result = diag
            log(
                f"  arm_and_verify FAIL t{track} primary={diag.get('primary_cause')} "
                f"next={diag.get('next_action')}"
            )
            return False

        if not studio_one_running():
            log("  arm_and_verify: Studio One not running")
            return _fail("s1_not_running")

        focus_studio_one()
        time.sleep(0.2)
        pre = _snapshot(f"arm_pre_t{track}", "pre")
        shots["pre"] = pre
        if pre is None or not is_studio_one_arrange_shot(pre):
            log("  arm_and_verify: not S1 arrange — refocus once")
            focus_studio_one()
            time.sleep(0.35)
            pre = _snapshot(f"arm_pre2_t{track}", "pre_retry")
            shots["pre"] = pre
            if pre is None or not is_studio_one_arrange_shot(pre):
                return _fail("not_s1_arrange_ui")

        if scan_rec_red(pre, track=track, allow_fallback=False):
            log(f"  arm_and_verify: already armed track={track}")
            self.last_arm_result = {"ok": True, "track": track, "already": True}
            return True

        # --- Attempt plan: keys first, then MCU; mouse only if allow_mouse ---
        # Each attempt = ONE action (no double-toggle).
        plan: List[str] = ["keyboard"]
        if retries >= 2:
            plan.append("mcu")
        if allow_mouse and retries >= 3:
            plan.append("mouse_rec_once")
        plan = plan[:retries]

        for attempt, method in enumerate(plan, start=1):
            focus_studio_one()
            time.sleep(0.15)
            if method == "keyboard":
                keyboard_used = True
                log(f"  arm try {attempt}: keyboard select + single [R]")
                self._arm_once_keyboard(track)
            elif method == "mcu":
                mcu_used = True
                log(
                    f"  arm try {attempt}: MCU select+rec_arm strip={strip} "
                    "(may not match arrange — diagnostic only if fail)"
                )
                self._arm_once_mcu(strip)
            elif method == "mouse_rec_once":
                log(f"  arm try {attempt}: ONE vision Rec click (allow_mouse)")
                self._arm_once_vision_click(track, eyes)
            else:
                continue
            time.sleep(0.55)
            shot = _snapshot(f"arm_attempt{attempt}_{method}_t{track}", method)
            shots["final"] = shot
            if shot is None or not is_studio_one_arrange_shot(shot):
                log(f"  arm attempt {attempt}: lost S1 UI — stop (no thrash)")
                break
            if scan_rec_red(shot, track=track, allow_fallback=False):
                log(f"  arm_and_verify OK track={track} via {method}")
                try:
                    annotate_rec_hud(
                        shot,
                        locate_track_rec_buttons(shot),
                        armed_row=track,
                        label=f"ARMED t{track} {method}",
                    )
                except Exception:
                    pass
                self.last_arm_result = {
                    "ok": True,
                    "track": track,
                    "method": method,
                    "attempts": attempts,
                }
                return True
            armed_else = list_armed_visible_rows(shot)
            if armed_else:
                log(
                    f"  arm attempt {attempt}: Rec red on {armed_else}, "
                    f"not target {track} — will diagnose (no more thrash on wrong track)"
                )
                # Stop: further [R] on wrong selection makes diagnosis worse
                if method == "keyboard":
                    break
            time.sleep(0.1)

        return _fail()

    def _select_arrange_track(self, track: int) -> None:
        """Best-effort keyboard focus on Arrange track N (1-based)."""
        from .hotkeys import focus_studio_one, send_hotkey
        from pywinauto.keyboard import send_keys

        focus_studio_one()
        time.sleep(0.15)
        # Escape overlays, then walk from top of track list
        try:
            send_keys("{ESC}{ESC}")
        except Exception:
            pass
        time.sleep(0.1)
        # Many S1 builds: Ctrl+Home focuses start; then Up thrash to top
        try:
            send_hotkey(["ctrl"], "HOME")
        except Exception:
            try:
                send_keys("^{HOME}")
            except Exception:
                pass
        time.sleep(0.1)
        for _ in range(24):
            try:
                send_keys("{UP}")
            except Exception:
                break
        time.sleep(0.08)
        for _ in range(max(0, track - 1)):
            try:
                send_keys("{DOWN}")
            except Exception:
                break
            time.sleep(0.04)
        time.sleep(0.12)

    def _arm_once_keyboard(self, track: int) -> None:
        """Select Arrange track then toggle Rec Enable with [R] once."""
        try:
            from .hotkeys import run_action

            self._select_arrange_track(track)
            time.sleep(0.1)
            run_action("arm", focus=False)
        except Exception:
            pass

    def _arm_once_mcu(self, strip: int) -> None:
        """Single MCU select + rec_arm (0-based strip)."""
        try:
            self.select(strip)
            time.sleep(0.25)
            self.remote.mcu.rec_arm(strip)
        except Exception:
            pass

    def _arm_once_hotkey(self) -> None:
        """Single hotkey [R] on currently focused track (legacy)."""
        try:
            from .hotkeys import focus_studio_one, run_action

            focus_studio_one()
            time.sleep(0.15)
            run_action("arm", focus=False)
        except Exception:
            pass

    def _main_window_rect(self):
        """Screen rect of Studio One song window, or None."""
        try:
            from pywinauto import Desktop

            for w in Desktop(backend="uia").windows():
                try:
                    t = (w.window_text() or "").strip()
                except Exception:
                    continue
                if t.startswith("Studio One") and "Safety" not in t and w.is_visible():
                    return w.rectangle()
        except Exception:
            pass
        return None

    def _click_screen(self, x: int, y: int, *, alt: bool = False) -> None:
        """Human-like click (smooth move + single press). Never grid-spam."""
        import sys as _sys

        _sys.path.insert(0, str(ROOT / "tools"))
        try:
            from s1_tools.human_input import click_human  # type: ignore[import]

            click_human(int(x), int(y), alt=alt)
            return
        except Exception:
            pass
        import ctypes

        user32 = ctypes.windll.user32
        user32.SetCursorPos(int(x), int(y))
        time.sleep(0.05)
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        time.sleep(0.04)
        user32.mouse_event(0x0004, 0, 0, 0, 0)

    def _arm_once_vision_click(self, track: int, eyes) -> bool:
        """Single click on vision-located Rec for track N (never Monitor)."""
        import sys as _sys

        _sys.path.insert(0, str(ROOT / "tools"))
        try:
            from s1_tools.eyes import (  # type: ignore[import]
                locate_track_rec_buttons,
                rec_click_point_for_track,
                is_studio_one_arrange_shot,
                REC_X_BAND,
            )
            from s1_tools.logutil import log  # type: ignore[import]
            from .hotkeys import focus_studio_one
        except ImportError:
            return False

        focus_studio_one()
        time.sleep(0.1)
        shot = eyes.shot(f"arm_locate_t{track}")
        if shot is None or not is_studio_one_arrange_shot(shot):
            log("  vision arm: not S1 arrange shot")
            return False
        pts = locate_track_rec_buttons(shot)
        log(f"  vision Rec pts={len(pts)} for track={track}")
        if pts and 1 <= track <= len(pts):
            x, y = pts[track - 1]
            if x >= 660:
                x = (REC_X_BAND[0] + REC_X_BAND[1]) // 2
            log(f"  vision Rec click @ ({x},{y})")
            self._click_screen(x, y)
            time.sleep(0.35)
            return True
        rect = self._main_window_rect()
        wr = None
        if rect is not None:
            wr = (int(rect.left), int(rect.top), int(rect.width()), int(rect.height()))
        pt = rec_click_point_for_track(shot, track, window_rect=wr)
        if pt is None:
            return False
        x, y = int(pt[0]), int(pt[1])
        if x >= 660:
            x = (REC_X_BAND[0] + REC_X_BAND[1]) // 2
        self._click_screen(x, y)
        time.sleep(0.35)
        return True

    def _arm_once_click(self, track: int, *, search: bool = False) -> bool:
        """
        Click Arrange Rec Enable using Rec X band (not Monitor).
        Calibrated S1 6.6 @ 1920: Rec ~x 605–655.
        """
        rect = self._main_window_rect()
        if rect is None:
            return False
        try:
            from .hotkeys import focus_studio_one

            focus_studio_one()
        except Exception:
            pass
        time.sleep(0.1)

        left, top = int(rect.left), int(rect.top)
        w, h = int(rect.width()), int(rect.height())
        rec_x = left + 635 if w >= 1800 else left + int(w * 0.33)
        yf = 0.20 + max(0, track - 1) * 0.042
        ys = [top + int(h * yf)]
        if search:
            for dy in (-18, 18, -36, 36, -54, 54):
                ys.append(top + int(h * yf) + dy)

        import sys as _sys

        _sys.path.insert(0, str(ROOT / "tools"))
        try:
            from s1_tools.eyes import Eyes, scan_rec_red  # type: ignore[import]
        except ImportError:
            self._click_screen(rec_x, ys[0])
            return True

        eyes = Eyes(Path.cwd() / "_vision" / "arm_watch", enabled=True)
        for y in ys:
            self._click_screen(rec_x, y)
            time.sleep(0.4)
            shot = eyes.shot(f"arm_frac_t{track}")
            if scan_rec_red(shot, track=track, allow_fallback=False):
                return True
        return False

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
