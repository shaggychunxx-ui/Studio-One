"""Low-level MIDI I/O bridge (rtmidi via mido)."""

from __future__ import annotations

import threading
import time
from typing import Callable, Iterable, Optional

import mido


MessageHandler = Callable[[mido.Message], None]


def list_ports() -> dict[str, list[str]]:
    return {
        "inputs": list(mido.get_input_names()),
        "outputs": list(mido.get_output_names()),
    }


def _match_port(names: Iterable[str], preferred: str) -> Optional[str]:
    preferred = (preferred or "").strip()
    if not preferred:
        return None
    names = list(names)
    if preferred in names:
        return preferred
    # Fuzzy: substring match (case-insensitive)
    low = preferred.lower()
    for n in names:
        if low in n.lower() or n.lower() in low:
            return n
    # Prefix without trailing index: "S1 Controller" -> "S1 Controller 1"
    for n in names:
        if n.lower().startswith(low):
            return n
    return None


class MidiBridge:
    """Bidirectional MIDI port pair used by MCU, Control Link, and instrument I/O."""

    def __init__(
        self,
        out_name: str = "",
        in_name: str = "",
        on_message: Optional[MessageHandler] = None,
    ) -> None:
        self.out_name = out_name
        self.in_name = in_name
        self.on_message = on_message
        self._out: Optional[mido.ports.BaseOutput] = None
        self._in: Optional[mido.ports.BaseInput] = None
        self._lock = threading.RLock()
        self._poll_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    @property
    def connected(self) -> bool:
        return self._out is not None and not self._out.closed

    def connect(
        self,
        out_name: Optional[str] = None,
        in_name: Optional[str] = None,
        *,
        open_input: bool = True,
    ) -> None:
        if out_name is not None:
            self.out_name = out_name
        if in_name is not None:
            self.in_name = in_name

        ports = list_ports()
        out = _match_port(ports["outputs"], self.out_name)
        if not out:
            available = ", ".join(ports["outputs"]) or "(none)"
            raise RuntimeError(
                f"MIDI output port not found: {self.out_name!r}. Available: {available}"
            )

        self.disconnect()
        self._out = mido.open_output(out, autoreset=False)
        self.out_name = out

        if not open_input:
            return

        inn = _match_port(ports["inputs"], self.in_name) if self.in_name else None
        if not inn and self.in_name:
            inn = _match_port(ports["inputs"], self.out_name)
        if inn:
            try:
                self._in = mido.open_input(inn)
                self.in_name = inn
                self._stop.clear()
                self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
                self._poll_thread.start()
            except Exception:
                # Feedback port optional — still usable for outbound control.
                self._in = None

    def disconnect(self) -> None:
        self._stop.set()
        thread = self._poll_thread
        self._poll_thread = None
        with self._lock:
            # Close ports first so the poll thread unblocks quickly on Windows.
            if self._in is not None:
                try:
                    self._in.close()
                except Exception:
                    pass
                self._in = None
            if self._out is not None:
                try:
                    self._out.close()
                except Exception:
                    pass
                self._out = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=0.3)

    def send(self, msg: mido.Message) -> None:
        with self._lock:
            if self._out is None or self._out.closed:
                raise RuntimeError("MIDI output not connected")
            self._out.send(msg)

    def send_raw(self, data: list[int] | bytes) -> None:
        data = list(data)
        with self._lock:
            if self._out is None or self._out.closed:
                raise RuntimeError("MIDI output not connected")
            self._out.send(mido.Message.from_bytes(data))

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            try:
                if self._in is None:
                    break
                for msg in self._in.iter_pending():
                    if self.on_message:
                        try:
                            self.on_message(msg)
                        except Exception:
                            pass
            except Exception:
                pass
            time.sleep(0.002)

    def __enter__(self) -> "MidiBridge":
        self.connect()
        return self

    def __exit__(self, *_) -> None:
        self.disconnect()
