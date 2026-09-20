"""
Watches the project for file changes and auto-deploys to Cloud Run.
Debounces rapid saves: deploys once after edits settle for IDLE_SECONDS.

Usage: python watch_deploy.py
"""

import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).parent
IDLE_SECONDS = 10
IGNORE_DIRS = {".git", "__pycache__", ".venv", "venv"}
DEPLOY_CMD = [
    "gcloud", "run", "deploy", "email-assistant",
    "--source", ".",
    "--region", "us-central1",
    "--project", "email-assistant-508816",
]


def snapshot():
    latest = {}
    for path in ROOT.rglob("*"):
        if path.is_dir() or any(part in IGNORE_DIRS for part in path.parts):
            continue
        try:
            latest[path] = path.stat().st_mtime
        except OSError:
            continue
    return latest


def deploy():
    print("\n--- change settled, deploying ---")
    subprocess.run(DEPLOY_CMD, cwd=ROOT, check=False)
    print("--- deploy done, watching for changes ---\n")


def main():
    print(f"Watching {ROOT} for changes (deploy after {IDLE_SECONDS}s idle)...")
    last_snapshot = snapshot()
    dirty_since = None

    while True:
        time.sleep(2)
        current = snapshot()

        if current != last_snapshot:
            last_snapshot = current
            dirty_since = time.time()
            continue

        if dirty_since is not None and time.time() - dirty_since >= IDLE_SECONDS:
            deploy()
            dirty_since = None
            last_snapshot = snapshot()


if __name__ == "__main__":
    main()
