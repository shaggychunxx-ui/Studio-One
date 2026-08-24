# Latest UI learn session (auto)

Host **GROMIT** · 2026-08-24T13:35:00Z (continue)
Counts: `{'PASS': 18, 'FAIL': 8, 'SKIP': 2}`
Geometry: `{'width': 1920, 'height': 1080, 's1_window': '1745x999', 'dpi': 96, 'scale': 1.0, 'ok': True}`
S1 Controller: `{'midi_connected': True, 'instrument_midi_connected': True, 'instrument_midi_out': 'S1 Notes 7', 'mcu_out': 'S1 Controller 6'}`

Song: `Documents\Studio One\Songs\Learn_GROMIT_20260824\Learn_GROMIT_20260824\Learn_GROMIT_20260824.song`  
(nested because the dest folder was pre-created; next time pass `Songs\Name\Name.song` without mkdir of the leaf.)

## Lessons
- Launch Studio One in a **background** job (`Start-Process` + `Wait-Process`). A foreground agent shell kills S1 when the command exits (no WER — clean job-object death).
- Safety dialog: UIA has no Start button (`MenuBar/Close` only). Coord Start works. Then Close Locate Missing Files (64 Impact XT samples) and Missing Devices (Surge XT / SynthMaster).
- Mix tab is the Template default. F3 does not leave Mix. Find Command name `Editor` opened **Save As Template**. Bottom Edit/Mix/Browse tabs are custom-drawn.
- Find Command clipboard paste missed twice; empty box + Enter re-fired **Save As Template**. Type the command. Escape unexpected Template dialogs. Never OK them.
- MCU play/stop/record is live: green play, red record, playhead, Mackie Control 76 in the toolbar.
- Add Instrument Track: UIA menu works (`Track 15` created, Rec already red, Out=None). Find Command did not.
- `browser_load Presence XT` searches (tag cloud) but Inspector Out stayed None — not a load. Use a track that already has Mai Tai.
- Compact Rec sits next to Mute/Solo, not `REC_X_FRAC` 605/1920. Look at the filled red circle.
- Live MIDI record on Mai Tai (track 3): Rec red + MCU record + S1 Notes → **blue clip** bars 1–3. Playback playhead crossed it.
- Artist 6.6: **Save As has no hotkey**. `Ctrl+Shift+S` does nothing. File menu letter A opened Save New Version. UIA `Save As...` opens the Windows dialog; type the full path.
- 48 kHz confirmed in transport. Do not Ctrl+S over Template. Do not rec-arm 32 channels. Do not File→New.
- Continue 2026-08-24: Song Setup via UIA `Song` → `Song Setup...` (Alt+S opens the **Studio One** menu). General tab is custom; click the gear. Sample rate was **44.1 with mismatch** — set **48.0 kHz** via dropdown + Down + Enter, then OK. Tempo is **not** in Song Setup Timeline (timebase/offsets only). Transport **160.00** is left of Master Volume (~x=1312, y=952 on this window) — 0.80 frac hits Master Volume. Edit tab opens the piano roll on the Mai Tai clip. Mix tab shows Mai Tai + Main with Compressor/Pro EQ. Hardware MIDI notes sent on `TR-8S 1`, `Moog Matriarch 3`, `monologue 4` (ports opened; ears not scored). UCNET live: DAW `Studio One/6.6.4` tcp **54687** + StudioLive AUD tcp 60716.

Shots: `Documents\Studio One\S1FullControl\ui_shots\` (`mcu_play`, `recording`, `after_record`, `playback_clip`, `save_as_dialog`, `after_save_as_path`).

Full ops notes: `docs/AGENT_OPS_LEARNED.md` (GROMIT live learn 2026-08-24).
