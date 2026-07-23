#!/usr/bin/env python3
import binascii
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from s1remote.ucnet.session import (
    pack_discovery_alive,
    pack_encoded_message,
    pack_extension_query,
    pack_ka,
    pack_param_value_cstr,
    ucxml_subscribe,
    wrap_size,
)


def probe(host: str, port: int) -> None:
    print(f"=== TCP {host}:{port} ===", flush=True)
    try:
        s = socket.create_connection((host, port), timeout=1.5)
    except Exception as e:
        print(" connect fail", e, flush=True)
        return
    s.settimeout(0.7)
    try:
        h = s.recv(4096)
    except Exception:
        h = b""
    print(" hello", len(h), h[:32], flush=True)
    s.close()

    for name, p in [
        ("UC", b"UC\x00\x01"),
        ("DA", pack_discovery_alive()),
        ("KA", pack_ka()),
        ("EQ", pack_extension_query()),
        ("PV", pack_param_value_cstr("transport/start", 1.0)),
        ("EM", pack_encoded_message(ucxml_subscribe("transport"))),
        ("le32DA", wrap_size(pack_discovery_alive(), "<I")),
    ]:
        try:
            s2 = socket.create_connection((host, port), timeout=1.0)
            s2.settimeout(0.6)
            s2.sendall(p)
            try:
                r = s2.recv(4096)
            except Exception:
                r = b""
            hx = binascii.hexlify(r[:40]).decode() if r else "-"
            print(f"  {name}: rx={len(r)} {hx}", flush=True)
            s2.close()
        except Exception as e:
            print(f"  {name}: err {e}", flush=True)


if __name__ == "__main__":
    for port in (49670, 56721, 56883):
        probe("127.0.0.1", port)
