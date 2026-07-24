# Manual walk summary (completed)

- **When:** 2026-07-24 ~02:35
- **Studio One:** launched with song; Song page ready (`ensure_song` OK)
- **Results:** `MANUAL_WALK_RESULTS.jsonl`
- **Score this run:** **23 OK / 0 FAIL** (excluding one earlier prereq fail when S1 was closed)

## Results by phase

| Phase | Op | Method | OK |
|-------|-----|--------|----|
| 0 | ensure_song | keyboard | yes |
| 1 | console | keyboard F3 | yes |
| 1 | inspector | keyboard F4 | yes |
| 1 | browser | keyboard F5 | yes |
| 1 | editor | keyboard F2 | yes |
| 1 | instruments_tab | keyboard F6 | yes |
| 1 | effects_tab | keyboard F7 | yes |
| 1 | files_tab | keyboard F9 | yes |
| 1 | pool | keyboard F10 | yes |
| 2 | stop | MIDI MCU | yes |
| 2 | rewind | MIDI MCU | yes |
| 2 | play_stop | MIDI MCU | yes |
| 2 | metronome | keyboard C | yes |
| 2 | loop_toggle | keyboard | yes |
| 3 | add_instrument_track | menu UIA | yes (created=1) |
| 3 | record_enable | keyboard R | yes |
| 5 | save | keyboard Ctrl+S | yes |
| 5 | undo | keyboard | yes |
| 5 | redo | keyboard | yes |
| 6 | fader_0 | MIDI MCU | yes |
| 6 | mute_0 | MIDI MCU | yes |
| 6 | solo_0 | MIDI MCU | yes |
| 6 | select_0 | MIDI MCU | yes |

## Priority used
1. **Keyboard** — views, metronome, loop, arm, save, undo/redo  
2. **MIDI (Mackie)** — transport, fader/mute/solo/select  
3. **User** — not required this run  

## Still not fully automated (catalog Phase 4/7+)
- Browser **drag** VST onto channel (custom UI; user demo needed)  
- Live MIDI **note record** (needs separate Notes MIDI port, not MCU)  
- Song → Import File dialog  
- Full FX list, Spatial, Show, Project pages  

## How to re-run (light)
Studio One already open with a Song, then:
```text
py -3.12 manual_walk_light.py --phase 1
```
Or full sequential (same as this run) when S1 is open.
