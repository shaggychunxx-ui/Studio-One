"""
Producer ears — capture and score what the machine is hearing.

Uses Windows loopback when available (WASAPI via pyaudiowpatch),
else sounddevice input (Stereo Mix). Time-bounded so capture cannot hang.
Never claims "sounded good" — only energy / activity metrics.
"""

from __future__ import annotations

import json
import time
import wave
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .logutil import log

DEFAULT_SR = 48000
DEFAULT_DEVICE_SUBSTR = "Realtek"


@dataclass
class AudioReport:
    ok: bool
    path: Optional[str]
    seconds: float
    sample_rate: int
    peak: float
    rms: float
    peak_db: float
    rms_db: float
    activity_ratio: float
    has_signal: bool
    backend: str
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _db(x: float) -> float:
    # Floor at -120 dBFS so silence does not report nonsense like -240
    return float(max(-120.0, 20.0 * np.log10(max(x, 1e-12))))


def analyze_array(audio: np.ndarray, sr: int, *, seconds: float) -> Dict[str, float]:
    if audio is None or getattr(audio, "size", 0) == 0:
        return {
            "peak": 0.0,
            "rms": 0.0,
            "peak_db": -120.0,
            "rms_db": -120.0,
            "activity_ratio": 0.0,
        }
    if audio.ndim > 1:
        mono = audio.mean(axis=1).astype(np.float64)
    else:
        mono = audio.astype(np.float64)
    if mono.size == 0:
        return {
            "peak": 0.0,
            "rms": 0.0,
            "peak_db": -120.0,
            "rms_db": -120.0,
            "activity_ratio": 0.0,
        }
    if np.issubdtype(mono.dtype, np.integer) or float(np.max(np.abs(mono))) > 1.5:
        mono = mono / 32768.0
    peak = float(np.max(np.abs(mono)))
    rms = float(np.sqrt(np.mean(mono**2)))
    frame = max(1, int(sr * 0.02))
    if mono.size < frame:
        act = 1.0 if rms > 0.005 else 0.0
    else:
        n = mono.size // frame
        chunks = mono[: n * frame].reshape(n, frame)
        levels = np.sqrt(np.mean(chunks**2, axis=1))
        act = float(np.mean(levels > 0.008))
    return {
        "peak": peak,
        "rms": rms,
        "peak_db": _db(peak),
        "rms_db": _db(rms),
        "activity_ratio": act,
    }


def write_wav(path: Path, audio: np.ndarray, sr: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    audio = np.asarray(audio)
    if audio.ndim == 1:
        audio = audio.reshape(-1, 1)
    if audio.dtype != np.int16:
        clipped = np.clip(audio.astype(np.float64), -1.0, 1.0)
        data = (clipped * 32767.0).astype(np.int16)
    else:
        data = audio
    ch = data.shape[1]
    with wave.open(str(path), "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())


def _pick_wasapi_loopback(p, device_substr: str):
    loops = []
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info.get("isLoopbackDevice"):
            loops.append(info)
    if not loops:
        raise RuntimeError("No WASAPI loopback devices")
    substr = (device_substr or DEFAULT_DEVICE_SUBSTR).lower()
    for info in loops:
        if substr in (info.get("name") or "").lower():
            return info

    def score(info) -> int:
        n = (info.get("name") or "").lower()
        s = 0
        if "realtek" in n:
            s += 100
        if "speaker" in n:
            s += 20
        if "display" in n or "hdmi" in n or "nvidia" in n:
            s -= 50
        return s

    return sorted(loops, key=score, reverse=True)[0]


def _capture_pyaudiowpatch(seconds: float, device_substr: str) -> Tuple[np.ndarray, int, str]:
    """WASAPI via pyaudiowpatch — often hangs on some drivers; use last resort."""
    import threading
    import pyaudiowpatch as pyaudio

    box: Dict[str, Any] = {}

    def worker() -> None:
        p = pyaudio.PyAudio()
        try:
            target = _pick_wasapi_loopback(p, device_substr)
            idx = int(target["index"])
            channels = max(1, int(target.get("maxInputChannels") or 2))
            sr = int(target.get("defaultSampleRate") or DEFAULT_SR)
            name = target["name"]
            frames_total = max(1, int(seconds * sr))
            chunk = max(256, int(sr * 0.05))
            log(f"  ears: wasapi loopback [{idx}] {name!r} {seconds:.1f}s")
            stream = p.open(
                format=pyaudio.paFloat32,
                channels=channels,
                rate=sr,
                input=True,
                input_device_index=idx,
                frames_per_buffer=chunk,
            )
            chunks: List[np.ndarray] = []
            got = 0
            try:
                while got < frames_total:
                    n = min(chunk, frames_total - got)
                    raw = stream.read(n, exception_on_overflow=False)
                    arr = np.frombuffer(raw, dtype=np.float32)
                    if channels > 1:
                        arr = arr.reshape(-1, channels)
                    else:
                        arr = arr.reshape(-1, 1)
                    chunks.append(arr.copy())
                    got += arr.shape[0]
            finally:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            if not chunks:
                raise RuntimeError("WASAPI read returned no frames")
            audio = np.concatenate(chunks, axis=0)
            if audio.shape[1] > 2:
                audio = audio[:, :2]
            box["result"] = (audio.astype(np.float32), sr, f"wasapi:{name}")
        except Exception as e:
            box["error"] = e
        finally:
            try:
                p.terminate()
            except Exception:
                pass

    th = threading.Thread(target=worker, daemon=True)
    th.start()
    th.join(float(seconds) + 3.0)
    if th.is_alive():
        raise RuntimeError("WASAPI loopback hung (skipped)")
    if "error" in box:
        raise box["error"]
    if "result" not in box:
        raise RuntimeError("WASAPI produced no result")
    return box["result"]


def _capture_sounddevice(seconds: float, device_substr: str) -> Tuple[np.ndarray, int, str]:
    import sounddevice as sd

    devices = sd.query_devices()
    pick = None
    substr = (device_substr or "").lower()
    # Prefer Stereo Mix / loopback-like names with Realtek
    for i, d in enumerate(devices):
        name = (d.get("name") or "").lower()
        if d.get("max_input_channels", 0) <= 0:
            continue
        if substr and substr in name and ("mix" in name or "loop" in name or "stereo" in name):
            pick = i
            break
    if pick is None:
        for i, d in enumerate(devices):
            name = (d.get("name") or "").lower()
            if d.get("max_input_channels", 0) > 0 and substr and substr in name:
                pick = i
                break
    if pick is None:
        for i, d in enumerate(devices):
            if d.get("max_input_channels", 0) > 0:
                pick = i
                break
    if pick is None:
        raise RuntimeError("No sounddevice input found")
    info = devices[pick]
    sr = int(info.get("default_samplerate") or DEFAULT_SR)
    ch = min(2, int(info["max_input_channels"]))
    frames = max(1, int(seconds * sr))
    log(f"  ears: sounddevice [{pick}] {info['name']!r} {seconds:.1f}s")
    rec = sd.rec(frames, samplerate=sr, channels=ch, device=pick, dtype="float32")
    sd.wait()
    return np.asarray(rec, dtype=np.float32), sr, f"sounddevice:{info['name']}"


def _capture_soundcard(seconds: float, device_substr: str) -> Tuple[np.ndarray, int, str]:
    import soundcard as sc

    mics = sc.all_microphones(include_loopback=True)
    pick = None
    substr = (device_substr or DEFAULT_DEVICE_SUBSTR).lower()
    for m in mics:
        name = (m.name or "").lower()
        if getattr(m, "isloopback", False) and substr in name:
            pick = m
            break
    if pick is None:
        for m in mics:
            if getattr(m, "isloopback", False):
                pick = m
                break
    if pick is None:
        raise RuntimeError("No soundcard loopback mic")
    sr = DEFAULT_SR
    log(f"  ears: soundcard loopback {pick.name!r} {seconds:.1f}s")
    data = pick.record(numframes=int(seconds * sr), samplerate=sr)
    return np.asarray(data, dtype=np.float32), sr, f"soundcard:{pick.name}"


def capture(
    directory: Path,
    *,
    tag: str = "listen",
    seconds: float = 4.0,
    device_substr: str = DEFAULT_DEVICE_SUBSTR,
    enabled: bool = True,
) -> AudioReport:
    """Capture system/loopback audio and write WAV + metrics."""
    if not enabled:
        return AudioReport(
            ok=False,
            path=None,
            seconds=seconds,
            sample_rate=DEFAULT_SR,
            peak=0.0,
            rms=0.0,
            peak_db=-120.0,
            rms_db=-120.0,
            activity_ratio=0.0,
            has_signal=False,
            backend="disabled",
            error="ears disabled",
        )

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%H%M%S")
    out = directory / f"{stamp}_{tag}.wav"
    audio = None
    sr = DEFAULT_SR
    backend = "none"
    err = None
    seconds = float(max(0.3, min(seconds, 60.0)))

    # Prefer reliable backends first. WASAPI pyaudiowpatch often hangs on Realtek.
    for fn in (_capture_soundcard, _capture_sounddevice, _capture_pyaudiowpatch):
        try:
            audio, sr, backend = fn(seconds, device_substr)
            if audio is not None and getattr(audio, "size", 0) > 0:
                break
            audio = None
        except Exception as e:
            err = str(e)
            log(f"  ears backend fail ({fn.__name__}): {e}")
            audio = None

    if audio is None:
        return AudioReport(
            ok=False,
            path=None,
            seconds=seconds,
            sample_rate=sr,
            peak=0.0,
            rms=0.0,
            peak_db=-120.0,
            rms_db=-120.0,
            activity_ratio=0.0,
            has_signal=False,
            backend="none",
            error=err or "all backends failed",
        )

    metrics = analyze_array(audio, sr, seconds=seconds)
    path_str: Optional[str]
    try:
        write_wav(out, audio, sr)
        path_str = str(out)
    except Exception as e:
        path_str = None
        err = f"wav write: {e}"

    has_signal = metrics["rms"] > 0.005 and metrics["activity_ratio"] > 0.05
    report = AudioReport(
        ok=True,
        path=path_str,
        seconds=seconds,
        sample_rate=sr,
        peak=metrics["peak"],
        rms=metrics["rms"],
        peak_db=metrics["peak_db"],
        rms_db=metrics["rms_db"],
        activity_ratio=metrics["activity_ratio"],
        has_signal=has_signal,
        backend=backend,
        error=err,
    )
    meta = directory / f"{stamp}_{tag}.json"
    try:
        meta.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    except Exception:
        pass
    log(
        f"  ears 🎧 peak={report.peak_db:.1f}dB rms={report.rms_db:.1f}dB "
        f"act={report.activity_ratio:.0%} signal={report.has_signal} ({backend})"
    )
    return report


def analyze_wav(path: Path) -> AudioReport:
    path = Path(path)
    if not path.is_file():
        return AudioReport(
            ok=False,
            path=str(path),
            seconds=0.0,
            sample_rate=0,
            peak=0.0,
            rms=0.0,
            peak_db=-120.0,
            rms_db=-120.0,
            activity_ratio=0.0,
            has_signal=False,
            backend="file",
            error="missing",
        )
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        n = w.getnframes()
        raw = w.readframes(n)
        width = w.getsampwidth()
    if width == 2:
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
    else:
        data = np.frombuffer(raw, dtype=np.float32).astype(np.float64)
    if ch > 1:
        data = data.reshape(-1, ch)
    sec = n / float(sr or 1)
    metrics = analyze_array(data, sr, seconds=sec)
    has_signal = metrics["rms"] > 0.005 and metrics["activity_ratio"] > 0.05
    return AudioReport(
        ok=True,
        path=str(path),
        seconds=sec,
        sample_rate=sr,
        peak=metrics["peak"],
        rms=metrics["rms"],
        peak_db=metrics["peak_db"],
        rms_db=metrics["rms_db"],
        activity_ratio=metrics["activity_ratio"],
        has_signal=has_signal,
        backend="file",
    )
