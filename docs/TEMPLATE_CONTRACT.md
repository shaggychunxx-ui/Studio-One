# Template song contract (zero-touch prerequisite)

Standing Template path (default):

`Documents\Studio One\Songs\Template\Template.song`

Production **must** Save As a new song before any stream — never write takes into Template.

**Sample rate: 48 kHz for every song** (StudioLive 32SC / engine). Do not create or export at 44.1 kHz.

## Required track map (1-based Arrange)

| Role | Track | Suggested instrument |
|------|------:|----------------------|
| drums | 1 | Impact XT / Multi-Instrument kit |
| drums2 | 2 | optional kit layer |
| lead | 3 | Mai Tai / Presence |
| color | 4 | Mai Tai / FX |
| bass | 5 | Mojito / Presence bass |
| bass2 | 6 | optional |
| bed | 7 | Presence pad |
| bed2 | 8 | optional |
| sample | 9 | optional |

Written to each song as `tracks.json` at start (`s1_tools.tracks_map`).

## One-time human setup (then zero interaction)

1. **loopMIDI** cables: `S1 Controller` (MCU) + `S1 Notes` (instrument).
2. Studio One → External Devices:
   - Mackie Control: Receive/Send on Controller ports
   - Keyboard: **Receive From = S1 Notes 1** (not MCU)
3. Open Template; confirm each role track has an **instrument** and Input = Keyboard.
4. Control Link maps (optional but recommended): core EQ/cutoff on stock plugs.
5. Save Template.

## Agent behavior

- `start_from_template.py` / `autonomous_run.py` open Template → Save As.
- Hands use `role` in job steps → `tracks.json` resolve.
- Arm max 3 tries → import fallback → no thrash.
- Eyes + ears prove capture; note_ons alone never lock gates.
