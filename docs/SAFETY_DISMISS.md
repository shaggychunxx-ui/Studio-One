# Studio One Safety dialog dismiss

## Why this exists

Task **085** on AI-CODING failed produce with `primary_cause=safety_dialog_blocking`.
Window titles stayed `Studio One` + `Studio One Safety`. Old `dismiss_safety_dialog`
only invoked UIA Button name exactly `Start` and still matched **invisible/stale**
UIA nodes, so the gate never cleared.

Safety (PreSonus Startup/Recovery Options) appears after a crash/force-quit, or if
SHIFT is held at launch. Start is bottom-right; Create Diagnostics Report is
bottom-left (green) — never click that for automation.

## Code

| Function | File | Role |
|----------|------|------|
| `detect_safety_dialog_uia` | `tools/s1_tools/vision.py` | Visible + real rect only; UIA+win32 |
| `dismiss_safety_dialog` | same | Multi-strategy: radio, Start button, Enter/Space, bottom-right coords |
| `hard_clear_safety` | same | Kill S1 + delete small crash/recovery markers under PreSonus AppData |
| `dismiss_blocking_dialogs` | `tools/s1_tools/ui_gate.py` | Safety first (2 dismiss passes + hard clear) |
| Boot path | `tools/start_from_template.py` | Dismiss on open; hard clear + relaunch Template if stuck |

## Operator notes (AI-CODING)

1. `git pull` Studio-One before Template produce (need this Safety fix commit).
2. Prefer interactive desktop (not pure RDP-locked session) so `click_input` / coords work.
3. If Safety still loops after hard clear: human opens S1 once, clicks **Start**, save Template, close cleanly (no force kill).
4. Headless masters on GROMIT remain valid if Template produce stays blocked.

## Manual dismiss

In the dialog: leave **Start normally** selected → click **Start** (bottom right).
Do not hold SHIFT while launching Studio One during automation.
