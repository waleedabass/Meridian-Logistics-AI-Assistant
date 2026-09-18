# Runs everything: ingest (if needed) -> start the api -> run the eval -> stop the api
#
#   python run.py              full run, writes eval/results.md
#   python run.py serve        just start the api on :8000
#   python run.py --reingest   rebuild the index even if it looks up to date
#   python run.py --repeat 3   run the questions 3 times (better latency numbers)

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from app import config  # noqa: E402  (needs the sys.path line above)


def index_needs_rebuild():
    if not config.INDEX_PATH.exists():
        return True
    built = config.INDEX_PATH.stat().st_mtime
    for pdf in config.CORPUS_DIR.glob("*.pdf"):
        if pdf.stat().st_mtime > built:
            return True
    return False


def wait_for_server(url, server):
    # poll /health for up to 60 seconds
    for _ in range(120):
        try:
            if httpx.get(url + "/health", timeout=1).status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        if server.poll() is not None:
            print("Service exited during startup")
            return False
        time.sleep(0.5)
    print("Service did not become healthy within 60s")
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs="?", default="all", choices=["all", "serve"])
    parser.add_argument("--reingest", action="store_true")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key.")
        return 1

    if args.reingest or index_needs_rebuild():
        print("== Ingesting corpus/")
        subprocess.run([sys.executable, "-m", "app.ingest"], cwd=ROOT, check=True)
    else:
        print("== Index is up to date (use --reingest to rebuild)")

    server_cmd = [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(args.port), "--log-level", "info"]
    if args.command == "serve":
        return subprocess.call(server_cmd, cwd=ROOT)

    print("== Starting service")
    server = subprocess.Popen(server_cmd, cwd=ROOT)
    url = f"http://127.0.0.1:{args.port}"
    try:
        if not wait_for_server(url, server):
            return 1
        print("== Running evaluation")
        return subprocess.call([sys.executable, "eval/evaluate.py", "--url", url, "--repeat", str(args.repeat)], cwd=ROOT)
    finally:
        server.terminate()
        server.wait(timeout=10)


if __name__ == "__main__":
    sys.exit(main())
