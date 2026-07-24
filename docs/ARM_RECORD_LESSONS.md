# Arm & live MIDI record — deep lessons

Grounded in Studio One 6.6 Recording chapter + 2026-07 live automation sessions.

**Control method priority: keyboard shortcuts → MIDI (MCU) → ask user. No mouse movements.**

## Manual order (do not skip)

1. Song open  
2. Keyboard device: **Receive From** = notes port (**S1 Notes 1**), not MCU  
3. Instrument Track with **Output** = real instrument (agent: `browser_load` or UIA menu)  
4. Track **Input** = that Keyboard  
5. **Record Enable red** on that track (agent: `arm_and_verify`)  
6. Meter moves when notes arrive  
7. Transport **Record**  
8. Stream notes  
9. Stop  

Without step 5, Record does not capture MIDI to the track.

## Toggles (root cause of “not staying armed”)

| Action | Behavior |
|--------|----------|
| Keyboard **`[R]`** | **Toggle** Rec Enable on selected track |
| MCU channel **Rec** | **Toggle** on that mixer strip |
| Press either when already red | **Disarms** |

### Anti-patterns that broke takes

1. Arm with `[R]` **and** MCU `rec_arm` (double toggle → often off).  
2. “Clear” another track by toggling its Rec (often **arms the empty track**).  
3. Arm → rewind/stop thrash → re-arm thrash without looking.  
4. MCU `rec_arm(0)` assuming it arms Arrange **Track 1** — live screenshots showed **Arrange Rec stayed grey**.  
5. Keyboard nav + `[R]` arming **wrong** track (e.g. Track 2 while intending Track 1).  
6. Streaming while claiming success from **note_ons count** with empty timeline.

## MCU strip vs Arrange track

- Mackie select/rec operate on the **mixer surface bank**, not a guaranteed 1:1 with Arrange instrument rows.  
- Studio One track headers are largely **custom-drawn** — UIA often **does not** expose `"Track 1"` names.  
- Prefer: user confirms Rec red on the named track, **or** coordinate/vision eyes, **or** Import MIDI (no arm).

## Preferred agent policies

### A. `arm_and_verify` (default — keyboard + MIDI only)

1. Call `FullControl.arm_and_verify(track)`.
   - Attempt 1: MCU `select(strip)` + `rec_arm(strip)` (MIDI).
   - Screenshot; if Rec red → done.
   - Attempt 2+: hotkey `[R]` on focused track (keyboard).
   - Screenshot after each; stop when red or retries exhausted.
2. If `arm_and_verify` returns `False` after all retries → ask user once to confirm Rec red.
3. Transport Record → stream **S1 Notes** → Stop.
4. **Eyes:** screenshots before/during/after under `_vision/arm_watch/`.
5. User confirms clip on correct track.

### B. Import path (no live arm)

- **Song → Import File** / Browser Files drag `.mid` onto instrument track.
- Tool: `tools/import_and_verify_midi.py` (song-dir CLI).
- Still need instrument on track to hear.

### C. User-armed fallback (only when A fails)

Pass `--user-armed` to any tool. The agent skips arm entirely.
User sets Rec red manually before the tool runs.

**No mouse hunting.** If the agent cannot arm via keyboard/MIDI, it asks the user once and waits.

## Producer “eyes” (UI watch)

Screenshot sequence is the agent’s eyes when UIA is blind:

| Shot | When |
|------|------|
| `01_home` | After rewind |
| `02_armed` | After arm attempt |
| `03_recording` | After transport Record |
| `watch_NN` | Every ~8s during stream |
| `04_stopped` | After stop |

Look for: Rec **red** on target row, **blue MIDI parts** on that lane, playhead motion.  
If Rec grey and/or empty lane → take failed regardless of MIDI log.

## Ports reminder

| Wrong | Right |
|-------|--------|
| Notes on MCU cable | Notes on **S1 Notes** |
| Keyboard Receive From = Controller | Keyboard = **S1 Notes 1** |
| Agent out only Controller | Agent notes out = **S1 Notes 2** |

## Checklist before claiming success

- [ ] Instrument name under track (not “None”)  
- [ ] Rec was red during stream (screenshot)  
- [ ] MIDI part visible on **that** track  
- [ ] User heard pocket / approved or rejected  

Until those pass, status is **attempted stream**, not **recorded**.
