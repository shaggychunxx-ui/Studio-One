"""
Session-frame matrix against discovered DAW TCP port.

Tests:
  - length-prefixed bodies (LE/BE u16/u32)
  - UC header + length + body
  - FourCC tags seen in remoteservice (pUCF / UCFP style)
  - UCXML / Subscribe / component paths from DAWRemote model
  - compressed/encrypted flags as string tags
"""
from __future__ import annotations

import binascii
import socket
import struct
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from s1remote.ucnet.discovery import discover  # noqa: E402


def safe_transact(host: str, port: int, payload: bytes, wait: float = 0.8) -> bytes:
    try:
        t = socket.create_connection((host, port), timeout=1.0)
    except OSError as e:
        return f"CONNECT_FAIL:{e}".encode()
    t.settimeout(wait)
    try:
        if payload:
            t.sendall(payload)
        chunks = []
        end = time.time() + wait
        while time.time() < end:
            try:
                d = t.recv(65535)
            except socket.timeout:
                break
            except OSError:
                break
            if not d:
                break
            chunks.append(d)
            end = min(end, time.time() + 0.25)
        return b"".join(chunks)
    except OSError as e:
        return f"IO_FAIL:{e}".encode()
    finally:
        try:
            t.close()
        except Exception:
            pass


def frames() -> list[tuple[str, bytes]]:
    out: list[tuple[str, bytes]] = []

    bodies = [
        b"",
        b"UC\x00\x01",
        b"Subscribe",
        b"subscribe",
        b"UCXML",
        b'<?xml version="1.0"?><uc:Subscribe xmlns:uc="http://www.presonus.com/xml/uc"/>',
        b'<?xml version="1.0"?><uc:Hello xmlns:uc="http://www.presonus.com/xml/uc" namespace="Presonus:DAWRemote"/>',
        b'<?xml version="1.0"?><uc:ComponentModel xmlns:uc="http://www.presonus.com/xml/uc" namespace="Presonus:DAWRemote"/>',
        b'{"cmd":"subscribe","path":"transport"}',
        b"transport/start",
        b"mixer",
        # param path style from SurfaceData
        b"transport\x00start\x00",
        # UC discovery-style client announce
        (
            b"UC\x00\x01"
            + struct.pack("<H", 0)
            + struct.pack("<H", 0x4144)
            + struct.pack("<II", 0x6B, 0)
            + b"s1-remote\x00REMOTE\x00s1remote-client\x00AI-CODING\x00"
        ),
    ]

    fourccs = [
        b"UCFp",
        b"pUCF",
        b"UCFP",
        b"FCUp",
        b"UCXM",
        b"MSG\x00",
        b"SUB\x00",
        b"EVNT",
        b"DATA",
        b"PING",
        b"HELO",
        b"AUTH",
    ]

    for body in bodies:
        out.append((f"raw:{body[:24]!r}", body))
        for name, fmt in (("le32", "<I"), ("be32", ">I"), ("le16", "<H"), ("be16", ">H")):
            try:
                out.append((f"{name}:{body[:16]!r}", struct.pack(fmt, len(body)) + body))
            except struct.error:
                pass
        # UC + ver + len + body
        out.append((f"UCle32:{body[:12]!r}", b"UC\x00\x01" + struct.pack("<I", len(body)) + body))
        out.append((f"UCbe32:{body[:12]!r}", b"UC\x00\x01" + struct.pack(">I", len(body)) + body))
        # size class 0x1000 max from Subscribe code path
        if len(body) < 0x1000:
            out.append((f"sz1000pad:{body[:8]!r}", struct.pack("<I", 0x1000) + body + bytes(0x1000 - len(body))))

    for fc in fourccs:
        for body in (b"", b"\x00\x00\x00\x00", b"Subscribe", b"UC\x00\x01"):
            # fourcc + u32 len + body
            out.append((f"fc-{fc!r}-le", fc + struct.pack("<I", len(body)) + body))
            out.append((f"fc-{fc!r}-be", fc + struct.pack(">I", len(body)) + body))
            # fourcc as u32 LE value + body
            out.append((f"imm-{fc!r}", struct.pack("<I", struct.unpack("<I", fc)[0]) + body))

    # Multi-message: UC hello then subscribe
    out.append(
        (
            "seq-hello-sub",
            b"UC\x00\x01" + struct.pack("<I", 9) + b"Subscribe",
        )
    )
    # 8-byte header: type u32 + len u32
    for typ in (1, 2, 3, 0x4451, 0x4441, 0x46435570):
        body = b"Subscribe"
        out.append((f"type{typ:x}-le", struct.pack("<II", typ, len(body)) + body))
        out.append((f"type{typ:x}-be", struct.pack(">II", typ, len(body)) + body))

    # unique
    seen = set()
    uniq = []
    for label, p in out:
        if p in seen:
            continue
        seen.add(p)
        uniq.append((label, p))
    return uniq


def main() -> None:
    servers = discover(timeout=2.5)
    if not servers:
        print("No DAW discovered")
        return
    s = servers[0]
    host = "127.0.0.1" if any(ip.startswith("127.") for ip in s.source_ips) else s.host
    port = s.tcp_port
    print(f"Target {s.name} {host}:{port}")

    hits = []
    for i, (label, payload) in enumerate(frames()):
        resp = safe_transact(host, port, payload, wait=0.5)
        if not resp:
            continue
        if resp.startswith(b"CONNECT_FAIL") or resp.startswith(b"IO_FAIL"):
            # still log first few failures of each kind
            if i < 5:
                print(label, resp[:80])
            continue
        hits.append((label, payload, resp))
        print(
            f"HIT {label} sent={len(payload)} got={len(resp)} "
            f"{binascii.hexlify(resp[:64]).decode()} {resp[:48]!r}"
        )

    print(f"\nTotal hits: {len(hits)} / frames tried")
    # Also try UDP unicast to discovery reply port
    if s.udp_reply_port:
        print(f"\nUDP session probe -> {host}:{s.udp_reply_port}")
        u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        u.settimeout(0.8)
        for label, payload in frames()[:30]:
            try:
                u.sendto(payload, (host, s.udp_reply_port))
                data, addr = u.recvfrom(65535)
                print(f"UDP HIT {label} from {addr} {data[:60]!r}")
            except socket.timeout:
                pass
            except OSError as e:
                print("UDP err", e)
                break
        u.close()


if __name__ == "__main__":
    main()
