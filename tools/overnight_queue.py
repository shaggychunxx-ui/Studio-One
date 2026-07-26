#!/usr/bin/env python3
"""
Overnight multi-song queue — one heavy produce job at a time (team CPU rule).

Queue file (JSON list):
  [
    {"name": "Song_A", "parts": "drums,bass,lead", "max_sec": 40},
    {"name": "Song_B", "prefer_import": true}
  ]

Usage:
  py -3.12 tools\\overnight_queue.py --queue path\\to\\queue.json
  py -3.12 tools\\overnight_queue.py --names Auto1,Auto2 --max-sec 30
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_one(item: dict) -> dict:
    name = item.get("name") or f"Auto_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    cmd = [
        sys.executable,
        str(TOOLS / "autonomous_run.py"),
        "--name",
        str(name),
        "--parts",
        str(item.get("parts") or "drums,bass,lead"),
        "--max-sec",
        str(item.get("max_sec") or 40),
    ]
    if item.get("prefer_import"):
        cmd.append("--prefer-import")
    if item.get("seed") is not None:
        cmd.extend(["--seed", str(item["seed"])])
    if item.get("skip_mix"):
        cmd.append("--skip-mix")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + str(TOOLS) + os.pathsep + env.get("PYTHONPATH", "")
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=str(ROOT))
    return {
        "name": name,
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "elapsed_sec": round(time.time() - t0, 1),
        "stdout_tail": (proc.stdout or "")[-1500:],
        "stderr_tail": (proc.stderr or "")[-800:],
        "finished_at": _utc(),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", type=Path, default=None, help="JSON list of song jobs")
    ap.add_argument("--names", default=None, help="Comma song names (simple queue)")
    ap.add_argument("--parts", default="drums,bass,lead")
    ap.add_argument("--max-sec", type=float, default=40.0)
    ap.add_argument("--prefer-import", action="store_true")
    ap.add_argument("--pause-sec", type=float, default=5.0, help="Pause between songs")
    ap.add_argument("--out", type=Path, default=None, help="Write summary JSON")
    args = ap.parse_args()

    items: list[dict] = []
    if args.queue and args.queue.is_file():
        items = json.loads(args.queue.read_text(encoding="utf-8"))
        if not isinstance(items, list):
            raise SystemExit("queue must be a JSON list")
    elif args.names:
        for n in args.names.split(","):
            n = n.strip()
            if n:
                items.append(
                    {
                        "name": n,
                        "parts": args.parts,
                        "max_sec": args.max_sec,
                        "prefer_import": args.prefer_import,
                    }
                )
    else:
        raise SystemExit("Provide --queue or --names")

    summary = {"started_at": _utc(), "jobs": [], "policy": "sequential_one_heavy_at_a_time"}
    for i, item in enumerate(items):
        print(f"=== overnight [{i+1}/{len(items)}] {item.get('name')} ===", flush=True)
        result = run_one(item)
        summary["jobs"].append(result)
        print(json.dumps({"name": result["name"], "ok": result["ok"]}, indent=2), flush=True)
        if i < len(items) - 1 and args.pause_sec > 0:
            time.sleep(args.pause_sec)

    summary["finished_at"] = _utc()
    summary["n_ok"] = sum(1 for j in summary["jobs"] if j.get("ok"))
    summary["n_total"] = len(summary["jobs"])
    out_path = args.out or (ROOT / "config" / f"overnight_{datetime.now().strftime('%Y%m%d_%H%M')}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({"ok": summary["n_ok"] == summary["n_total"], "summary": str(out_path), **{k: summary[k] for k in ("n_ok", "n_total")}}, indent=2))
    return 0 if summary["n_ok"] == summary["n_total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
