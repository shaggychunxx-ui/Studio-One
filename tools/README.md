# S1 tools (path-agnostic)

Producer automation for an **open** Studio One Song. No hardcoded user paths or song names.

## Env

| Variable | Purpose |
|----------|---------|
| `S1_REMOTE` | Root of this repo (optional if you run from checkout) |
| `S1_SONG_DIR` | Song folder (`MIDI/`, optional `_vision/`) |

## Eyes (producer UI watch)

Screenshots under `<song>/_vision/arm_watch/` (or `--eyes-dir`).  
Use when UIA cannot see Rec buttons or clips. See `docs/ARM_RECORD_LESSONS.md`.

Requires: `pillow` for grabs.

## Tools

| Script | Role |
|--------|------|
| `create_s1_tracks.py` | Menu **Track → Add Instrument Track** |
| `import_and_verify_midi.py` | File import `.mid` (no live arm) |
| `run_pocket_watched.py` | Stream drums/bass with eyes |
| `pipeline_monitored.py` | Phased status / compose lead / stream |

## Examples

```bat
cd %S1_REMOTE%
set PYTHONPATH=%CD%
set S1_SONG_DIR=D:\Studio One\Songs\MySong

py -3.12 tools\create_s1_tracks.py --count 2
py -3.12 tools\import_and_verify_midi.py --files drums.mid bass.mid
py -3.12 tools\run_pocket_watched.py --user-armed
py -3.12 tools\pipeline_monitored.py --phase=status
py -3.12 tools\pipeline_monitored.py --phase=stream-drums --armed
```

## Preference

Prefer **S1-first** control split in `docs/S1_UI_PIPELINE.md`.  
Standing music process: Music-producer `production-workflow-knowledge/PRODUCTION_WORKFLOW.md`.
