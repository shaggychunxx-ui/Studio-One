"""
Heuristic static RE of discovery packet format in ucnet.dll.

Looks for:
- immediate 47809 (0xBAA1) in code
- nearby string xrefs to discovery log messages
- candidate packet field sizes from format strings: tcp %d udp %d
"""
from __future__ import annotations

import re
import struct
from pathlib import Path

DLL = Path(r"C:\Program Files\PreSonus\Universal Control\ucnet.dll")
# Studio One copy as fallback
if not DLL.is_file():
    DLL = Path(r"C:\Program Files\PreSonus\Studio One 6\ucnet.dll")


def main() -> None:
    data = DLL.read_bytes()
    print("file", DLL, "size", len(data))

    # PE parse minimal: find .text and .rdata sections
    if data[:2] != b"MZ":
        print("not PE")
        return
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if data[e_lfanew : e_lfanew + 4] != b"PE\0\0":
        print("bad PE")
        return
    coff = e_lfanew + 4
    num_sections = struct.unpack_from("<H", data, coff + 2)[0]
    size_opt = struct.unpack_from("<H", data, coff + 16)[0]
    opt = coff + 20
    magic = struct.unpack_from("<H", data, opt)[0]
    pe32plus = magic == 0x20B
    print("PE32+" if pe32plus else "PE32", "sections", num_sections)
    sec_off = opt + size_opt
    sections = []
    for i in range(num_sections):
        off = sec_off + i * 40
        name = data[off : off + 8].split(b"\0", 1)[0].decode("ascii", "replace")
        vsize, vaddr, rsize, roff = struct.unpack_from("<IIII", data, off + 8)
        sections.append((name, vaddr, vsize, roff, rsize))
        print(f"  section {name:8s} va=0x{vaddr:x} vs=0x{vsize:x} raw=0x{roff:x}+0x{rsize:x}")

    def rva_to_off(rva: int) -> int | None:
        for name, vaddr, vsize, roff, rsize in sections:
            if vaddr <= rva < vaddr + max(vsize, rsize):
                return roff + (rva - vaddr)
        return None

    def off_to_rva(off: int) -> int | None:
        for name, vaddr, vsize, roff, rsize in sections:
            if roff <= off < roff + rsize:
                return vaddr + (off - roff)
        return None

    # Find string RVAs for discovery messages
    interesting = [
        b"UC Discovery sending query event to %s",
        b"UC Discovery reply to query event to %s",
        b"Adding server via UDP discovery %s : tcp %d udp %d",
        b"Enabled UDP multicast on official port %d",
        b"Server \"%s\" (id = \"%s\") resolved at host \"%s\", tcp %d udp %d",
        b"UCNETLocalDiscoveryRegistry",
    ]
    string_rvas = {}
    for s in interesting:
        off = data.find(s)
        if off < 0:
            print("missing string", s)
            continue
        rva = off_to_rva(off)
        string_rvas[s.decode()] = (off, rva)
        print(f"string {s.decode()!r} file@0x{off:x} rva={hex(rva) if rva else None}")

    # Find LEA/RIP-relative references in .text to these strings (x64)
    text_sec = next((s for s in sections if s[0] == ".text"), None)
    if not text_sec:
        print("no .text")
        return
    _, text_va, text_vs, text_off, text_rs = text_sec
    text = data[text_off : text_off + text_rs]

    def find_xrefs(target_rva: int) -> list[int]:
        """Find RIP-relative LEA/MOV references: 48 8D 0D xx xx xx xx etc."""
        hits = []
        # scan for rel32 that points to target
        for i in range(len(text) - 7):
            # pattern: 48 8D ?? rel32  or 4C 8D ?? rel32 or 48 8B ?? rel32
            b0, b1 = text[i], text[i + 1]
            if b0 in (0x48, 0x4C) and b1 in (0x8D, 0x8B):
                # need ModRM with RIP-relative: mod=00 rm=101 -> ModRM & 0xC7 == 0x05
                modrm = text[i + 2]
                if (modrm & 0xC7) != 0x05:
                    continue
                rel = struct.unpack_from("<i", text, i + 3)[0]
                insn_rva = text_va + i
                next_rva = insn_rva + 7
                dest = next_rva + rel
                if dest == target_rva:
                    hits.append(insn_rva)
        return hits

    for name, (off, rva) in string_rvas.items():
        if rva is None:
            continue
        xrefs = find_xrefs(rva)
        print(f"xrefs to {name!r}: {len(xrefs)} -> {[hex(x) for x in xrefs[:8]]}")
        for xr in xrefs[:3]:
            # dump 64 bytes before xref (likely function body with packet parse)
            foff = rva_to_off(xr - 96)
            if foff is None:
                continue
            blob = data[foff : foff + 160]
            print(f"  context @{hex(xr)}:")
            print("   ", blob.hex())

    # Immediate 0xBAA1 (47809) as 16-bit and 32-bit in .text
    imm16 = struct.pack("<H", 47809)
    imm32 = struct.pack("<I", 47809)
    for label, needle in (("imm16", imm16), ("imm32", imm32)):
        idx = 0
        count = 0
        while True:
            j = text.find(needle, idx)
            if j < 0:
                break
            count += 1
            if count <= 8:
                rva = text_va + j
                ctx = text[max(0, j - 16) : j + 24]
                print(f"{label} @{hex(rva)} ctx={ctx.hex()}")
            idx = j + 1
        print(f"total {label} in .text: {count}")

    # Search whole file for GUID-like discovery struct markers / 'query' event ids
    for pat in [b"query", b"alive", b"leave", b"hello", b"UCXML", b"subscribe"]:
        print(f"count {pat!r}:", data.lower().count(pat.lower()))


if __name__ == "__main__":
    main()
