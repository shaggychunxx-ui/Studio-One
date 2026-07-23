from __future__ import annotations

import re
from pathlib import Path

ROOTS = [
    Path(__file__).parent / "macros_pkg" / "unzipped",
    Path(__file__).parent / "toolset" / "unzipped",
    Path(__file__).parent / "musicedit" / "unzipped",
    Path(__file__).parent / "trackedit" / "unzipped",
]


def main() -> None:
    apis: set[str] = set()
    cmds: set[str] = set()
    for root in ROOTS:
        if not root.is_dir():
            continue
        for p in root.rglob("*.js"):
            t = p.read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r"Host\.[A-Za-z0-9_.]+", t):
                apis.add(m.group(0))
            for m in re.finditer(
                r'interpretCommand\s*\(\s*"([^"]+)"\s*,\s*"([^"]+)"', t
            ):
                cmds.add(f"{m.group(1)} / {m.group(2)}")
    print("=== Host APIs ===")
    for a in sorted(apis):
        print(a)
    print("=== Commands ===")
    for c in sorted(cmds):
        print(c)


if __name__ == "__main__":
    main()
