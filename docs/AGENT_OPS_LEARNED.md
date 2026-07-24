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

- Dual bridge: MCU on Controller, notes on Notes (see `s1remote/controller.py`)
- Do not thrash `[R]` mid-stream
- Prompt user for mouse: instrument drag, exclusive arm, confirm Rec red
- Screenshots under song `_vision/` when debugging arm

## Manual walk docs in this repo

- `docs/MANUAL_WALKTHROUGH_CATALOG.md`
- `docs/FULL_MANUAL_WALK_REPORT.md`
- `docs/MANUAL_MISSED_REPORT.md`
- `docs/MANUAL_WALK_SUMMARY.md`
