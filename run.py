"""Entry point for the Dynamic DAG Multi-Agent Code Generation Studio.

Usage:
    py run.py            # starts on http://127.0.0.1:8000
    py run.py --port 9000
"""
from __future__ import annotations

import argparse
import sys

import uvicorn


def main() -> None:
    # Windows consoles default to cp1252; force UTF-8 for the banner.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

    parser = argparse.ArgumentParser(description="DAG Multi-Agent Code Generation Studio")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    from dag_studio.config import settings

    host = args.host or settings.host
    port = args.port or settings.port
    print(f"\n  DAG Multi-Agent Code Generation Studio")
    print(f"  → http://{host}:{port}   (mode: {settings.mode}, model: {settings.model})\n")
    uvicorn.run("dag_studio.main:app", host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
