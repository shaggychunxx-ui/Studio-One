"""
Named Studio One 6 UI regions as fractions of the *client* rectangle.

These are Song-page chrome targets, not blind knob hunts. Rec / Monitor
columns reuse the 1920-wide calibration from tools/s1_tools/eyes.py
(REC_X_FRAC / MONITOR_X_FRAC) so arm clicks stay on Rec, not Monitor.

Fractions: (left, top, right, bottom) in 0..1 of client width/height.
Click uses the box center unless a named point is given.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

# Rec Enable column (not Monitor) — 1920 calibration, scaled to window.
REC_X_FRAC = (605 / 1920.0, 655 / 1920.0)
MONITOR_X_FRAC = 660 / 1920.0

# (left, top, right, bottom) client fractions
REGIONS: Dict[str, Tuple[float, float, float, float]] = {
    # Pages (top-left tab strip)
    "page.start": (0.010, 0.008, 0.070, 0.048),
    "page.song": (0.070, 0.008, 0.130, 0.048),
    "page.project": (0.130, 0.008, 0.200, 0.048),
    "page.show": (0.200, 0.008, 0.265, 0.048),
    "menu.bar": (0.000, 0.000, 0.450, 0.030),
    "toolbar": (0.000, 0.045, 1.000, 0.095),
    "control_link": (0.620, 0.048, 0.720, 0.092),
    # Song chrome
    "inspector": (0.000, 0.100, 0.175, 0.880),
    "track_list": (0.000, 0.120, 0.310, 0.880),
    "rec_column": (REC_X_FRAC[0], 0.140, REC_X_FRAC[1], 0.820),
    "monitor_column": (MONITOR_X_FRAC, 0.140, MONITOR_X_FRAC + 0.018, 0.820),
    "mute_column": (0.270, 0.140, 0.295, 0.820),
    "solo_column": (0.295, 0.140, 0.315, 0.820),
    "arrange": (0.345, 0.125, 0.780, 0.880),
    "arrange.blank": (0.520, 0.450, 0.760, 0.820),
    "timeline": (0.345, 0.095, 0.780, 0.125),
    "arranger_track": (0.345, 0.095, 0.780, 0.118),
    "browser": (0.780, 0.095, 1.000, 0.900),
    "browser.search": (0.800, 0.105, 0.985, 0.145),
    "browser.result": (0.810, 0.175, 0.975, 0.255),
    "browser.instruments": (0.790, 0.095, 0.840, 0.130),
    "browser.effects": (0.840, 0.095, 0.890, 0.130),
    "editor": (0.220, 0.540, 0.780, 0.880),
    "console": (0.000, 0.540, 1.000, 0.900),
    "console.channel0": (0.040, 0.560, 0.110, 0.880),
    "transport": (0.000, 0.900, 1.000, 1.000),
    "transport.rewind": (0.270, 0.915, 0.310, 0.985),
    "transport.stop": (0.310, 0.915, 0.350, 0.985),
    "transport.play": (0.350, 0.915, 0.400, 0.985),
    "transport.record": (0.400, 0.915, 0.450, 0.985),
    "transport.loop": (0.450, 0.915, 0.490, 0.985),
    "transport.metronome": (0.490, 0.915, 0.535, 0.985),
    "start.new": (0.040, 0.280, 0.160, 0.340),
    "start.open": (0.040, 0.350, 0.160, 0.410),
    "dialog.ok": (0.55, 0.62, 0.72, 0.72),
    "dialog.cancel": (0.38, 0.62, 0.54, 0.72),
}


def list_regions(q: str = "") -> List[str]:
    q = (q or "").lower().strip()
    names = sorted(REGIONS)
    if not q:
        return names
    return [n for n in names if q in n]


def region_box(name: str) -> Tuple[float, float, float, float]:
    if name not in REGIONS:
        raise KeyError(f"Unknown region {name!r}. Known: {', '.join(list_regions())}")
    return REGIONS[name]


def box_center(box: Tuple[float, float, float, float]) -> Tuple[float, float]:
    l, t, r, b = box
    return (l + r) / 2.0, (t + b) / 2.0


def client_to_screen(
    fx: float,
    fy: float,
    *,
    client_left: int,
    client_top: int,
    client_width: int,
    client_height: int,
) -> Tuple[int, int]:
    x = int(round(client_left + fx * client_width))
    y = int(round(client_top + fy * client_height))
    return x, y


def region_screen_rect(
    name: str,
    *,
    client_left: int,
    client_top: int,
    client_width: int,
    client_height: int,
) -> Tuple[int, int, int, int]:
    l, t, r, b = region_box(name)
    x0, y0 = client_to_screen(l, t, client_left=client_left, client_top=client_top, client_width=client_width, client_height=client_height)
    x1, y1 = client_to_screen(r, b, client_left=client_left, client_top=client_top, client_width=client_width, client_height=client_height)
    return x0, y0, x1, y1


def region_click_point(
    name: str,
    *,
    client_left: int,
    client_top: int,
    client_width: int,
    client_height: int,
) -> Tuple[int, int]:
    l, t, r, b = region_box(name)
    fx, fy = box_center((l, t, r, b))
    return client_to_screen(
        fx,
        fy,
        client_left=client_left,
        client_top=client_top,
        client_width=client_width,
        client_height=client_height,
    )


def rec_point_for_track(
    track: int,
    *,
    client_left: int,
    client_top: int,
    client_width: int,
    client_height: int,
    row_pitch: float = 0.042,
    first_row_y: float = 0.20,
) -> Tuple[int, int]:
    """Best-effort Rec Enable for 1-based Arrange track (no screenshot)."""
    track = max(1, int(track))
    fx = (REC_X_FRAC[0] + REC_X_FRAC[1]) / 2.0
    fy = first_row_y + (track - 1) * row_pitch
    fy = min(0.80, max(0.14, fy))
    return client_to_screen(
        fx,
        fy,
        client_left=client_left,
        client_top=client_top,
        client_width=client_width,
        client_height=client_height,
    )


def overlay_boxes(names: Optional[Iterable[str]] = None) -> List[Tuple[str, Tuple[float, float, float, float]]]:
    keys = list(names) if names else list(REGIONS)
    return [(n, REGIONS[n]) for n in keys if n in REGIONS]
