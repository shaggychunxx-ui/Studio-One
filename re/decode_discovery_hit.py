"""Isolate which query elicits the UC discovery reply and fully decode it."""
from __future__ import annotations

import binascii
import socket
import struct
import time

PORT = 47809


def parse_packet(data: bytes) -> dict:
    info: dict = {"raw_len": len(data), "hex": binascii.hexlify(data).decode()}
    if len(data) < 8 or data[:2] != b"UC":
        info["error"] = "not UC packet"
        return info
    info["magic"] = data[:2].decode()
    info["ver_be"] = struct.unpack_from(">H", data, 2)[0]
    info["ver_le"] = struct.unpack_from("<H", data, 2)[0]
    info["u16_4_le"] = struct.unpack_from("<H", data, 4)[0]
    info["u16_4_be"] = struct.unpack_from(">H", data, 4)[0]
    info["u16_6_le"] = struct.unpack_from("<H", data, 6)[0]
    info["u16_6_be"] = struct.unpack_from(">H", data, 6)[0]
    info["u32_6_le"] = struct.unpack_from("<I", data, 6)[0] if len(data) >= 10 else None
    info["u32_8_le"] = struct.unpack_from("<I", data, 8)[0] if len(data) >= 12 else None
    info["bytes_6_16"] = binascii.hexlify(data[6:16]).decode()
    # strings from first nul-run region
    # find first printable cstring after header
    rest = data[8:]
    # try start at 12 and 16
    for start in (8, 10, 12, 14, 16):
        parts = data[start:].split(b"\x00")
        strings = [p.decode("utf-8", "replace") for p in parts if p and all(32 <= c < 127 for c in p)]
        if strings:
            info[f"strings_from_{start}"] = strings
    return info


def try_query(query: bytes, label: str) -> list[bytes]:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("", 0))
    s.settimeout(0.5)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    for mcast in ("239.255.255.255", "239.255.0.1"):
        try:
            mreq = struct.pack("=4s4s", socket.inet_aton(mcast), socket.inet_aton("0.0.0.0"))
            s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        except OSError:
            pass
    targets = [
        ("127.0.0.1", PORT),
        ("192.168.1.116", PORT),
        ("10.10.10.1", PORT),
        ("255.255.255.255", PORT),
        ("239.255.255.255", PORT),
        ("192.168.1.255", PORT),
    ]
    for t in targets:
        try:
            s.sendto(query, t)
        except OSError:
            pass
    hits = []
    end = time.time() + 1.2
    while time.time() < end:
        try:
            data, addr = s.recvfrom(65535)
        except socket.timeout:
            continue
        if data[:2] == b"UC" and len(data) > 20:
            hits.append(data)
            print(f"  HIT {label} from {addr} len={len(data)}")
    s.close()
    return hits


def main() -> None:
    candidates = []
    # Minimal guesses
    candidates.append(("UC_ver1", b"UC\x00\x01"))
    candidates.append(("UC_ver1le", b"UC\x01\x00"))
    candidates.append(("UC_ver1_pad", b"UC\x00\x01" + bytes(12)))
    candidates.append(("QD_le", struct.pack("<I", 0x4451)))
    candidates.append(("QD_le_pad", struct.pack("<I", 0x4451) + bytes(32)))
    candidates.append(("UC_QD", b"UC\x00\x01" + struct.pack("<I", 0x4451)))
    candidates.append(("UC_QD_be", b"UC\x00\x01" + struct.pack(">I", 0x4451)))
    candidates.append(("empty", b""))
    candidates.append(("zero4", b"\x00\x00\x00\x00"))
    # fourcc query
    candidates.append(("QDxx", b"QD\x00\x00"))
    candidates.append(("UCQDxx", b"UC\x00\x01QD\x00\x00"))
    # size 0x24 query body
    body = bytearray(0x24)
    struct.pack_into("<I", body, 0, 0x4451)
    candidates.append(("body24_QD", b"UC\x00\x01" + bytes(body)))
    candidates.append(("body24_only", bytes(body)))
    # from earlier working mix — UC\x00\x01 header variants with ports
    candidates.append(("UC_ports", b"UC\x00\x01" + struct.pack("<HH", 0, PORT)))
    candidates.append(("UC_query_flag", b"UC\x00\x01\x00\x00\x00\x00\x01\x00"))
    # event after UC header
    for eid in (0x4451, 0x4441, 1, 2, 0):
        candidates.append((f"UC+eid{eid:x}", b"UC\x00\x01" + struct.pack("<I", eid)))
        candidates.append((f"UC+eid{eid:x}pad", b"UC\x00\x01" + struct.pack("<I", eid) + bytes(28)))

    seen_payloads = set()
    for label, q in candidates:
        hits = try_query(q, label)
        for h in hits:
            if h not in seen_payloads:
                seen_payloads.add(h)
                print("NEW PACKET", label)
                print(parse_packet(h))
                print("FULL", binascii.hexlify(h).decode())

    if not seen_payloads:
        print("No hits — try broadcast flood of QD only on bound 47809")
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("", PORT))
        s.settimeout(1.0)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for q in (struct.pack("<I", 0x4451), b"UC\x00\x01", b"UC\x00\x01" + struct.pack("<I", 0x4451)):
            for t in (("255.255.255.255", PORT), ("127.0.0.1", PORT), ("239.255.255.255", PORT)):
                s.sendto(q, t)
        end = time.time() + 3
        while time.time() < end:
            try:
                data, addr = s.recvfrom(65535)
            except socket.timeout:
                continue
            if data[:2] == b"UC" and len(data) > 20:
                print("bound-hit", addr, parse_packet(data))
                print(binascii.hexlify(data).decode())
        s.close()


if __name__ == "__main__":
    main()
