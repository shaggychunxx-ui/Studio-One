# VST MIDI control (Studio One)

Control **any stock plugin or third-party VST** by sending MIDI CCs into Studio One **Control Link**.

## Setup (once)

```bat
cd %USERPROFILE%\s1-remote
py -3.12 -m s1remote vst setup
```

1. **loopMIDI** port (you have `S1 Controller 1` as output).
2. Studio One → **Options → External Devices → Add**  
   - New Keyboard **or** Control Surface  
   - **Receive From** = port this tool sends on (`S1 Controller 1`)
3. Toolbar: **Control Link ON** + **Focus ON**.

## Learn one knob

1. Open plugin, click the parameter.  
2. Wiggle a CC:

```bat
py -3.12 -m s1remote vst learn-wiggle 20
```

3. Drive it:

```bat
py -3.12 -m s1remote vst cc 20 100
py -3.12 -m s1remote vst cc 20 0
```

## Named maps (after learn)

```bat
py -3.12 -m s1remote vst define "Serum" "Cutoff" 20
py -3.12 -m s1remote vst set Serum Cutoff 0.8
```

## Third-party VST bank (16 knobs)

```bat
py -3.12 -m s1remote vst show generic_16
py -3.12 -m s1remote vst learn-all generic_16 --pause 1.5
py -3.12 -m s1remote vst set generic_16 knob_1 100
```

Fast path for any VST: assign key params to **Channel Macro Controls**, then:

```bat
py -3.12 -m s1remote vst learn-all channel_macros
```

## Stock plugins

Maps generated from Studio One remote SurfaceData (CC 20+).  
You still must **Control Link learn** once per param (or use learn-all).

```bat
py -3.12 -m s1remote vst list
py -3.12 -m s1remote vst show pro_eq
py -3.12 -m s1remote vst show mai_tai
py -3.12 -m s1remote vst learn pro_eq lcfreq
py -3.12 -m s1remote vst set pro_eq lcfreq 64
```

## Python

```python
from s1remote.vst_midi import VstMidiControl

with VstMidiControl() as vst:
    vst.cc(20, 100)
    vst.set("generic_16", "knob_1", 0.5)
    vst.learn_wiggle(21)
```

## Limits (honest)

| Can | Cannot |
| --- | --- |
| Drive any param after Control Link learn | Auto-dump every third-party VST param without learn |
| Notes to instrument tracks (`vst` is CC; use `note` for keys) | Bypass host MIDI security / offline editors |

Instrument **notes** (play the synth), not knobs:

```bat
py -3.12 -m s1remote note 60 --duration 0.4
```
