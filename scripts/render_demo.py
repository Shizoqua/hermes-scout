"""Render an asciicast from scripts/record_demo.py into docs/demo.gif and docs/demo.mp4.

Frames follow the cast's own timings, so the animation shows the session as it happened. Needs
Pillow, and ffmpeg for the MP4:

    python scripts/render_demo.py demo.cast
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
UI = "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"
BG, PANEL, BAR = (0, 0, 0), (28, 28, 30), (44, 44, 46)
TEXT, DIM, VIOLET, CYAN, GREEN, RED = (
    (244, 244, 245),
    (161, 161, 170),
    (192, 132, 252),
    (125, 211, 252),
    (74, 222, 128),
    (251, 113, 133),
)
FONT_SIZE, LINE_H, CHAR_W = 15, 22, 9.03
COLS, ROWS = 104, 26
PAD_X, TOP = 26, 64
W = int(PAD_X * 2 + COLS * CHAR_W) + 24
H = TOP + ROWS * LINE_H + 26
ANSI = re.compile(r"\x1b\[[0-9;]*m")
FRAME_STEP = 0.1  # merge events closer than this into one frame
HOLD_END = 3.0


def screen_lines(text: str) -> list[str]:
    """The terminal's visible rows: long lines wrap like a real terminal, newest rows last."""
    rows: list[str] = []
    for line in ANSI.sub("", text).replace("\r\n", "\n").split("\n"):
        while len(line) > COLS:
            cut = line.rfind(" ", 0, COLS)
            cut = cut if cut > 4 else COLS
            rows.append(line[:cut])
            line = "  " + line[cut:].lstrip()
        rows.append(line)
    return rows[-ROWS:]


def colour(line: str) -> tuple[int, int, int]:
    if line.startswith("FAIL"):
        return RED
    if line.startswith(("OK", "All checks")):
        return GREEN
    if re.match(r"(\d\.\d\d|  -  )\s{2}\S", line):
        return CYAN
    if line.startswith("      ") or line.startswith("note:"):
        return DIM
    return TEXT


def draw(lines: list[str], cursor: bool) -> Image.Image:
    mono = ImageFont.truetype(MONO, FONT_SIZE)
    ui = ImageFont.truetype(UI, 14)
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((8, 8, W - 8, H - 8), 20, fill=PANEL)
    d.rounded_rectangle((8, 8, W - 8, 46), 20, fill=BAR)
    d.rectangle((8, 30, W - 8, 46), fill=BAR)
    for i, dot in enumerate([(255, 95, 87), (254, 188, 46), (40, 200, 64)]):
        d.ellipse((28 + i * 20, 21, 40 + i * 20, 33), fill=dot)
    d.text((W // 2, 27), "hermes-scout", font=ui, fill=DIM, anchor="mm")
    y = TOP
    for index, line in enumerate(lines):
        x = PAD_X
        if line.startswith("$ "):
            d.text((x, y), "$", font=mono, fill=VIOLET)
            d.text((x + 2 * CHAR_W, y), line[2:], font=mono, fill=TEXT)
        else:
            d.text((x, y), line, font=mono, fill=colour(line))
        if cursor and index == len(lines) - 1:
            cx = x + len(line) * CHAR_W
            d.rectangle((cx, y + 3, cx + CHAR_W - 1, y + FONT_SIZE + 3), fill=VIOLET)
        y += LINE_H
    return im


def frames(cast: Path) -> list[tuple[Image.Image, float]]:
    rows = cast.read_text(encoding="utf-8").splitlines()
    events = [json.loads(row) for row in rows[1:] if row.strip()]
    out: list[tuple[Image.Image, float]] = []
    text, last_t, pending = "", 0.0, False
    for t, _kind, data in events:
        if pending and t - last_t >= FRAME_STEP:
            out.append((draw(screen_lines(text), cursor=True), t - last_t))
            last_t, pending = t, False
        text += data
        pending = True
    out.append((draw(screen_lines(text), cursor=False), HOLD_END))
    return out


def main() -> int:
    cast = Path(sys.argv[1] if len(sys.argv) > 1 else "demo.cast")
    shots = frames(cast)
    gif = ROOT / "docs" / "demo.gif"
    images = [image.convert("P", palette=Image.Palette.ADAPTIVE, colors=64) for image, _ in shots]
    durations = [max(20, int(seconds * 1000)) for _, seconds in shots]
    images[0].save(gif, save_all=True, append_images=images[1:], duration=durations, loop=0, optimize=True)
    print(f"wrote docs/demo.gif ({len(images)} frames, {gif.stat().st_size // 1024} KB)")
    if shutil.which("ffmpeg"):
        with tempfile.TemporaryDirectory() as tmp:
            listing = Path(tmp) / "frames.txt"
            entries = []
            for number, (image, seconds) in enumerate(shots):
                name = Path(tmp) / f"{number:05d}.png"
                image.save(name)
                entries.append(f"file '{name}'\nduration {seconds:.3f}")
            entries.append(f"file '{Path(tmp) / f'{len(shots) - 1:05d}.png'}'")
            listing.write_text("\n".join(entries) + "\n", encoding="utf-8")
            mp4 = ROOT / "docs" / "demo.mp4"
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-v",
                    "error",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(listing),
                    "-vf",
                    "fps=30,format=yuv420p,scale=trunc(iw/2)*2:trunc(ih/2)*2",
                    "-movflags",
                    "+faststart",
                    str(mp4),
                ],
                check=True,
            )
            print(f"wrote docs/demo.mp4 ({mp4.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
