#!/usr/bin/env python3
"""Keep the Maruvet detail collector running until every listing is saved.

Restarts the collector if it exits early, and if the output file stops growing.
Already collected rows are kept. A partial last line is dropped before restart.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LISTING = ROOT / "data/hospitals/sources/maruvet-hospitals.jsonl"
OUT = ROOT / "data/hospitals/sources/maruvet-details.jsonl"
COLLECTOR = ROOT / "scripts/collect_maruvet_details.py"
LOG = Path("/tmp/maru_watch.log")

STALL_S = 180
POLL_S = 20


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def repair_tail() -> None:
    if not OUT.exists() or OUT.stat().st_size == 0:
        return
    data = OUT.read_bytes()
    if not data.endswith(b"\n"):
        head, sep, _ = data.rpartition(b"\n")
        OUT.write_bytes(head + sep)
        log("dropped partial trailing line")
        data = OUT.read_bytes()
    if not data:
        return
    last = data.rstrip(b"\n").split(b"\n")[-1]
    try:
        json.loads(last)
    except json.JSONDecodeError:
        head, sep, _ = data.rstrip(b"\n").rpartition(b"\n")
        OUT.write_bytes(head + sep)
        log("dropped invalid last json line")


def remaining() -> int:
    wanted = set()
    for line in LISTING.open(encoding="utf-8"):
        if line.strip():
            wanted.add(json.loads(line)["license_id"])
    have = set()
    if OUT.exists():
        for line in OUT.open(encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                have.add(json.loads(line)["license_id"])
            except json.JSONDecodeError:
                continue
    return len(wanted - have)


def kill_group(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    for _ in range(20):
        if proc.poll() is not None:
            return
        time.sleep(0.25)
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait(timeout=10)


def run_once() -> int:
    repair_tail()
    left = remaining()
    if left == 0:
        log("complete")
        return 0
    log(f"starting collector, remaining={left}")
    proc = subprocess.Popen(
        [sys.executable, "-u", str(COLLECTOR)],
        cwd=ROOT,
        start_new_session=True,
    )
    last_size = OUT.stat().st_size if OUT.exists() else 0
    last_change = time.monotonic()
    while True:
        time.sleep(POLL_S)
        code = proc.poll()
        size = OUT.stat().st_size if OUT.exists() else 0
        if size != last_size:
            last_size = size
            last_change = time.monotonic()
        if code is not None:
            left = remaining()
            log(f"collector exited code={code} remaining={left}")
            return 0 if left == 0 else 1
        stalled = time.monotonic() - last_change
        if stalled >= STALL_S:
            log(f"no new data for {int(stalled)}s, restarting collector")
            kill_group(proc)
            return 1


def main() -> None:
    while True:
        code = run_once()
        if code == 0 and remaining() == 0:
            log("watch finished, all listings saved")
            return
        log("restarting in 5s")
        time.sleep(5)


if __name__ == "__main__":
    main()
