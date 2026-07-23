#!/usr/bin/env python3
"""
Deep reverse-engineering pass for UCNET session framing.

Runs static extraction + live probes against Studio One discovery TCP port.
Writes findings to re/extracted/session_re_report.json
"""
from __future__ import annotations

import binascii
import json
import re
import socket
import struct
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "extracted"
OUT.mkdir(exist_ok=True)

LIBUCNET = ROOT / "apk" / "ucremote_libs" / "lib_arm64-v8a_libucnet.so"
UCNET_DLL = Path(r"C:\Program Files\PreSonus\Studio One 6\ucnet.dll")
REMOTE_DLL = Path(r"C:\Program Files\PreSonus\Studio One 6\Plugins\remoteservice.dll")


def extract_event_ids(data: bytes) -> list[dict]:
    ids = re.findall(rb"(?:Primitive|Data)EventClass(?:NoMembers)?INS0_([A-Za-z0-9]+)ELi(\d+)EEE", data)
    out = {}
    for name, num in ids:
        n = int(num)
        out[n] = {
            "id": n,
            "hex": f"0x{n:04X}",
            "tag_be": bytes([(n >> 8) & 0xFF, n & 0xFF]).decode("latin1", "replace"),
            "name": name.decode(),
        }
    return sorted(out.values(), key=lambda x: x["id"])


def extract_strings(path: Path, keys: list[str]) -> list[str]:
    if not path.exists():
        return []
    data = path.read_bytes()
    strs = re.findall(rb"[\x20-\x7e]{6,160}", data)
    out = []
    for s in strs:
        t = s.decode("latin1", "replace")
        tl = t.lower()
        if any(k.lower() in tl for k in keys):
            if t not in out:
                out.append(t)
    return out


def discover_local(timeout: float = 2.5) -> list[dict]:
    from s1remote.ucnet.discovery import discover

    servers = discover(timeout=timeout, extra_hosts=["127.0.0.1"])
    return [
        {
            "name": s.name,
            "host": s.host,
            "tcp_port": s.tcp_port,
            "udp_reply_port": s.udp_reply_port,
            "id": s.server_id,
            "flags": s.flags,
            "endpoint": s.endpoint(),
            "source_ips": s.source_ips,
        }
        for s in servers
    ]


def pack_discovery_alive(tcp_port: int = 0, flags: int = 0x6B) -> bytes:
    body = b"UC" + struct.pack(">H", 1)
    body += struct.pack("<H", tcp_port)
    body += struct.pack(">H", 0x4441)  # DA
    body += struct.pack("<II", flags, 0)
    body += b"s1-remote\x00REMOTE\x00s1remote-re\x00AI-CODING\x00"
    return body


def pack_event_uc(tag: bytes, payload: bytes = b"") -> bytes:
    return b"UC" + struct.pack(">H", 1) + tag + payload


def recv_some(sock: socket.socket, timeout: float = 0.8) -> bytes:
    sock.settimeout(timeout)
    chunks: list[bytes] = []
    try:
        while True:
            d = sock.recv(65535)
            if not d:
                break
            chunks.append(d)
            sock.settimeout(0.12)
    except Exception:
        pass
    return b"".join(chunks)


def probe_tcp(host: str, port: int) -> list[dict]:
    results = []
    payloads: list[tuple[str, bytes]] = []

    da = pack_discovery_alive(0)
    ka = pack_event_uc(b"KA", b"\x00\x00")
    lq = pack_event_uc(b"LQ", struct.pack("<I", 1))
    eq = pack_event_uc(b"EQ", b"\x00\x00s1-remote\x00")
    um = pack_event_uc(b"UM", struct.pack("<HH", 53044, 0))
    # EncodedMessage tag JM? 19021=0x4A4D
    em_tag = struct.pack(">H", 19021)
    xml = b'<uc:Subscribe path="transport"/>'
    em = b"UC" + struct.pack(">H", 1) + em_tag + struct.pack("<I", len(xml)) + xml
    # ParamValue guess: path cstr + float
    pv = pack_event_uc(
        b"PV",
        b"transport/start\x00" + struct.pack("<f", 1.0),
    )
    pv2 = pack_event_uc(
        b"PV",
        struct.pack("<I", 1) + b"transport.start\x00" + struct.pack("<d", 1.0),
    )
    # BO binary blob
    bo = pack_event_uc(b"BO", struct.pack("<I", len(xml)) + xml)

    payloads += [
        ("empty", b""),
        ("UC_ver", b"UC\x00\x01"),
        ("DA_announce", da),
        ("KA", ka),
        ("LQ", lq),
        ("EQ", eq),
        ("UM", um),
        ("EM_xml", em),
        ("PV_start", pv),
        ("PV_start2", pv2),
        ("BO_xml", bo),
        ("xml_raw", xml),
    ]
    for fmt, label in [("<I", "le32"), (">I", "be32"), ("<H", "le16"), (">H", "be16")]:
        payloads.append((f"{label}_DA", struct.pack(fmt, len(da)) + da))
        payloads.append((f"{label}_KA", struct.pack(fmt, len(ka)) + ka))
        payloads.append((f"{label}_EM", struct.pack(fmt, len(em)) + em))
        # size includes prefix
        payloads.append((f"{label}i_DA", struct.pack(fmt, len(da) + struct.calcsize(fmt)) + da))

    for name, payload in payloads:
        entry = {"name": name, "sent": len(payload), "hello": 0, "resp": 0, "hex": "", "error": ""}
        try:
            sock = socket.create_connection((host, port), timeout=1.5)
        except OSError as e:
            entry["error"] = f"connect:{e}"
            results.append(entry)
            continue
        try:
            hello = recv_some(sock, 0.4)
            entry["hello"] = len(hello)
            if hello:
                entry["hello_hex"] = binascii.hexlify(hello[:48]).decode()
            if payload:
                sock.sendall(payload)
            resp = recv_some(sock, 0.7)
            entry["resp"] = len(resp)
            if resp:
                entry["hex"] = binascii.hexlify(resp[:80]).decode()
                entry["ascii"] = "".join(chr(b) if 32 <= b < 127 else "." for b in resp[:60])
        except Exception as e:
            entry["error"] = str(e)
        finally:
            try:
                sock.close()
            except Exception:
                pass
        results.append(entry)
        print(
            f"  {name:16} hello={entry['hello']:4} resp={entry['resp']:4} "
            f"{entry.get('hex','')[:40]} {entry.get('error','')}",
            flush=True,
        )
    return results


def probe_udp_reply(host: str, udp_port: int) -> list[dict]:
    """Send events to discovery reply UDP port (may accept UM / KA)."""
    results = []
    if not udp_port:
        return results
    payloads = [
        ("UC", b"UC\x00\x01"),
        ("KA", pack_event_uc(b"KA", b"\x00\x00")),
        ("UM", pack_event_uc(b"UM", struct.pack("<HH", udp_port, 0))),
        ("DA", pack_discovery_alive(0)),
    ]
    for name, payload in payloads:
        entry = {"name": name, "resp": 0, "hex": "", "error": ""}
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.8)
            s.sendto(payload, (host, udp_port))
            try:
                data, _ = s.recvfrom(65535)
                entry["resp"] = len(data)
                entry["hex"] = binascii.hexlify(data[:64]).decode()
            except socket.timeout:
                pass
            s.close()
        except Exception as e:
            entry["error"] = str(e)
        results.append(entry)
        print(f"  UDP {name}: resp={entry['resp']} {entry.get('hex','')[:40]}", flush=True)
    return results


def list_file_mappings() -> list[str]:
    """Best-effort: strings that look like mapping object names near CreateFileMapping."""
    names = []
    for p in (UCNET_DLL, REMOTE_DLL):
        if not p.exists():
            continue
        data = p.read_bytes()
        for m in re.finditer(rb"[\x20-\x7e]{4,64}", data):
            t = m.group().decode("latin1")
            if any(k in t for k in ("UCNET", "UCNet", "RemoteSession", "LocalDiscovery", "Shared")):
                if t not in names:
                    names.append(t)
    return names


def build_daw_paths() -> list[str]:
    """Canonical DAWRemote param paths from component model."""
    paths = [
        "transport/start",
        "transport/stop",
        "transport/record",
        "transport/loop",
        "transport/tempo",
        "transport/returnToZero",
        "metronome/clickOn",
        "mixer/anySolo",
        "mixer/anyMute",
        "mixer/focus/path",
        "document/title",
    ]
    for i in range(1, 17):
        base = f"mixer/channel/ch{i}"
        for p in ("volume", "mute", "solo", "pan", "selected", "recordArmed", "monitor", "label"):
            paths.append(f"{base}/{p}")
    for i in range(0, 16):
        paths.append(f"controls/c{i}/value")
        paths.append(f"surface/c{i}/value")
    return paths


def main() -> int:
    report: dict = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "static": {}, "live": {}}

    print("=== Static: event IDs from libucnet.so ===", flush=True)
    if LIBUCNET.exists():
        events = extract_event_ids(LIBUCNET.read_bytes())
        report["static"]["events"] = events
        print(f"  {len(events)} event classes")
        for e in events:
            print(f"    {e['hex']} '{e['tag_be']}' {e['name']}")
    else:
        print("  libucnet.so missing")

    print("=== Static: interesting strings ===", flush=True)
    report["static"]["ucnet_dll"] = extract_strings(
        UCNET_DLL, ["UDP", "TCP", "Event", "map", "Subscribe", "File", "socket"]
    )
    report["static"]["remoteservice"] = extract_strings(
        REMOTE_DLL, ["Subscribe", "UCXML", "Remote", "param", "Session", "compressed"]
    )[:80]
    report["static"]["mapping_candidates"] = list_file_mappings()
    print(f"  mapping candidates: {report['static']['mapping_candidates'][:12]}")

    print("=== DAWRemote param paths ===", flush=True)
    paths = build_daw_paths()
    report["static"]["daw_paths_sample"] = paths
    (OUT / "daw_param_paths.json").write_text(json.dumps(paths, indent=2), encoding="utf-8")
    print(f"  {len(paths)} paths written")

    print("=== Live discovery ===", flush=True)
    try:
        servers = discover_local(3.0)
    except Exception as e:
        servers = []
        report["live"]["discover_error"] = str(e)
        print("  discover error", e)
    report["live"]["servers"] = servers
    print(f"  servers: {servers}")

    if servers:
        # Prefer loopback
        host = "127.0.0.1"
        port = servers[0]["tcp_port"]
        for s in servers:
            if "127.0.0.1" in (s.get("source_ips") or []) or s.get("host", "").startswith("127."):
                host = "127.0.0.1"
                port = s["tcp_port"]
                break
            host = s["host"]
            port = s["tcp_port"]

        print(f"=== Live TCP probes {host}:{port} ===", flush=True)
        report["live"]["tcp_probes"] = probe_tcp(host, port)

        udp = servers[0].get("udp_reply_port") or 0
        print(f"=== Live UDP reply port {host}:{udp} ===", flush=True)
        report["live"]["udp_probes"] = probe_udp_reply(host, int(udp))

        # Hits only
        hits = [p for p in report["live"]["tcp_probes"] if p.get("resp", 0) > 0 or p.get("hello", 0) > 0]
        report["live"]["tcp_hits"] = hits
        print(f"  TCP hello/resp non-zero: {len(hits)}")
    else:
        print("  No DAW found — enable Options → Network → remote control apps")

    path = OUT / "session_re_report.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nWrote {path}", flush=True)

    # Update protocol status snippet
    status = {
        "discovery": "working",
        "event_ids": "complete_from_libucnet_RTTI",
        "encoded_message_id": 19021,
        "encoded_message_hex": "0x4A4D",
        "daw_param_paths": len(paths),
        "tcp_session_framing": "probed_see_report",
        "shared_memory": "CreateFileMapping present; object name not yet recovered",
        "next": [
            "Capture official Remote app traffic (passive_session_sniff + phone)",
            "Continue EM/BO length framing against hello-bearing connections",
            "Map PV body: path encoding + float/double + tags",
        ],
    }
    (OUT / "session_re_status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
