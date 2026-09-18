"""Runs main.py on a fixed interval, forever. Used by the Docker container
so it behaves like a self-contained cron without needing cron installed.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

INTERVAL_SECONDS = int(os.environ.get("CHECK_INTERVAL_SECONDS") or str(6 * 3600))
SCRIPT = Path(__file__).parent / "main.py"

if __name__ == "__main__":
    while True:
        print(f"[scheduler] running check at {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
        result = subprocess.run([sys.executable, str(SCRIPT)])
        if result.returncode != 0:
            print(f"[scheduler] main.py exited with code {result.returncode}", flush=True)
        print(f"[scheduler] sleeping {INTERVAL_SECONDS}s", flush=True)
        time.sleep(INTERVAL_SECONDS)
