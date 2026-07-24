# S1 Notes port (live MIDI record)

## What we created

| loopMIDI port | Role |
|---------------|------|
| **S1 Controller** | Mackie Control (mixer/transport) — unchanged |
| **S1 Notes** | Instrument Track notes only (new) |

Windows ports (current numbering):

- Out (agent → S1): `S1 Notes 2`
- In (S1 listens): `S1 Notes 1`

`s1-remote` settings:

- `midi_out_port`: `S1 Controller 1` (MCU)
- `instrument_midi_out_port`: `S1 Notes` (fuzzy-matches `S1 Notes 2`)

## Studio One setup (once)

1. **Options → External Devices**
2. **Mackie Control**  
   - Receive From = `S1 Controller 1` (keep as before)
3. **Keyboard** (your new Keyboard device, or Add → New Keyboard)  
   - **Receive From = `S1 Notes 1`**  
   - Optional: enable **Default Instrument Input**
4. On an **Instrument Track**:  
   - Input = that Keyboard (or All Inputs)  
   - Output = Impact / Mojito / etc.  
   - **Record Enable** red  
5. Agent records notes → they go on **S1 Notes**, not MCU.

## Test

```bat
cd %USERPROFILE%\s1-remote
set PYTHONPATH=%CD%
py -3.12 -c "from s1remote.full_control import FullControl; s=FullControl().__enter__(); print(s.status()); s.note(60); s.__exit__(None,None,None)"
```

Arm a track, hit Record in S1, run note stream — meter should move.
