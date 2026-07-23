"""Probe Studio One TCP UCNET session port after discovery."""
from __future__ import annotations

import binascii
import socket
import struct
import time

TCP = 56721
HOSTS = ["127.0.0.1", "192.168.1.116", "10.10.10.1"]


def recv_some(t: socket.socket, timeout: float = 1.0) -> bytes:
    t.settimeout(timeout)
    chunks = []
    end = time.time() + timeout
    while time.time() < end:
        try:
            d = t.recv(65535)
            if not d:
                break
            chunks.append(d)
            # if we got something, wait a bit more for more
            end = min(end, time.time() + 0.3)
        except socket.timeout:
            break
    return b"".join(chunks)


def try_payload(host: str, payload: bytes, label: str) -> None:
    try:
        t = socket.create_connection((host, TCP), timeout=1.0)
    except OSError as e:
        print(f"connect fail {host}: {e}")
        return
    # optional: read greeting first
    gre = recv_some(t, 0.3)
    if gre:
        print(f"GREETING {host} {binascii.hexlify(gre[:80]).decode()} {gre[:40]!r}")
    try:
        t.sendall(payload)
    except OSError as e:
        print(f"send fail {label}: {e}")
        t.close()
        return
    data = recv_some(t, 1.2)
    t.close()
    if data:
        print(
            f"HIT {host} {label} sent={len(payload)} got={len(data)} "
            f"{binascii.hexlify(data[:100]).decode()} {data[:80]!r}"
        )
    else:
        print(f"no-reply {host} {label} sent={len(payload)}")


def main() -> None:
    payloads: list[tuple[str, bytes]] = []
    # Discovery-like header
    payloads.append(("UC_ver1", b"UC\x00\x01"))
    payloads.append(("UC_ver1_pad16", b"UC\x00\x01" + bytes(12)))
    # length-prefixed
    for body in (
        b"UC\x00\x01",
        struct.pack("<I", 0x4451),
        b"UCXML",
        b'<?xml version="1.0"?><uc:Hello xmlns:uc="http://www.presonus.com/xml/uc"/>',
        b'<?xml version="1.0"?><Hello/>',
        b"subscribe",
        b"Subscribe",
        b"DAWRemote",
        b"Presonus:DAWRemote",
    ):
        payloads.append((f"raw-{body[:12]!r}", body))
        payloads.append((f"lelen-{body[:12]!r}", struct.pack("<I", len(body)) + body))
        payloads.append((f"belen-{body[:12]!r}", struct.pack(">I", len(body)) + body))
        # UC frame: magic ver + len + body
        payloads.append(
            (
                f"UCfr-{body[:8]!r}",
                b"UC\x00\x01" + struct.pack("<I", len(body)) + body,
            )
        )
        payloads.append(
            (
                f"UCfrBE-{body[:8]!r}",
                b"UC\x00\x01" + struct.pack(">I", len(body)) + body,
            )
        )

    # Mirror discovery reply shape as client hello
    client_hello = (
        b"UC\x00\x01"
        + struct.pack("<H", 0)  # tcp? 
        + b"DA"
        + struct.pack("<I", 0x6b)
        + struct.pack("<I", 0)
        + b"s1-remote\x00"
        + b"REMOTE\x00"
        + b"s1remote-client\x00"
        + b"AI-CODING\x00"
    )
    payloads.append(("client_hello_mirror", client_hello))
    payloads.append(("lelen_hello", struct.pack("<I", len(client_hello)) + client_hello))

    # Event IDs
    for eid in (0x4451, 0x4441, 0x10001, 1, 2):
        p = struct.pack("<I", eid)
        payloads.append((f"eid-{eid:x}", p))
        payloads.append((f"eidlen-{eid:x}", struct.pack("<I", 4) + p))
        payloads.append((f"UCeid-{eid:x}", b"UC\x00\x01" + p))

    host = "127.0.0.1"
    print("probing", host, "port", TCP, "payloads", len(payloads))
    for label, p in payloads:
        try_payload(host, p, label)


if __name__ == "__main__":
    main()
