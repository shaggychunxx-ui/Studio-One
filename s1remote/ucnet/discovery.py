"""
UCNET UDP discovery (port 47809).

Reverse-engineered against Studio One 6.6.1 / ucnet.dll:

Query (minimal that elicits a reply when sent to UDP 47809):
  - ``b"UC\\x00\\x01"``  (magic + version 1 BE)
  - and/or little-endian event id ``0x4451`` ('QD')

Reply layout (89+ bytes observed)::

    offset 0-1   magic      'UC'
    offset 2-3   version    uint16 BE (=1)
    offset 4-5   tcp_port   uint16 LE  (session TCP port)
    offset 6-7   class_code uint16 LE  (0x4144 == b'DA' for DAW)
    offset 8-11  flags      uint32 LE  (0x6b observed)
    offset 12-15 reserved   uint32 LE  (0)
    offset 16+   C-strings  name \\0 type \\0 id \\0 hostname \\0

Example name:  ``Studio One/6.6.1.99821 Win x64``
         type:  ``DAW``
         id:    ``joc3krytki7gpvyy.studioapp6``
         host:  ``AI-CODING``

The reply is sourced from an ephemeral UDP port on the DAW host; that
port is retained as ``udp_reply_port`` for further session RE.
"""

from __future__ import annotations

import socket
import struct
import time
from dataclasses import dataclass, field
from typing import Iterable, Optional


from .events import EventType, event_tag_be, pack_uc_header

DISCOVERY_PORT = 47809
QUERY_VERSION = pack_uc_header(1)
# DQ tag alone and with UC header (both accepted by Studio One)
QUERY_EVENT_QD = event_tag_be(EventType.DISCOVERY_QUERY)  # b'DQ'
QUERY_EVENT_QD_PAD = event_tag_be(EventType.DISCOVERY_QUERY) + b"\x00\x00"


@dataclass
class UCServer:
    host: str
    tcp_port: int
    name: str
    type: str
    server_id: str
    hostname: str
    event_type: int = 0  # BE u16 tag at offset 6 (e.g. 0x4441 DA = alive)
    flags: int = 0
    version: int = 1
    udp_reply_port: int = 0
    source_ips: list[str] = field(default_factory=list)
    raw: bytes = b""

    # Back-compat alias
    @property
    def class_code(self) -> int:
        return self.event_type

    @property
    def is_daw(self) -> bool:
        return self.type.upper() == "DAW"

    def endpoint(self) -> str:
        return f"{self.host}:{self.tcp_port}"


def parse_discovery_packet(data: bytes, src_addr: tuple[str, int] | None = None) -> Optional[UCServer]:
    if len(data) < 16 or data[:2] != b"UC":
        return None
    version = struct.unpack_from(">H", data, 2)[0]
    tcp_port = struct.unpack_from("<H", data, 4)[0]
    # offset 6-7 is BE event tag (0x4441 = DA = DiscoveryAlive on beacons)
    event_type = struct.unpack_from(">H", data, 6)[0]
    flags = struct.unpack_from("<I", data, 8)[0]
    # reserved = struct.unpack_from("<I", data, 12)[0]
    strings: list[str] = []
    parts = data[16:].split(b"\x00")
    for p in parts:
        if not p:
            continue
        try:
            s = p.decode("utf-8")
        except UnicodeDecodeError:
            s = p.decode("latin1", errors="replace")
        if s:
            strings.append(s)
    name = strings[0] if len(strings) > 0 else ""
    typ = strings[1] if len(strings) > 1 else ""
    sid = strings[2] if len(strings) > 2 else ""
    hostname = strings[3] if len(strings) > 3 else ""
    host = src_addr[0] if src_addr else hostname
    udp_reply = src_addr[1] if src_addr else 0
    return UCServer(
        host=host,
        tcp_port=tcp_port,
        name=name,
        type=typ,
        server_id=sid,
        hostname=hostname,
        event_type=event_type,
        flags=flags,
        version=version,
        udp_reply_port=udp_reply,
        source_ips=[host] if host else [],
        raw=data,
    )


def _default_targets(extra: Iterable[str] | None = None) -> list[tuple[str, int]]:
    targets = {
        ("127.0.0.1", DISCOVERY_PORT),
        ("255.255.255.255", DISCOVERY_PORT),
        ("239.255.255.255", DISCOVERY_PORT),
        ("239.255.0.1", DISCOVERY_PORT),
    }
    # local hostnames / common interface guesses left to caller via extra
    if extra:
        for h in extra:
            targets.add((h, DISCOVERY_PORT))
    return list(targets)


def _run_discover_pass(
    timeout: float,
    extra_hosts: Iterable[str] | None,
    bind_discovery_port: bool,
) -> dict[str, UCServer]:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    if bind_discovery_port:
        try:
            s.bind(("", DISCOVERY_PORT))
        except OSError:
            s.bind(("", 0))
    else:
        s.bind(("", 0))

    for mcast in ("239.255.255.255", "239.255.0.1"):
        try:
            mreq = struct.pack("=4s4s", socket.inet_aton(mcast), socket.inet_aton("0.0.0.0"))
            s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        except OSError:
            pass

    queries = [
        QUERY_VERSION,
        QUERY_EVENT_QD,
        QUERY_EVENT_QD_PAD,
        QUERY_VERSION + QUERY_EVENT_QD,
        QUERY_VERSION + QUERY_EVENT_QD_PAD,
    ]
    targets = _default_targets(extra_hosts)

    def blast() -> None:
        for addr in targets:
            for q in queries:
                try:
                    s.sendto(q, addr)
                except OSError:
                    pass

    blast()
    s.settimeout(0.2)
    found: dict[str, UCServer] = {}
    end = time.time() + timeout
    last_blast = time.time()
    while time.time() < end:
        # re-query periodically — S1 sometimes only answers the first burst
        if time.time() - last_blast > 0.6:
            blast()
            last_blast = time.time()
        try:
            data, addr = s.recvfrom(65535)
        except socket.timeout:
            continue
        except OSError:
            break
        if len(data) < 20 or data[:2] != b"UC":
            continue
        srv = parse_discovery_packet(data, addr)
        if not srv or not srv.name:
            continue
        # Require a real DAW-like payload (has type or long name)
        if not srv.type and "Studio" not in srv.name and "DAW" not in srv.name:
            continue
        key = srv.server_id or f"{srv.name}:{srv.tcp_port}"
        if key in found:
            existing = found[key]
            if addr[0] not in existing.source_ips:
                existing.source_ips.append(addr[0])
            if existing.host.startswith("127.") and not addr[0].startswith("127."):
                existing.host = addr[0]
            if not existing.udp_reply_port:
                existing.udp_reply_port = addr[1]
        else:
            found[key] = srv
    s.close()
    return found


def discover(
    timeout: float = 2.5,
    extra_hosts: Iterable[str] | None = None,
    bind_discovery_port: bool = True,
) -> list[UCServer]:
    """
    Broadcast/multicast UCNET discovery queries and return unique DAW/servers.

    Tries binding UDP 47809 first (most reliable on Windows with SO_REUSEADDR),
    then falls back to an ephemeral port if needed.
    """
    found = _run_discover_pass(timeout, extra_hosts, bind_discovery_port=True)
    if not found:
        found = _run_discover_pass(timeout, extra_hosts, bind_discovery_port=False)
    return list(found.values())
