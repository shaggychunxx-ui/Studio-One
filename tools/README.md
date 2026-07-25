# S1 tools (path-agnostic)

Producer automation for an **open** Studio One Song. No hardcoded user paths or song names.

## Env

| Variable | Purpose |
|----------|---------|
| `S1_REMOTE` | Root of this repo (optional if you run from checkout) |
| `S1_SONG_DIR` | Song folder (`MIDI/`, optional `_vision/`) after Save As |
| `S1_TEMPLATE_SONG` | Override Template.song path |
| `S1_SONGS_ROOT` | Override Songs parent folder |

## Song start policy (required)

1. Open `Documents\Studio One\Songs\Template\Template.song`
2. **Save As** a new song name (never write into Template)
3. Set `S1_SONG_DIR` to the new folder
4. Only then run production (MIDI, arm, stream, mix)

```bat
cd %S1_REMOTE%
set PYTHONPATH=%CD%;%CD%\tools
py -3.12 tools\start_from_template.py --name "MySong"
:: then
set S1_SONG_DIR=...\Songs\MySong
py -3.12 tools\execute_job.py
```

Or one shot: `py -3.12 tools\live_make_song.py --from-template --name "MySong"`

## Eyes (producer UI watch)

Screenshots under `<song>/_vision/arm_watch/` (or `--eyes-dir`).  
Use when UIA cannot see Rec buttons or clips. See `docs/ARM_RECORD_LESSONS.md`.

Requires: `pillow` for grabs.

## Tools

| Script | Role |
|--------|------|
| **`start_from_template.py`** | **Open Template → Save As new song → set S1_SONG_DIR** |
| **`produce.py`** | **Orchestrator: template → one-part jobs → live eyes/ears** |
| **`execute_job.py`** | **Run producer `s1_jobs/current.json` (eyes + ears)** |
| `live_make_song.py` | Compose + stream (`--from-template` for full start) |
| `diagnose_arm.py` | Rec-arm offline/live diagnosis |
| `create_s1_tracks.py` | Menu **Track → Add Instrument Track** |
| `import_and_verify_midi.py` | File import `.mid` (no live arm) |
| `run_pocket_watched.py` | Stream drums/bass with eyes |
| `pipeline_monitored.py` | Phased status / compose lead / stream |

Job schema: `s1_tools/job_schema.py`. Sensors: `eyes.py`, `ears.py`, `vision.py`.  
See `docs/EXECUTION_JOBS.md`.

## Examples

```bat
cd %S1_REMOTE%
set PYTHONPATH=%CD%;%CD%\tools

py -3.12 tools\start_from_template.py --name MySong
call %S1_SONG_DIR%\s1_jobs\set_song_env.cmd

py -3.12 tools\create_s1_tracks.py --count 2
py -3.12 tools\import_and_verify_midi.py --files drums.mid bass.mid
py -3.12 tools\run_pocket_watched.py --user-armed
py -3.12 tools\pipeline_monitored.py --phase=status
py -3.12 tools\pipeline_monitored.py --phase=stream-drums --armed
```

## Preference

Prefer **S1-first** control split in `docs/S1_UI_PIPELINE.md`.  
Standing music process: Music-producer `production-workflow-knowledge/PRODUCTION_WORKFLOW.md`.
