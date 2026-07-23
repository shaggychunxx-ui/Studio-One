"""
Legacy UCNET TCP scaffold — thin wrapper around UCSession.

Prefer: from s1remote.ucnet.session import UCSession
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .discovery import UCServer, discover
from .session import UCSession, SessionResult


@dataclass
class SessionInfo:
    """Back-compat shape used by older call sites."""

    server: UCServer
    tcp: Optional[object] = None
    connected: bool = False
    note: str = ""


class UCNetClient:
    """Back-compat facade over UCSession."""

    def __init__(self) -> None:
        self.servers: list[UCServer] = []
        self.session: Optional[SessionInfo] = None
        self._sess = UCSession()

    def discover(self, timeout: float = 2.0, extra_hosts: list[str] | None = None) -> list[UCServer]:
        self.servers = discover(timeout=timeout, extra_hosts=extra_hosts)
        return self.servers

    def connect(self, server: UCServer | None = None, timeout: float = 2.0) -> SessionInfo:
        self._sess.timeout = timeout
        result: SessionResult = self._sess.connect(server)
        if result.server is None:
            raise RuntimeError(result.note or "UCNET connect failed")
        info = SessionInfo(
            server=result.server,
            tcp=self._sess.sock,
            connected=bool(result.ok or self._sess.sock),
            note=result.note,
        )
        self.session = info
        return info

    def close(self) -> None:
        self._sess.close()
        self.session = None

    def __enter__(self) -> "UCNetClient":
        return self

    def __exit__(self, *_) -> None:
        self.close()
