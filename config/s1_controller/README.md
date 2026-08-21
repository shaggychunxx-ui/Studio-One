# Software S1 Controller (templates)

Copied onto this PC by `py -3.12 -m s1remote setup --apply` (Studio One must be closed).

| File | Role |
|------|------|
| `S1 Notes.device` | Studio One Keyboard device (instrument notes) |
| `S1 Notes.surface.xml` | Control Link knobs CC 20–35 |

Mackie Control uses the built-in PreSonus class `{EE428900-E2B0-477a-B27C-2730D0F373B7}` — no user `.device` file.

See `tools/install_s1_controller.py` and `S1_NOTES_PORT_SETUP.md`.
