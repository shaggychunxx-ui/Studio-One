import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
c = json.loads((root / "config/vst_re_catalog.json").read_text(encoding="utf-8"))
print("plugins", len(c["plugins"]))
for p in c["plugins"]:
    print(f"{p['name']:30s} {p['format']:6s} params={len(p['params']):4d} src={p['sources']}")
m = json.loads((root / "config/plugin_maps.json").read_text(encoding="utf-8"))
print("maps", len(m["plugins"]))
for k in sorted(m["plugins"]):
    if any(x in k for x in ("move", "synth", "melody", "generic")):
        print(" map", k, "params", len(m["plugins"][k].get("params") or {}))
