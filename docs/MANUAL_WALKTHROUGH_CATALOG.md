# Studio One 6.6 — Manual walkthrough catalog

**Priority for each op:** (1) Keyboard → (2) MIDI/MCU → (3) User  
**Pace:** ≥0.30s between clicks; type char-by-char with ≥0.12s gaps  
**Monitor:** one screenshot per step only when verifying (not every frame)  
**Load rule:** do **not** auto-launch Studio One from scripts if already heavy; user opens one Song first  

Source: Reference Manual chapters via `Music-producer/studio-one-6.6-agent-knowledge/`

---

## Status legend

| Code | Meaning |
|------|---------|
| `KB_OK` | Worked via keyboard |
| `MIDI_OK` | Worked via Mackie/notes MIDI |
| `FAIL` | Attempted, did not work |
| `SKIP` | Needs user / unsafe / edition limit |
| `TODO` | Not run this session |

---

## Phase 0 — Prerequisites (user once)

| # | Op | KB | MIDI | Notes |
|---|-----|----|------|-------|
| 0.1 | Studio One running, **one Song open** (not Start page) | SKIP | — | Agent does not auto-launch DAW (load) |
| 0.2 | External Devices: Keyboard + Mackie on loopMIDI | SKIP | — | Setup once |
| 0.3 | Separate **S1 Notes** port for live MIDI record | SKIP | — | Same port as MCU blocks note record |

---

## Phase 1 — Pages & views (Fundamentals / Pages)

| # | Manual ref | Op | Method | Result |
|---|------------|-----|--------|--------|
| 1.1 | Views | Console | KB `F3` | **KB_OK** |
| 1.2 | Views | Inspector | KB `F4` | **KB_OK** |
| 1.3 | Views | Browser | KB `F5` | **KB_OK** |
| 1.4 | Views | Editor | KB `F2` | **KB_OK** |
| 1.5 | Browser | Instruments tab | KB `F6` | **KB_OK** |
| 1.6 | Browser | Effects tab | KB `F7` | **KB_OK** |
| 1.7 | Browser | Files tab | KB `F9` | **KB_OK** |
| 1.8 | Browser | Pool | KB `F10` | **KB_OK** |
| 1.9 | Channel editor | Open | KB `F11` | TODO |
| 1.10 | Instrument editor | Open | KB `Shift+F11` | TODO |

---

## Phase 2 — Transport (Fundamentals)

| # | Op | Method | Result |
|---|-----|--------|--------|
| 2.1 | Stop | MIDI MCU stop | **MIDI_OK** |
| 2.2 | Play | MIDI MCU play | **MIDI_OK** |
| 2.3 | Return to zero | MIDI MCU rewind | **MIDI_OK** |
| 2.4 | Record engage | KB NumPad `*` / MIDI MCU record | TODO |
| 2.5 | Loop toggle | KB Ctrl+L | **KB_OK** |
| 2.6 | Metronome | KB `C` | **KB_OK** |
| 2.7 | Precount | KB Shift+C | TODO |
| 2.8 | Preroll | KB `O` | TODO |
| 2.9 | Auto Punch | KB `I` | TODO |

---

## Phase 3 — Tracks (Recording)

| # | Op | Method | Result |
|---|-----|--------|--------|
| 3.1 | Add Instrument Track | **Menu** Track → Add Instrument Track (UIA click) | **KB_OK** (menu UIA) |
| 3.2 | Add Audio Track mono | Menu Track → Add Audio Track (mono) | TODO |
| 3.3 | Add Tracks dialog | KB `T` | TODO — dialog mostly custom UI |
| 3.4 | Record Enable | KB `R` on selected track | **KB_OK** |
| 3.5 | Monitor (auto with arm) | — | default ON with Record Enable |
| 3.6 | Exclusive arm | Alt+click Record Enable | SKIP mouse unless needed |

**Known FAIL (prior sessions):** streaming notes on MCU port does not record; need Notes port or Import MIDI.

---

## Phase 4 — Instruments / Browser (Browser + VI chapters)

| # | Op | Method | Result |
|---|-----|--------|--------|
| 4.1 | Open Instruments browser | KB `F6` | TODO |
| 4.2 | Load instrument onto track | Browser drag / Output dropdown | TODO — custom browser UI; user demo used Browser + Replace |
| 4.3 | Replace instrument dialog | Click **Replace** button (UIA) | OK when dialog appears |
| 4.4 | Console Instruments panel | Click + | TODO fragile coords |

**Learned:** Typing works char-by-char; must be **on Song page**, not Start page search.

---

## Phase 5 — Edit / Arrange (high-signal only)

| # | Op | Method | Result |
|---|-----|--------|--------|
| 5.1 | Undo / Redo | KB Ctrl+Z / Ctrl+Shift+Z | **KB_OK** |
| 5.2 | Save | KB Ctrl+S | **KB_OK** |
| 5.3 | Quantize | KB Q | TODO |
| 5.4 | Duplicate | KB D | TODO |
| 5.5 | Merge | KB G | TODO |
| 5.6 | Split at cursor | KB Alt+X | TODO |
| 5.7 | Mute event | KB M | TODO |
| 5.8 | Bounce selection | KB Ctrl+B | TODO |

---

## Phase 6 — Mix / MCU (Mixing + Control Link)

| # | Op | Method | Result |
|---|-----|--------|--------|
| 6.1 | Fader ch0 | MIDI MCU | **MIDI_OK** |
| 6.2 | Mute ch0 | MIDI MCU | **MIDI_OK** |
| 6.3 | Solo ch0 | MIDI MCU | **MIDI_OK** |
| 6.4 | Select | MIDI MCU | **MIDI_OK** |
| 6.5 | Plugin mode / pan mode | MIDI MCU | Prior OK |
| 6.6 | Track mute/solo keys | KB M / S | Prior OK (context-dependent) |

---

## Phase 7 — Import / Export

| # | Op | Method | Result |
|---|-----|--------|--------|
| 7.1 | Import File | Menu Song → Import File… (Ctrl+Shift+O) | Prior FAIL dialog automation |
| 7.2 | Export Mixdown | KB Ctrl+E | TODO |
| 7.3 | Drag MIDI from Browser Files | User / drag | SKIP preferred for MIDI parts |

---

## Phase 8 — Not automated this pass (user or later)

- Full Options/Audio I/O matrix  
- Every built-in FX parameter  
- Spatial/Atmos, Show page, Project mastering  
- Collaboration, video  
- Step record, comping layers, Chord Track deep edit  

---

## Runner

Light sequential script (only if S1 already open):

`Open_Session_Jam\manual_walk_light.py`

Does **not** launch Studio One. Runs one phase per invocation:

```text
py -3.12 manual_walk_light.py --phase 1
py -3.12 manual_walk_light.py --phase 2
…
```

---

## Session log

| Date | Note |
|------|------|
| 2026-07-24 | Terminal crash; S1 not running; catalog written offline; light runner added; no auto-launch |
| 2026-07-24 | Resume after crash: **no auto-launch S1**, no multi-process thrash; `manual_walk_light.py` one phase at a time |
| 2026-07-24 | Missed-ops pass: `manual_missed_walk.py` — 19 newly OK (incl. live note stream on S1 Notes, Import File menu, Performance, Pack Folder, Export Stems, Convert To, Notion menu). Report: MANUAL_MISSED_REPORT.md |
