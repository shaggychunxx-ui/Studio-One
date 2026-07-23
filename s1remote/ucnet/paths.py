"""
DAWRemote object paths reverse-engineered from remoteservice / dawremote.xml.

These are the hierarchical parameter addresses a session client would
Subscribe / ParamValue against once TCP framing is complete.
"""

from __future__ import annotations

from typing import Iterable, List


def transport_paths() -> List[str]:
    return [
        "transport/start",
        "transport/stop",
        "transport/record",
        "transport/returnToZero",
        "transport/fastForward",
        "transport/rewind",
        "transport/loop",
        "transport/punch",
        "transport/preroll",
        "transport/precount",
        "transport/tempo",
        "transport/timeSignatureNum",
        "transport/timeSignatureDenom",
        "metronome/clickOn",
    ]


def channel_paths(group: str = "channel", index: int = 1) -> List[str]:
    base = f"mixer/{group}/ch{index}"
    return [
        f"{base}/volume",
        f"{base}/pan",
        f"{base}/mute",
        f"{base}/solo",
        f"{base}/selected",
        f"{base}/recordArmed",
        f"{base}/monitor",
        f"{base}/label",
        f"{base}/color",
        f"{base}/automationMode",
        f"{base}/edit",
    ]


def mixer_bank_paths(n: int = 32) -> List[str]:
    out = ["mixer/anySolo", "mixer/anyMute", "mixer/focus/path"]
    for i in range(1, n + 1):
        out.extend(channel_paths("channel", i))
    return out


def surface_control_paths(n: int = 28) -> List[str]:
    """Generic remote knobs c0.. / p0.. (Control Link surface)."""
    out = []
    for i in range(n):
        out.append(f"controls/c{i}/value")
        out.append(f"controls/c{i}/title")
    for i in range(min(n, 25)):
        out.append(f"controls/p{i}/value")
    return out


def insert_paths(ch: int = 1, slots: int = 8) -> List[str]:
    out = []
    for s in range(1, slots + 1):
        base = f"mixer/channel/ch{ch}/inserts/slot{s}"
        out.extend(
            [
                f"{base}/bypass",
                f"{base}/edit",
                f"{base}/name",
            ]
        )
    return out


def all_core_paths(channels: int = 16) -> List[str]:
    paths = transport_paths()
    paths.extend(mixer_bank_paths(channels))
    paths.extend(surface_control_paths())
    paths.extend(insert_paths(1))
    paths.append("document/title")
    return paths


def plugin_surface_path(device_guid: str, param: str) -> str:
    """
    Stock plugin remote mapping key style from SurfaceData:
      {GUID}/param.name
    """
    g = device_guid.strip()
    if not g.startswith("{"):
        g = "{" + g + "}"
    return f"{g}/{param}"
