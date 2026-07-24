# Missed manual ops — follow-up run (completed before terminal crash)

- **When:** 2026-07-24T02:58:45  
- **Score:** **19 OK** / **23 still USER or menu-not-found** / **42 total**  
- **Raw log:** `MANUAL_MISSED_RESULTS.jsonl`  
- **S1 Notes port:** `instrument_out=S1 Notes 2` (live note stream attempted)

## Newly OK (were missed before)

| Op | Method | Detail |
|----|--------|--------|
| Song Setup | keyboard | Ctrl+. |
| Performance Monitor | menu | View → Performance |
| Import File menu | menu | Song → Import File… |
| Add Instrument Track | menu UIA | created 1 |
| Record Enable | keyboard | [R] |
| Notes port wired | midi | S1 Notes 2 |
| **Live note stream** | midi notes port | 8 notes C4–C5 — **check Arrange for clip** |
| Notion menu | menu | Song → Send to Notion… |
| Instruments tab | keyboard | F6 |
| Pack Folder menu | menu | Track → Pack Folder |
| Export Stems menu | menu | Song → Export Stems… |
| Automation lanes | keyboard | A |
| Effects browser | keyboard | F7 |
| Channel editor | keyboard | F11 |
| Instrument editor | keyboard | Shift+F11 |
| Save As | keyboard | Ctrl+Shift+S (dismissed) |
| Convert To menu | menu | File → Convert To |

## Still needs you (mouse / edition / unsafe auto)

- New Show / New Project / Atmos / Video / Studio One+  
- Step record toolbar, Score view button  
- Browser **drag** VST or FX onto track  
- Timestretch edge-drag, comping layers  
- Arranger / Chord / Tempo / Signature / Scratch (no menu item found in View/Track)  
- Channel automation modes, MIDI Learn  
- Multi Instrument, export MIDI part (needs selection)  

## Live MIDI record checklist (verify in UI)

1. Keyboard device **Receive From = S1 Notes 1**  
2. Track Input = that Keyboard · Output = instrument  
3. Record Enable red  
4. Look for MIDI clip from the 8-note probe (or re-run short test)

## Combined progress

| Run | Scope | OK |
|-----|--------|-----|
| Full manual walk | ch 1–22 ops | 86 |
| Missed follow-up | previous USER/FAIL list | +19 menu/KB/MIDI |
| Remaining hard UI | drag, global track buttons, Pro pages | ~23 |
