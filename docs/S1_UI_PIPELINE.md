# Preferred use: S1-first UI pipeline

**Preference:** when Studio One has a Song open, create and capture **in the DAW UI** first.  
Offline Python/stems are fallback or parallel, not a replacement for a working S1 session.

**Control split**

| Who | Does |
|-----|------|
| **Agent** | Keyboard + MIDI (MCU transport/mix + **S1 Notes** for instrument notes) |
| **User** | Browser drag instruments/FX, External Devices confirm, taste locks, Rec red if arm won’t stick |

## Ports

| Port | Role |
|------|------|
| MCU: `S1 Controller 1` / `0` | Mackie |
| Notes out: `S1 Notes 2` | Agent instrument stream |
| Notes in: `S1 Notes 1` | Keyboard **Receive From** |

See Studio-One repo: `S1_NOTES_PORT_SETUP.md`.

## Session rules

1. Stay on **Song page** (not Start).  
2. MVP: drums + bass tracks only until pocket approved.  
3. **Instrument on track before any stream** (never empty track).  
4. **Record Enable red** on the target track before Transport Record.  
5. One part at a time after pocket lock.  
6. Stream logs (`note_ons`) ≠ UI proof — confirm parts on the right track.

## Track numbering

- **User language:** Track 1, Track 2, Track 3 (1-based Arrange order).  
- **MCU strip:** often 0-based and **not guaranteed** equal to Arrange track index.  
- Prefer user naming the track or Arrange selection over blind strip numbers.

## Hand-offs (user / mouse)

- Open S1 + Song  
- Keyboard Receive From = **S1 Notes 1**  
- Drag instruments onto tracks  
- Confirm Rec **red** when asked  
- Approve pocket / lead / bed after listen  

## Agent ops

- Add Instrument Track: menu **Track → Add Instrument Track** (UIA)  
- Tools in Studio-One repo: `tools/` (path-agnostic; set `S1_SONG_DIR`)  
- Eyes: screenshot watch under song `_vision/` or `--eyes-dir`  

Deep arm/record: `ARM_RECORD_LESSONS.md`.
