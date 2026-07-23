"""Locate numeric constants (ports, multicast IPs) near UCNET strings."""
from __future__ import annotations

import re
import struct
from pathlib import Path

PATHS = [
    Path(r"C:\Program Files\PreSonus\Universal Control\ucnet.dll"),
    Path(r"C:\Program Files\PreSonus\Studio One 6\ucnet.dll"),
    Path(r"C:\Program Files\PreSonus\Studio One 6\Plugins\remoteservice.dll"),
]


def find_all(data: bytes, needle: bytes) -> list[int]:
    out = []
    start = 0
    while True:
        i = data.find(needle, start)
        if i < 0:
            break
        out.append(i)
        start = i + 1
    return out


def main() -> None:
    for path in PATHS:
        if not path.is_file():
            continue
        data = path.read_bytes()
        print(f"\n==== {path} ====")
        # port 47809 = 0xBAA1
        for endian, fmt in (("le", "<H"), ("be", ">H")):
            needle = struct.pack(fmt, 47809)
            hits = find_all(data, needle)
            print(f"  port 47809 {endian}: {len(hits)} hits @ {hits[:12]}")
        # common multicast prefixes 239.x / 224.x as bytes
        for ip in [
            bytes([239, 255, 255, 250]),
            bytes([239, 255, 0, 1]),
            bytes([239, 192, 152, 143]),
            bytes([224, 0, 0, 251]),
            bytes([239, 255, 255, 255]),
        ]:
            hits = find_all(data, ip)
            if hits:
                print(f"  IP {'.'.join(map(str, ip))}: {hits[:8]}")
        # search for dotted multicast strings
        for m in re.finditer(rb"22[4-9]\.\d{1,3}\.\d{1,3}\.\d{1,3}", data):
            print("  mcast str", m.group().decode(), "at", m.start())
        for m in re.finditer(rb"239\.\d{1,3}\.\d{1,3}\.\d{1,3}", data):
            print("  mcast239", m.group().decode(), "at", m.start())
        # string offsets for discovery logs — dump nearby bytes as possible magic
        for s in [
            b"UC Discovery sending query",
            b"Adding server via UDP discovery",
            b"Enabled UDP multicast on official port",
            b"DAWREMOTE",
            b"DAWRemote",
            b"alive event",
            b"UCNET",
        ]:
            for off in find_all(data, s)[:3]:
                window = data[max(0, off - 32) : off + len(s) + 64]
                print(f"  near {s!r} @{off}: {window[:80]!r}")


if __name__ == "__main__":
    main()
