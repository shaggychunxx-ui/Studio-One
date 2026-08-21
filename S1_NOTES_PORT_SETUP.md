# S1 Notes port (live MIDI record)

## What we created

| loopMIDI port | Role |
|---------------|------|
| **S1 Controller** | Mackie Control (mixer/transport) |
| **S1 Notes** | Instrument Track notes only |

Install (Studio One closed):

```bat
py -3.12 -m s1remote setup --apply
```

Windows ports (rtmidi index is not stable — hardware MIDI occupies 0–4 on GROMIT):

- MCU out (agent → S1): `S1 Controller N` (name match, not `1`)
- MCU in (S1 feedback): `S1 Controller M`
- Notes out (agent): `S1 Notes N`
- Notes in (S1 Keyboard): `S1 Notes M`

`s1-remote` settings store the live names after `--apply`.

## Studio One setup (once)

1. **Options → External Devices** (or `setup --apply`)
2. **Mackie Control**  
   - Receive From / Send To = `S1 Controller`
3. **Keyboard** named **S1 Notes**
   - **Receive From = `S1 Notes`**  
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
