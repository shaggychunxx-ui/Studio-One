# s1-remote

External remote control for **PreSonus Studio One 6** on Windows.

Uses supported surfaces only (no process injection):

| Layer | Controls | How |
| --- | --- | --- |
| **Mackie Control (MCU)** | Transport, 8-ch faders, mute/solo/rec/select, banks, V-Pots, **plugin mode** | Virtual MIDI |
| **Control Link** | Named VST / stock params (after map + optional learn) | MIDI CC |
| **Instrument MIDI** | Notes, velocity, program change | MIDI |
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

1. **loopMIDI** — ports e.g. `S1 Controller 0` / `S1 Controller 1`
2. Studio One → **Options → External Devices → Add → Mackie → Control**
   - **Receive From** = this tool’s OUT (`S1 Controller 1`)
   - **Send To** = feedback (`S1 Controller 0`)
3. Optional: **New Keyboard** on the same cable for notes / Control Link CCs

> We open a MIDI **output**. That must be what Studio One **receives from**. If nothing moves, swap ports in `config/settings.json`.

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
