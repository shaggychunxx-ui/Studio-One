"""
Static RE of UCNET session / TCP message handling.

Focus: message size fields, fourcc/event IDs, XML/UCXML markers,
and cross-refs from 'Subscribe' / 'Incoming socket' strings.
"""
from __future__ import annotations

import struct
from pathlib import Path

DLLS = [
    Path(r"C:\Program Files\PreSonus\Universal Control\ucnet.dll"),
    Path(r"C:\Program Files\PreSonus\Studio One 6\ucnet.dll"),
    Path(r"C:\Program Files\PreSonus\Studio One 6\Plugins\remoteservice.dll"),
    Path(r"C:\Program Files\PreSonus\Studio One 6\cclnet.dll"),
]


def parse_pe(data: bytes):
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    coff = e_lfanew + 4
    num_sections = struct.unpack_from("<H", data, coff + 2)[0]
    size_opt = struct.unpack_from("<H", data, coff + 16)[0]
    opt = coff + 20
    sec_off = opt + size_opt
    sections = []
    for i in range(num_sections):
        off = sec_off + i * 40
        name = data[off : off + 8].split(b"\0", 1)[0].decode("ascii", "replace")
        vsize, vaddr, rsize, roff = struct.unpack_from("<IIII", data, off + 8)
        sections.append((name, vaddr, vsize, roff, rsize))
    return sections


def rva_to_off(sections, rva: int) -> int | None:
    for name, vaddr, vsize, roff, rsize in sections:
        if vaddr <= rva < vaddr + max(vsize, rsize):
            return roff + (rva - vaddr)
    return None


def off_to_rva(sections, off: int) -> int | None:
    for name, vaddr, vsize, roff, rsize in sections:
        if roff <= off < roff + rsize:
            return vaddr + (off - roff)
    return None


def find_xrefs_rip(text: bytes, text_va: int, target_rva: int) -> list[int]:
    hits = []
    for i in range(len(text) - 7):
        b0, b1 = text[i], text[i + 1]
        if b0 in (0x48, 0x4C) and b1 in (0x8D, 0x8B):
            modrm = text[i + 2]
            if (modrm & 0xC7) != 0x05:
                continue
            rel = struct.unpack_from("<i", text, i + 3)[0]
            insn_rva = text_va + i
            dest = insn_rva + 7 + rel
            if dest == target_rva:
                hits.append(insn_rva)
    return hits


def dump_ctx(data: bytes, off: int, before: int = 64, after: int = 96) -> str:
    start = max(0, off - before)
    end = min(len(data), off + after)
    return data[start:end].hex()


def analyze(path: Path) -> None:
    if not path.is_file():
        return
    data = path.read_bytes()
    print(f"\n======== {path.name} ({len(data)} bytes) ========")
    sections = parse_pe(data)
    text_sec = next((s for s in sections if s[0] == ".text"), None)
    if not text_sec:
        print("no .text")
        return
    _, text_va, _, text_off, text_rs = text_sec
    text = data[text_off : text_off + text_rs]

    markers = [
        b"Subscribe Failed",
        b"Unsubscribe Failed",
        b"Incoming socket is in error state",
        b"Outgoing socket is in error state",
        b"Started listening on TCP port",
        b"Can't send periodic event",
        b"Sending events to network before shutdown",
        b"Subscribe",
        b"Unsubscribe",
        b"UCXML",
        b"networkServerEnabled",
        b"RemoteSession",
        b"messageReceived",
        b"compressed",
        b"aesencrypted",
        b"xteaencrypted",
        b"basicencrypted",
        b"WebSocket",
        b"Content-Length",
    ]
    for m in markers:
        off = data.find(m)
        if off < 0:
            continue
        rva = off_to_rva(sections, off)
        print(f"STR {m!r} file@0x{off:x} rva={hex(rva) if rva else None}")
        if rva is None:
            continue
        xrefs = find_xrefs_rip(text, text_va, rva)
        print(f"  xrefs: {[hex(x) for x in xrefs[:6]]}")
        for xr in xrefs[:2]:
            foff = rva_to_off(sections, xr)
            if foff is None:
                continue
            # dump surrounding code
            print(f"  ctx@{hex(xr)}: {dump_ctx(data, foff, 80, 120)}")

    # Scan for immediate constants that look like max message sizes
    for imm in (0x2800, 0x10000, 0x100000, 0x400, 0x800, 0x1000, 0x2000, 0x4000, 0x8000):
        needle = struct.pack("<I", imm)
        count = text.count(needle)
        if count:
            print(f"imm32 0x{imm:x} in .text: {count}")

    # FourCC-like immediates in .text (printable ASCII)
    # look for cmp eax, imm32 where imm32 is printable
    fourccs = {}
    for i in range(len(text) - 5):
        if text[i] == 0x3D:  # cmp eax, imm32
            imm = struct.unpack_from("<I", text, i + 1)[0]
            b = struct.pack("<I", imm)
            if all(32 <= c < 127 for c in b):
                fourccs.setdefault(b.decode("ascii"), 0)
                fourccs[b.decode("ascii")] += 1
        # cmp reg, imm32 with REX? skip for now
    if fourccs:
        print("printable cmp-eax fourccs:")
        for k, v in sorted(fourccs.items(), key=lambda x: -x[1])[:40]:
            print(f"  {k!r} x{v}  (0x{struct.unpack('<I', k.encode())[0]:08x})")


def main() -> None:
    for p in DLLS:
        analyze(p)


if __name__ == "__main__":
    main()
