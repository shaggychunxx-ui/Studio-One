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
| **Alt+click Rec** | Exclusive Rec Enable (only that track) |

### Anti-patterns that broke takes

1. Arm with `[R]` **and** MCU `rec_arm` (double toggle → often off).  
2. “Clear” another track by toggling its Rec (often **arms the empty track**).  
3. Arm → rewind/stop thrash → re-arm thrash without looking.  
4. MCU `rec_arm(0)` assuming it arms Arrange **Track 1** — live screenshots showed **Arrange Rec stayed grey**.  
5. Keyboard nav + `[R]` arming **wrong** track (e.g. Track 2 while intending Track 1).  
6. Streaming while claiming success from **note_ons count** with empty timeline.

### Root causes found 2026-07 (ralph song / multi-track)

| # | Bug | Evidence | Fix |
|---|-----|----------|-----|
| 1 | **Clicked Monitor, not Rec** | Annotate maps put markers on speaker icons; Rec red lives **x≈619–652**, Monitor **x≥665** | `locate_track_rec_buttons` restricted to Rec X band `605–655` |
| 2 | **Focus loss / S1 crash** | `081418_arm_fail.png` is **Grok TUI**, not S1 — hundreds of arm clicks hit the agent window | `is_studio_one_arrange_shot()` gate; refuse arm if shot is not arrange |
| 3 | **False arm success** | `scan_rec_red` fell back to “any red” (inspector Mute/Rec, wrong row) | Strict row-only check (`allow_fallback=False`) for verify |
| 4 | **Wrong track index** | Visible rows ≠ S1 track numbers when scrolled; 12 “rows” from Rec+Monitor peaks | One Rec peak per track, min spacing; map by visible order after scroll-to-top |
| 5 | **Green clips missed** | Mojito parts are green; blue-only growth said “fail” when bass landed | Count blue **or** cyan **or** green lane pixels |
| 6 | **Double-toggle thrash** | Grid search Alt+plain spam arms then disarms | One action per attempt in `arm_and_verify` |

Diagnostic: `py -3.12 tools/diagnose_arm.py` (offline shots + optional `--live`).

### Stay on the open song (UI availability)

Before arm/stream, `ui_gate.check_ui_available(expected_song=song.name)`:

- S1 running, title matches song, no **New**/Safety/Save As/Import, arrange visible  
- Blockers → **Cancel/ESC only** (never OK New mid-session)  
- Still blocked → **STOP** + `last_failure.json` with why  
- Hotkey `new_song` (Ctrl+N) **blocked** unless `S1_ALLOW_NEW_SONG=1` (prevents song “going away”)

### Policy 2026-07 (efficiency + accuracy)

| Rule | Detail |
|------|--------|
| **No thrash** | Max **3** arm attempts; max **2** human clicks per arm; never grid-search 50 points |
| **Human-like click** | `s1_tools/human_input.py` — smooth move, single press, DPI-aware |
| **Live vision** | Eyes watch every ~2.5s during stream (`live_*.png` + HUD) |
| **Live hearing** | Short probe + play listen + null-bus check after stop |
| **Lane accuracy** | Multi-color clip count (blue/cyan/green) per track row, before/after delta |
| **Import fallback** | On arm fail → File Import (no more click spam) |
| **tracks.json** | Role → track number from Template defaults |
| **Orchestrator** | `tools/produce.py` — one part per job |

Diagnostic DPI: this machine often runs at **150%** scale — `ensure_dpi_aware()` must run before grab/click.

## MCU strip vs Arrange track

- Mackie select/rec operate on the **mixer surface bank**, not a guaranteed 1:1 with Arrange instrument rows.  
- Studio One track headers are largely **custom-drawn** — UIA often **does not** expose `"Track 1"` names.  
- Prefer: user confirms Rec red on the named track, **or** coordinate/vision eyes, **or** Import MIDI (no arm).

## Preferred agent policies

### A. `arm_and_verify` (default — **keyboard + MIDI only**)

1. Call `FullControl.arm_and_verify(track, allow_mouse=False)` (default).
   - Attempt 1: **keyboard** — select arrange track + **one** `[R]`.
   - Screenshot; if Rec red on **target row** → done.
   - Attempt 2: **MCU** select + rec_arm once (may fail map — used for transport more than arm).
   - **Mouse is OFF** unless `allow_mouse=True` (then one Rec-column click only).
2. If still fail → **do not thrash**. Write `s1_jobs/arm_diagnosis.json` with:
   - `primary_cause` (e.g. `wrong_track_armed`, `no_rec_red_anywhere`, `not_s1_arrange_ui`)
   - `remediations` (fix select, tracks.json, ports, user arm once)
   - `next_action` for the orchestrator
3. Optional: import MIDI fallback **after** diagnosis is saved.
4. Or ask user once to set Rec red (`user_armed`).
5. Transport Record → stream **S1 Notes** → Stop.
6. **Eyes:** `_vision/arm_watch/` + HUD; never claim success from note_ons alone.

**Why diagnose:** arm fail is usually wrong track selected, MCU≠arrange, double-toggle, focus loss, or DPI — not “need more clicks.”

### B. Import path (no live arm)

- **Song → Import File…** (`Ctrl+Shift+O`) — **not** File → Import Files (wrong menu; dialog never opens).
- Tool: `tools/import_and_verify_midi.py` tries: Ctrl+Shift+O → Song menu → File legacy → Alt+S/F I.
- Still need instrument on track to hear.

### C. Track select (wrong_track_armed / armed_rows [-1])

- Do **not** use Ctrl+Home for track focus (timeline only).
- Select: ESC → F2 arrange → PageUp/Up to top → Down (N-1) → one `[R]`.
- If keyboard still arms wrong row: `allow_mouse` enables **one** vision Rec click (never grid spam).

### D. User-armed fallback (only when A fails)

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
