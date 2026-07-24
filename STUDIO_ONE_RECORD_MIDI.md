# Record MIDI into Studio One (from the 6.6 manual)

Source: Studio One 6.6 Reference Manual — Recording / Setup / Browser chapters  
Local pack: `Music-producer/studio-one-6.6-agent-knowledge/FUNCTIONS.md`

## Required order (do not skip)

1. **Keyboard** exists in External Devices, Receive From = note port (`S1 Controller 1`).
2. **Instrument Track** created (`Track → Add Instrument Track` or Browser drag instrument to blank Arrange).
3. Track **Input** = Keyboard (or All Inputs with a defined Keyboard).
4. Track **Output** = Impact XT / Mojito / etc.
5. **Record Enable** the Instrument Track → button **red**  
   - Manual: click Record Enable  
   - Audio shortcut: select track + **[R]**  
   - Exclusive: **Alt+click** Record Enable  
   - Option: Instrument Input Follows Selection auto-arms selected Instrument Track  
6. Confirm: play a note → **track meter moves** (note data arriving).
7. **Transport Record** (**NumPad \*** or MCU Record).
8. Stream / play MIDI notes.
9. **Stop** (Space).

Without step 5, transport Record does **not** capture MIDI to the track.

## Preferred non-realtime handoff

Browser **Files** → drag `drums.mid` / `bass.mid` into Arrange  
→ new Instrument Track + Part (still assign instrument to hear).

## Scripts

| Script | Role |
|--------|------|
| `Open_Session_Jam/create_s1_tracks.py` | Track → Add Instrument Track ×N + load instruments |
| `Open_Session_Jam/setup_tracks_and_record.py` | Must **record-enable** before stream (update to press R / MCU rec after select) |
