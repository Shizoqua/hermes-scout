"""Record a real hermes-scout terminal session as an asciicast (v2) for docs/demo.

Runs each command below against the synthetic project in ``benchmarks/corpus`` with a real
embeddings server, and writes what the terminal showed, with real output timings. The commands are
typed at a steady pace in the recording (the typing is the only simulated part); everything printed
after a command is the command's actual output, at the time it arrived.

    python scripts/record_demo.py --base-url http://localhost:11434/v1 --model nomic-embed-text > demo.cast

Standard library only. ``scripts/render_demo.py`` turns the cast into the GIF and MP4.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUESTION = "how do we keep a copy of the database in case it gets lost"
SCENES = [
    ["doctor"],
    ["search", QUESTION, "benchmarks/corpus", "--ranking", "keyword", "-k", "3"],
    ["search", QUESTION, "benchmarks/corpus", "-k", "3"],
    ["search", "E4021", "benchmarks/corpus", "-k", "2"],
    ["similar", "src/auth/tokens.py", "--in", "benchmarks/corpus", "-k", "3"],
]
TYPE_DELAY = 0.04  # seconds per typed character
PAUSE_AFTER = 1.8  # seconds to rest on each command's output


def _shown(argv: list[str]) -> str:
    return "hermes-scout " + " ".join(f'"{a}"' if " " in a else a for a in argv)


def record(base_url: str, model: str) -> list[list[object]]:
    events: list[list[object]] = []
    clock = 0.0
    env = {**os.environ, "SCOUT_BASE_URL": base_url, "SCOUT_MODEL": model, "PYTHONPATH": str(ROOT)}
    with tempfile.TemporaryDirectory() as tmp:
        index = str(Path(tmp) / "index.db")
        for argv in SCENES:
            events.append([round(clock, 3), "o", "\x1b[38;5;141m$\x1b[0m "])
            for char in _shown(argv):
                clock += TYPE_DELAY
                events.append([round(clock, 3), "o", char])
            events.append([round(clock, 3), "o", "\r\n"])
            started = time.monotonic()
            proc = subprocess.Popen(
                [sys.executable, "-m", "hermes_scout.cli", *argv, "--index", index],
                cwd=ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                at = clock + (time.monotonic() - started)
                text = line.replace(index, "~/.cache/hermes-scout/index.db").replace("\n", "\r\n")
                events.append([round(at, 3), "o", text])
            proc.wait()
            clock += time.monotonic() - started
            events.append([round(clock, 3), "o", "\r\n"])
            clock += PAUSE_AFTER
    events.append([round(clock, 3), "o", ""])
    return events


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://localhost:11434/v1")
    parser.add_argument("--model", default="nomic-embed-text")
    args = parser.parse_args()
    header = {"version": 2, "width": 104, "height": 30, "title": "hermes-scout", "env": {"TERM": "xterm-256color"}}
    print(json.dumps(header))
    for event in record(args.base_url, args.model):
        print(json.dumps(event, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
