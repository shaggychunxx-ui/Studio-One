from __future__ import annotations

from datetime import datetime
from pathlib import Path

_log_path: Path | None = None


def set_log_file(path: Path | None) -> None:
    global _log_path
    _log_path = path
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# log start {datetime.now().isoformat()}\n", encoding="utf-8")


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    if _log_path is not None:
        try:
            with _log_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass
