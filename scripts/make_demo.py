"""Render docs/demo.gif: an illustrative terminal session using the scout_search tool.

Run from the repository root with Pillow installed: python scripts/make_demo.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1000, 560
BG, PANEL, BAR = (11, 16, 34), (16, 21, 48), (26, 31, 62)
TEXT, DIM, ACCENT, CYAN, GREEN = (233, 230, 255), (143, 139, 179), (167, 139, 250), (125, 211, 252), (74, 222, 128)
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
UI = "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"

mono = ImageFont.truetype(MONO, 19)
mono_small = ImageFont.truetype(MONO, 16)
ui = ImageFont.truetype(UI, 15)

QUESTION = "Search ~/notes for how we handle rate limits"
RESULTS = [
    ("notes/retries.md", "lines 12-30", 0.82),
    ("src/client/backoff.py", "lines 40-71", 0.77),
    ("docs/api-errors.md", "lines 5-19", 0.64),
]
X0, Y0 = 48, 96


def frame(typed: str, tool: int = 0, shown: int = 0, answer: bool = False) -> Image.Image:
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((20, 20, W - 20, H - 20), 18, fill=PANEL, outline=(45, 50, 90))
    d.rounded_rectangle((20, 20, W - 20, 64), 18, fill=BAR)
    d.rectangle((20, 46, W - 20, 64), fill=BAR)
    for i, color in enumerate([(255, 95, 87), (254, 188, 46), (40, 200, 64)]):
        d.ellipse((44 + i * 22, 36, 56 + i * 22, 48), fill=color)
    d.text((W // 2, 42), "hermes", font=ui, fill=DIM, anchor="mm")

    y = Y0
    d.text((X0, y), ">", font=mono, fill=ACCENT)
    d.text((X0 + 24, y), typed + ("_" if not tool else ""), font=mono, fill=TEXT)
    y += 52
    if tool >= 1:
        d.text((X0, y), "scout_search", font=mono, fill=CYAN)
        d.text((X0 + 190, y), 'path="~/notes"', font=mono, fill=DIM)
        y += 32
    if tool >= 2:
        d.text((X0 + 24, y), "indexed 128 files, 1,284 chunks", font=mono_small, fill=GREEN)
        y += 44
    for path, lines, score in RESULTS[:shown]:
        d.text((X0 + 24, y), path, font=mono, fill=TEXT)
        d.text((W - 72, y), f"{score:.2f}", font=mono, fill=CYAN, anchor="ra")
        d.text((X0 + 24, y + 26), lines, font=mono_small, fill=DIM)
        bar_w = W - 72 - (X0 + 24)
        d.rounded_rectangle((X0 + 24, y + 52, W - 72, y + 57), 3, fill=(40, 44, 80))
        d.rounded_rectangle((X0 + 24, y + 52, X0 + 24 + int(bar_w * score), y + 57), 3, fill=ACCENT)
        y += 78
    if answer:
        d.text((X0, y + 6), "Rate limits are handled in notes/retries.md: exponential", font=mono_small, fill=TEXT)
        d.text(
            (X0, y + 30), "backoff with jitter, up to five retries (src/client/backoff.py).", font=mono_small, fill=TEXT
        )
    return im


def main() -> None:
    frames, durations = [], []

    def add(im: Image.Image, ms: int) -> None:
        frames.append(im)
        durations.append(ms)

    add(frame(""), 600)
    for i in range(1, len(QUESTION) + 1, 2):
        add(frame(QUESTION[:i]), 55)
    add(frame(QUESTION), 700)
    add(frame(QUESTION, tool=1), 700)
    add(frame(QUESTION, tool=2), 800)
    for shown in range(1, len(RESULTS) + 1):
        add(frame(QUESTION, tool=2, shown=shown), 500)
    add(frame(QUESTION, tool=2, shown=len(RESULTS), answer=True), 3500)

    out = Path(__file__).resolve().parents[1] / "docs" / "demo.gif"
    palette = [f.convert("P", palette=Image.Palette.ADAPTIVE, colors=64) for f in frames]
    palette[0].save(out, save_all=True, append_images=palette[1:], duration=durations, loop=0, optimize=True)
    print(f"wrote {out} ({out.stat().st_size // 1024} KB, {len(frames)} frames)")


if __name__ == "__main__":
    main()
