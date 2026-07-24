# Full Studio One 6.6 manual walk report

- When: 2026-07-24T02:42:33
- Source: Reference Manual EN chapters 1–22
- Priority: keyboard → MIDI → user
- **Attempted this run: 118  OK=86  FAIL/need-user=32  (user-tagged=31)**

## Results

| Ch | Op | Method | OK | Detail |
|----|-----|--------|----|--------|
| 0 | ensure_song_page | keyboard | yes |  |
| 01 | edition_awareness | doc | yes | Artist/Pro/Prime — operational notes only |
| 01 | no_runtime_op | doc | yes | overview chapter |
| 02 | already_installed | doc | yes | Studio One 6 present on disk |
| 02 | skip_activation_ui | user | no | USER: my.presonus / content install if needed |
| 03 | options_open_close | keyboard | yes | Ctrl+, then Esc |
| 03 | external_devices_keyboard_mcu | doc | yes | assumed wired for s1-remote |
| 03 | audio_io_matrix | user | no | USER: Song Setup Audio I/O if routing wrong |
| 04 | console | keyboard | yes |  |
| 04 | inspector | keyboard | yes |  |
| 04 | browser | keyboard | yes |  |
| 04 | editor | keyboard | yes |  |
| 04 | metronome | keyboard | yes |  |
| 04 | loop_toggle | keyboard | yes |  |
| 04 | save | keyboard | yes |  |
| 04 | undo | keyboard | yes |  |
| 04 | redo | keyboard | yes |  |
| 04 | retrospective_recall | keyboard | yes | Shift+NumPad* attempt |
| 04 | performance_monitor | user | no | USER: View → Performance if needed |
| 05 | song_page_active | keyboard | yes | Track menu present |
| 05 | start_page | keyboard | yes | Alt+Home start page attempt |
| 05 | quick_switch_ctrl_tab | keyboard | yes |  |
| 05 | show_page | user | no | USER/Pro: File New Show |
| 05 | project_page | user | no | USER/Pro: File New Project |
| 06 | add_instrument_track | menu_uia | yes | n=1 |
| 06 | record_enable | keyboard | yes | [R] |
| 06 | transport_prep | midi_mcu | yes |  |
| 06 | transport_record_probe | midi_mcu | yes | notes on MCU port often fail to record |
| 06 | precount | keyboard | yes | Shift+C |
| 06 | preroll | keyboard | yes | O |
| 06 | auto_punch | keyboard | yes | I |
| 06 | loop_record | doc | yes | uses loop + record when armed |
| 06 | step_record | user | no | USER: Editor Step enable |
| 06 | import_midi_file | user | no | USER: Song→Import File or Browser drag |
| 07 | tool_arrow | keyboard | yes | key 1 |
| 07 | tool_range | keyboard | yes | key 2 |
| 07 | tool_split_tool | keyboard | yes | key 3 |
| 07 | tool_eraser | keyboard | yes | key 4 |
| 07 | tool_paint | keyboard | yes | key 5 |
| 07 | tool_mute_tool | keyboard | yes | key 6 |
| 07 | quantize | keyboard | yes | Q/Ctrl+Q |
| 07 | duplicate | keyboard | yes | D |
| 07 | merge | keyboard | yes | G |
| 07 | split_at_cursor | keyboard | yes | Alt+X |
| 07 | crossfade | keyboard | yes | X |
| 07 | nudge | keyboard | yes | Alt+Left |
| 07 | select_all | keyboard | yes |  |
| 07 | cut_copy_paste | keyboard | yes | Ctrl+C/V |
| 07 | comping_layers | user | no | USER: Record Takes to Layers |
| 07 | timestretch | user | no | USER: Alt+edge drag |
| 08 | open_editor | keyboard | yes | F2 then score view in editor |
| 08 | score_view_toggle | user | no | USER: Note Editor Score button |
| 08 | notion_send | user | no | USER: Song→Send to Notion |
| 09 | browser | keyboard | yes | F5 |
| 09 | instruments | keyboard | yes |  |
| 09 | effects | keyboard | yes |  |
| 09 | loops | keyboard | yes |  |
| 09 | files | keyboard | yes |  |
| 09 | pool | keyboard | yes |  |
| 09 | load_instrument_drag | user | no | USER: drag from Instruments to Arrange |
| 09 | search | keyboard | yes | Ctrl+F in browser if focused |
| 10 | duplicate_event | keyboard | yes |  |
| 10 | pack_folder | user | no | USER: right-click Pack Folder |
| 10 | arranger_track | user | no | USER: Arranger Track button |
| 10 | chord_track | user | no | USER: Chord Track (Pro features vary) |
| 10 | tempo_track | user | no | USER: Tempo Track button |
| 10 | signature_track | user | no | USER: Signature Track button |
| 10 | bounce_selection | keyboard | yes | Ctrl+B |
| 10 | find_track | keyboard | yes | Ctrl+Alt+T |
| 10 | scratch_pad | user | no | USER: Scratch Pad button |
| 11 | console | keyboard | yes | F3 |
| 11 | fader | midi_mcu | yes |  |
| 11 | mute | midi_mcu | yes |  |
| 11 | solo | midi_mcu | yes |  |
| 11 | select | midi_mcu | yes |  |
| 11 | track_mute_key | keyboard | yes | M |
| 11 | track_solo_key | keyboard | yes | S |
| 11 | group_tracks | keyboard | yes | Ctrl+G |
| 11 | dissolve_group | keyboard | yes | Ctrl+Shift+G |
| 11 | export_mixdown | keyboard | yes | Ctrl+E — Esc if dialog |
| 11 | export_stems | user | no | USER: Song→Export Stems |
| 11 | scenes | keyboard | yes | Ctrl+Alt+S scenes dialog attempt |
| 12 | atmos_setup | user | no | USER/Pro: Spatial Audio / Atmos config |
| 12 | doc_only | doc | yes | Artist may lack full Atmos |
| 13 | new_show | user | no | USER: File→New→Show (avoid leaving Song) |
| 13 | doc_setlist_players | doc | yes | setlist/players/performance view |
| 14 | show_automation | keyboard | yes | A toggle automation lanes |
| 14 | automation_modes | user | no | USER: Read/Touch/Latch/Write on channel |
| 14 | control_link_write | doc | yes | needs playback + mapped control |
| 15 | mcu_plugin_mode | midi_mcu | yes |  |
| 15 | mcu_pan_mode | midi_mcu | yes |  |
| 15 | mcu_bank | midi_mcu | yes |  |
| 15 | control_link_assign | keyboard | yes | Alt+M |
| 15 | midi_learn_map | user | no | USER: External panel MIDI Learn |
| 16 | project_page | user | no | USER/Pro: New Project / Add Song to Project |
| 16 | doc_loudness_cd | doc | yes | LUFS/CD/DDP in Project page |
| 17 | browser_effects | keyboard | yes | F7 Effects |
| 17 | open_channel_editor | keyboard | yes | F11 |
| 17 | insert_fx_drag | user | no | USER: drag Compressor/Pro EQ from Browser |
| 17 | fx_chain_presets | doc | yes | FX Chains in Browser |
| 18 | browser_instruments | keyboard | yes | F6 |
| 18 | add_instrument_track | menu_uia | yes |  |
| 18 | load_impact_presence_mojito_maitai | user | no | USER: Browser drag or Output dropdown |
| 18 | multi_instrument | user | no | USER: Multi Instruments folder |
| 18 | instrument_editor | keyboard | yes | Shift+F11 |
| 19 | studio_one_plus | user | no | USER: account/cloud |
| 19 | doc_only | doc | yes |  |
| 20 | video_track | user | no | USER/Pro: Video Track / import video |
| 20 | doc_only | doc | yes |  |
| 21 | save | keyboard | yes | Ctrl+S |
| 21 | save_as | keyboard | no | skip dialog spam — USER if needed |
| 21 | import_file_menu | menu_uia | yes | opened/dismissed |
| 21 | export_mixdown | keyboard | yes | Ctrl+E Esc |
| 21 | export_midi_part | user | no | USER: right-click Part → Export Selection |
| 21 | aaf_zip | user | no | USER: File Convert To |
| 22 | help_keyboard_shortcuts | keyboard | yes | F1 help attempt |
| 22 | find_command | keyboard | yes | Ctrl+K |
| 22 | catalog_complete | doc | yes | full manual chapter pass logged |

## Method counts

- keyboard: 65
- midi_mcu: 9
- user: 31
- doc: 13

## Gaps requiring you

- **02/skip_activation_ui**: USER: my.presonus / content install if needed
- **03/audio_io_matrix**: USER: Song Setup Audio I/O if routing wrong
- **04/performance_monitor**: USER: View → Performance if needed
- **05/show_page**: USER/Pro: File New Show
- **05/project_page**: USER/Pro: File New Project
- **06/step_record**: USER: Editor Step enable
- **06/import_midi_file**: USER: Song→Import File or Browser drag
- **07/comping_layers**: USER: Record Takes to Layers
- **07/timestretch**: USER: Alt+edge drag
- **08/score_view_toggle**: USER: Note Editor Score button
- **08/notion_send**: USER: Song→Send to Notion
- **09/load_instrument_drag**: USER: drag from Instruments to Arrange
- **10/pack_folder**: USER: right-click Pack Folder
- **10/arranger_track**: USER: Arranger Track button
- **10/chord_track**: USER: Chord Track (Pro features vary)
- **10/tempo_track**: USER: Tempo Track button
- **10/signature_track**: USER: Signature Track button
- **10/scratch_pad**: USER: Scratch Pad button
- **11/export_stems**: USER: Song→Export Stems
- **12/atmos_setup**: USER/Pro: Spatial Audio / Atmos config
- **13/new_show**: USER: File→New→Show (avoid leaving Song)
- **14/automation_modes**: USER: Read/Touch/Latch/Write on channel
- **15/midi_learn_map**: USER: External panel MIDI Learn
- **16/project_page**: USER/Pro: New Project / Add Song to Project
- **17/insert_fx_drag**: USER: drag Compressor/Pro EQ from Browser
- **18/load_impact_presence_mojito_maitai**: USER: Browser drag or Output dropdown
- **18/multi_instrument**: USER: Multi Instruments folder
- **19/studio_one_plus**: USER: account/cloud
- **20/video_track**: USER/Pro: Video Track / import video
- **21/save_as**: skip dialog spam — USER if needed
- **21/export_midi_part**: USER: right-click Part → Export Selection
- **21/aaf_zip**: USER: File Convert To