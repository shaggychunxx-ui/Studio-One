# Video import for Studio One (from Mira-Soline ffmpeg)

GROMIT DAW host is **Studio One 6 Artist 6.6.4**. Video Player / Video Track are **Professional-only** (`Music-producer/studio-one-6.6-agent-knowledge/chapters/20-video.md`).

This helper does **not** drive the S1 UI. It makes files the human (or a later Pro install) can drop in.

## Tool

```bat
cd %S1_REMOTE%
py -3.12 tools\prepare_video_for_s1.py CLIP.mp4
py -3.12 tools\prepare_video_for_s1.py CLIP.mp4 --song-dir %S1_SONG_DIR%
py -3.12 tools\prepare_video_for_s1.py CLIP.mp4 --wav-only
```

Writes:

| File | Use |
|------|-----|
| `*.48k.wav` | 48 kHz stereo PCM. **Artist: drag onto an Audio Track.** |
| `*.s1.mp4` | Constant-fps yuv420p h264, no audio. OpenShot / mux / Pro Video Track. |
| `*.s1.json` | Probe + paths. Not git. |

`--song-dir` copies into `<Song>/Media/video-in/` (local media; do not commit).

## Artist (GROMIT)

1. Run the script (wav-only is enough if you only need the soundtrack).
2. In the Song: drag the wav into Arrange as an Audio Track.
3. Compose / mix against it. Bounce the master.
4. Visualizer loop + mux the bounce: Music-producer `python -m clip_edit_kb loop` then `mux`.

Do not expect a Video Track on Artist. Do not invent a menu path for it.

## Professional

1. Same prep (constant fps — mixed frame rates flash black on xfade and confuse S1).
2. Drag `*.s1.mp4` onto the Video Track.
3. Audio Sub-track stays locked; drag it down to Arrange if you need independent edit (manual ch.20).
4. Video Player mute is on by default.

## What stayed in Music-producer

Loop, stitch, RIFE 60fps, grain, QC frames, remux/C2PA strip, mux song onto picture:

```
Documents\GitHub\Music-producer\clip-edit-github-agent
python -m clip_edit_kb info
```

OpenShot NLE (no watermark): `C:\Program Files\OpenShot Video Editor\openshot-qt.exe`. Do not reverse-concat loops there.

## Source

Mira-Soline `scripts/Edit-Video.py` (loop/stitch/RIFE/QC) and `Post-ToX.drop_c2pa` (metadata remux). Mira identity / I2V / adult QC were not copied.
