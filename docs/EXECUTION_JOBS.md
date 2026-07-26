# Execution jobs (Studio One = hands)

**Studio One / s1-remote executes. Music-producer decides.**

Do not put production phases, pocket approval, or creative policy in this repo
(except running jobs written by producer / autonomous_run).

## Contract

| Who | Owns | Writes | Reads |
|-----|------|--------|--------|
| **Music-producer** | What/when, gates, NOTES, compose, recipes | `GATES.txt`, `NOTES.txt`, `MIDI/*`, `s1_jobs/current.json` | `s1_jobs/last_result.json` |
| **Studio-One** | How: MCU, notes, hotkeys, eyes, ears | `s1_jobs/last_result.json`, `_vision/` | `s1_jobs/current.json`, `MIDI/*`, `tracks.json` |

## Run

```bat
cd %USERPROFILE%\Documents\GitHub\Studio-One
set PYTHONPATH=%CD%;%CD%\tools
set S1_SONG_DIR=D:\Songs\MySong
py -3.12 tools\setup_check.py
py -3.12 tools\execute_job.py --no-prompt
py -3.12 tools\autonomous_run.py --name MySong --max-sec 40
```

## Job ops

| op | Meaning |
|----|---------|
| `check_setup` | Ports + S1 running |
| `ensure_workspace` | MIDI/ `_vision/` `s1_jobs/` + UI gate |
| `create_tracks` | UIA Add Instrument Track × N |
| `browser_load` | Best-effort browser search (optional) |
| `stream_record` | arm_and_verify → Record → stream mid → Stop + eyes/ears |
| `import_midi` | Best-effort import path |
| `transport` | play / stop / record / rewind |
| `set_fader` | MCU fader by channel/track/role |
| `set_pan` | MCU vpot delta (best-effort) |
| `mix_balance` | Role fader map (preset or levels) |
| `export_mixdown` | Ctrl+E export intent + Masters/ dir |
| `play_listen` | Play + ears capture |
| `ears_check` | Peak/RMS threshold check |
| `program_change` | MIDI program change on notes port |
| `save` / `sleep` / `shot` / `report` / `rewind` / `stop` | utilities |

Schema: `tools/s1_tools/job_schema.py`.

## Anti-patterns

- Do not lock `GATES.txt` from Studio-One tools.
- Do not invent next creative step here — return escalate/result only.
- Do not thrash arm more than 3 times; use import fallback.
