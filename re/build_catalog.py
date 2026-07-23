"""Parse remoteservice SurfaceData XML into a plugin parameter catalog."""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

XML_PATH = Path(__file__).parent / "extracted" / "remoteservice_xml_03.xml"
OUT_PATH = Path(__file__).parent / "plugin_param_catalog.json"


def main() -> None:
    text = XML_PATH.read_text(encoding="utf-8", errors="replace")
    # SurfaceData uses x:id without xmlns; strip or declare prefix.
    if 'xmlns:x=' not in text:
        text = text.replace(
            "<SurfaceData ",
            '<SurfaceData xmlns:x="http://www.presonus.com/xml/x" ',
            1,
        )
    root = ET.fromstring(text)
    catalog: dict = {}

    for sda in root.findall("SurfaceDeviceAssignment"):
        did = sda.get("deviceID") or ""
        name = sda.get("friendlyName") or did
        params: dict = {}
        for assoc in sda.iter("Association"):
            key = assoc.get("key") or ""
            val = assoc.get("value") or ""
            m = re.match(r"(\{[^}]+\})/(.+)$", val)
            if m:
                guid, path = m.group(1), m.group(2)
                entry = params.setdefault(path, {"guid": guid, "controls": []})
                entry["controls"].append(key)
            elif val:
                entry = params.setdefault(val, {"guid": did, "controls": []})
                entry["controls"].append(key)
        subs = []
        for sub in sda.iter("SurfaceAssignmentData"):
            subs.append(
                {
                    "folder": sub.get("folder"),
                    "deviceID": sub.get("deviceID"),
                    "friendlyName": sub.get("friendlyName"),
                }
            )
        catalog[name] = {"deviceID": did, "params": params, "subdevices": subs}

    OUT_PATH.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    print(f"plugins: {len(catalog)}")
    for k, v in sorted(catalog.items(), key=lambda x: x[0].lower()):
        print(f"  {k:32s} params={len(v['params']):3d}")
    print("wrote", OUT_PATH)


if __name__ == "__main__":
    main()
