#!/usr/bin/env python3
"""Prepare a video for Studio One import (48 kHz wav + constant-fps mp4).

Ported from Mira-Soline ffmpeg patterns (Edit-Video.py / drop_c2pa) for music.

GROMIT is Studio One 6 Artist: there is no Video Track (Professional-only).
Import the sidecar *.48k.wav as an Audio Track. The mp4 is for OpenShot / mux
or for a Pro machine.

Usage:
  py -3.12 tools\\prepare_video_for_s1.py CLIP.mp4
  py -3.12 tools\\prepare_video_for_s1.py CLIP.mp4 --song-dir %S1_SONG_DIR%
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

DAW_SR = 48000


def get_ffmpeg() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    raise SystemExit("ffmpeg not found. pip install imageio-ffmpeg or add ffmpeg to PATH.")


def run_ffmpeg(args: list[str]) -> subprocess.CompletedProcess[str]:
    cmd = [get_ffmpeg(), "-hide_banner", "-y", *args]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def probe(path: Path) -> dict:
    p = subprocess.run(
        [get_ffmpeg(), "-hide_banner", "-i", str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    err = p.stderr or ""
    dur = 0.0
    fps = 0.0
    has_audio = "Audio:" in err
    if "Duration:" in err:
        t = err.split("Duration:")[1].split(",")[0].strip()
        hh, mm, ss = t.split(":")
        dur = int(hh) * 3600 + int(mm) * 60 + float(ss)
    if " fps" in err:
        try:
            fps = float(err.split(" fps")[0].split()[-1])
        except ValueError:
            pass
    return {"dur": round(dur, 3), "fps": fps, "audio": has_audio}


def extract_wav(src: Path, dest: Path) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = run_ffmpeg(
        [
            "-i", str(src),
            "-vn", "-acodec", "pcm_s16le", "-ar", str(DAW_SR), "-ac", "2",
            str(dest),
        ]
    )
    if r.returncode != 0:
        print((r.stderr or "")[-2000:])
        return r.returncode
    print("wav", dest, dest.stat().st_size)
    return 0


def transcode_mp4(src: Path, dest: Path, fps: float) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = run_ffmpeg(
        [
            "-i", str(src),
            "-an",
            "-vf", f"fps={fps:.3f},format=yuv420p",
            "-c:v", "libx264", "-crf", "18", "-preset", "fast",
            "-movflags", "+faststart",
            str(dest),
        ]
    )
    if r.returncode != 0:
        print((r.stderr or "")[-2000:])
        return r.returncode
    print("mp4", dest, dest.stat().st_size)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="48 kHz wav + constant-fps mp4 for Studio One")
    p.add_argument("src", type=Path)
    p.add_argument("--song-dir", type=Path, help="Song folder (copies into Media/video-in/)")
    p.add_argument("--out-dir", type=Path)
    p.add_argument("--fps", type=float)
    p.add_argument("--wav-only", action="store_true", help="Skip mp4 transcode (Artist sample pull)")
    args = p.parse_args(argv)

    src = args.src.expanduser().resolve()
    if not src.is_file():
        print("missing", src, file=sys.stderr)
        return 1

    dest_dir = args.out_dir
    if args.song_dir:
        dest_dir = Path(args.song_dir).expanduser().resolve() / "Media" / "video-in"
    if dest_dir is None:
        dest_dir = src.parent / f"{src.stem}-s1"
    dest_dir.mkdir(parents=True, exist_ok=True)

    info = probe(src)
    use_fps = args.fps or (info["fps"] if info["fps"] >= 1 else 30.0)
    wav = dest_dir / f"{src.stem}.48k.wav"
    mp4 = dest_dir / f"{src.stem}.s1.mp4"

    rc = 0
    if info.get("audio"):
        rc = extract_wav(src, wav)
    else:
        print("no audio in source; wav skipped")
        wav = None

    if rc == 0 and not args.wav_only:
        rc = transcode_mp4(src, mp4, use_fps)
    elif args.wav_only:
        mp4 = None

    report = {
        "src": str(src),
        "wav": str(wav) if wav else None,
        "mp4": str(mp4) if mp4 else None,
        "fps": use_fps,
        "sample_rate": DAW_SR,
        "probe_in": info,
        "studio_one_artist": (
            "GROMIT is Artist: import the wav as an Audio Track. "
            "Video Track is Professional-only (ch.20)."
        ),
        "next": (
            "Artist: drag the wav into Arrange. "
            "Pro: drag the mp4 onto the Video Track. "
            "Loop/mux visualizers: Music-producer clip_edit_kb."
        ),
    }
    rep = dest_dir / f"{src.stem}.s1.json"
    rep.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("report", rep)
    print(json.dumps(report, indent=2))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
