"""Windows UI Automation walk of Studio One chrome (menus, dialogs, buttons).

Studio One's Arrange / Console canvas is custom-drawn and usually absent
from the UIA tree. Use this for native chrome; use layout + Find Command
for the rest.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

SKIP_TITLE = (
    "grok",
    "windows terminal",
    "powershell",
    "visual studio",
    "chrome",
    "edge",
    "firefox",
)

# Child dialogs of Studio One often omit "Studio One" in the title.
S1_DIALOG_TITLES = (
    "save as template",
    "save as",
    "save new version",
    "locate missing files",
    "missing devices",
    "safety",
)


def _is_s1_window_title(title: str) -> bool:
    low = (title or "").lower()
    if "studio one" in low:
        return True
    return any(s in low for s in S1_DIALOG_TITLES)


def _s1_windows(backend: str = "uia"):
    from pywinauto import Desktop

    out = []
    desk = Desktop(backend=backend)
    for w in desk.windows():
        try:
            t = (w.window_text() or "").strip()
        except Exception:
            continue
        if not t:
            continue
        low = t.lower()
        if not _is_s1_window_title(t):
            continue
        if any(s in low for s in SKIP_TITLE):
            continue
        try:
            if hasattr(w, "is_visible") and not w.is_visible():
                continue
        except Exception:
            pass
        out.append(w)
    return out


def main_window():
    wins = _s1_windows("uia")
    if not wins:
        wins = _s1_windows("win32")
    if not wins:
        return None
    for w in wins:
        try:
            t = (w.window_text() or "")
        except Exception:
            continue
        if "safety" in t.lower():
            continue
        if " - " in t:
            return w
    return wins[0]


def list_top_windows() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen = set()
    for backend in ("uia", "win32"):
        for w in _s1_windows(backend):
            try:
                t = (w.window_text() or "").strip()
                r = w.rectangle()
                key = (backend, t, int(r.left), int(r.top), int(r.right), int(r.bottom))
                if key in seen:
                    continue
                seen.add(key)
                ctype = ""
                try:
                    ctype = str(w.element_info.control_type)
                except Exception:
                    pass
                rows.append(
                    {
                        "backend": backend,
                        "title": t,
                        "control_type": ctype,
                        "left": int(r.left),
                        "top": int(r.top),
                        "right": int(r.right),
                        "bottom": int(r.bottom),
                    }
                )
            except Exception:
                continue
    return rows


def _node_info(el, depth: int) -> Optional[Dict[str, Any]]:
    try:
        name = (el.window_text() or "").strip()
    except Exception:
        name = ""
    try:
        ctype = str(el.element_info.control_type or "")
    except Exception:
        ctype = ""
    auto_id = ""
    try:
        auto_id = str(el.element_info.automation_id or "")
    except Exception:
        pass
    try:
        r = el.rectangle()
        rect = [int(r.left), int(r.top), int(r.right), int(r.bottom)]
        wdt = rect[2] - rect[0]
        hgt = rect[3] - rect[1]
    except Exception:
        rect = None
        wdt = hgt = 0
    if wdt <= 0 or hgt <= 0:
        if not name and not auto_id:
            return None
    return {
        "name": name,
        "control_type": ctype,
        "automation_id": auto_id,
        "rect": rect,
        "depth": depth,
    }


def dump_tree(
    *,
    query: str = "",
    max_depth: int = 6,
    max_nodes: int = 400,
    named_only: bool = True,
) -> List[Dict[str, Any]]:
    """Flattened UIA descendants of the main Studio One window."""
    w = main_window()
    if w is None:
        return []
    q = (query or "").lower().strip()
    nodes: List[Dict[str, Any]] = []

    def walk(el, depth: int) -> None:
        if len(nodes) >= max_nodes or depth > max_depth:
            return
        info = _node_info(el, depth)
        if info:
            if named_only and not info["name"] and not info["automation_id"]:
                pass
            else:
                blob = f"{info['name']} {info['control_type']} {info['automation_id']}".lower()
                if not q or q in blob:
                    nodes.append(info)
                    if len(nodes) >= max_nodes:
                        return
        if depth >= max_depth:
            return
        try:
            kids = el.children()
        except Exception:
            return
        for kid in kids:
            walk(kid, depth + 1)
            if len(nodes) >= max_nodes:
                return

    walk(w, 0)
    return nodes


def find_elements(
    *,
    name: str = "",
    control_type: str = "",
    automation_id: str = "",
    max_nodes: int = 80,
) -> List[Dict[str, Any]]:
    name_l = (name or "").lower().strip()
    ct_l = (control_type or "").lower().strip()
    aid_l = (automation_id or "").lower().strip()
    hits = []
    for n in dump_tree(query=name_l, max_depth=8, max_nodes=800, named_only=False):
        if name_l and name_l not in (n.get("name") or "").lower():
            continue
        if ct_l and ct_l not in (n.get("control_type") or "").lower():
            continue
        if aid_l and aid_l not in (n.get("automation_id") or "").lower():
            continue
        hits.append(n)
        if len(hits) >= max_nodes:
            break
    return hits


def _match_wrapper(name: str, control_type: str = ""):
    w = main_window()
    if w is None:
        return None
    name_l = (name or "").lower()
    try:
        descendants = w.descendants()
    except Exception:
        return None
    for el in descendants:
        try:
            nm = (el.window_text() or "").strip()
        except Exception:
            continue
        if name_l not in nm.lower():
            continue
        if control_type:
            try:
                ct = str(el.element_info.control_type or "")
            except Exception:
                ct = ""
            if control_type.lower() not in ct.lower():
                continue
        return el
    return None


def invoke(name: str, *, control_type: str = "") -> Dict[str, Any]:
    el = _match_wrapper(name, control_type)
    if el is None:
        return {"ok": False, "error": f"no UIA element matching {name!r}"}
    try:
        el.click_input()
        return {"ok": True, "method": "click_input", "name": name}
    except Exception as e:
        try:
            el.invoke()
            return {"ok": True, "method": "invoke", "name": name}
        except Exception as e2:
            return {"ok": False, "error": f"{e}; {e2}"}


def set_value(name: str, value: str, *, control_type: str = "Edit") -> Dict[str, Any]:
    el = _match_wrapper(name, control_type)
    if el is None:
        # Try any Edit
        el = _match_wrapper(name, "")
    if el is None:
        return {"ok": False, "error": f"no UIA field matching {name!r}"}
    try:
        el.set_edit_text(value)
        return {"ok": True, "name": name, "value": value}
    except Exception:
        try:
            el.type_keys("^a{" + "BACKSPACE}" + value, with_spaces=True)
            return {"ok": True, "name": name, "value": value, "method": "type_keys"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
