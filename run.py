"""One command: ingest (if needed) -> start the service -> run the evaluation -> stop.

    python run.py              # full pipeline, writes eval/results.md
    python run.py serve        # ingest if needed, then just run the API on :8000
    python run.py --reingest   # force a rebuild of the index
    python run.py --repeat 3   # extra passes for steadier latency percentiles
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from app import config  # noqa: E402


def index_is_stale() -> bool:
    if not config.INDEX_PATH.exists():
        return True
    built = config.INDEX_PATH.stat().st_mtime
    return any(p.stat().st_mtime > built for p in config.CORPUS_DIR.glob("*.pdf"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", nargs="?", default="all", choices=["all", "serve"])
    ap.add_argument("--reingest", action="store_true")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key.")
        return 1

    if args.reingest or index_is_stale():
        print("== Ingesting corpus/")
        subprocess.run([sys.executable, "-m", "app.ingest"], cwd=ROOT, check=True)
    else:
        print("== Index is up to date (use --reingest to rebuild)")

    server_cmd = [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(args.port), "--log-level", "info"]
    if args.command == "serve":
        return subprocess.call(server_cmd, cwd=ROOT)

    print("== Starting service")
    server = subprocess.Popen(server_cmd, cwd=ROOT)
    try:
        url = f"http://127.0.0.1:{args.port}"
        for _ in range(120):
            try:
                if httpx.get(f"{url}/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if server.poll() is not None:
                print("Service exited during startup")
                return 1
            time.sleep(0.5)
        else:
            print("Service did not become healthy within 60s")
            return 1
        print("== Running evaluation")
        return subprocess.call([sys.executable, "eval/evaluate.py", "--url", url, "--repeat", str(args.repeat)], cwd=ROOT)
    finally:
        server.terminate()
        server.wait(timeout=10)


if __name__ == "__main__":
    sys.exit(main())
