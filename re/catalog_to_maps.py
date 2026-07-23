"""Convert RE plugin catalog into s1remote Control Link map stubs (CC 20+)."""
from __future__ import annotations

import json
from pathlib import Path

CATALOG = Path(__file__).parent / "plugin_param_catalog.json"
OUT = Path(__file__).parent.parent / "config" / "plugin_maps.json"

# Skip synthetic / non-plugin entries
SKIP = {"static", "Channel Controls", "Macro Controls", "{12345678-90AB-CDEF-1234-567890ABCDEF}"}


def slug(name: str) -> str:
    return (
        name.strip()
        .lower()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("-", "_")
    )


def main() -> None:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    plugins: dict = {}
    for name, entry in catalog.items():
        if name in SKIP:
            continue
        params = entry.get("params") or {}
        # Prefer real {GUID}/path params; skip pure macro set paths unless that's all we have
        real = {
            p: meta
            for p, meta in params.items()
            if not str(p).startswith("AudioChannel")
            and not str(p).startswith("GlobalMacro")
            and not str(p).startswith("Control/")
        }
        if not real:
            real = params
        # Assign sequential CCs starting at 20 (stable, learnable)
        mapped = {}
        cc = 20
        for path in sorted(real.keys()):
            if cc > 119:
                break
            mapped[path] = {
                "cc": cc,
                "channel": 0,
                "guid": (real[path] or {}).get("guid"),
                "note": "RE: remoteservice SurfaceData — learn CC in Control Link",
            }
            cc += 1
        plugins[slug(name)] = {
            "title": name,
            "deviceID": entry.get("deviceID"),
            "params": mapped,
            "source": "remoteservice.dll SurfaceData",
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"plugins": plugins}, indent=2), encoding="utf-8")
    print(f"Wrote {len(plugins)} plugins -> {OUT}")


if __name__ == "__main__":
    main()
