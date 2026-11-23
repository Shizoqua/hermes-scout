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
BG, PANEL, BAR = (0, 0, 0), (28, 28, 30), (44, 44, 46)
TEXT, DIM, ACCENT, CYAN, GREEN, RED = (
    (244, 244, 245),
    (161, 161, 170),
    (192, 132, 252),
    (125, 211, 252),
    (74, 222, 128),
    (251, 113, 133),
)
TILES = {
    "purple": ((192, 132, 252), (124, 58, 237)),
    "green": ((134, 239, 172), (22, 163, 74)),
    "orange": ((253, 186, 116), (234, 88, 12)),
    "blue": ((125, 211, 252), (37, 99, 235)),
}
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
UI = "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"
UI_BOLD = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"
FONT, LINE_H, WRAP = 20, 30, 78


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


def gradient_tile(size: int, colours: tuple[tuple[int, int, int], tuple[int, int, int]]) -> Image.Image:
    """A rounded square that fades from the first colour at the top to the second at the bottom."""
    top, bottom = colours
    fill = Image.new("RGB", (size, size))
    d = ImageDraw.Draw(fill)
    for y in range(size):
        t = y / (size - 1)
        d.line((0, y, size, y), fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom, strict=True)))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), round(size * 0.23), fill=255)
    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    tile.paste(fill, (0, 0), mask)
    return tile


def render(name: str, title: str, text: str, caption: str, tile: str, glyph: str) -> None:
    mono = ImageFont.truetype(MONO, FONT * SCALE)
    ui = ImageFont.truetype(UI, 15 * SCALE)
    cap = ImageFont.truetype(UI_BOLD, 22 * SCALE)
    lines = wrap(text, WRAP)
    longest = max(mono.getlength(line) for line in lines) / SCALE
    w = int(max(longest + 2 * 44, ImageFont.truetype(UI_BOLD, 22).getlength(caption) + 130))
    h = 148 + LINE_H * len(lines) + 22
    im = Image.new("RGB", (w * SCALE, h * SCALE), BG)
    d = ImageDraw.Draw(im)

    def s(*values: float) -> tuple[int, ...]:
        return tuple(round(v * SCALE) for v in values)

    badge = gradient_tile(52 * SCALE, TILES[tile])
    im.paste(badge, s(20, 18), badge)
    d.text(s(46, 44), glyph, font=ImageFont.truetype(UI_BOLD, 24 * SCALE), fill=(255, 255, 255), anchor="mm")
    d.text(s(88, 44), caption, font=cap, fill=TEXT, anchor="lm")
    d.rounded_rectangle(s(0, 88, w, h), 24 * SCALE, fill=PANEL)
    d.rounded_rectangle(s(0, 88, w, 128), 24 * SCALE, fill=BAR)
    d.rectangle(s(0, 110, w, 128), fill=BAR)
    for i, dot in enumerate([(255, 95, 87), (254, 188, 46), (40, 200, 64)]):
        d.ellipse(s(24 + i * 22, 102, 36 + i * 22, 114), fill=dot)
    d.text(s(w / 2, 108), title, font=ui, fill=DIM, anchor="mm")
    y = 148
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
        render("exact-search", "terminal", text, "Exact names and error codes, with filters", "purple", "#")
        # The health check runs against the real client with no server running, to show its fix.
        embeddings.embed_texts = real_embed
        doctor = run(["doctor", "--index", index, "--base-url", "http://127.0.0.1:9/v1"])
        doctor = doctor.replace("http://127.0.0.1:9/v1", "http://localhost:11434/v1")
        doctor = doctor.replace(index, "~/.cache/hermes-scout/index.db")
        doctor = re.sub(r"\(\[Errno[^)]*\)", "(connection refused)", doctor)
        doctor = re.sub(r", \d+\.\d MB", "", doctor)
        render(
            "doctor",
            "terminal",
            "$ hermes-scout doctor\n" + doctor,
            "doctor names the fix when something is wrong",
            "green",
            "+",
        )
    render(
        "scout-command", "hermes", SCOUT_HELP, "/scout inside Hermes: status, checks and index upkeep", "orange", "/"
    )
    render(
        "benchmark",
        "benchmark results",
        BENCHMARK,
        "Measured: the right file first for 28 of 30 questions",
        "blue",
        "%",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
