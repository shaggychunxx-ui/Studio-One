from __future__ import annotations

import binascii
import socket
import ssl
import struct
import time

HOSTS = ["127.0.0.1"]
PORTS = [56721, 49670]


def safe_recv(t: socket.socket, timeout: float = 1.0) -> bytes:
    t.settimeout(timeout)
    try:
        return t.recv(65535)
    except (socket.timeout, ConnectionResetError, ConnectionAbortedError, OSError):
        return b""


def main() -> None:
    for host in HOSTS:
        for port in PORTS:
            print(f"\n=== {host}:{port} ===")
            # 1) connect and wait for server hello
            try:
                t = socket.create_connection((host, port), timeout=1.0)
            except OSError as e:
                print("connect", e)
                continue
            data = safe_recv(t, 2.0)
            print("server-first", len(data), binascii.hexlify(data[:64]).decode() if data else "-")
            t.close()

            # 2) TLS wrap attempt
            try:
                raw = socket.create_connection((host, port), timeout=1.0)
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                ts = ctx.wrap_socket(raw, server_hostname=host)
                print("TLS OK", ts.version())
                ts.send(b"UC\x00\x01")
                print("TLS recv", safe_recv(ts, 1.0)[:40])
                ts.close()
            except Exception as e:
                print("TLS fail", type(e).__name__, e)

            # 3) payloads that shouldn't crash the loop
            payloads = []
            # exact discovery-style query that worked on UDP
            payloads.append(b"UC\x00\x01")
            payloads.append(struct.pack("<I", 0x4451))
            payloads.append(b"UC\x00\x01" + struct.pack("<I", 0x4451))
            # discovery reply mirrored as client announce
            payloads.append(
                b"UC\x00\x01"
                + struct.pack("<H", port)
                + struct.pack("<H", 0x4144)
                + struct.pack("<II", 0x6B, 0)
                + b"s1-remote\x00REMOTE\x00client1\x00AI-CODING\x00"
            )
            # length prefixes 1-8
            body = b"UC\x00\x01"
            for fmt in ("<I", ">I", "<H", ">H"):
                payloads.append(struct.pack(fmt, len(body)) + body)
            # null / empty
            payloads.append(b"")
            payloads.append(b"\x00" * 16)
            # big-endian size 0x24 message
            payloads.append(struct.pack(">I", 0x24) + bytes(0x24))
            payloads.append(struct.pack("<I", 0x24) + bytes(0x24))

            for i, p in enumerate(payloads):
                try:
                    t = socket.create_connection((host, port), timeout=0.8)
                except OSError as e:
                    print("reconnect fail", e)
                    break
                try:
                    if p:
                        t.sendall(p)
                    data = safe_recv(t, 0.8)
                    if data:
                        print(
                            f"HIT#{i} sent={len(p)} got={len(data)} "
                            f"{binascii.hexlify(data[:80]).decode()} {data[:60]!r}"
                        )
                    else:
                        print(f"none#{i} sent={len(p)}")
                except (ConnectionResetError, ConnectionAbortedError, OSError) as e:
                    print(f"reset#{i} sent={len(p)} {e}")
                finally:
                    try:
                        t.close()
                    except Exception:
                        pass


if __name__ == "__main__":
    main()
