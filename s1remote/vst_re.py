"""
Reverse-engineer installed VST / VST3 plugins for parameter maps.

Approach (layered — whatever yields signal, we keep):
  1. Host-load via pedalboard (VST3/AU-style param IDs when load works)
  2. Binary string scrape of plugin modules (titles, param-like tokens)
  3. Merge Studio One SurfaceData catalog (stock plugins — already RE'd)
  4. Emit Control Link CC maps for s1remote VST MIDI control

Nothing here injects into Studio One.exe. We extract structure from plugin
binaries and Studio One's own remote tables, then drive via MIDI CCs.
"""

from __future__ import annotations

import json
import re
import struct
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable, Optional

from . import config

DEFAULT_SEARCH_ROOTS = [
    Path(r"C:\Program Files\Common Files\VST3"),
    Path(r"C:\Program Files\VSTPlugins"),
    Path(r"C:\Program Files\Steinberg\VSTPlugins"),
    Path(r"C:\Program Files\Common Files\VST2"),
    # NOTE: do NOT scan Studio One 6\Plugins — those are host modules, not user VSTs.
]

# Host-side DLLs that are not user-facing plugins
SKIP_NAME_SUBSTR = (
    "service",
    "handler",
    "engine",
    "codec",
    "sqlite",
    "elastique",
    "goobers",
    "cdburn",
    "jsengine",
    "timestretch",
    "windowsaudio",
    "windowsmidi",
)

# Prefer readable / stable-looking parameter tokens
PARAM_TOKEN = re.compile(
    r"^(?:"
    r"[A-Za-z][A-Za-z0-9_ ./+\-]{1,48}"
    r")$"
)
NOISE = re.compile(
    r"(?i)("
    r"http|https|www\.|copyright|microsoft|runtime|exception|error|"
    r"assert|nullptr|std::|kernel32|user32|vst3|plugin|company|"
    r"vendor|version|build|debug|release|window|class|object|"
    r"function|return|float|double|int32|uint|void|true|false|"
    r"\.dll|\.exe|\.vst|xml|json|utf-?8|guid|clsid"
    r")"
)
PARAM_HINT = re.compile(
    r"(?i)("
    r"cutoff|reso|freq|gain|volume|level|pan|mix|dry|wet|"
    r"attack|decay|sustain|release|threshold|ratio|knee|"
    r"drive|tone|bass|mid|treble|presence|depth|rate|feedback|"
    r"delay|time|size|width|spread|color|shape|mode|type|"
    r"amount|send|return|mute|solo|bypass|enable|on|off|"
    r"osc|filter|env|lfo|mod|pitch|tune|detune|portamento|"
    r"comp|gate|limit|eq|band|q\b|hz|db|ms|bpm|"
    r"param|knob|fader|slider|control"
    r")"
)


@dataclass
class PluginParam:
    name: str
    index: Optional[int] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    default: Optional[float] = None
    units: str = ""
    source: str = ""  # pedalboard | strings | surface


@dataclass
class PluginInfo:
    name: str
    path: str
    format: str  # vst3 | vst2 | stock | unknown
    uid: str = ""
    params: list[PluginParam] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

    def slug(self) -> str:
        s = re.sub(r"[^a-z0-9]+", "_", self.name.lower()).strip("_")
        return s or "plugin"


def find_plugin_files(roots: Iterable[Path] | None = None) -> list[Path]:
    roots = list(roots or DEFAULT_SEARCH_ROOTS)
    found: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            suf = p.suffix.lower()
            # VST3 package: prefer the binary inside Contents\x86_64-win
            if suf == ".vst3" and "Contents" in p.parts and "x86_64-win" in p.parts:
                key = str(p.resolve()).lower()
                if key not in seen:
                    seen.add(key)
                    found.append(p)
            elif suf == ".dll":
                low = p.name.lower()
                if low in ("msvcp140.dll", "vcruntime140.dll"):
                    continue
                if any(s in low for s in SKIP_NAME_SUBSTR):
                    continue
                # Only treat as VST2 if path suggests plugin folders
                pl = str(p).lower()
                if not any(x in pl for x in ("vstplugin", "vst2", "\\vst\\", "/vst/")):
                    continue
                key = str(p.resolve()).lower()
                if key not in seen:
                    seen.add(key)
                    found.append(p)
            elif suf == ".vst3" and p.parent.name.lower() != "x86_64-win":
                # bundle root — also record if no nested binary later
                key = str(p.resolve()).lower()
                # only if it's a directory-like package file (Windows uses folder)
                pass
    # Also add bundle directories as candidates for pedalboard (it may accept .vst3 folder)
    for root in roots:
        if not root.exists():
            continue
        for p in root.glob("*.vst3"):
            if p.is_dir() or p.is_file():
                key = str(p.resolve()).lower()
                if key not in seen:
                    seen.add(key)
                    found.append(p)
        for p in root.rglob("*.vst3"):
            if p.is_dir():
                key = str(p.resolve()).lower()
                if key not in seen:
                    seen.add(key)
                    found.append(p)
    return found


def extract_ascii_strings(data: bytes, min_len: int = 4, max_len: int = 64) -> list[str]:
    out: list[str] = []
    cur = bytearray()
    for b in data:
        if 32 <= b < 127:
            cur.append(b)
        else:
            if min_len <= len(cur) <= max_len:
                out.append(cur.decode("ascii"))
            cur.clear()
    if min_len <= len(cur) <= max_len:
        out.append(cur.decode("ascii"))
    return out


def score_param_string(s: str) -> int:
    if not PARAM_TOKEN.match(s):
        return -1
    if NOISE.search(s):
        return -1
    if len(s) < 2 or s.isdigit():
        return -1
    # reject pure hex / GUID chunks
    if re.fullmatch(r"[0-9A-Fa-f\-]{8,}", s):
        return -1
    score = 0
    if PARAM_HINT.search(s):
        score += 5
    if " " in s or "_" in s or "." in s:
        score += 1
    if s[0].isupper():
        score += 1
    if any(c.islower() for c in s) and any(c.isupper() for c in s):
        score += 1
    # path-like param ids: amp.presence, filter.cutoff
    if re.search(r"^[a-z][a-z0-9]+(\.[a-z][a-z0-9]+){1,4}$", s):
        score += 6
    return score


def scrape_plugin_binary(path: Path, max_bytes: int = 40_000_000) -> list[PluginParam]:
    try:
        size = path.stat().st_size
        if size > max_bytes or size < 1024:
            # For huge bundles, try nested binary
            if path.is_dir() or path.suffix.lower() == ".vst3":
                nested = list(path.rglob("*")) if path.is_dir() else list(path.parent.rglob("*"))
                # if path is file .vst3 inside x86_64-win, read it
                if path.is_file():
                    data = path.read_bytes()
                else:
                    bins = [
                        n
                        for n in path.rglob("*")
                        if n.is_file()
                        and n.suffix.lower() in (".vst3", ".dll")
                        and "x86_64" in str(n)
                    ]
                    if not bins:
                        return []
                    data = bins[0].read_bytes()[:max_bytes]
            else:
                return []
        else:
            if path.is_dir():
                bins = [
                    n
                    for n in path.rglob("*")
                    if n.is_file() and n.suffix.lower() in (".vst3", ".dll")
                ]
                if not bins:
                    return []
                data = bins[0].read_bytes()[:max_bytes]
            else:
                data = path.read_bytes()
    except OSError:
        return []

    scored: dict[str, int] = {}
    for s in extract_ascii_strings(data):
        sc = score_param_string(s)
        if sc >= 5:
            scored[s] = max(scored.get(s, 0), sc)
    # rank
    ordered = sorted(scored.items(), key=lambda kv: (-kv[1], kv[0].lower()))
    params: list[PluginParam] = []
    seen_l: set[str] = set()
    for name, sc in ordered[:256]:
        key = name.lower()
        if key in seen_l:
            continue
        seen_l.add(key)
        params.append(PluginParam(name=name, index=len(params), source="strings"))
    return params


def dump_via_pedalboard(path: Path) -> Optional[PluginInfo]:
    try:
        from pedalboard import load_plugin
    except ImportError:
        return None
    try:
        plug = load_plugin(str(path))
    except Exception:
        return None
    name = getattr(plug, "name", None) or path.stem
    params: list[PluginParam] = []
    raw = getattr(plug, "parameters", None)
    if raw is not None:
        try:
            items = list(raw.items())
        except Exception:
            items = []
        for i, (key, p) in enumerate(items):
            # Prefer human name attribute when present
            label = getattr(p, "name", None) or key
            params.append(
                PluginParam(
                    name=str(label),
                    index=i,
                    min_value=getattr(p, "min_value", None),
                    max_value=getattr(p, "max_value", None),
                    default=getattr(p, "raw_value", None),
                    units=str(getattr(p, "units", "") or ""),
                    source="pedalboard",
                )
            )
    fmt = "vst3" if "vst3" in str(path).lower() else "vst2"
    return PluginInfo(
        name=str(name),
        path=str(path),
        format=fmt,
        params=params,
        sources=["pedalboard"],
    )


def load_surface_catalog() -> list[PluginInfo]:
    cat_path = Path(__file__).resolve().parent.parent / "re" / "plugin_param_catalog.json"
    if not cat_path.is_file():
        return []
    data = json.loads(cat_path.read_text(encoding="utf-8"))
    out: list[PluginInfo] = []
    skip = {"static", "Channel Controls", "Macro Controls"}
    for name, entry in data.items():
        if name in skip or name.startswith("{"):
            continue
        params = []
        for i, (pname, meta) in enumerate((entry.get("params") or {}).items()):
            if str(pname).startswith(("AudioChannel", "GlobalMacro", "Control/")):
                continue
            params.append(
                PluginParam(
                    name=str(pname),
                    index=i,
                    source="surface",
                )
            )
        out.append(
            PluginInfo(
                name=name,
                path="stock://remoteservice",
                format="stock",
                uid=entry.get("deviceID") or "",
                params=params,
                sources=["surface"],
            )
        )
    return out


def reverse_all_plugins(
    roots: Iterable[Path] | None = None,
    use_pedalboard: bool = True,
    use_strings: bool = True,
    use_surface: bool = True,
) -> list[PluginInfo]:
    results: dict[str, PluginInfo] = {}

    if use_surface:
        for info in load_surface_catalog():
            results[info.slug()] = info

    files = find_plugin_files(roots)
    for path in files:
        info: Optional[PluginInfo] = None
        if use_pedalboard:
            info = dump_via_pedalboard(path)
        if info is None:
            info = PluginInfo(
                name=path.stem.replace(".vst3", "").replace("_", " "),
                path=str(path),
                format="vst3" if "vst3" in str(path).lower() else "vst2",
                sources=[],
            )
        if use_strings:
            scraped = scrape_plugin_binary(path if path.is_file() else path)
            if scraped:
                # merge: prefer pedalboard names; add string names not present
                existing = {p.name.lower() for p in info.params}
                for sp in scraped:
                    if sp.name.lower() not in existing:
                        sp.index = len(info.params)
                        info.params.append(sp)
                        existing.add(sp.name.lower())
                if "strings" not in info.sources:
                    info.sources.append("strings")
        key = info.slug()
        if key in results and results[key].params and not info.params:
            continue
        # merge with existing stock if same name
        if key in results:
            base = results[key]
            existing = {p.name.lower() for p in base.params}
            for p in info.params:
                if p.name.lower() not in existing:
                    p.index = len(base.params)
                    base.params.append(p)
            base.sources = sorted(set(base.sources + info.sources))
            if info.path and info.path != base.path:
                base.path = info.path
                base.format = info.format
        else:
            results[key] = info

    return sorted(results.values(), key=lambda p: p.name.lower())


def to_control_link_maps(
    plugins: list[PluginInfo],
    cc_start: int = 20,
    max_cc: int = 119,
    max_channels: int = 16,
) -> dict[str, Any]:
    """
    Assign sequential MIDI CCs for Control Link maps.

    Uses MIDI channels 0..max_channels-1 as banks so plugins with >100 params
    (e.g. Movement, SynthMaster) still get full coverage:
      channel 0: CC 20-119, channel 1: CC 20-119, ...
    """
    out: dict[str, Any] = {}
    span = max_cc - cc_start + 1
    capacity = span * max_channels
    for plug in plugins:
        if not plug.params:
            continue
        params = {}
        for i, p in enumerate(plug.params):
            if i >= capacity:
                break
            ch = i // span
            cc = cc_start + (i % span)
            params[p.name] = {
                "cc": cc,
                "channel": ch,
                "index": p.index if p.index is not None else i,
                "min": p.min_value,
                "max": p.max_value,
                "source": p.source,
            }
        out[plug.slug()] = {
            "title": plug.name,
            "path": plug.path,
            "format": plug.format,
            "uid": plug.uid,
            "sources": plug.sources,
            "param_count": len(params),
            "params_total_discovered": len(plug.params),
            "params": params,
        }
    return {"plugins": out}


def scan_and_save(
    out_catalog: Optional[Path] = None,
    out_maps: Optional[Path] = None,
    **kwargs,
) -> dict[str, Any]:
    plugins = reverse_all_plugins(**kwargs)
    catalog = {
        "plugins": [
            {
                "name": p.name,
                "slug": p.slug(),
                "path": p.path,
                "format": p.format,
                "uid": p.uid,
                "sources": p.sources,
                "params": [asdict(x) for x in p.params],
            }
            for p in plugins
        ]
    }
    maps = to_control_link_maps(plugins)

    out_catalog = out_catalog or (config.CONFIG_DIR / "vst_re_catalog.json")
    out_maps = out_maps or config.MAPS_PATH
    config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # Merge maps into existing plugin_maps (keep user defines)
    existing: dict[str, Any] = {}
    if out_maps.is_file():
        try:
            existing = json.loads(out_maps.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    merged_plugins = dict(existing.get("plugins") or {})
    for k, v in maps["plugins"].items():
        # Don't wipe user maps that have "user map" notes exclusively — merge params
        if k in merged_plugins and merged_plugins[k].get("params"):
            # Prefer richer RE map if more params
            if len(v.get("params") or {}) >= len(merged_plugins[k].get("params") or {}):
                merged_plugins[k] = v
        else:
            merged_plugins[k] = v
    # ensure generic banks remain
    from .vst_midi import GENERIC_BANKS

    for k, v in GENERIC_BANKS.items():
        merged_plugins.setdefault(k, v)

    out_catalog.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    out_maps.write_text(json.dumps({"plugins": merged_plugins}, indent=2), encoding="utf-8")

    summary = {
        "plugins_found": len(plugins),
        "with_params": sum(1 for p in plugins if p.params),
        "total_params": sum(len(p.params) for p in plugins),
        "catalog": str(out_catalog),
        "maps": str(out_maps),
        "plugins": [
            {
                "name": p.name,
                "format": p.format,
                "params": len(p.params),
                "sources": p.sources,
            }
            for p in plugins
        ],
    }
    return summary
