"""Probe TCP/UDP with decoded event-type tags."""
from __future__ import annotations

import binascii
import socket
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from s1remote.ucnet.discovery import discover
from s1remote.ucnet.events import EventType, event_tag_be, pack_uc_header


def transact_tcp(host: str, port: int, payload: bytes, wait: float = 1.0) -> bytes:
    try:
        t = socket.create_connection((host, port), timeout=1.2)
    except OSError as e:
        return f"CF:{e}".encode()
    t.settimeout(wait)
    try:
        t.sendall(payload)
        chunks = []
        end = time.time() + wait
        while time.time() < end:
            try:
                d = t.recv(65535)
            except (socket.timeout, OSError):
                break
            if not d:
                break
            chunks.append(d)
            end = min(end, time.time() + 0.3)
        return b"".join(chunks)
    except OSError as e:
        return f"IO:{e}".encode()
    finally:
        try:
            t.close()
        except Exception:
            pass


def main() -> None:
    servers = discover(timeout=2.5)
    if not servers:
        print("no servers")
        return
    s = servers[0]
    host = "127.0.0.1" if any(x.startswith("127.") for x in s.source_ips) else s.host
    print("target", s.name, host, s.tcp_port, "udp", s.udp_reply_port)

    # Build candidate session frames using event IDs
    candidates: list[tuple[str, bytes]] = []

    # 1) Raw event tags
    for et in EventType:
        tag = event_tag_be(et)
        candidates.append((f"tag-{et.name}", tag))
        candidates.append((f"tag0-{et.name}", tag + b"\x00\x00"))
        candidates.append((f"UC-tag-{et.name}", pack_uc_header() + tag))
        candidates.append((f"UC-tag0-{et.name}", pack_uc_header() + tag + b"\x00\x00"))
        # length-prefixed: u32 LE total following
        body = tag + b"\x00\x00"
        candidates.append((f"le32-{et.name}", struct.pack("<I", len(body)) + body))
        candidates.append((f"be32-{et.name}", struct.pack(">I", len(body)) + body))
        # size + event + empty payload (8 byte header)
        candidates.append((f"hdr8-{et.name}", struct.pack(">HH", int(et), 0)))
        candidates.append((f"hdr8le-{et.name}", struct.pack("<HH", int(et), 0)))
        candidates.append((f"UC-hdr8-{et.name}", pack_uc_header() + struct.pack(">HH", int(et), 0)))

    # 2) KeepAlive / Loopback (often session openers)
    for et in (EventType.KEEP_ALIVE, EventType.LOOPBACK_QUERY, EventType.EXTENSION_QUERY):
        for n in range(0, 32, 4):
            body = event_tag_be(et) + bytes(n)
            candidates.append((f"pad-{et.name}-{n}", pack_uc_header() + body))
            candidates.append((f"padle-{et.name}-{n}", struct.pack("<I", len(body)) + body))

    # 3) ParamValue guesses: event + path cstring + float
    path = b"transport/start\x00"
    val = struct.pack("<f", 1.0)
    for et in (EventType.PARAM_VALUE, EventType.PARAM_EDIT, EventType.PARAM_MODE):
        body = event_tag_be(et) + path + val
        candidates.append((f"param-{et.name}", pack_uc_header() + body))
        candidates.append((f"paramle-{et.name}", struct.pack("<I", len(body)) + body))
        # with u16 path len
        body2 = event_tag_be(et) + struct.pack(">H", len(path)) + path + val
        candidates.append((f"param2-{et.name}", pack_uc_header() + body2))
        candidates.append((f"param2le-{et.name}", struct.pack("<I", len(body2)) + body2))

    # 4) Mirror discovery alive as TCP client hello
    alive = (
        pack_uc_header()
        + struct.pack("<H", 0)  # no tcp?
        + event_tag_be(EventType.DISCOVERY_ALIVE)
        + struct.pack("<II", 0x6B, 0)
        + b"s1-remote\x00REMOTE\x00client\x00AI-CODING\x00"
    )
    candidates.append(("alive-mirror", alive))
    candidates.append(("alive-mirror-le", struct.pack("<I", len(alive)) + alive))

    # dedupe
    seen = set()
    uniq = []
    for label, p in candidates:
        if p in seen:
            continue
        seen.add(p)
        uniq.append((label, p))

    print("trying", len(uniq), "frames")
    hits = 0
    for label, p in uniq:
        resp = transact_tcp(host, s.tcp_port, p, wait=0.35)
        if not resp or resp.startswith(b"CF:") or resp.startswith(b"IO:"):
            continue
        hits += 1
        print(
            f"HIT {label} sent={len(p)} got={len(resp)} "
            f"{binascii.hexlify(resp[:48]).decode()} {resp[:40]!r}"
        )
    print("hits", hits)

    # UDP to reply port + discovery port with keepalives
    for dest_port in filter(None, [s.udp_reply_port, 47809]):
        print("UDP", host, dest_port)
        u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        u.settimeout(0.5)
        for et in (
            EventType.KEEP_ALIVE,
            EventType.LOOPBACK_QUERY,
            EventType.PARAM_VALUE,
            EventType.UDP_MAPPING,
            EventType.DISCOVERY_QUERY,
        ):
            for p in (
                event_tag_be(et),
                pack_uc_header() + event_tag_be(et),
                pack_uc_header() + event_tag_be(et) + b"\x00\x00",
            ):
                try:
                    u.sendto(p, (host, dest_port))
                    data, addr = u.recvfrom(65535)
                    print(f"UDP HIT {et.name} from {addr} {data[:60]!r}")
                except socket.timeout:
                    pass
                except OSError as e:
                    print("udp err", e)
                    break
        u.close()


if __name__ == "__main__":
    import binascii

    main()
