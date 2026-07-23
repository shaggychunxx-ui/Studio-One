"""Load / save project settings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
SETTINGS_PATH = CONFIG_DIR / "settings.json"
MAPS_PATH = CONFIG_DIR / "plugin_maps.json"

DEFAULTS: dict[str, Any] = {
    "midi_out_port": "S1 Controller 1",
    "midi_in_port": "S1 Controller 0",
    "api_host": "127.0.0.1",
    "api_port": 8765,
    "mcu_channels": 8,
}


def load_settings() -> dict[str, Any]:
    data = dict(DEFAULTS)
    if SETTINGS_PATH.is_file():
        try:
            file_data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(file_data, dict):
                data.update(file_data)
        except Exception:
            pass
    return data


def save_settings(settings: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    merged = dict(DEFAULTS)
    merged.update(settings)
    SETTINGS_PATH.write_text(json.dumps(merged, indent=2), encoding="utf-8")
