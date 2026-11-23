"""Render docs/screenshots/*.png from real hermes-scout output on the synthetic benchmark project.

Every command really runs. The index is built with a stand-in embedder (hashed words), so only
output that does not depend on embedding quality is shown: keyword searches and filters. The health
check runs against the real embeddings client with no server running, to show the fix it gives;
only the port is rewritten to Ollama's default. The /scout help is the plugin's own text, and the
benchmark card holds the numbers from the benchmark workflow's real run, laid out as a table.

Run from the repository root with Pillow installed: python scripts/make_screenshots.py
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import re
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hermes_scout import COMMAND_HELP, cli, embeddings  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "docs" / "screenshots"
SCALE = 2
W = 1000
BG, PANEL, BAR = (11, 16, 34), (16, 21, 48), (26, 31, 62)
TEXT, DIM, ACCENT, CYAN, GREEN, RED = (
    (233, 230, 255),
    (143, 139, 179),
    (167, 139, 250),
    (125, 211, 252),
    (74, 222, 128),
    (248, 113, 113),
)
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
UI = "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"
LINE_H = 26


def stand_in_embed(texts: list[str], **_: object) -> list[list[float]]:
    """Hashed bag of words: enough to build an index; never shown as a measure of quality."""
    out = []
    for text in texts:
        vec = [0.0] * 64
        for word in re.findall(r"[a-z0-9_]+", text.lower()):
            vec[int(hashlib.sha256(word.encode()).hexdigest(), 16) % 64] += 1.0
        out.append(vec or [1.0])
    return out


def run(argv: list[str]) -> str:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer), contextlib.suppress(SystemExit):
        cli.main(argv)
    return buffer.getvalue().rstrip()


def colour(line: str) -> tuple[int, int, int]:
    if line.startswith("$ ") or line.startswith("> "):
        return ACCENT
    if line.startswith("FAIL"):
        return RED
    if line.startswith("OK") or line.startswith("All checks"):
        return GREEN
    if re.match(r"\s{2}-\s{2}|\d\.\d\d\s", line):
        return CYAN
    if line.startswith("      ") or line.startswith("usage:"):
        return DIM
    return TEXT


def wrap(text: str, width: int) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines() or [""]:
        indent = re.match(r"\s*", raw).group(0)  # type: ignore[union-attr]
        while len(raw) > width:
            cut = raw.rfind(" ", 0, width)
            cut = cut if cut > len(indent) else width
            lines.append(raw[:cut])
            raw = indent + "  " + raw[cut:].lstrip()
        lines.append(raw)
    return lines


def render(name: str, title: str, text: str, caption: str) -> None:
    mono = ImageFont.truetype(MONO, 17 * SCALE)
    ui = ImageFont.truetype(UI, 15 * SCALE)
    cap = ImageFont.truetype(UI, 17 * SCALE)
    lines = wrap(text, 84)
    h = 150 + LINE_H * len(lines)
    im = Image.new("RGB", (W * SCALE, h * SCALE), BG)
    d = ImageDraw.Draw(im)

    def s(*values: int) -> tuple[int, ...]:
        return tuple(v * SCALE for v in values)

    d.text(s(32, 22), caption, font=cap, fill=TEXT)
    d.rounded_rectangle(s(20, 60, W - 20, h - 20), 18 * SCALE, fill=PANEL, outline=(45, 50, 90))
    d.rounded_rectangle(s(20, 60, W - 20, 100), 18 * SCALE, fill=BAR)
    d.rectangle(s(20, 84, W - 20, 100), fill=BAR)
    for i, dot in enumerate([(255, 95, 87), (254, 188, 46), (40, 200, 64)]):
        d.ellipse(s(44 + i * 22, 74, 56 + i * 22, 86), fill=dot)
    d.text(s(W // 2, 80), title, font=ui, fill=DIM, anchor="mm")
    y = 116
    for line in lines:
        d.text(s(44, y), line, font=mono, fill=colour(line))
        y += LINE_H
    OUT.mkdir(parents=True, exist_ok=True)
    im.save(OUT / f"{name}.png", optimize=True)
    print(f"wrote docs/screenshots/{name}.png")


BENCHMARK = """nomic-embed-text, 23 files, 30 questions with known answers

Ranking    hit@1   hit@5   MRR    exact   mixed   paraphrase
hybrid       93%    100%   0.97    100%    100%      89%
semantic     93%    100%   0.97    100%    100%      89%
keyword      63%     83%   0.72    100%    100%      39%"""

SCOUT_HELP = "> /scout\n" + COMMAND_HELP


def main() -> int:
    real_embed = embeddings.embed_texts
    embeddings.embed_texts = stand_in_embed  # type: ignore[assignment]
    corpus = "benchmarks/corpus"
    with tempfile.TemporaryDirectory() as tmp:
        index = str(Path(tmp) / "index.db")
        searches = [
            ["search", "E4021", corpus, "--ranking", "keyword"],
            ["search", "pg_dump", corpus, "--ranking", "keyword", "-g", "docs/"],
        ]
        text = "\n\n".join(
            "$ hermes-scout " + " ".join(argv) + "\n" + run([*argv, "--index", index]) for argv in searches
        )
        render("exact-search", "terminal", text, "Exact names and error codes, with filters")
        # The health check runs against the real client with no server running, to show its fix.
        embeddings.embed_texts = real_embed
        doctor = run(["doctor", "--index", index, "--base-url", "http://127.0.0.1:9/v1"])
        doctor = doctor.replace("http://127.0.0.1:9/v1", "http://localhost:11434/v1")
        doctor = doctor.replace(index, "~/.cache/hermes-scout/index.db")
        doctor = re.sub(r"\(\[Errno[^)]*\)", "(connection refused)", doctor)
        doctor = re.sub(r", \d+\.\d MB", "", doctor)
        render("doctor", "terminal", "$ hermes-scout doctor\n" + doctor, "doctor names the fix when something is wrong")
    render("scout-command", "hermes", SCOUT_HELP, "/scout inside Hermes: status, checks and index upkeep")
    render("benchmark", "benchmark results", BENCHMARK, "Measured: the right file first for 28 of 30 questions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
