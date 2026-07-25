#!/usr/bin/env python3
"""
Boot Studio One from the standing Template and Save As a new song.

Deprecated ad-hoc song paths — production always:
  Template.song → Save As <new name> → set S1_SONG_DIR

Wrapper around tools/start_from_template.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS.parent))
sys.path.insert(0, str(TOOLS))

from start_from_template import start_new_song_from_template, main as _main


def main() -> int:
    # Pass-through CLI (supports --name, --no-open, …)
    if len(sys.argv) > 1:
        return _main()
    summary = start_new_song_from_template()
    print(json.dumps(summary, indent=2))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
