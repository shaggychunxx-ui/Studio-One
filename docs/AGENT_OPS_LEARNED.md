# s1-remote / Studio One — agent ops learned

**Date:** 2026-07-24  
**Companion:** Music-producer `studio-one-6.6-agent-knowledge/` (manual chapters + same ops notes)

## Sample rate (standing — 2026-08-15)

**Every song is 48 kHz.** StudioLive 32SC and `AudioEngine.settings` are 48 kHz. New Song / Song Setup / mixdown WAV must be 48 kHz. 44.1 kHz songs make S1 resample and hitch on LAPTOP.

## Ports

| Port | Role |
|------|------|
| `S1 Controller 1` (out) / `0` (in) | Mackie Control — transport, faders, mute/solo/select |
| `S1 Notes 2` (agent out) / `1` (S1 in) | Instrument notes only |

Config keys: `midi_out_port`, `midi_in_port`, `instrument_midi_out_port` (default fuzzy `S1 Notes`).

See `S1_NOTES_PORT_SETUP.md` and `STUDIO_ONE_RECORD_MIDI.md`.

### Software S1 Controller vs physical external devices (2026-08-07)

- **Always prefer software S1 Controller** (loopMIDI Mackie / MCU) when ports exist.
- **Physical external devices** (audio interface, hardware MIDI keyboard, hardware surface) may be **offline** until the human connects them later.
- UI learn / verify sessions must **still use S1 Controller**; only **SKIP** true hardware I/O, not virtual MCU.
- Continuous learner: `tools/learn_ui_loop.py` + LAPTOP runner `Invoke-S1-LearnUI-LAPTOP.ps1`.
- Eyes must scale Rec column by **screenshot width / aspect ratio** (`rec_x_band_for_width`, `get_screen_geometry`) — LAPTOP is not always 1920×1080.

### LAPTOP learn session 080 (2026-08-07) — live results

| Metric | Value |
|--------|-------|
| Cycles | 21 |
| PASS / FAIL / SKIP / RETRY_PASS | 441 / 1 / 63 / 21 |
| Geometry | 1920×1080 (16:9) |
| S1 Controller MCU + Notes | **connected** (loopMIDI) |
| Physical gear | SKIP (policy) |
| Ears after Play | signal present (sounddevice) |

**Mistakes learned**

1. **Save As at boot** — dialog not found; continued on Template arrange (1 FAIL, not fatal). Harden `start_from_template.save_as_new_song` + clone fallback; learn may stay on Template* if song UI visible.
2. **Arm vision at Windows DPI scale 1.25** — `arm_and_verify` eyes click often fails Rec-red confirm; **hotkey `[R]` RETRY_PASS** every cycle. Prefer keyboard arm + screenshot verify; recommend **display scale 100%** on LAPTOP for reliable Rec map.
3. **Stuck prompt** — human saw a prompt during learn; Save As was the likely blocker. Comms: `gsw/work/music-production/s1-learn-comms/` + `unblock_and_diagnose.py`.

## Record path (manual + live)

1. Song open; Keyboard **Receive From = S1 Notes 1**
2. Instrument on Arrange track (user drag)
3. **Record Enable red** on that track (`[R]` is a **toggle**)
4. Transport Record → stream notes via `FullControl` / instrument bridge → Stop
5. Verify **MIDI part in Arrange** — never trust stream log alone

## What failed in live automation

- MCU `rec_arm(strip)` often **does not** arm Arrange instrument Rec
- Multi-press `[R]` / “clear” arm on other strips **disarms** or arms empty tracks
- `browser_load` does not assign VSTs
- MCU strip 0/1 may not equal Track 1/2 in Arrange

## Agent policy

**Default: independent.** The agent completes every step it can without interrupting the user.
It asks for help only when a capability is genuinely unavailable (instrument drag in the Browser,
one-time External Devices wiring, subjective pocket approval).

### Step-by-step autonomous loop

1. Create instrument tracks: `add_instrument_tracks` (UIA menu).
2. Load instrument: `FullControl.browser_load(name)` — keyboard search + Enter.
3. Arm track: `FullControl.arm_and_verify(track)` — MCU rec_arm, then hotkey `[R]` retries,
   screenshot-verified. Returns `True` when Rec is confirmed red.
4. Record: `s1.record()` → stream notes → `s1.stop()`.
5. Verify: check eyes screenshots for blue MIDI part on the correct lane.

### Escalate to user only when

- `arm_and_verify` returns `False` after all retries → ask user to set Rec red.
- `browser_load` did not assign the correct VST → ask user to drag from Browser.
- Pocket / lead / bed approval is needed (creative taste, cannot automate).

### Anti-patterns (do not do)

- Do not thrash `[R]` or MCU rec without screenshot verification between presses.
- Do not claim "recorded" from `note_ons` count alone — verify eyes + Arrange clip.
- Do not arm with both `[R]` and `rec_arm` in one pass (double toggle often disarms).

## Manual walk docs in this repo

- `docs/MANUAL_WALKTHROUGH_CATALOG.md`
- `docs/FULL_MANUAL_WALK_REPORT.md`
- `docs/MANUAL_MISSED_REPORT.md`
- `docs/MANUAL_WALK_SUMMARY.md`
