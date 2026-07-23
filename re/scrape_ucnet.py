"""Extract protocol-relevant strings from UCNET-related binaries."""
from __future__ import annotations

import re
import struct
from pathlib import Path

BINS = [
    Path(r"C:\Program Files\PreSonus\Studio One 6\ucnet.dll"),
    Path(r"C:\Program Files\PreSonus\Studio One 6\Plugins\remoteservice.dll"),
    Path(r"C:\Program Files\PreSonus\Studio One 6\cclnet.dll"),
    Path(r"C:\Program Files\PreSonus\Studio One 6\Studio One.exe"),
]
OUT = Path(__file__).parent / "ucnet_strings.txt"

# Focus filters
KEEP = re.compile(
    r"(?i)("
    r"ucnet|ucxml|dawremote|remote|discover|broadcast|multicast|"
    r"subscribe|publish|session|handshake|hello|ping|pong|"
    r"param|mixer|transport|volume|mute|solo|"
    r"socket|tcp|udp|port|47809|xml|json|protobuf|"
    r"presonus|component|device|surface|control|"
    r"message|packet|frame|header|magic|version|"
    r"UC[A-Z][A-Za-z0-9_]{2,40}"
    r")"
)


def extract_ascii(data: bytes, min_len: int = 6) -> list[str]:
    out: list[str] = []
    cur = bytearray()
    for b in data:
        if 32 <= b < 127:
            cur.append(b)
        else:
            if len(cur) >= min_len:
                out.append(cur.decode("ascii"))
            cur.clear()
    if len(cur) >= min_len:
        out.append(cur.decode("ascii"))
    return out


def extract_utf16le(data: bytes, min_len: int = 6) -> list[str]:
    out: list[str] = []
    # naive: sequences of printable ASCII as UTF-16LE
    i = 0
    cur = []
    while i + 1 < len(data):
        lo, hi = data[i], data[i + 1]
        if hi == 0 and 32 <= lo < 127:
            cur.append(chr(lo))
            i += 2
        else:
            if len(cur) >= min_len:
                out.append("".join(cur))
            cur = []
            i += 2 if hi == 0 else 1
    if len(cur) >= min_len:
        out.append("".join(cur))
    return out


def main() -> None:
    lines: list[str] = []
    for path in BINS:
        if not path.is_file():
            lines.append(f"\n## MISSING {path}\n")
            continue
        data = path.read_bytes()
        lines.append(f"\n## {path.name} ({len(data)} bytes)\n")
        seen: set[str] = set()
        for s in extract_ascii(data) + extract_utf16le(data):
            if s in seen:
                continue
            if not KEEP.search(s):
                continue
            # drop junk
            if len(s) > 200:
                continue
            seen.add(s)
        for s in sorted(seen, key=str.lower):
            lines.append(s)

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT} ({len(lines)} lines)")
    # print compact summary of high-value tokens
    text = "\n".join(lines)
    for pat in [
        r"47809",
        r"UC[A-Z][A-Za-z0-9_]{3,50}",
        r"DAWRemote",
        r"discover[A-Za-z0-9_]*",
        r"UCNET[A-Za-z0-9_]*",
        r"Presonus:[A-Za-z0-9_]+",
    ]:
        hits = sorted(set(re.findall(pat, text, flags=re.I)))
        print(f"\n=== {pat} ({len(hits)}) ===")
        for h in hits[:40]:
            print(" ", h)


if __name__ == "__main__":
    main()
