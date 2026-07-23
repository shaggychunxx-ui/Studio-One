"""
Probe UCNET discovery using event IDs recovered from ucnet.dll disassembly:
  0x4451  ('QD' LE) — query event (cmp eax, 0x4451)
  0x4441  ('AD' LE) — alive/add event (cmp eax, 0x4441)

Also try 36-byte (0x24) structures and port fields at +0x40/+0x42 in larger blobs.
"""
from __future__ import annotations

import binascii
import socket
import struct
import time

PORT = 47809
EVENTS = {
    "QD": 0x4451,
    "AD": 0x4441,
    "LD": 0x444C,  # leave discovery guess
    "QR": 0x5251,
    "OK": 0x4B4F,
}


def hx(b: bytes) -> str:
    return binascii.hexlify(b).decode()


def main() -> None:
    # Shared bind on discovery port if possible
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("", PORT))
        print("bound", PORT)
    except OSError as e:
        print("bind", PORT, e)
        s.bind(("", 0))
        print("ephemeral", s.getsockname())
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    for mcast in ("239.255.255.255", "239.255.0.1"):
        try:
            mreq = struct.pack("=4s4s", socket.inet_aton(mcast), socket.inet_aton("0.0.0.0"))
            s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            print("joined", mcast)
        except OSError as e:
            print("join", mcast, e)
    s.settimeout(0.4)

    probes: list[tuple[str, bytes]] = []

    # Minimal event-id packets (LE and BE, 4 and 8 bytes)
    for name, eid in EVENTS.items():
        for endian in "<>":
            p = struct.pack(f"{endian}I", eid)
            probes.append((f"{name}-{endian}I", p))
            probes.append((f"{name}-{endian}IH0", p + struct.pack(f"{endian}HH", 0, 0)))
            probes.append((f"{name}-{endian}I_ver1", p + struct.pack(f"{endian}HH", 1, 0)))
            # 36-byte body zeros
            body = p + bytes(32)
            probes.append((f"{name}-{endian}-36", body[:36] if len(body) >= 36 else body + bytes(36 - len(body))))
            # size prefix
            probes.append((f"{name}-lenle", struct.pack("<I", 4) + p))
            probes.append((f"{name}-lenbe", struct.pack(">I", 4) + p))

    # FourCC style 'QD\0\0'
    for four in (b"QD\x00\x00", b"AD\x00\x00", b"LD\x00\x00", b"QR\x00\x00", b"UC\x00\x00"):
        probes.append((f"four-{four[:2].decode()}", four))
        probes.append((f"four-{four[:2].decode()}-pad", four + bytes(32)))

    # Structure guess from offsets 0x40/0x42 being ports in server object
    # Maybe on-wire is different; try packing name/id/host/tcp/udp loosely
    name = b"s1-remote-probe\x00"
    sid = b"s1remote\x00"
    host = b"127.0.0.1\x00"
    for eid_name, eid in (("QD", 0x4451), ("AD", 0x4441)):
        # layout A: event, flags, tcp, udp, then cstrings
        pkt = struct.pack("<IHHH", eid, 0, 56721, PORT) + name + sid + host
        probes.append((f"layoutA-{eid_name}", pkt))
        pkt = struct.pack(">IHHH", eid, 0, 56721, PORT) + name + sid + host
        probes.append((f"layoutAbe-{eid_name}", pkt))
        # layout B: event + 0x24 size header
        pkt = struct.pack("<II", eid, 0x24) + bytes(0x24)
        probes.append((f"layoutB-{eid_name}", pkt))
        # layout C: event at start of 0x24 block with ports at end
        blk = bytearray(0x24)
        struct.pack_into("<I", blk, 0, eid)
        struct.pack_into("<H", blk, 0x20, 56721)
        struct.pack_into("<H", blk, 0x22, PORT)
        probes.append((f"layoutC-{eid_name}", bytes(blk)))

    targets = [
        ("127.0.0.1", PORT),
        ("192.168.1.116", PORT),
        ("10.10.10.1", PORT),
        ("255.255.255.255", PORT),
        ("239.255.255.255", PORT),
        ("239.255.0.1", PORT),
        ("192.168.1.255", PORT),
        ("10.10.10.255", PORT),
    ]

    me = s.getsockname()
    print(f"sending {len(probes)} probes from {me}")
    for addr in targets:
        for label, p in probes:
            try:
                s.sendto(p, addr)
            except OSError:
                pass

    # Also try TCP session on 56721 with event IDs length-prefixed
    for host in ("127.0.0.1", "192.168.1.116"):
        for label, p in probes[:40]:
            try:
                t = socket.create_connection((host, 56721), timeout=0.4)
                t.settimeout(0.4)
                # try raw and length-prefixed
                for payload in (p, struct.pack("<I", len(p)) + p, struct.pack(">I", len(p)) + p):
                    try:
                        t.sendall(payload)
                        data = t.recv(8192)
                        if data:
                            print(f"TCP HIT {host} {label} sent={len(payload)} got={len(data)} {hx(data[:64])} {data[:40]!r}")
                    except socket.timeout:
                        pass
                    except OSError:
                        break
                t.close()
            except OSError:
                break

    end = time.time() + 5
    hits = 0
    while time.time() < end:
        try:
            data, addr = s.recvfrom(65535)
        except socket.timeout:
            continue
        # filter loopback of our own probes if from our port
        if addr[1] == me[1] and addr[0] in ("127.0.0.1", "192.168.1.116", "10.10.10.1"):
            # still print if not exact echo of short probes? skip pure echoes
            continue
        hits += 1
        print(f"UDP HIT from {addr} len={len(data)} {hx(data[:80])} {data[:60]!r}")
    print("foreign udp hits", hits)
    s.close()


if __name__ == "__main__":
    main()
