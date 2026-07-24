# s1-remote / Studio One — agent ops learned

**Date:** 2026-07-24  
**Companion:** Music-producer `studio-one-6.6-agent-knowledge/` (manual chapters + same ops notes)

## Ports

| Port | Role |
|------|------|
| `S1 Controller 1` (out) / `0` (in) | Mackie Control — transport, faders, mute/solo/select |
| `S1 Notes 2` (agent out) / `1` (S1 in) | Instrument notes only |

Config keys: `midi_out_port`, `midi_in_port`, `instrument_midi_out_port` (default fuzzy `S1 Notes`).

See `S1_NOTES_PORT_SETUP.md` and `STUDIO_ONE_RECORD_MIDI.md`.

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
