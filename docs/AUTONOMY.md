# Autonomy path (Studio One hands)

## Single command (after one-time Template + loopMIDI)

```bat
cd %USERPROFILE%\Documents\GitHub\Studio-One
set PYTHONPATH=%CD%;%CD%\tools
py -3.12 tools\setup_check.py
py -3.12 tools\autonomous_run.py --name AutoSong --parts drums,bass,lead --max-sec 40
```

Or from Music-producer (brain drives hands):

```bat
cd %USERPROFILE%\Documents\GitHub\Music-producer\song-creation-pipeline-github-agent
python -m song_pipeline_kb run-unattended --song-dir "PATH\Songs\AutoSong" --genre dark_pulse --max-sec 40
```

## Overnight queue (one song at a time)

```bat
py -3.12 tools\overnight_queue.py --names SongA,SongB --max-sec 40 --prefer-import
```

## Policy split

| Mode | Who | Gates |
|------|-----|-------|
| taste | human listen | pocket/lead locked by user |
| unattended | metrics + QC | capture gates auto-lock when conf high |

## UCNET status (P3)

- UDP discovery: working (`s1remote ucnet-discover`)
- TCP param session: **not finished** — do not block autonomy on UCNET
- See `re/UCNET_PROTOCOL.md` and `re/FINDINGS.md`
- Path to completion: capture official Remote app traffic with `re/passive_session_sniff.py`

## Job ops added for quality

`mix_balance`, `set_fader`, `export_mixdown`, `ears_check`, `transport`, `program_change`, `sleep`
