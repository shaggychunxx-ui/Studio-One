# UCNET Protocol Notes (Studio One 6.6.1) — RE progress

**Updated:** deep reverse-engineering pass (libucnet.so RTTI, remoteservice.dll, live UDP/TCP)

---

## Status matrix

| Layer | Status | Notes |
| --- | --- | --- |
| UDP discovery (47809) | **Working** | Query `UC\\x00\\x01` / `DQ` → full Alive reply |
| Event type IDs | **Complete** | 37 classes from Android `libucnet.so` RTTI |
| DAW param paths | **Complete model** | `transport/*`, `mixer/channel/chN/*`, surface `c0..` |
| EncodedMessage variants | **IDs known** | `JM` `UB` `ZB` `ZM` (likely encode/compress modes) |
| UDP ExtensionQuery reply | **Observed** | 12-byte short UC frame from HW service |
| TCP session param stream | **Open** | Connect succeeds; app-layer frames not yet acked |
| TLS on DAW TCP | **Rejected** | Connection reset |
| Shared memory | **API present** | `CreateFileMappingA` in ucnet.dll; name not recovered |

---

## Live topology (this machine)

| Endpoint | Role |
| --- | --- |
| UDP **47809** | Discovery query + alive beacons |
| UDP **53044** (ephemeral) | Discovery reply source / client target |
| UDP **56883** | Seen as source of short DQ after ExtensionQuery |
| TCP **56721** | DAW session port (from Alive.tcp_port) |
| TCP **49670** | PreSonusHardwareAccessService (short DQ advertises this port) |

Discovery example:
```
Studio One/6.6.1.99821 Win x64 / DAW / joc3krytki7gpvyy.studioapp6 / AI-CODING
flags=0x6b  tcp=56721
```

---

## Discovery packet (decoded — production)

### Query
```
UC 00 01                 # magic + version 1 BE
-- or --
44 51                    # DQ
```

### Alive (full, ~89 bytes)
```
0  UC
2  u16 BE version (=1)
4  u16 LE tcp_port
6  u16 BE event (=0x4441 DA)
8  u32 LE flags (0x6b observed)
12 u32 LE reserved (0)
16 C-strings: name, type, id, hostname
```

### Short DQ reply (12 bytes) — **new**
Observed after client `DiscoveryAlive` announce or `ExtensionQuery` on UDP:

```
UC 00 01 | tcp_port LE | 44 51 (DQ) | 00 00 6b 00
```

Examples:
- `UC 00 01 91 dd 44 51 00 00 6b 00` → port **56721** (DAW)
- `UC 00 01 06 c2 44 51 00 00 6b 00` → port **49670** (Hardware Access), src UDP 56883

Interpretation: peer is querying/advertising a TCP endpoint in compact form.

---

## Event type catalog (complete from RTTI)

Tags are **uint16 big-endian** ASCII digraphs (`LiNNNN` in RTTI = tag value).

| ID | Tag | Name |
| --- | --- | --- |
| 0x424F | BO | BinaryEvent |
| 0x434B | CK | MessageChunkEvent |
| 0x4441 | DA | DiscoveryAliveEvent |
| 0x4442 | DB | DebugEvent |
| 0x444C | DL | DiscoveryLeaveEvent |
| 0x4451 | DQ | DiscoveryQueryEvent |
| 0x4551 | EQ | ExtensionQueryEvent |
| 0x4641 | FA | FileAbortEvent |
| 0x4644 | FD | FileDataEvent |
| 0x4652 | FR | FileRequestEvent |
| 0x4653 | FS | FileDataRateEvent |
| **0x4A4D** | **JM** | **EncodedMessageEvent** (Li19021) |
| 0x4B41 | KA | KeepAliveEvent |
| 0x4C51 | LQ | LoopbackQueryEvent |
| 0x4C52 | LR | LoopbackReplyEvent |
| 0x4D41 | MA | MultiMidiMessageEvent |
| 0x4D42 | MB | MeterEvent8 |
| 0x4D49 | MI | MusicInputEvent |
| 0x4D4D | MM | MidiMessageEvent |
| 0x4D52 | MR | SurroundMeterEvent |
| 0x4D53 | MS | MeterEvent16 |
| 0x4E4F | NO | NoOpEvent |
| 0x5043 | PC | ParamColorEvent |
| 0x5045 | PE | ParamEditEvent |
| 0x5049 | PI | ParamIncrementEvent |
| 0x504C | PL | ParamStringListEvent |
| 0x504D | PM | ParamModeEvent |
| 0x5052 | PR | ParamRangeEvent |
| 0x5053 | PS | ParamStringEvent |
| **0x5056** | **PV** | **ParamValueEvent** |
| 0x534C | SL | MidiLongSysexEvent |
| 0x5353 | SS | MidiShortSysexEvent |
| 0x5443 | TC | TimeCodeEvent |
| **0x5542** | **UB** | **EncodedMessageEvent** (Li21826) |
| 0x554D | UM | UDPMappingEvent |
| **0x5A42** | **ZB** | **EncodedMessageEvent** (Li23106) — likely zlib |
| **0x5A4D** | **ZM** | **EncodedMessageEvent** (Li23117) — likely zlib |

Code: `s1remote/ucnet/events.py`

---

## DAWRemote object model (what session will drive)

From `remoteservice.dll` / `dawremote.xml` — full path catalog:

```
transport/start|stop|record|loop|tempo|returnToZero|…
metronome/clickOn
mixer/anySolo|anyMute
mixer/focus/path
mixer/channel/ch{N}/volume|mute|solo|pan|selected|recordArmed|monitor|label
mixer/channel/ch{N}/inserts/slot{M}/…
controls/c{i}/value   (surface knobs)
document/title
```

Generated list: `re/extracted/daw_param_paths.json` (171 core paths)  
API: `s1remote/ucnet/paths.py`

Stock plugin SurfaceData: `re/plugin_param_catalog.json` (**732** remote params across 39 devices)

---

## Session framing — remaining work

TCP **56721** accepts connections but does not reply to guessed frames (KA/DA/EQ/PV/EM/size-prefix).  
TLS is reset.  

Likely missing pieces (priority order):

1. **Client registration sequence** after discovery (maybe multi-step UDP then TCP with cookie from short DQ)
2. **Exact EncodedMessage body** (UCXML vs binary archive; compress flags `compressed` / `aesencrypted` in remoteservice)
3. **Official Remote app capture** — still the fastest path to ground-truth frames

### Capture workflow (do this to finish TCP)

```bat
py -3.12 re\passive_session_sniff.py 120
REM optional elevated:
powershell -ExecutionPolicy Bypass -File re\start_capture.ps1
```

Then connect **Fender Studio Pro Remote** / Studio One Remote on LAN, move a fader, stop capture.

### Deep RE tools

```bat
set PYTHONPATH=%USERPROFILE%\s1-remote
py -3.12 re\re_session_deep.py
py -3.12 re\probe_hw_ports.py
py -3.12 -c "from s1remote.ucnet.session import UCSession; print(UCSession().connect())"
```

---

## Code map

```
s1remote/ucnet/
  discovery.py   # working discovery
  events.py      # full event ID enum
  paths.py       # DAWRemote path model
  session.py     # handshake + ParamValue packers (best-effort)
  client.py      # older TCP scaffold
re/
  re_session_deep.py
  probe_hw_ports.py
  extracted/session_re_report.json
  extracted/daw_param_paths.json
  apk/ucremote_libs/lib_arm64-v8a_libucnet.so
```

---

## Practical control today (while TCP session open)

Until session framing is finished, Full Control uses:

| Need | Path |
| --- | --- |
| Mixer / transport / plugin params | **MCU MIDI** (`full plugin-mode` + V-Pots) |
| Named stock VST CCs | **Control Link maps** + `program-maps` |
| Channel volume by index | **In-host package** Host.Objects queue |
| Notes | **Keyboard MIDI** |
| Menus / browser | Hotkeys + Alt menu / browser-load |

UCNET will replace/augment these once PV/Subscribe frames are confirmed on the wire.
