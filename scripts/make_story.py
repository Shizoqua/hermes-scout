"""Render docs/story.mp4: a short, silent widescreen video that tells what hermes-scout does.

The story follows one real question through the synthetic benchmark project: keyword search misses
the answer, hermes-scout puts it first, an exact error code still works, and the measured benchmark
numbers close it. Every result, score and line range is copied from the recorded session in
docs/demo.cast and the benchmark workflow; nothing is invented. Each scene is an HTML page in the
same style as the README pictures, screenshotted with Playwright and joined with ffmpeg crossfades:

    python scripts/make_story.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from make_visuals import QUESTION, item, page, tile  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FADE = 0.35  # seconds of crossfade between frames

STORY_CSS = """
body { width: 1280px; height: 720px; padding: 0 90px; display: flex; flex-direction: column; justify-content: center;
       background: radial-gradient(900px 600px at 50% 0%, #1d1530, #000 70%); }
.kicker { font-size: 20px; font-weight: 700; letter-spacing: 3px; text-transform: uppercase; color: #c084fc;
          margin-bottom: 14px; }
.big { font-size: 54px; font-weight: 800; letter-spacing: -1px; line-height: 1.1; }
.lead { font-size: 26px; color: #a1a1aa; margin-top: 14px; }
.fold { margin-top: 30px; }
.it b { font-size: 22px; } .it span { font-size: 19px; }
.it .tag { font-size: 17px; }
.it .score { font-family: "DejaVu Sans Mono", monospace; font-size: 26px; font-weight: 700; color: #4ade80; }
.dim { opacity: 0.38; }
.center { text-align: center; align-items: center; }
.stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; margin-top: 34px; }
.stat { background: #1c1c1e; border-radius: 28px; padding: 28px; }
.stat b { display: block; font-size: 64px; font-weight: 800; color: #4ade80; letter-spacing: -1px; }
.stat span { font-size: 21px; color: #d4d4d8; }
.cmd { font-family: "DejaVu Sans Mono", monospace; font-size: 24px; background: #1c1c1e; border-radius: 20px;
       padding: 18px 26px; margin-top: 14px; text-align: left; }
.cmd i { color: #c084fc; font-style: normal; }
.quote { font-family: "DejaVu Sans Mono", monospace; font-size: 21px; line-height: 1.6; color: #e4e4e7;
         background: #1c1c1e; border-radius: 24px; padding: 26px 30px; margin-top: 26px; }
.quote mark { background: #14532d; color: #bbf7d0; border-radius: 6px; padding: 0 4px; }
"""


def scene(body: str) -> str:
    return page(body, STORY_CSS)


def result(icon: str, color: str, path: str, note: str, score: str, extra: str = "", dim: bool = False) -> str:
    html = item(
        icon,
        color,
        f'<span class="mono" style="color:#fff;font-size:21px">{path}</span>',
        note,
        extra or f'<span class="score">{score}</span>',
    )
    return html.replace('class="it"', 'class="it dim"', 1) if dim else html


def frames() -> list[tuple[str, float]]:
    """(HTML, seconds on screen) for every frame of the story."""
    out: list[tuple[str, float]] = []
    title = (
        f'<div class="center" style="display:flex;flex-direction:column">{tile("search", "purple", 130)}'
        '<div class="big" style="margin-top:34px;font-size:72px">hermes-scout</div>'
        '<div class="lead">Search your files by meaning, not just keywords.</div></div>'
    )
    out.append((scene(title), 2.6))

    words = QUESTION.split()
    ask = '<div class="kicker">The question</div><div class="big">&ldquo;{}&rdquo;</div>'
    for count in (3, 6, len(words)):
        out.append((scene(ask.format(" ".join(words[:count]))), 0.6 if count < len(words) else 2.2))
    lead = (
        '<div class="lead">The answer is in docs/backups.md, '
        "but it never says &ldquo;copy&rdquo; or &ldquo;lost&rdquo;.</div>"
    )
    out.append((scene(ask.format(QUESTION) + lead), 2.8))

    head = '<div class="kicker">Keyword search</div><div class="big">Matches words, not meaning</div>'
    missed = [
        ("doc", "blue", "src/uploads/images.py:1-16", "Processing for pictures people attach to tasks."),
        ("doc", "blue", "src/storage/cache.py:1-19", "Read-through cache in front of the primary store."),
        ("doc", "blue", "notes/hiring.md:1-8", "# Backend engineer interview loop"),
    ]
    for shown in range(1, 4):
        rows = "".join(result(i, c, p, n, "", '<span class="tag bad">no</span>') for i, c, p, n in missed[:shown])
        out.append((scene(head + f'<div class="fold">{rows}</div>'), 0.5 if shown < 3 else 0.3))
    verdict = '<div class="lead" style="color:#fda4af">docs/backups.md is not in the results at all.</div>'
    rows = "".join(result(i, c, p, n, "", '<span class="tag bad">no</span>') for i, c, p, n in missed)
    out.append((scene(head + f'<div class="fold">{rows}</div>' + verdict), 2.8))

    head = '<div class="kicker">hermes-scout</div><div class="big">Ranks by meaning</div>'
    found = [
        ("check", "green", "docs/backups.md:1-15", "# Backups and restores", "0.63"),
        ("code", "blue", "src/storage/cache.py:1-19", "Read-through cache in front of the primary store.", "0.57"),
        ("doc", "purple", "notes/meeting-2026-05-12.md:1-15", "# Platform meeting, 12 May", "0.54"),
    ]
    for shown in range(1, 4):
        rows = "".join(result(*row, dim=index > 0) for index, row in enumerate(found[:shown]))
        out.append((scene(head + f'<div class="fold">{rows}</div>'), 0.5 if shown < 3 else 0.3))
    verdict = '<div class="lead" style="color:#86efac">The right file first, with the line range to cite.</div>'
    rows = "".join(result(*row, dim=index > 0) for index, row in enumerate(found))
    out.append((scene(head + f'<div class="fold">{rows}</div>' + verdict), 3.0))

    quote = (
        '<div class="kicker">docs/backups.md, lines 1-15</div><div class="big">Same meaning, other words</div>'
        '<div class="quote"># Backups and restores<br><br>'
        "A scheduled job runs <mark>pg_dump</mark> at 02:00 UTC for every region<br>"
        "and uploads the compressed file to object storage.<br>"
        "<mark>Files are kept for 30 days</mark>, then expire automatically.</div>"
    )
    out.append((scene(quote), 3.4))

    head = '<div class="kicker">Exact names still work</div><div class="big">E4021</div>'
    codes = [
        (
            "check",
            "green",
            "src/billing/errors.py:1-17",
            "Error codes shown to customers on the billing pages.",
            "0.56",
        ),
        ("doc", "red", "docs/incident-2026-03.md:1-17", "# Postmortem: 14 March outage", "0.46"),
    ]
    rows = "".join(result(*row, dim=index > 0) for index, row in enumerate(codes))
    out.append((scene(head + f'<div class="fold">{rows}</div>'), 3.0))

    stats = (
        '<div class="kicker">Measured, not claimed</div><div class="big">30 questions, real model</div>'
        '<div class="stats"><div class="stat"><b>93%</b><span>right file first</span></div>'
        '<div class="stat"><b>100%</b><span>right file in the top five</span></div>'
        '<div class="stat"><b>89%</b><span>first on reworded questions, against 39% for keywords</span></div></div>'
    )
    out.append((scene(stats), 3.6))

    end = (
        f'<div class="center" style="display:flex;flex-direction:column">{tile("search", "purple", 96)}'
        '<div class="big" style="margin-top:24px">Try it on your own files</div>'
        '<div style="width:880px;margin-top:22px">'
        '<div class="cmd"><i>$</i> hermes plugins install Shizoqua/hermes-scout</div>'
        '<div class="cmd"><i>$</i> pipx install hermes-scout</div></div>'
        '<div class="lead" style="font-size:22px">github.com/Shizoqua/hermes-scout</div></div>'
    )
    out.append((scene(end), 4.5))
    return out


RENDER = """
const { chromium } = require('playwright');
(async () => {
  const jobs = JSON.parse(process.argv[1]);
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1.5 });
  for (const job of jobs) {
    await page.goto('file://' + job.src);
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: job.out });
  }
  await browser.close();
})();
"""


def poster() -> str:
    """The README thumbnail: the title frame with a play button."""
    play = (
        '<div style="width:96px;height:96px;border-radius:50%;background:rgba(255,255,255,.12);display:flex;'
        'align-items:center;justify-content:center;margin-top:34px"><svg width="40" height="40" viewBox="0 0 24 24">'
        '<path d="M8 5v14l11-7z" fill="white"/></svg></div>'
    )
    return scene(
        f'<div class="center" style="display:flex;flex-direction:column">{tile("search", "purple", 120)}'
        '<div class="big" style="margin-top:30px;font-size:68px">hermes-scout</div>'
        '<div class="lead">Search your files by meaning, not just keywords.</div>'
        f'{play}<div class="lead" style="font-size:20px;margin-top:14px">Watch the 30-second demo</div></div>'
    )


def main() -> int:
    story = frames()
    with tempfile.TemporaryDirectory() as tmp:
        jobs = []
        for number, (html, _) in enumerate(story):
            source = Path(tmp) / f"{number:03d}.html"
            source.write_text(html, encoding="utf-8")
            jobs.append({"src": str(source), "out": str(Path(tmp) / f"{number:03d}.png")})
        cover = Path(tmp) / "poster.html"
        cover.write_text(poster(), encoding="utf-8")
        jobs.append({"src": str(cover), "out": str(ROOT / "docs" / "story-poster.png")})
        env = dict(os.environ)
        if "NODE_PATH" not in env:
            npm_root = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True, check=False).stdout.strip()
            env["NODE_PATH"] = npm_root
        subprocess.run(["node", "-e", RENDER, json.dumps(jobs)], check=True, env=env)

        inputs: list[str] = []
        for job, (_, seconds) in zip(jobs[:-1], story, strict=True):
            inputs += ["-loop", "1", "-framerate", "30", "-t", f"{seconds + FADE:.2f}", "-i", job["out"]]
        chain, offset, last = [], 0.0, "0:v"
        for number in range(1, len(story)):
            offset += story[number - 1][1]
            label = f"v{number}"
            chain.append(f"[{last}][{number}:v]xfade=transition=fade:duration={FADE}:offset={offset:.2f}[{label}]")
            last = label
        chain.append(f"[{last}]format=yuv420p[out]")
        target = ROOT / "docs" / "story.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                *inputs,
                "-filter_complex",
                ";".join(chain),
                "-map",
                "[out]",
                "-c:v",
                "libx264",
                "-crf",
                "20",
                "-preset",
                "slow",
                "-movflags",
                "+faststart",
                str(target),
            ],
            check=True,
        )
    total = sum(seconds for _, seconds in story)
    print(f"wrote docs/story.mp4 ({len(story)} frames, {total:.0f} s, {target.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
