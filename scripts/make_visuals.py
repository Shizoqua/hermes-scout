"""Render the README pictures from the HTML sources in docs/visuals/ to PNG files in docs/.

Each picture is a plain HTML page (open it in a browser to edit it); this script screenshots it at
twice its size with Playwright's Chromium. Needs Node with the ``playwright`` package and a
Chromium it can launch, plus the Inter font installed:

    python scripts/make_visuals.py
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PICTURES = {
    "architecture.html": ("architecture.png", 1600, 720),
    "problem.html": ("problem.png", 1600, 540),
    "solution.html": ("solution.png", 1600, 640),
}

RENDER = """
const { chromium } = require('playwright');
(async () => {
  const jobs = JSON.parse(process.argv[1]);
  const browser = await chromium.launch();
  for (const job of jobs) {
    const page = await browser.newPage({ viewport: { width: job.w, height: job.h }, deviceScaleFactor: 2 });
    await page.goto('file://' + job.src);
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: job.out });
    await page.close();
    console.log('wrote ' + job.name);
  }
  await browser.close();
})();
"""


def main() -> int:
    jobs = []
    for source, (target, width, height) in PICTURES.items():
        path = ROOT / "docs" / "visuals" / source
        if path.exists():
            out = str(ROOT / "docs" / target)
            jobs.append({"src": str(path), "out": out, "w": width, "h": height, "name": f"docs/{target}"})
    env = dict(os.environ)
    if "NODE_PATH" not in env:
        npm_root = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True, check=False).stdout.strip()
        env["NODE_PATH"] = npm_root
    subprocess.run(["node", "-e", RENDER, json.dumps(jobs)], check=True, env=env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
