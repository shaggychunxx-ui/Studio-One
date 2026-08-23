"""
S1UI — agent-facing Studio One UI driver.

Manipulate the live DAW window: inspect, dump UIA, Find Command (Ctrl+K),
named-region clicks/drags, type, menus, dialogs, screenshots.

Does not launch Studio One. Does not hunt unlabeled knobs.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..hotkeys import ACTIONS, focus_studio_one, run_action, send_hotkey
from ..menus import open_menu_path
from . import catalog as ui_catalog
from . import layout as ui_layout
from . import tree as ui_tree
from .window import WindowInfo, attach, ensure_dpi_aware, restore_and_focus

SHOT_DIR = Path.home() / "Documents" / "Studio One" / "S1FullControl" / "ui_shots"


class S1UI:
    """One object that can drive every reachable Studio One UI surface."""

    def __init__(self) -> None:
        self.last: Dict[str, Any] = {}

    # ---- attach / inspect ----

    def inspect(self, *, focus: bool = False) -> Dict[str, Any]:
        info = attach(focus=focus)
        dialogs = []
        try:
            dialogs = [
                w
                for w in ui_tree.list_top_windows()
                if "safety" in (w.get("title") or "").lower()
                or w.get("control_type", "").lower() == "dialog"
                or any(
                    k in (w.get("title") or "").lower()
                    for k in ("save as", "open", "new", "import", "options", "export", "mixdown")
                )
            ]
        except Exception as e:
            dialogs = [{"error": str(e)}]
        out = {
            **info.to_dict(),
            "dialogs": dialogs,
            "regions": ui_layout.list_regions(),
            "ui_commands": ui_catalog.coverage(),
            "how": (
                "command() = Ctrl+K Find Command; "
                "do(id) = catalog hotkey/find/menu/region; "
                "invoke() = UIA; click_region() = named chrome; "
                "MCU/MIDI stay on FullControl"
            ),
        }
        self.last = out
        return out

    def window(self, *, focus: bool = False) -> WindowInfo:
        return attach(focus=focus)

    def focus(self) -> WindowInfo:
        return restore_and_focus()

    # ---- UIA ----

    def tree(
        self,
        query: str = "",
        *,
        max_depth: int = 6,
        max_nodes: int = 400,
        named_only: bool = True,
    ) -> List[Dict[str, Any]]:
        self.focus()
        return ui_tree.dump_tree(
            query=query, max_depth=max_depth, max_nodes=max_nodes, named_only=named_only
        )

    def find(
        self,
        name: str = "",
        *,
        control_type: str = "",
        automation_id: str = "",
    ) -> List[Dict[str, Any]]:
        return ui_tree.find_elements(
            name=name, control_type=control_type, automation_id=automation_id
        )

    def invoke(self, name: str, *, control_type: str = "") -> Dict[str, Any]:
        self.focus()
        time.sleep(0.05)
        result = ui_tree.invoke(name, control_type=control_type)
        self.last = result
        return result

    def set_value(self, name: str, value: str, *, control_type: str = "Edit") -> Dict[str, Any]:
        self.focus()
        result = ui_tree.set_value(name, value, control_type=control_type)
        self.last = result
        return result

    # ---- Find Command (Ctrl+K) — any named S1 command ----

    def command(self, name: str, *, confirm: bool = True) -> Dict[str, Any]:
        """
        Open Find Command, type `name`, press Enter.

        This is the supported way to fire any Keyboard-Shortcuts command
        without a dedicated hotkey.
        """
        name = (name or "").strip()
        if not name:
            return {"ok": False, "error": "empty command name"}
        info = self.focus()
        if not info.hwnd:
            return {"ok": False, "error": "Studio One not running"}
        focus_studio_one()
        time.sleep(0.12)
        send_hotkey(["ctrl"], "K")
        time.sleep(0.28)
        _paste(name)
        time.sleep(0.22)
        if confirm:
            send_hotkey([], "RETURN")
            time.sleep(0.18)
        result = {"ok": True, "method": "find_command", "name": name, "title": info.title}
        self.last = result
        return result

    # ---- catalog router ----

    def do(self, command_id: str, **override: Any) -> Dict[str, Any]:
        """Route a catalog id: hotkey → Find Command → menu → region."""
        meta = {**ui_catalog.get(command_id), **override}
        info = self.focus()
        if not info.hwnd:
            return {"ok": False, "error": "Studio One not running", "id": command_id}

        hotkey = meta.get("hotkey") or ""
        if hotkey and hotkey in ACTIONS:
            run_action(hotkey, focus=False)
            result = {"ok": True, "id": command_id, "layer": "hotkey", "hotkey": hotkey}
            self.last = result
            return result

        name = meta.get("name") or ""
        if name:
            result = self.command(name)
            result["id"] = command_id
            result["layer"] = "find"
            return result

        menu = meta.get("menu") or []
        if menu:
            open_menu_path(menu, focus=True)
            result = {"ok": True, "id": command_id, "layer": "menu", "path": menu}
            self.last = result
            return result

        region = meta.get("region") or ""
        if region:
            result = self.click_region(region)
            result["id"] = command_id
            result["layer"] = "region"
            return result

        return {"ok": False, "error": "no invocation path", "id": command_id, "meta": meta}

    def menu(self, path: Sequence[str]) -> Dict[str, Any]:
        self.focus()
        open_menu_path(list(path), focus=True)
        result = {"ok": True, "layer": "menu", "path": list(path)}
        self.last = result
        return result

    # ---- named regions / mouse ----

    def click_region(
        self,
        name: str,
        *,
        button: str = "left",
        double: bool = False,
    ) -> Dict[str, Any]:
        info = self.focus()
        if not info.hwnd:
            return {"ok": False, "error": "Studio One not running"}
        x, y = ui_layout.region_click_point(
            name,
            client_left=info.client_left,
            client_top=info.client_top,
            client_width=info.client_width,
            client_height=info.client_height,
        )
        _click(x, y, button=button, double=double)
        result = {"ok": True, "region": name, "x": x, "y": y, "button": button, "double": double}
        self.last = result
        return result

    def click_frac(self, fx: float, fy: float, *, button: str = "left") -> Dict[str, Any]:
        info = self.focus()
        if not info.hwnd:
            return {"ok": False, "error": "Studio One not running"}
        x, y = ui_layout.client_to_screen(
            float(fx),
            float(fy),
            client_left=info.client_left,
            client_top=info.client_top,
            client_width=info.client_width,
            client_height=info.client_height,
        )
        _click(x, y, button=button)
        result = {"ok": True, "fx": fx, "fy": fy, "x": x, "y": y}
        self.last = result
        return result

    def click_xy(self, x: int, y: int, *, button: str = "left", double: bool = False) -> Dict[str, Any]:
        self.focus()
        _click(int(x), int(y), button=button, double=double)
        result = {"ok": True, "x": int(x), "y": int(y), "button": button}
        self.last = result
        return result

    def click_rec(self, track: int) -> Dict[str, Any]:
        """Click Rec Enable for 1-based Arrange track (named column, not Monitor)."""
        info = self.focus()
        if not info.hwnd:
            return {"ok": False, "error": "Studio One not running"}
        x, y = ui_layout.rec_point_for_track(
            track,
            client_left=info.client_left,
            client_top=info.client_top,
            client_width=info.client_width,
            client_height=info.client_height,
        )
        _click(x, y)
        result = {"ok": True, "track": int(track), "x": x, "y": y, "region": "rec_column"}
        self.last = result
        return result

    def drag(
        self,
        src: str,
        dst: str,
        *,
        hold: float = 0.35,
    ) -> Dict[str, Any]:
        """Drag from one named region center to another (browser → arrange)."""
        info = self.focus()
        if not info.hwnd:
            return {"ok": False, "error": "Studio One not running"}
        kw = dict(
            client_left=info.client_left,
            client_top=info.client_top,
            client_width=info.client_width,
            client_height=info.client_height,
        )
        x0, y0 = ui_layout.region_click_point(src, **kw)
        x1, y1 = ui_layout.region_click_point(dst, **kw)
        _drag(x0, y0, x1, y1, hold=hold)
        result = {"ok": True, "src": src, "dst": dst, "from": [x0, y0], "to": [x1, y1]}
        self.last = result
        return result

    def scroll(self, region: str = "arrange", *, clicks: int = -3) -> Dict[str, Any]:
        info = self.focus()
        if not info.hwnd:
            return {"ok": False, "error": "Studio One not running"}
        x, y = ui_layout.region_click_point(
            region,
            client_left=info.client_left,
            client_top=info.client_top,
            client_width=info.client_width,
            client_height=info.client_height,
        )
        _move(x, y)
        time.sleep(0.05)
        import ctypes

        # WHEEL_DELTA = 120; positive = up
        ctypes.windll.user32.mouse_event(0x0800, 0, 0, int(clicks) * 120, 0)
        result = {"ok": True, "region": region, "clicks": clicks, "x": x, "y": y}
        self.last = result
        return result

    # ---- keys / type ----

    def keys(self, action: str) -> Dict[str, Any]:
        """Named hotkey from s1remote.hotkeys.ACTIONS."""
        info = self.focus()
        if not info.hwnd:
            return {"ok": False, "error": "Studio One not running"}
        run_action(action, focus=False)
        result = {"ok": True, "action": action}
        self.last = result
        return result

    def type_text(self, text: str, *, paste: bool = True) -> Dict[str, Any]:
        info = self.focus()
        if not info.hwnd:
            return {"ok": False, "error": "Studio One not running"}
        if paste:
            _paste(text)
        else:
            _type_ascii(text)
        result = {"ok": True, "text": text, "method": "paste" if paste else "keys"}
        self.last = result
        return result

    def escape(self, times: int = 1) -> Dict[str, Any]:
        self.focus()
        for _ in range(max(1, int(times))):
            send_hotkey([], "ESCAPE")
            time.sleep(0.05)
        return {"ok": True, "escape": times}

    def enter(self) -> Dict[str, Any]:
        self.focus()
        send_hotkey([], "RETURN")
        return {"ok": True}

    # ---- dialogs ----

    def dialogs(self) -> List[Dict[str, Any]]:
        return ui_tree.list_top_windows()

    def dismiss(self, *, ok: bool = False) -> Dict[str, Any]:
        """Escape blocking dialogs. ok=True presses Enter instead (dangerous)."""
        self.focus()
        if ok:
            send_hotkey([], "RETURN")
            method = "enter"
        else:
            send_hotkey([], "ESCAPE")
            time.sleep(0.05)
            send_hotkey([], "ESCAPE")
            method = "escape"
        return {"ok": True, "method": method}

    # ---- screenshot ----

    def shot(self, tag: str = "ui", *, overlay: bool = False) -> Dict[str, Any]:
        ensure_dpi_aware()
        info = attach(focus=False)
        SHOT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in tag)[:40]
        path = SHOT_DIR / f"{stamp}_{safe}.png"
        try:
            from PIL import ImageGrab, ImageDraw
        except ImportError:
            return {"ok": False, "error": "pillow not installed"}
        img = ImageGrab.grab()
        if overlay and info.hwnd:
            dr = ImageDraw.Draw(img)
            for name, box in ui_layout.overlay_boxes():
                x0, y0, x1, y1 = ui_layout.region_screen_rect(
                    name,
                    client_left=info.client_left,
                    client_top=info.client_top,
                    client_width=info.client_width,
                    client_height=info.client_height,
                )
                dr.rectangle([x0, y0, x1, y1], outline=(0, 220, 255), width=1)
                dr.text((x0 + 2, y0 + 1), name, fill=(0, 255, 120))
            dr.text((12, 10), (info.title or "Studio One")[:80], fill=(255, 220, 0))
        img.save(str(path))
        result = {"ok": True, "path": str(path), "overlay": overlay, "title": info.title}
        self.last = result
        return result

    # ---- catalog helpers ----

    def commands(self, q: str = "") -> List[Dict[str, Any]]:
        return ui_catalog.search(q)

    def regions(self, q: str = "") -> List[str]:
        return ui_layout.list_regions(q)


def _paste(text: str) -> None:
    _set_clipboard(text)
    time.sleep(0.04)
    send_hotkey(["ctrl"], "A")
    time.sleep(0.04)
    send_hotkey(["ctrl"], "V")


def _set_clipboard(text: str) -> None:
    """Put Unicode text on the Windows clipboard (Find Command / type_text)."""
    try:
        import ctypes

        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        payload = str(text).encode("utf-16-le") + b"\x00\x00"
        if not user32.OpenClipboard(0):
            raise OSError("OpenClipboard failed")
        try:
            user32.EmptyClipboard()
            handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(payload))
            locked = kernel32.GlobalLock(handle)
            ctypes.memmove(locked, payload, len(payload))
            kernel32.GlobalUnlock(handle)
            user32.SetClipboardData(CF_UNICODETEXT, handle)
        finally:
            user32.CloseClipboard()
        return
    except Exception:
        pass
    import subprocess

    subprocess.run(["clip"], input=text, text=True, check=False)



def _type_ascii(text: str) -> None:
    import ctypes

    user32 = ctypes.windll.user32
    for ch in text[:80]:
        if ch == "\n":
            send_hotkey([], "RETURN")
            continue
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


def _click(x: int, y: int, *, button: str = "left", double: bool = False) -> None:
    try:
        import sys
        from pathlib import Path

        tools = Path(__file__).resolve().parents[2] / "tools"
        if str(tools) not in sys.path:
            sys.path.insert(0, str(tools))
        from s1_tools.human_input import click_human  # type: ignore

        click_human(int(x), int(y), alt=(button == "right"))
        if double:
            time.sleep(0.05)
            click_human(int(x), int(y), alt=(button == "right"))
        return
    except Exception:
        pass
    import ctypes

    u = ctypes.windll.user32
    u.SetCursorPos(int(x), int(y))
    time.sleep(0.04)
    down, up = (0x0008, 0x0010) if button == "right" else (0x0002, 0x0004)
    u.mouse_event(down, 0, 0, 0, 0)
    time.sleep(0.04)
    u.mouse_event(up, 0, 0, 0, 0)
    if double:
        time.sleep(0.05)
        u.mouse_event(down, 0, 0, 0, 0)
        time.sleep(0.04)
        u.mouse_event(up, 0, 0, 0, 0)


def _move(x: int, y: int) -> None:
    try:
        import sys
        from pathlib import Path

        tools = Path(__file__).resolve().parents[2] / "tools"
        if str(tools) not in sys.path:
            sys.path.insert(0, str(tools))
        from s1_tools.human_input import move_human  # type: ignore

        move_human(int(x), int(y))
        return
    except Exception:
        pass
    import ctypes

    ctypes.windll.user32.SetCursorPos(int(x), int(y))


def _drag(x0: int, y0: int, x1: int, y1: int, *, hold: float = 0.35) -> None:
    import ctypes

    u = ctypes.windll.user32
    _move(x0, y0)
    time.sleep(0.08)
    u.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(max(0.12, hold))
    _move(x1, y1)
    time.sleep(0.12)
    u.mouse_event(0x0004, 0, 0, 0, 0)


def dumps(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str)
