# S1 Full Control

Maximum practical control of **Studio One 6** from one program (`s1-remote`).

## One-time setup

```bat
cd %USERPROFILE%\s1-remote
py -3.12 -m s1remote setup
py -3.12 -m s1remote full package
```

1. **loopMIDI** — port `S1 Controller 1` (OUT).
2. Studio One → **Options → External Devices**
   - **Mackie Control** — Receive From = `S1 Controller 1`
   - **New Keyboard** — same port (notes + Control Link CCs)
3. Install `scripts\S1FullControl.package` (Scripts menu / drag into S1).
4. Optional: Control Link toolbar ON for permanent CC binds.

## Capability matrix

| Want | How | Command |
| --- | --- | --- |
| Transport | MCU | `transport play` |
| Mixer mute/fader/solo | MCU | `mute 0` / `fader 0 --db -6` |
| **VST params without per-knob learn** | MCU **plugin mode** + V-Pots | `full plugin-mode` then `full vpot 0 --delta 4` |
| Named VST params | Control Link maps | `vst set mai_tai …` |
| MIDI notes in | Keyboard MIDI | `note 60` |
| Views / file / edit | Hotkeys | `hotkey mixer` / `browser` |
| Menu bar | Alt menu path | `full do menu.track` |
| Browser load instrument | F5 + type + Enter | `full browser-load Mojito` |
| Channel volume by index | In-host Host.Objects | `full host set_channel_volume --params "{\"index\":0,\"db\":-6}"` then run **Process Queue** in S1 |
| All map CCs pulsed | MIDI only | `full program-maps` |
| UCNET full remote session | Still RE incomplete | `ucnet-discover` only |

## Python API

```python
from s1remote.full_control import FullControl

with FullControl() as s1:
    print(s1.capabilities())

    s1.play()
    s1.mute(0)
    s1.fader(0, -6)

    # Focus a plugin in S1 first, then:
    s1.plugin_mode()
    s1.vpot(0, +8)   # first mapped param of focused VST

    s1.note(60, duration=0.3)
    s1.console()
    s1.browser_load("Presence XT")

    s1.host_set_volume(0, -6)  # then Process Queue in S1
    s1.do("mixer.mode_plugin")
```

## CLI

```bat
py -3.12 -m s1remote full caps
py -3.12 -m s1remote full commands mixer
py -3.12 -m s1remote full program-maps
py -3.12 -m s1remote full plugin-mode
py -3.12 -m s1remote full vpot 0 --delta 6
py -3.12 -m s1remote full do view.browser
py -3.12 -m s1remote full browser-load "Mai Tai"
py -3.12 -m s1remote full host set_channel_mute --params "{\"index\":0,\"state\":true}"
```

## Honest limits

- **UCNET session** (phone Remote app protocol) is not fully decoded — cannot yet set remote SurfaceData params over TCP.
- **In-host Host.Objects** requires running the package task once per queue (S1 does not expose continuous external IPC).
- **Third-party VST param lists** need Control Link learn, Channel Macros, or MCU plugin-mode focus — no public dump of every third-party param.
- **No pixel thrash** — cursor is not used to hunt knobs.

This is the real maximum stack PreSonus allows without reverse-engineering the process memory.
