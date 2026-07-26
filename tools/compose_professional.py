#!/usr/bin/env python3
"""
Compose professional multi-part MIDI for a new original song.

32 bars @ 92 BPM — modern dark-pulse electronic (drums, bass, lead, bed, color).
Writes under <song>/MIDI/ and NOTES sketch.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import mido

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS.parent))

from s1_tools.paths import resolve_song_dir  # noqa: E402
from s1_tools.logutil import log  # noqa: E402

BPM = 92
BARS = 32
TPB = 480


def _write(path: Path, builder, *, seed: int) -> float:
    rng = random.Random(seed)
    mid = mido.MidiFile(ticks_per_beat=TPB)
    tr = mido.MidiTrack()
    mid.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(BPM)))
    events = []
    for bar in range(BARS):
        for n in builder(bar, rng):
            t0 = max(0, int((bar * 4 + n["t"]) * TPB))
            t1 = t0 + max(1, int(n["d"] * TPB))
            events.append((t0, 1, int(n["p"]), int(n["v"])))
            events.append((t1, 0, int(n["p"]), 0))
    events.sort(key=lambda e: (e[0], e[1]))
    abs_t = 0
    for t, on, p, v in events:
        dt = max(0, t - abs_t)
        abs_t = t
        tr.append(
            mido.Message(
                "note_on" if on else "note_off",
                note=max(0, min(127, p)),
                velocity=max(0, min(127, v)) if on else 0,
                time=dt,
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    mid.save(str(path))
    return float(mido.MidiFile(str(path)).length)


def drums(bar: int, rng: random.Random):
    """Punchy 4-on-floor + ghost hats; fills every 8 bars."""
    out = []
    # form: intro 0-3 sparse, groove 4-23, lift 24-27, outro 28-31
    energy = 1.0
    if bar < 4:
        energy = 0.55
    elif bar >= 24:
        energy = 1.15
    if bar >= 28:
        energy = 0.7

    kick_v = int(108 * min(1.0, energy))
    sn_v = int(92 * min(1.0, energy))
    # kick
    for beat in (0.0, 1.0, 2.0, 3.0):
        out.append({"t": beat, "d": 0.12, "p": 36, "v": kick_v - (0 if beat in (0, 2) else 8)})
    if bar % 2 == 1 and bar >= 4:
        out.append({"t": 2.5, "d": 0.08, "p": 36, "v": int(70 * energy)})
    # snare / clap
    out.append({"t": 1.0, "d": 0.12, "p": 38, "v": sn_v})
    out.append({"t": 3.0, "d": 0.12, "p": 38, "v": sn_v - 4})
    if bar % 4 == 3 and bar >= 7:
        out.append({"t": 3.5, "d": 0.08, "p": 39, "v": 100})  # clap fill
        out.append({"t": 3.75, "d": 0.06, "p": 38, "v": 80})
    # hats
    for i in range(8):
        t = i * 0.5
        v = int((52 + (10 if i % 2 == 0 else 0)) * min(1.1, energy))
        if bar < 4 and i % 2:
            continue
        out.append({"t": t + rng.uniform(-0.008, 0.008), "d": 0.07, "p": 42, "v": v})
    if bar >= 16 and bar < 28:
        for i in range(4):
            out.append({"t": 0.25 + i, "d": 0.05, "p": 44, "v": 48})  # pedal
    return out


def bass(bar: int, rng: random.Random):
    """Deep minor pulse — A minor-ish center (MIDI 33=A1)."""
    # progression roots (degree in A minor): i - VI - III - VII
    roots = [33, 33, 29, 29, 36, 36, 31, 31]  # A F C G
    r = roots[bar % 8]
    if bar < 4:
        return [
            {"t": 0.0, "d": 1.8, "p": r, "v": 88},
            {"t": 2.0, "d": 1.6, "p": r, "v": 78},
        ]
    if bar >= 28:
        return [{"t": 0.0, "d": 3.5, "p": r, "v": 70}]
    out = [
        {"t": 0.0, "d": 0.7, "p": r, "v": 102},
        {"t": 0.75, "d": 0.2, "p": r, "v": 70},
        {"t": 1.5, "d": 0.4, "p": r, "v": 88},
        {"t": 2.0, "d": 0.7, "p": r + 7 if bar % 4 < 2 else r + 5, "v": 94},
        {"t": 2.75, "d": 0.2, "p": r, "v": 68},
        {"t": 3.25, "d": 0.45, "p": r - 5 if bar % 2 else r, "v": 86},
    ]
    if bar % 8 == 7:
        out.append({"t": 3.75, "d": 0.2, "p": r + 12, "v": 75})
    return out


def lead(bar: int, rng: random.Random):
    """Sparse melodic hook after intro; rests for pocket space."""
    if bar < 8:
        return []  # pocket first — no lead in MVP zone conceptually, but we write full form
    # A minor pentatonic-ish
    scale = [57, 60, 62, 64, 67, 69, 72, 74]  # A C D E G A C D
    if bar >= 28:
        return [{"t": 0.0, "d": 3.2, "p": 69, "v": 62}]
    if bar % 4 == 0:
        deg = [0, 2, 4, 2]
    elif bar % 4 == 1:
        deg = [4, 3, 2, 0]
    elif bar % 4 == 2:
        deg = [2, 4, 5, 4]
    else:
        deg = [5, 4, 2, 0]
    out = []
    for i, d in enumerate(deg):
        if bar % 8 == 7 and i >= 2:
            break
        pitch = scale[d % len(scale)] + (12 if 16 <= bar < 24 and i == 0 else 0)
        out.append(
            {
                "t": i * 0.95 + rng.uniform(-0.015, 0.015),
                "d": 0.55 + (0.2 if i == 0 else 0),
                "p": pitch,
                "v": 92 if i == 0 else 68 + rng.randint(0, 8),
            }
        )
    return out


def bed(bar: int, rng: random.Random):
    """Wide pads — sustained triads under the progression."""
    # Am F C G (voiced mid)
    chords = [
        [45, 48, 52],  # Am
        [45, 48, 52],
        [41, 45, 48],  # F
        [41, 45, 48],
        [48, 52, 55],  # C
        [48, 52, 55],
        [43, 47, 50],  # G
        [43, 47, 50],
    ]
    ch = chords[bar % 8]
    v = 48 if bar < 4 else (58 if bar < 24 else 50)
    if bar >= 28:
        v = 40
    return [{"t": 0.0, "d": 3.85, "p": p, "v": v} for p in ch]


def color(bar: int, rng: random.Random):
    """Light stabs / FX — sparse."""
    if bar < 12 or bar >= 28:
        return []
    if bar % 4 != 3:
        return []
    return [
        {"t": 3.0, "d": 0.25, "p": 84, "v": 55},
        {"t": 3.5, "d": 0.2, "p": 79, "v": 48},
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--song-dir", type=Path, default=None)
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()
    song = resolve_song_dir(args.song_dir)
    midi_dir = song / "MIDI"
    seed = args.seed if args.seed is not None else 92026
    meta = {"bpm": BPM, "bars": BARS, "seed": seed, "parts": {}}
    for name, fn in [
        ("drums.mid", drums),
        ("bass.mid", bass),
        ("lead.mid", lead),
        ("bed.mid", bed),
        ("color.mid", color),
    ]:
        length = _write(midi_dir / name, fn, seed=seed + hash(name) % 1000)
        meta["parts"][name] = {"length_sec": round(length, 2)}
        log(f"  compose {name} ~{length:.1f}s")
    (midi_dir / "compose_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    notes = song / "NOTES.txt"
    sketch = (
        f"\n--- COMPOSE {BPM} BPM / {BARS} bars ---\n"
        f"Style: dark modern pulse (Meridian)\n"
        f"Form: intro 1-4 | groove 5-24 | lift 25-28 | outro 29-32\n"
        f"Parts: drums Impact, bass Mojito, lead Mai Tai, bed Presence, color Mai Tai2\n"
        f"Seed={seed}\n"
    )
    if notes.is_file():
        notes.write_text(notes.read_text(encoding="utf-8") + sketch, encoding="utf-8")
    else:
        notes.write_text(sketch, encoding="utf-8")
    print(json.dumps({"ok": True, "song_dir": str(song), **meta}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
