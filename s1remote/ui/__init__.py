"""Studio One UI driver — inspect, Find Command, UIA, named-region clicks."""

from .catalog import UI_COMMANDS, coverage, search
from .driver import S1UI, SHOT_DIR
from .layout import REGIONS, list_regions
from .window import WindowInfo, attach, restore_and_focus, studio_one_hwnd

__all__ = [
    "S1UI",
    "SHOT_DIR",
    "UI_COMMANDS",
    "REGIONS",
    "WindowInfo",
    "attach",
    "restore_and_focus",
    "studio_one_hwnd",
    "coverage",
    "search",
    "list_regions",
]
