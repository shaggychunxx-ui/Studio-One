# Execution jobs (Studio-One hands)

Music-producer writes `s1_jobs/current.json`. This repo runs it and writes
`s1_jobs/last_result.json` with **visual + audio cues**.

## Roles

| Repo | Role |
|------|------|
| Music-producer | What / when / gates / plan jobs / **observe cues** |
| Studio-One | Execute only + capture eyes/ears evidence |

## Run

```bat
cd C:\Users\Box One\s1-remote
set PYTHONPATH=%CD%
set S1_SONG_DIR=C:\Users\Box One\Documents\Studio One\Songs\YourSong

py -3.12 tools\execute_job.py
py -3.12 tools\execute_job.py --dry-run
py -3.12 tools\execute_job.py --no-prompt --max-sec 8
```

Producer side:

```bat
cd C:\Users\Box One\Documents\GitHub\Music-producer\song-creation-pipeline-github-agent
python -m song_pipeline_kb plan mvp --song-dir "%S1_SONG_DIR%"
python -m song_pipeline_kb observe --song-dir "%S1_SONG_DIR%"
python -m song_pipeline_kb cycle --song-dir "%S1_SONG_DIR%" --execute --max-sec 8
```

## Job ops

| op | Meaning |
|----|---------|
| `check_setup` | S1 Notes + process |
| `ensure_workspace` | Focus S1 + screenshot |
| `create_tracks` | UIA Add Instrument Track |
| `browser_load` | Best-effort browser search |
| `stream_record` | Arm verify → Record → stream MIDI → play+ears |
| `play_listen` | Transport play + ears capture |
| `save` / `rewind` / `stop` / `shot` / `report` | Utilities |

## Evidence in `last_result.json`

- `steps[]` — per-op ok, note_ons, arm flags
- `vision` — any_rec_red, blue_clip_hint, per-shot stats
- `audio[]` — peak/rms dB, activity_ratio, has_signal, wav path
- Screenshots: `<song>/_vision/arm_watch/`
- WAVs: `<song>/_vision/ears/`

## Policy

- **note_ons ≠ recorded** — need Rec red + clip/audio cues
- Producer **never** locks pocket/lead from metrics alone (taste)
- Use `observe` for confidence; user listens for pocket approval
- **Studio One Safety** (crash recovery) is detected via UIA + green-button pixels and auto-dismissed on `ensure_workspace` / preflight
- Eyes: `<song>/_vision/arm_watch/` — programmers must open PNGs, not trust logs alone
- Ears: Realtek loopback via `soundcard` (WASAPI pyaudiowpatch often hangs; skipped with timeout)
