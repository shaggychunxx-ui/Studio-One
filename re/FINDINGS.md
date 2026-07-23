# Studio One 6 — Reverse Engineering Findings

**Target:** PreSonus Studio One 6.6.x on Windows  
**Goal:** External control of host + plug-ins + MIDI I/O  
**Method:** Binary string/XML extraction, package inspection, network observation  
**Not in scope:** License bypass, DRM crack, process injection malware

---

## Executive summary

Studio One does **not** expose a documented public automation API. It **does** ship three powerful, reverse-engineerable control stacks:

| Stack | Location | What it controls |
| --- | --- | --- |
| **DAWRemote / UCNET** | `Plugins\remoteservice.dll` + `ucnet.dll` + `PreSonusHardwareAccessService` | Full remote-app model (mixer, transport, macros, per-plugin surfaces) — same as *Studio One Remote / Fender Studio Pro Remote* |
| **Music Devices (control surfaces)** | `devices\**\*.js` + `*.surface.xml` + embedded SDK `resource://com.presonus.musicdevices/sdk/*` | MCU/HUI/ATOM/etc. — JS host component with `PreSonus.ParamID.*`, bank elements, Control Link |
| **Host script packages** | `Extensions\*\scripts\*.package`, `Scripts\*.package` | In-process JS: `Host.GUI.Commands.interpretCommand`, IO, signals, gadgets |

**Best RE leverage right now:** the DAWRemote **SurfaceData** tables inside `remoteservice.dll` — they name every stock plug-in by GUID and list remote-mappable parameters (`amp.presence`, `cutoff`, …).

---

## 1. DAWRemote component model

Extracted from `remoteservice.dll`:

- Namespace: `Presonus:DAWRemote`
- Schema: `http://www.presonus.com/xml/uc`
- Ranges: Volume (gain curve −∞…+10 dB), Pan, Tempo, automation modes, record modes, macro presentations
- Comment in binary: *“total number of remote channels is limited to 512 for now!”*
- Layouts:
  - Generic remote app: controls `c0`…`c27` (16 knobs, 2×XY pads, 8 buttons) + titles/text
  - CS18AI layout: `p0`…`p24`

Artifacts:

```
re/extracted/remoteservice_xml_01.xml   # ComponentModel definitions
re/extracted/remoteservice_xml_02.xml   # ControlSurface layouts
re/extracted/remoteservice_xml_03.xml   # SurfaceData (plugin maps)
re/plugin_param_catalog.json            # Parsed catalog (39 devices)
```

### Stock plug-in catalog (from SurfaceData)

Examples of `deviceID` → parameters:

| Plugin | GUID (prefix) | Example params |
| --- | --- | --- |
| Ampire | `{B6407C28-…}` | `input.level`, `amp.presence`, `controls.wah`, `controls.active[stomp1]` |
| Pro EQ | `{073C4094-…}` | remote-mapped EQ bands |
| Compressor | `{54F19B72-…}` | threshold/ratio/… |
| Mai Tai | `{B625F134-…}` | `osc1.type`, `osc1.active`, … |
| Presence | `{3713E26C-…}` | `modFx.depth`, `delayFx.mix`, … |
| Mojito | `{19C6BEAB-…}` | `sawSquareOsc1`, … |
| Macro Controls | `{3333…}` | `GlobalMacroControlSet/float-1`…`bool-8` |
| Channel Controls | `{2222…}` | `AudioChannelMacroControlSet/float-1`… |

Full machine-readable dump: `re/plugin_param_catalog.json`.

---

## 2. Network: UCNET / discovery — **DECODED**

See full write-up: [`UCNET_PROTOCOL.md`](UCNET_PROTOCOL.md)

| Endpoint | Owner | Role |
| --- | --- | --- |
| **UDP 47809** | `Studio One.exe` | Discovery query/reply (**working**) |
| **TCP (advertised, e.g. 56721)** | `Studio One.exe` | Session port from discovery |
| TCP 49670 / UDP 56883 | `PreSonusHardwareAccessService` | Hardware access service |

### Discovery reply (live capture)

```
UC | ver=1 BE | tcp_port LE | class 0x4144 ('DA') | flags 0x6b | 0
+ CString name, type="DAW", id, hostname
```

Example: `Studio One/6.6.1.99821 Win x64` / `DAW` / `joc3krytki7gpvyy.studioapp6` / `AI-CODING` → TCP 56721

Query: `UC\x00\x01` and/or event `0x4451` (QD) to UDP 47809.

```bat
py -3.12 -m s1remote ucnet-discover
```

### Session framing

TCP accepts; full UCXML/param subscribe framing **not yet decoded** (HTTP/WS reset; binary guesses silent/reset). Next: capture official Remote app or deeper `ucnet.dll` session parser RE.

---

## 3. Music Devices control-surface SDK

Device scripts include:

```js
include_file("resource://com.presonus.musicdevices/sdk/controlsurfacecomponent.js");
include_file("resource://com.presonus.musicdevices/sdk/musicprotocol.js");
include_file("resource://com.presonus.musicdevices/presonus/pslsurfacecomponent.js");
```

These SDK files are **embedded resources** (not loose on disk). Host APIs used by ship devices:

- `PreSonus.ParamID.kVolume`, `kPan`, `kMute`, `kSolo`, `kSendLevel`, `kInsertBypass`, …
- `PreSonus.FolderID.kInsertsFolder`, `kSendsFolder`
- `PreSonus.MixerConsoleBankID.kAudioTrack`, `kAudioSynth`, …
- `hostComponent.paramList`, `mixerMapping`, `channelBankElement`
- `connectAliasParam`, `invokeChildMethod`, Control Link `vpot[i]` generic mapping

MCU note map lives in:

`C:\Program Files\PreSonus\Studio One 6\devices\Mackie\Control\MackieControl.surface.xml`

User-installable devices go under AppData **User Devices** (same layout as `devices\`).

---

## 4. Host script package API (in-process)

Macros package is a standard ZIP (`PK…`).  
Core Scripts `*.package` use proprietary magic `PACKAGEF` (not ZIP) — further unpacker needed.

From macros JS, observed **Host** surface:

```
Host.GUI.Commands.interpretCommand(category, name, ...)
Host.GUI.Commands.registerCommand / findCommand / assignKey
Host.GUI.Commands.beginTransaction / endTransaction
Host.IO.File / XmlTree / createPackage / openPackage / findFiles
Host.Signals.signal / advise / postMessage
Host.Objects.getObjectByUrl
Host.Services.getInstance
Host.Settings.getAttributes
Host.Console.writeLine
Host.Interfaces.IComponent | IObserver | ICommandHandler | ...
```

Example:

```js
Host.GUI.Commands.interpretCommand(
  "Gadgets", "Macro Organizer", false,
  Host.Attributes(["State", "1"])
);
```

This runs **inside** Studio One after a package is installed — the deepest legal extension point short of reverse-engineering UCNET.

---

## 5. What “full control” maps to (RE roadmap)

| Desire | Path | Status |
| --- | --- | --- |
| Transport / mixer 8-wide | MCU over virtual MIDI | **Implemented** in `s1remote` |
| Instrument MIDI I/O | Virtual keyboard port | **Implemented** |
| Any param after learn | Control Link CC | **Implemented** |
| Named stock-plugin params | SurfaceData catalog → maps | **Catalog extracted** |
| Mixer beyond 8 + full remote UI | UCNET DAWRemote client | **Discovery known; framing TBD** |
| Arbitrary menu/command | Host package `interpretCommand` | **API found; package scaffold next** |
| Third-party VST full dump | Vendor MIDI / Control Link / UI | No free host dump API |
| Inject into process / patch EXE | — | **Out of scope** |

---

## 6. Practical next reverse-engineering steps

1. **UCNET** — Wireshark/npcap while official Remote app connects; document message types; implement Python client.
2. **SDK resources** — dump `controlsurfacecomponent.js` from Studio One resources (resource section / jsengine).
3. **PACKAGEF unpacker** — recover trackedit/musicedit APIs (deeper song object model).
4. **User control surface** — install a custom `.device` + `.js` under User Devices that bridges OSC/HTTP ↔ host params.
5. **Command catalog** — dump all `interpretCommand` categories from UI / bindings files in settings folder.

---

## Files produced

```
s1-remote/
  re/
    FINDINGS.md
    build_catalog.py
    scan_host_api.py
    plugin_param_catalog.json
    extracted/remoteservice_xml_*.xml
    macros_pkg/unzipped/          # Host script samples
  s1remote/                       # working MIDI/MCU remote (separate from RE)
```
