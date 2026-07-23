#!/usr/bin/env python3
"""
30s mixer test using Studio One's own control surfaces (s1-remote).

No pixel guessing / blind mouse clicks.

  1) NAVIGATE — focus S1, Esc dialogs, F3 Console (official shortcut)
  2) ACT      — Mackie Control: mute + fader strips 0–3
                (matches Studio One 6 MackieControl.surface.xml)

  py -3.12 -u -m s1remote.test_mixer_30s
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from s1remote.controller import S1Remote
from s1remote.hotkeys import focus_studio_one, run_action, studio_one_running

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "config"
REPORT = OUT / "MIXER_30S_REPORT.txt"
DEADLINE_S = 30.0
N = 4


def log(msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def dismiss_dialogs(s1: S1Remote, times: int = 3) -> None:
    """Esc any Song Setup / Options modal that steals focus."""
    try:
        from s1remote.hotkeys import VK, KEYEVENTF_KEYUP
        import ctypes

        user32 = ctypes.windll.user32
        vk = VK["ESCAPE"]
        focus_studio_one()
        for _ in range(times):
            user32.keybd_event(vk, 0, 0, 0)
            time.sleep(0.04)
            user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
            time.sleep(0.2)
    except Exception as exc:
        log(f"  dismiss skip: {exc}")


def main() -> int:
    t0 = time.time()
    results: dict = {
        "project": "s1-remote",
        "mode": "mcu+hotkeys",
        "mutes": [],
        "faders": [],
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "blind_clicks": 0,
    }

    log("=" * 56)
    log("MIXER 30s — s1-remote (MCU + F3, no blind clicks)")
    log("=" * 56)

    if not studio_one_running():
        log("FAIL: Studio One is not running")
        REPORT.write_text("FAIL: Studio One not running\n", encoding="utf-8")
        return 2

    s1 = S1Remote()
    try:
        s1.connect(open_input=False)
    except Exception as exc:
        log(f"FAIL: MIDI connect: {exc}")
        REPORT.write_text(f"FAIL: MIDI connect: {exc}\n", encoding="utf-8")
        return 2

    results["midi"] = {
        "out": s1.bridge.out_name,
        "connected": s1.connected,
    }
    log(f"MIDI OUT={s1.bridge.out_name!r} connected={s1.connected}")

    try:
        # --- NAVIGATE with program shortcuts ---
        log("Navigate: focus + Esc dialogs + F3 Console")
        focus_studio_one()
        time.sleep(0.15)
        dismiss_dialogs(s1, times=3)
        # Official View → Console
        try:
            run_action("mixer", focus=True)  # F3
        except Exception:
            run_action("console", focus=True)
        time.sleep(0.55)
        dismiss_dialogs(s1, times=2)
        results["nav"] = {"action": "hotkey_mixer_F3", "ok": True}

        # Bank to first 8 if needed (start known)
        # Do not bank randomly — stay on current bank for strips 0–3

        # --- ACT via Mackie Control (Studio One External Device) ---
        log(f"MCU mute channels 0..{N-1}")
        for ch in range(N):
            if time.time() - t0 > DEADLINE_S - 12:
                break
            log(f"  mute ch{ch}  (MCU note 0x{0x10 + ch:02X})")
            try:
                s1.mute(ch)
                results["mutes"].append(
                    {"i": ch + 1, "ok": True, "method": "s1remote.mcu.mute", "channel": ch}
                )
            except Exception as exc:
                results["mutes"].append(
                    {"i": ch + 1, "ok": False, "reason": str(exc), "channel": ch}
                )
            time.sleep(0.22)

        fader_dbs = [-6.0, -12.0, -3.0, -9.0]
        log(f"MCU fader channels 0..{N-1}")
        for ch in range(N):
            if time.time() - t0 > DEADLINE_S - 1:
                break
            db = fader_dbs[ch % len(fader_dbs)]
            log(f"  fader ch{ch} → {db} dB  (MCU pitchbend + touch)")
            try:
                s1.fader(ch, db)
                results["faders"].append(
                    {
                        "i": ch + 1,
                        "ok": True,
                        "method": "s1remote.mcu.fader",
                        "channel": ch,
                        "db": db,
                    }
                )
            except Exception as exc:
                results["faders"].append(
                    {"i": ch + 1, "ok": False, "reason": str(exc), "channel": ch, "db": db}
                )
            time.sleep(0.25)

    finally:
        s1.disconnect()

    elapsed = time.time() - t0
    results["elapsed_s"] = round(elapsed, 2)
    mute_ok = sum(1 for r in results["mutes"] if r.get("ok"))
    fader_ok = sum(1 for r in results["faders"] if r.get("ok"))

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "mixer_30s_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    lines = [
        "MIXER 30s — s1-remote (PROGRAM CODE)",
        "====================================",
        "Project: C:\\Users\\Box One\\s1-remote",
        "Method: hotkey F3 Console + Mackie Control MIDI",
        "No mouse mute/fader targeting (never blind-click).",
        "",
        f"Elapsed: {elapsed:.1f}s",
        f"MIDI: {results.get('midi')}",
        f"Nav: {results.get('nav')}",
        f"Mutes MCU-sent:  {mute_ok}/{len(results['mutes'])}",
        f"Faders MCU-sent: {fader_ok}/{len(results['faders'])}",
        f"Blind clicks: 0",
        "",
        "Requires Studio One:",
        "  Options → External Devices → Mackie Control",
        "  Receive From: S1 Controller 1  (this app's OUT)",
        "  Send To:      S1 Controller 0  (optional feedback)",
        "",
        "Mutes:",
    ]
    for r in results["mutes"]:
        lines.append(f"  {r}")
    lines.append("Faders:")
    for r in results["faders"]:
        lines.append(f"  {r}")
    REPORT.write_text("\n".join(lines), encoding="utf-8")

    log("=" * 56)
    log(
        f"DONE {elapsed:.1f}s mutes={mute_ok}/{len(results['mutes'])} "
        f"faders={fader_ok}/{len(results['faders'])} blind=0"
    )
    log(f"Report: {REPORT}")

    if mute_ok < N or fader_ok < N:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
