"""
UCNET TCP session client — reverse-engineered scaffold.

Discovery is production-ready. Session framing is under active RE:
  - Event type IDs complete (libucnet.so RTTI)
  - EncodedMessage = 0x4A4D (Li19021)
  - DAW param paths known (dawremote.xml / remoteservice)
  - TCP length framing + Subscribe body still being validated live

When a frame elicits a response, packers below are the candidates to keep.
"""

from __future__ import annotations

import socket
import struct
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .discovery import UCServer, discover
from .events import EventType, event_tag_be, pack_uc_header
from .paths import all_core_paths, channel_paths, transport_paths


@dataclass
class SessionResult:
    ok: bool
    note: str
    server: Optional[UCServer] = None
    hello: bytes = b""
    last_rx: bytes = b""
    probes_hit: list[str] = field(default_factory=list)


def pack_discovery_alive(
    name: str = "s1-remote",
    typ: str = "REMOTE",
    sid: str = "s1remote-re",
    hostname: str = "AI-CODING",
    tcp_port: int = 0,
    flags: int = 0x6B,
) -> bytes:
    """Same layout as Studio One UDP DiscoveryAlive (worked on wire)."""
    body = pack_uc_header(1)
    body += struct.pack("<H", tcp_port & 0xFFFF)
    body += event_tag_be(EventType.DISCOVERY_ALIVE)
    body += struct.pack("<II", flags, 0)
    for s in (name, typ, sid, hostname):
        body += s.encode("utf-8") + b"\x00"
    return body


def pack_ka() -> bytes:
    return pack_uc_header(1) + event_tag_be(EventType.KEEP_ALIVE) + b"\x00\x00"


def pack_loopback(token: int = 1) -> bytes:
    return pack_uc_header(1) + event_tag_be(EventType.LOOPBACK_QUERY) + struct.pack("<I", token)


def pack_extension_query(client: str = "s1-remote") -> bytes:
    return pack_uc_header(1) + event_tag_be(EventType.EXTENSION_QUERY) + b"\x00\x00" + client.encode() + b"\x00"


def pack_udp_mapping(udp_port: int) -> bytes:
    return (
        pack_uc_header(1)
        + event_tag_be(EventType.UDP_MAPPING)
        + struct.pack("<HH", udp_port & 0xFFFF, 0)
    )


def pack_encoded_message(payload: bytes) -> bytes:
    """EncodedMessageEvent (0x4A4D) + u32 LE length + body."""
    return (
        pack_uc_header(1)
        + event_tag_be(EventType.ENCODED_MESSAGE)
        + struct.pack("<I", len(payload))
        + payload
    )


def pack_binary_event(payload: bytes) -> bytes:
    return (
        pack_uc_header(1)
        + event_tag_be(EventType.BINARY)
        + struct.pack("<I", len(payload))
        + payload
    )


def pack_param_value_cstr(path: str, value: float) -> bytes:
    """Guess: PV + path\\0 + float32 LE."""
    return (
        pack_uc_header(1)
        + event_tag_be(EventType.PARAM_VALUE)
        + path.encode("utf-8")
        + b"\x00"
        + struct.pack("<f", float(value))
    )


def pack_param_value_tagged(path: str, value: float) -> bytes:
    """Guess: PV + u32 path_len + path + float64."""
    pb = path.encode("utf-8")
    return (
        pack_uc_header(1)
        + event_tag_be(EventType.PARAM_VALUE)
        + struct.pack("<I", len(pb))
        + pb
        + struct.pack("<d", float(value))
    )


def wrap_size(payload: bytes, fmt: str = "<I", include_self: bool = False) -> bytes:
    n = len(payload) + (struct.calcsize(fmt) if include_self else 0)
    return struct.pack(fmt, n) + payload


def ucxml_subscribe(path: str) -> bytes:
    return f'<uc:Subscribe path="{path}"/>'.encode("utf-8")


def ucxml_set(path: str, value: str) -> bytes:
    return f'<uc:ParamValue path="{path}" value="{value}"/>'.encode("utf-8")


class UCSession:
    def __init__(self, timeout: float = 2.0) -> None:
        self.timeout = timeout
        self.server: Optional[UCServer] = None
        self.sock: Optional[socket.socket] = None
        self.hello = b""
        self.last_rx = b""
        self.hits: list[str] = []

    def discover(self) -> list[UCServer]:
        return discover(timeout=self.timeout, extra_hosts=["127.0.0.1"])

    def connect(self, server: UCServer | None = None) -> SessionResult:
        if server is None:
            servers = self.discover()
            daws = [s for s in servers if s.is_daw]
            if not daws:
                return SessionResult(False, "no DAW via UCNET discovery")
            server = daws[0]
        self.server = server

        host = "127.0.0.1"
        for ip in server.source_ips:
            if ip.startswith("127."):
                host = ip
                break
        else:
            host = server.host

        try:
            self.sock = socket.create_connection((host, server.tcp_port), timeout=self.timeout)
        except OSError as e:
            return SessionResult(False, f"tcp connect failed: {e}", server=server)

        self.sock.settimeout(self.timeout)
        self.hello = self._recv(0.5)
        note = f"tcp connected {host}:{server.tcp_port} hello={len(self.hello)}B"
        if self.hello:
            note += f" hello_hex={self.hello[:24].hex()}"
            self.hits.append("server_hello")

        # Handshake candidates (order matters for logging; all attempted lightly)
        for name, frame in self._handshake_frames(server):
            rx = self._send_recv(frame, wait=0.35)
            if rx:
                self.hits.append(name)
                self.last_rx = rx
                note += f" | HIT {name} +{len(rx)}B"
                break

        ok = bool(self.hits)
        if not ok:
            note += " | no app-layer reply yet (framing still open — see re/re_session_deep.py)"
        return SessionResult(ok, note, server=server, hello=self.hello, last_rx=self.last_rx, probes_hit=list(self.hits))

    def _handshake_frames(self, server: UCServer) -> list[tuple[str, bytes]]:
        da = pack_discovery_alive(tcp_port=0, flags=server.flags or 0x6B)
        ka = pack_ka()
        eq = pack_extension_query()
        um = pack_udp_mapping(server.udp_reply_port or 0)
        sub = pack_encoded_message(ucxml_subscribe("transport"))
        frames = [
            ("DA", da),
            ("KA", ka),
            ("EQ", eq),
            ("UM", um),
            ("EM_sub_transport", sub),
            ("le32_DA", wrap_size(da, "<I")),
            ("be32_DA", wrap_size(da, ">I")),
            ("le32_EM", wrap_size(sub, "<I")),
            ("le32i_DA", wrap_size(da, "<I", include_self=True)),
            ("BO_sub", pack_binary_event(ucxml_subscribe("transport"))),
        ]
        return frames

    def try_set_param(self, path: str, value: float) -> dict[str, Any]:
        """Best-effort ParamValue send (multiple encodings)."""
        if not self.sock:
            return {"ok": False, "error": "not connected"}
        variants = [
            ("pv_cstr_f32", pack_param_value_cstr(path, value)),
            ("pv_len_f64", pack_param_value_tagged(path, value)),
            ("em_xml", pack_encoded_message(ucxml_set(path, str(value)))),
            ("bo_xml", pack_binary_event(ucxml_set(path, str(value)))),
        ]
        tried = []
        for name, frame in variants:
            for wrap in (lambda x: x, lambda x: wrap_size(x, "<I"), lambda x: wrap_size(x, ">I")):
                payload = wrap(frame)
                rx = self._send_recv(payload, wait=0.25)
                tried.append({"enc": name, "sent": len(payload), "rx": len(rx)})
                if rx:
                    return {"ok": True, "enc": name, "rx": len(rx), "path": path, "value": value}
        return {"ok": False, "path": path, "tried": tried}

    def transport_start(self) -> dict:
        return self.try_set_param("transport/start", 1.0)

    def transport_stop(self) -> dict:
        return self.try_set_param("transport/stop", 1.0)

    def channel_mute(self, index: int = 1, state: bool = True) -> dict:
        return self.try_set_param(f"mixer/channel/ch{index}/mute", 1.0 if state else 0.0)

    def channel_volume(self, index: int = 1, linear: float = 1.0) -> dict:
        """Volume range 0..3.1622 linear gain (0 dB ≈ 1.0)."""
        return self.try_set_param(f"mixer/channel/ch{index}/volume", linear)

    def known_paths(self, channels: int = 8) -> list[str]:
        return all_core_paths(channels)

    def close(self) -> None:
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        self.sock = None

    def _send_recv(self, data: bytes, wait: float = 0.4) -> bytes:
        if not self.sock:
            return b""
        try:
            self.sock.sendall(data)
        except OSError:
            return b""
        return self._recv(wait)

    def _recv(self, timeout: float) -> bytes:
        if not self.sock:
            return b""
        self.sock.settimeout(timeout)
        chunks: list[bytes] = []
        try:
            while True:
                d = self.sock.recv(65535)
                if not d:
                    break
                chunks.append(d)
                self.sock.settimeout(0.1)
        except Exception:
            pass
        return b"".join(chunks)

    def __enter__(self) -> "UCSession":
        return self

    def __exit__(self, *_) -> None:
        self.close()
