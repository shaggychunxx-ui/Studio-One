"""
Bridge to in-host Studio One package (Full Control macros).

Python writes a request JSON; user (or bound hotkey) runs the host task
"S1 Full Control: Process Queue" which executes Host.Objects / interpretCommand
inside Studio One — the only way to set faders by index, mute by channel list, etc.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

# Drop folder visible to S1 package (Documents is always readable by S1)
QUEUE_DIR = Path.home() / "Documents" / "Studio One" / "S1FullControl"
QUEUE_FILE = QUEUE_DIR / "queue.json"
RESULT_FILE = QUEUE_DIR / "result.json"


def ensure_queue_dir() -> Path:
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    return QUEUE_DIR


def enqueue(task: str, **params: Any) -> str:
    """Append a host task. Returns request id."""
    ensure_queue_dir()
    rid = uuid.uuid4().hex[:12]
    item = {"id": rid, "task": task, "params": params, "ts": time.time()}
    q: List[dict] = []
    if QUEUE_FILE.exists():
        try:
            q = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
            if not isinstance(q, list):
                q = []
        except Exception:
            q = []
    q.append(item)
    QUEUE_FILE.write_text(json.dumps(q, indent=2), encoding="utf-8")
    return rid


def read_results() -> List[dict]:
    if not RESULT_FILE.exists():
        return []
    try:
        data = json.loads(RESULT_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def package_install_hint() -> str:
    return (
        f"Install host package from s1-remote/host_package/ then run menu:\n"
        f"  Scripts / Macros → S1 Full Control: Process Queue\n"
        f"Queue file: {QUEUE_FILE}\n"
        f"Results:    {RESULT_FILE}"
    )
