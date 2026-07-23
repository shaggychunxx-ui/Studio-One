"""Passive + active UCNET discovery probe."""
from __future__ import annotations

import binascii
import socket
import struct
import sys
import time
from typing import Iterable


PORT = 47809
MULTICASTS = [
    "239.255.255.255",
    "239.255.0.1",
    "239.192.152.143",
    "224.0.0.1",
    "224.0.0.251",
]


def hx(b: bytes, n: int = 96) -> str:
    return binascii.hexlify(b[:n]).decode()


def build_probes() -> list[bytes]:
    probes: list[bytes] = []
    # length-prefixed variants
    payloads = [
        b"",
        b"\x00",
        b"\x01",
        b"\x00\x00\x00\x00",
        b"QUERY",
        b"query",
        b"DISCOVER",
        b"UC",
        b"UCNET",
        b"DAWR",
        b"DAWREMOTE",
        b"PSUC",
        b"\x01\x00\x00\x00",
        b"\x00\x00\x00\x01",
        struct.pack("<I", 1),
        struct.pack(">I", 1),
        # possible TLV: type,len,value
        struct.pack("<HH", 1, 0),
        struct.pack(">HH", 1, 0),
        struct.pack("<BBH", 1, 0, 0),
        # XML hello
        b'<?xml version="1.0"?><uc:Query xmlns:uc="http://www.presonus.com/xml/uc"/>',
        b'<?xml version="1.0"?><uc:Discovery xmlns:uc="http://www.presonus.com/xml/uc"/>',
        b"<Query/>",
        b"<Hello/>",
    ]
    for p in payloads:
        probes.append(p)
        probes.append(struct.pack("<I", len(p)) + p)
        probes.append(struct.pack(">I", len(p)) + p)
        # 8-byte header guess: magic + version + type + flags
        for magic in (0x55434E54, 0x54454E55, 0x50535543, 0x43555350, 0x5543_0001):
            try:
                probes.append(struct.pack("<IHH", magic & 0xFFFFFFFF, 1, 0) + p)
                probes.append(struct.pack(">IHH", magic & 0xFFFFFFFF, 1, 0) + p)
            except Exception:
                pass
    # unique
    uniq = []
    seen = set()
    for p in probes:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def listen_multicast(seconds: float = 4.0) -> list[tuple]:
    results = []
    socks = []
    for mcast in MULTICASTS:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("", PORT))
        except OSError as e:
            # Studio One may own the port exclusively on Windows
            print(f"bind {PORT} failed ({e}); binding ephemeral and joining mcast {mcast}")
            s.bind(("", 0))
        try:
            mreq = struct.pack("=4s4s", socket.inet_aton(mcast), socket.inet_aton("0.0.0.0"))
            s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        except OSError as e:
            print("mcast join", mcast, e)
        s.settimeout(0.25)
        socks.append((mcast, s))

    # also plain unicast listener on ephemeral
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    u.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    u.bind(("", 0))
    u.settimeout(0.25)
    local = u.getsockname()
    print("ephemeral", local)
    socks.append(("unicast", u))

    probes = build_probes()
    targets = [
        ("127.0.0.1", PORT),
        ("255.255.255.255", PORT),
    ]
    # local interfaces
    for host in ("192.168.1.116", "10.10.10.1", "192.168.1.255", "10.10.10.255"):
        targets.append((host, PORT))
    for mcast in MULTICASTS:
        targets.append((mcast, PORT))

    u.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    print(f"sending {len(probes)} probes x {len(targets)} targets...")
    for addr in targets:
        for p in probes:
            try:
                u.sendto(p, addr)
            except OSError:
                pass

    end = time.time() + seconds
    while time.time() < end:
        for name, s in socks:
            try:
                data, addr = s.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                continue
            entry = (name, addr, data)
            results.append(entry)
            print(f"RX via={name} from={addr} len={len(data)} hex={hx(data)} ascii={data[:80]!r}")
    for _, s in socks:
        s.close()
    print("total packets", len(results))
    return results


def tcp_banner(hosts: Iterable[str], ports: Iterable[int]) -> None:
    for host in hosts:
        for port in ports:
            try:
                t = socket.create_connection((host, port), timeout=0.8)
            except OSError as e:
                print(f"TCP {host}:{port} closed ({e})")
                continue
            t.settimeout(0.8)
            # read any greeting
            try:
                data = t.recv(4096)
                print(f"TCP {host}:{port} greeting len={len(data)} {hx(data)} {data[:80]!r}")
            except socket.timeout:
                print(f"TCP {host}:{port} connected, no greeting")
            for p in build_probes()[:30]:
                try:
                    t2 = socket.create_connection((host, port), timeout=0.5)
                    t2.settimeout(0.4)
                    t2.sendall(p)
                    try:
                        data = t2.recv(8192)
                        if data:
                            print(
                                f"TCP {host}:{port} sent {len(p)} got {len(data)} "
                                f"{hx(data)} {data[:64]!r}"
                            )
                            t2.close()
                            break
                    except socket.timeout:
                        pass
                    t2.close()
                except OSError:
                    break
            t.close()


if __name__ == "__main__":
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
    print("=== TCP banners ===")
    tcp_banner(["127.0.0.1", "192.168.1.116", "10.10.10.1"], [56721, 49670, 56883])
    print("=== UDP discovery ===")
    listen_multicast(secs)
