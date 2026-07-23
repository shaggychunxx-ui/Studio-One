"""
Passive UCNET sniffer + lightweight active hooks.

1. Binds UDP 47809 (shared) and records all non-discovery-sized traffic.
2. Periodically sends KeepAlive / LoopbackQuery / UDPMapping candidates.
3. Opens TCP and holds it open, logging any server-initiated bytes.

Use while connecting Fender Studio Pro Remote from a phone on the LAN.
"""
from __future__ import annotations

import binascii
import socket
import struct
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from s1remote.ucnet.discovery import DISCOVERY_PORT, discover
from s1remote.ucnet.events import EventType, event_tag_be, pack_uc_header


def hx(b: bytes, n: int = 64) -> str:
    return binascii.hexlify(b[:n]).decode()


def main() -> None:
    duration = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
    servers = discover(timeout=2.0)
    if not servers:
        print("No DAW — is Studio One running with remote discovery enabled?")
        return
    s = servers[0]
    print("DAW", s.name, "tcp", s.tcp_port, "udp_reply", s.udp_reply_port, s.source_ips)

    log_path = Path(__file__).parent / "captures" / f"sniff_{int(time.time())}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("w", encoding="utf-8")

    def logline(msg: str) -> None:
        line = f"{time.time():.3f} {msg}"
        print(line)
        log.write(line + "\n")
        log.flush()

    # UDP listener on discovery port
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    u.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    u.bind(("", DISCOVERY_PORT))
    u.settimeout(0.3)
    for mcast in ("239.255.255.255", "239.255.0.1"):
        try:
            mreq = struct.pack("=4s4s", socket.inet_aton(mcast), socket.inet_aton("0.0.0.0"))
            u.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        except OSError:
            pass

    # second socket for our own UDP session attempts
    u2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    u2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    u2.bind(("", 0))
    u2.settimeout(0.3)
    our_udp = u2.getsockname()[1]
    logline(f"our_udp_port={our_udp}")

    # Hold TCP open
    tcp_host = "127.0.0.1" if any(x.startswith("127.") for x in s.source_ips) else s.host
    tcp_sock = None
    try:
        tcp_sock = socket.create_connection((tcp_host, s.tcp_port), timeout=2.0)
        tcp_sock.settimeout(0.3)
        logline(f"tcp_connected {tcp_host}:{s.tcp_port}")
    except OSError as e:
        logline(f"tcp_fail {e}")

    stop = threading.Event()

    def tcp_reader() -> None:
        if not tcp_sock:
            return
        while not stop.is_set():
            try:
                d = tcp_sock.recv(65535)
            except socket.timeout:
                continue
            except OSError as e:
                logline(f"tcp_err {e}")
                break
            if not d:
                logline("tcp_closed")
                break
            logline(f"TCP_RX len={len(d)} {hx(d)} {d[:40]!r}")

    thr = threading.Thread(target=tcp_reader, daemon=True)
    thr.start()

    end = time.time() + duration
    last_active = 0.0
    while time.time() < end:
        # receive discovery / any UDP
        for sock, name in ((u, "u47809"), (u2, "uours")):
            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                continue
            # classify
            kind = "UDP"
            if len(data) >= 8 and data[:2] == b"UC":
                et = struct.unpack_from(">H", data, 6)[0] if len(data) >= 8 else 0
                kind = f"UC et=0x{et:04X}"
            logline(f"{name}_RX from={addr} len={len(data)} {kind} {hx(data)} {data[:50]!r}")

        # active probes every 2s
        if time.time() - last_active > 2.0:
            last_active = time.time()
            probes = [
                pack_uc_header() + event_tag_be(EventType.KEEP_ALIVE),
                pack_uc_header() + event_tag_be(EventType.LOOPBACK_QUERY) + b"\x00\x00",
                # UDP mapping guess: UM + our port
                pack_uc_header()
                + event_tag_be(EventType.UDP_MAPPING)
                + struct.pack("<H", our_udp)
                + struct.pack("<H", 0),
                pack_uc_header()
                + event_tag_be(EventType.UDP_MAPPING)
                + struct.pack(">H", our_udp),
                event_tag_be(EventType.KEEP_ALIVE) + b"\x00\x00",
            ]
            for dest in {(tcp_host, DISCOVERY_PORT), (tcp_host, s.udp_reply_port or DISCOVERY_PORT)}:
                for p in probes:
                    try:
                        u2.sendto(p, dest)
                    except OSError:
                        pass
            if tcp_sock:
                for p in probes[:3]:
                    try:
                        tcp_sock.sendall(struct.pack(">I", len(p)) + p)
                        tcp_sock.sendall(p)
                    except OSError as e:
                        logline(f"tcp_send_err {e}")
                        break

    stop.set()
    if tcp_sock:
        try:
            tcp_sock.close()
        except Exception:
            pass
    u.close()
    u2.close()
    log.close()
    print("wrote", log_path)


if __name__ == "__main__":
    main()
