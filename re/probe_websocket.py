"""Try WebSocket handshake against Studio One UCNET TCP ports."""
from __future__ import annotations

import base64
import hashlib
import os
import socket
import struct
import time

HOSTS = ["127.0.0.1"]
PORTS = [56721, 49670]
PATHS = ["/", "/ucnet", "/uc", "/ws", "/dawremote", "/remote", "/UCNET", "/api"]


def ws_handshake(host: str, port: int, path: str) -> tuple[bool, bytes, socket.socket | None]:
    key = base64.b64encode(os.urandom(16)).decode()
    req = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n"
        f"Sec-WebSocket-Protocol: ucnet, UC, dawremote\r\n"
        f"Origin: http://{host}\r\n"
        f"\r\n"
    ).encode()
    t = socket.create_connection((host, port), timeout=1.5)
    t.settimeout(1.5)
    t.sendall(req)
    data = b""
    try:
        while b"\r\n\r\n" not in data and len(data) < 8192:
            chunk = t.recv(4096)
            if not chunk:
                break
            data += chunk
    except socket.timeout:
        pass
    ok = b"101" in data.split(b"\r\n", 1)[0] if data else False
    return ok, data, t if ok else None


def main() -> None:
    for host in HOSTS:
        for port in PORTS:
            for path in PATHS:
                try:
                    ok, resp, sock = ws_handshake(host, port, path)
                except OSError as e:
                    print(f"{host}:{port}{path} err {e}")
                    continue
                head = resp.split(b"\r\n\r\n", 1)[0][:300] if resp else b""
                print(f"{host}:{port}{path} ok={ok} resp={head!r}")
                if sock:
                    # send a few text/binary frames
                    for payload in (
                        b"UC\x00\x01",
                        b'{"type":"hello"}',
                        b"hello",
                        struct.pack("<I", 0x4451),
                    ):
                        # client frame masked
                        mask = os.urandom(4)
                        plen = len(payload)
                        hdr = bytes([0x81, 0x80 | plen]) + mask  # text, masked
                        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
                        try:
                            sock.sendall(hdr + masked)
                            sock.settimeout(1.0)
                            r = sock.recv(4096)
                            print("  frame reply", r[:80] if r else None)
                        except Exception as e:
                            print("  frame err", e)
                    sock.close()

            # also plain HTTP GET
            try:
                t = socket.create_connection((host, port), timeout=1.0)
                t.sendall(f"GET / HTTP/1.1\r\nHost: {host}\r\n\r\n".encode())
                t.settimeout(1.0)
                r = t.recv(2048)
                print(f"HTTP {host}:{port}", r[:200] if r else None)
                t.close()
            except Exception as e:
                print(f"HTTP {host}:{port} err", e)


if __name__ == "__main__":
    main()
