# Latest UI learn session (auto)

Host **LAPTOP** · 2026-08-17T00:57:46Z
Counts: `{'PASS': 37, 'FAIL': 46, 'SKIP': 4}`
Geometry: `{'width': 1920, 'height': 1080, 'aspect': 1.7778, 'aspect_label': '16:9', 'dpi': 120, 'scale': 1.25, 'ok': True, 'dpi_check': {'dpi': 120, 'scale': 1.25, 'ok': False}}`
S1 Controller: `{'midi_connected': True, 'instrument_midi_connected': True, 'instrument_midi_out': 'S1 Notes 5', 'mcu_out': 'S1 Controller 4'}`

## Lessons
- Software S1 Controller (MCU) connected — prefer MCU for transport/mix.
- Live-device learn: attached MIDI/mixer PASS; missing ports SKIP. Do not rec-arm 32 channels.
- ears:transport_play_stop no signal (peak_db=-90.30899869919436) — expected if no instrument audio / physical I/O offline
- S1 exited 2 times — stopping (098 crash guard). Do not File>New-each-cycle on this i7.

Full report: `C:\Users\Kristine\Documents\Studio One\Songs\2026-08-16\_vision\learn_ui\learn_session_report.json`
