# s1-remote

External remote control for **PreSonus Studio One 6** on Windows.

Uses supported surfaces only (no process injection):

| Layer | Controls | How |
| --- | --- | --- |
| **Mackie Control (MCU)** | Transport, 8-ch faders, mute/solo/rec/select, banks, V-Pots, **plugin mode** | Virtual MIDI (`S1 Controller`) |
| **Control Link** | Named VST / stock params (after map + optional learn) | MIDI CC (MCU cable) |
| **Instrument MIDI** | Notes, velocity, program change for **live record** | **Separate** port (`S1 Notes`) |
| **Hotkeys / menus** | Views, file, edit, menu bar paths | Focus window + keys |
| **In-host package** | Track/channel mute/volume by index | Studio One Scripts |
| **UCNET** | Discovery working; TCP param session still RE | UDP 47809 / TCP session |
| **HTTP API** | Same features for Stream Deck / scripts | `http://127.0.0.1:8765` |

## Install

```bat
cd %USERPROFILE%\s1-remote
py -3.12 -m pip install -r requirements.txt
copy config\settings.example.json config\settings.json
```

## One-time Studio One wiring

```bat
set PYTHONPATH=%CD%
py -3.12 -m s1remote setup
```

1. **loopMIDI** — **two** cables:
   - `S1 Controller` → MCU (out `S1 Controller 1`, in `S1 Controller 0`)
   - `S1 Notes` → instrument notes only (agent out `S1 Notes 2`, S1 in `S1 Notes 1`)
2. Studio One → **Options → External Devices → Add → Mackie → Control**
   - **Receive From** = MCU OUT (`S1 Controller 1`)
   - **Send To** = feedback (`S1 Controller 0`)
3. **New Keyboard** (or existing Keyboard) for live notes:
   - **Receive From = `S1 Notes 1`** (not the MCU port)
4. See **`S1_NOTES_PORT_SETUP.md`** and **`STUDIO_ONE_RECORD_MIDI.md`**

> MCU and notes must **not** share one port. Notes on the Mackie cable collide with surface note-numbers and do not record reliably.

## Docs (manual walk + ops)

| File | Purpose |
|------|---------|
| `docs/S1_UI_PIPELINE.md` | **Preferred use** — S1-first agent/user split |
| `docs/ARM_RECORD_LESSONS.md` | Deep arm/record failures + eyes policy |
| `docs/AGENT_OPS_LEARNED.md` | Live arm/port failures and agent policy |
| `docs/MANUAL_WALKTHROUGH_CATALOG.md` | Full manual walk catalog |
| `docs/FULL_MANUAL_WALK_REPORT.md` | Ch.1–22 results |
| `docs/MANUAL_MISSED_REPORT.md` | Follow-up missed ops |
| `S1_NOTES_PORT_SETUP.md` | Dual loopMIDI wiring |
| `STUDIO_ONE_RECORD_MIDI.md` | Record-enable order from 6.6 manual |
| `tools/` | Path-agnostic scripts + **producer eyes** (screenshots) |

Manual chapter text + full production workflow live in **Music-producer**:
`studio-one-6.6-agent-knowledge/`, `production-workflow-knowledge/`.

## Verify

```bat
set PYTHONPATH=%CD%
py -3.12 -u scripts\verify_all.py
```

Writes `config/VERIFY_REPORT.txt`. Safe to run without Studio One open (S1-only checks skip).

## CLI

```bat
set PYTHONPATH=%CD%
py -3.12 -m s1remote ports
py -3.12 -m s1remote status
py -3.12 -m s1remote transport play
py -3.12 -m s1remote fader 0 --db -6
py -3.12 -m s1remote mute 0
py -3.12 -m s1remote mode plugin
py -3.12 -m s1remote cc 20 100
py -3.12 -m s1remote note 60 --duration 0.4
py -3.12 -m s1remote full caps
py -3.12 -m s1remote full program-maps
py -3.12 -m s1remote full plugin-mode
py -3.12 -m s1remote full vpot 0 --delta 4
py -3.12 -m s1remote full package
py -3.12 -m s1remote ucnet-discover
py -3.12 -m s1remote ucnet-paths --kind transport
```

### Full Control (stacked API)

```python
from s1remote.full_control import FullControl

with FullControl() as s1:
    s1.play()
    s1.mute(0)
    s1.fader(0, -6)
    # Focus a plugin in S1 first:
    s1.plugin_mode()
    s1.vpot(0, +8)          # MCU maps V-Pots to focused plugin params
    s1.note(60)
    s1.do("view.console")
    s1.host_set_volume(0, -6)  # then Scripts → S1 Full Control: Process Queue
```

See [FULL_CONTROL.md](FULL_CONTROL.md) and [VST_MIDI.md](VST_MIDI.md).

## VST MIDI (Control Link)

```bat
py -3.12 -m s1remote vst list
py -3.12 -m s1remote vst show pro_eq
py -3.12 -m s1remote learn-wiggle 20
py -3.12 -m s1remote map-define "My Plugin" "Cutoff" 20
py -3.12 -m s1remote param "My Plugin" "Cutoff" 90
```

## HTTP

```bat
py -3.12 -m s1remote api
```

```bat
curl -X POST http://127.0.0.1:8765/transport/play
curl -X POST http://127.0.0.1:8765/mixer/fader -H "Content-Type: application/json" -d "{\"channel\":0,\"db\":-6}"
```

## UCNET reverse engineering

Discovery is live. TCP param session framing is incomplete (documented in [re/UCNET_PROTOCOL.md](re/UCNET_PROTOCOL.md)).

```bat
py -3.12 -m s1remote ucnet-discover
py -3.12 -m s1remote ucnet-connect
py -3.12 re\re_session_deep.py
```

To finish session decode: capture official Studio One / Fender Remote traffic with `re\passive_session_sniff.py`.

## Layout

```
s1-remote/
  main.py
  requirements.txt
  README.md
  FULL_CONTROL.md
  VST_MIDI.md
  config/
    settings.example.json
    plugin_maps.json
  s1remote/
    controller.py      # S1Remote facade
    full_control.py    # stacked FullControl API
    cli.py / api.py
    hotkeys.py / menus.py
    vst_midi.py
    host_bridge.py
    midi/              # MCU, Control Link, notes
    ucnet/             # discovery + session RE
  host_package/        # in-host Scripts package sources
  scripts/
    verify_all.py
  re/                  # RE notes, probes, extracted models
```

## Honest limits

- No public “control every S1 function via one host API”.
- Third-party VST params need Control Link learn, Channel Macros, or MCU plugin mode.
- UCNET path-based mixer/VST (`mixer/channel/ch1/volume`) is modeled; live TCP set not finished.
- No pixel thrash / blind mouse hunting.

## License / intent

Personal / research remote tooling for a licensed Studio One install. Does not bypass DRM or patch the DAW binary.
