# Studio One UI driver

Agent-facing control of the **live Studio One 6 window** — not MIDI, not the in-host queue.

```bat
set PYTHONPATH=%CD%
py -3.12 -m s1remote ui inspect
py -3.12 -m s1remote ui command "Add Instrument Track"
py -3.12 -m s1remote ui do track.add_instrument
py -3.12 -m s1remote ui click-region arrange
py -3.12 -m s1remote ui shot --overlay
```

Python:

```python
from s1remote.ui import S1UI

ui = S1UI()
print(ui.inspect())          # running, title, page, dialogs
ui.command("Add Instrument Track")
ui.do("view.browser")
ui.click_region("browser.search")
ui.type_text("Mai Tai")
ui.drag("browser.result", "arrange.blank")
ui.shot("after_load", overlay=True)
```

Does **not** launch Studio One. GROMIT is the DAW host.

## What each layer is for

| Want | Use | Example |
|------|-----|---------|
| Any named command | **Find Command** (`Ctrl+K`) | `ui command "Export Mixdown"` |
| Known shortcut | catalog hotkey | `ui do view.console` or `ui keys mixer` |
| Menu bar | Alt path | `ui menu "Track>Add>Instrument Track"` |
| Native chrome (OK, menu items) | UIA | `ui tree Rec` then `ui invoke OK` |
| Arrange / transport / browser chrome | named **region** | `ui click-region transport.record` |
| Rec Enable on track N | Rec column (not Monitor) | `ui click-rec 1` |
| Instrument onto arrange | named drag | `ui drag browser.result arrange.blank` |
| Mixer fader / transport MCU | keep **FullControl** | `s1remote transport play` |
| See what happened | screenshot | `ui shot --overlay` |

## Agent playbook

1. `ui inspect` — if `running` is false, stop (do not auto-launch).
2. If `page` is `start` / `safety`, handle that before Song work. Safety: existing `tools/dismiss_safety.py`. Never OK a New dialog mid-session.
3. Prefer **Find Command** or catalog `do` over mouse.
4. Prefer MCU for transport/mix. Use regions only when MIDI cannot do it (browser drop, Rec column, page tabs).
5. After a UI action, `ui shot` (and eyes) — logs are not proof.
6. One click per intent. No grid thrash.

## Catalog / regions

```bat
py -3.12 -m s1remote ui commands track
py -3.12 -m s1remote ui regions browser
```

Region boxes are **client-relative fractions** of the Studio One window (DPI-safe). Rec column uses the same 1920 calibration as `tools/s1_tools/eyes.py` (`REC_X_FRAC`) so clicks stay on Rec Enable, not Monitor.

`--overlay` draws every named box on the screenshot so you can recalibrate `s1remote/ui/layout.py` if chrome moved.

## Honest limits

- Arrange clips, mixer knobs, and browser rows are **custom-drawn**. UIA will not list them. Use Find Command, MCU, named regions, or vision Rec clicks.
- Find Command fires the **first match**. Use the Keyboard Shortcuts name (`Add Instrument Track`, not `add inst`). Empty Find Command + Enter re-fires the last command — on GROMIT that was **Save As Template**. `command()` types the name (does not trust clipboard paste) and Escapes an unexpected Save As Template dialog.
- Named transport clicks are a fallback. MCU is more reliable when loopMIDI is wired.
- `click-rec` without a screenshot is row-pitch math. Compact track headers put Rec around the Mute/Solo cluster, **not** `REC_X_FRAC` 605/1920. Prefer `[R]` on the selected track or `FullControl.arm_and_verify`.
- Studio One 6 **Artist**: File → Save As has **no** default hotkey (`Ctrl+Shift+S` is unbound). Use `ui.save_as_dialog()` / UIA `Save As...`. Do not `Ctrl+S` over Template.
- Mix vs Edit bottom tabs are custom-drawn. F3 does not leave Mix. Find Command `Editor` is the wrong name.
- Launch S1 outside the agent job (background `Start-Process` + `Wait-Process`). A foreground shell job kills Studio One when the command exits.
- `inspect().dialogs` only lists Studio One-titled windows. The Windows **Save As** file dialog will not appear there — screenshot it.

## HTTP (with `s1remote api`)

```
GET  /ui/inspect
GET  /ui/commands?q=track
GET  /ui/regions
POST /ui/command        {"name":"Add Instrument Track"}
POST /ui/do             {"id":"view.browser"}
POST /ui/click-region   {"name":"arrange"}
POST /ui/invoke         {"name":"OK"}
```
