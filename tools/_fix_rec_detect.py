#!/usr/bin/env python3
"""One Rec per track: use track color-index bars + fixed Rec X."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

shot = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    str(Path.home() / "Documents" / "Studio One" / "Songs" / "2026-07-25 ralph rodrigues")
    r"\_vision\one_track\075846_armed_BASS.png"
)
im = Image.open(shot).convert("RGB")
arr = np.asarray(im, dtype=np.int16)
r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
h, w = arr.shape[:2]

# 1) Rec X from red (armed) or known
red = (r > 200) & (g < 120) & (b < 120) & (r > g + 50)
mask = red.copy()
mask[:, :550] = False
mask[:, 700:] = False
mask[:150, :] = False
mask[700:, :] = False
ys, xs = np.where(mask)
if len(xs):
    rec_x = int(np.median(xs))
    print("red rec_x", rec_x, "red_y", int(np.median(ys)), "n", len(xs))
else:
    rec_x = 635
    print("fallback rec_x", rec_x)

# 2) Color index bars — thin high-chroma column left of M/S/Rec
# From layout ~ x 500-520 for cyan/green bars
best = None
for cx in range(490, 540):
    chroma = np.maximum(np.maximum(r[:, cx], g[:, cx]), b[:, cx]) - np.minimum(
        np.minimum(r[:, cx], g[:, cx]), b[:, cx]
    )
    sm = np.convolve(chroma.astype(float), np.ones(9) / 9, mode="same")
    peaks = []
    for y in range(160, 700):
        if sm[y] > 28 and sm[y] >= sm[y - 12 : y + 13].max():
            if not peaks or y - peaks[-1] >= 38:
                peaks.append(y)
            elif sm[y] > sm[peaks[-1]]:
                peaks[-1] = y
    if best is None or len(peaks) > len(best[1]):
        best = (cx, peaks, float(sm[peaks].mean()) if peaks else 0)

cx, peaks, _ = best
print("color_x", cx, "n_tracks", len(peaks), "ys", peaks)

# 3) For each color-bar center, find Rec in upper portion of track
# Track height ~ gap between peaks
pts = []
for i, cy in enumerate(peaks):
    # Rec sits on control row near top of track header (~ upper third)
    if i + 1 < len(peaks):
        gap = peaks[i + 1] - cy
    elif i > 0:
        gap = cy - peaks[i - 1]
    else:
        gap = 45
    # search upper half of this track band at rec_x
    y0 = max(150, cy - gap // 3)
    y1 = min(720, cy + gap // 2)
    best_y, best_s = cy, -1
    for y in range(y0, y1):
        reg = arr[max(0, y - 5) : y + 6, rec_x - 10 : rec_x + 11]
        rr, gg, bb = reg[:, :, 0].astype(int), reg[:, :, 1].astype(int), reg[:, :, 2].astype(int)
        rn = int(((rr > 180) & (gg < 130) & (bb < 130) & (rr > gg + 40)).sum())
        gn = int(
            (
                (rr >= 70)
                & (rr <= 140)
                & (gg >= 70)
                & (gg <= 140)
                & (bb >= 70)
                & (bb <= 140)
                & (np.abs(rr - gg) < 25)
            ).sum()
        )
        s = rn * 4 + gn
        if s > best_s:
            best_s, best_y = s, y
    pts.append((rec_x, best_y, best_s, cy))
    print(f"  T{i+1}: color_y={cy} rec=({rec_x},{best_y}) score={best_s}")

dr = ImageDraw.Draw(im)
for i, (x, y, s, cy) in enumerate(pts):
    dr.ellipse([x - 9, y - 9, x + 9, y + 9], outline=(0, 255, 0), width=2)
    dr.line([(cx, cy), (x, y)], fill=(255, 128, 0), width=1)
    dr.text((x + 12, y - 8), f"T{i+1}", fill=(255, 255, 0))
out = shot.with_name(shot.stem + "_fixed_recs.png")
im.save(out)
print("wrote", out)
print("PTS", [(p[0], p[1]) for p in pts])
