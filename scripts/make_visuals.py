"""Render the README and docs pictures in one style: black background, grey rounded panels and
gradient icon tiles with white symbols.

Each picture is written as an HTML page to docs/visuals/ (open one in a browser to inspect it) and
screenshotted at twice its size to docs/. Every number and result shown is real: they come from the
recorded demo (docs/demo.cast) and the benchmark workflow. Needs Node with the ``playwright``
package and a Chromium it can launch, plus the Inter font:

    python scripts/make_visuals.py
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "visuals"

ICONS = {
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "doc": '<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5"/><path d="M10 13h6M10 17h6"/>',
    "shield": '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
    "layers": '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>',
    "spark": '<circle cx="6" cy="7" r="2"/><circle cx="18" cy="6" r="2"/><circle cx="12" cy="17" r="2"/>'
    '<path d="M8 7.5l8-1M7 9l4 6.5M17 8l-4 7"/>',
    "text": '<path d="M5 6h14M12 6v13M9 19h6"/>',
    "db": '<ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6"/>'
    '<path d="M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3"/>',
    "search": '<circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5"/>',
    "chat": '<path d="M4 5h16v11H9l-5 4z"/>',
    "code": '<path d="M9 8l-4 4 4 4M15 8l4 4-4 4"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7"/>',
    "cross": '<path d="M6 6l12 12M18 6L6 18"/>',
    "link": '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/>'
    '<path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    "pulse": '<path d="M3 12h4l2-5 4 10 2-5h6"/>',
    "terminal": '<path d="M4 5h16v14H4z"/><path d="M8 10l3 2-3 2M13 15h4"/>',
}
GRADIENTS = {
    "purple": ("#c084fc", "#7c3aed"),
    "orange": ("#fdba74", "#ea580c"),
    "blue": ("#7dd3fc", "#2563eb"),
    "green": ("#86efac", "#16a34a"),
    "red": ("#fda4af", "#e11d48"),
    "yellow": ("#fde047", "#f59e0b"),
    "pink": ("#f9a8d4", "#db2777"),
    "indigo": ("#a5b4fc", "#4f46e5"),
}

CSS = """
* { box-sizing: border-box; margin: 0; }
body { font-family: Inter, sans-serif; background: #000; color: #fff; padding: 44px 56px; }
.tile { display: flex; align-items: center; justify-content: center; flex: none;
        box-shadow: 0 6px 18px rgba(0,0,0,.35); }
h1 { text-align: center; font-size: 44px; font-weight: 800; letter-spacing: -0.5px; }
.sub { text-align: center; color: #a1a1aa; font-size: 20px; margin: 8px 0 34px; }
.row { display: grid; gap: 30px; }
.fold { background: #1c1c1e; border-radius: 32px; padding: 24px; }
.head { display: flex; gap: 16px; align-items: center; margin-bottom: 10px; }
.head b { font-size: 26px; display: block; } .head span { color: #a1a1aa; font-size: 15px; }
.it { display: flex; gap: 16px; align-items: center; background: #2c2c2e; border-radius: 20px;
      padding: 14px 16px; margin-top: 12px; }
.it b { font-size: 18px; display: block; margin-bottom: 2px; } .it span { color: #a1a1aa; font-size: 15.5px; }
.it .grow { flex: 1; }
.mono { font-family: "DejaVu Sans Mono", monospace; }
.tag { font-family: "DejaVu Sans Mono", monospace; font-size: 15px; font-weight: 700;
       border-radius: 999px; padding: 7px 14px; }
.tag.good { background: #14532d; color: #86efac; } .tag.bad { background: #4c0519; color: #fda4af; }
.foot { margin-top: 28px; text-align: center; font-size: 20px; color: #d4d4d8; } .foot b { color: #4ade80; }
.note { margin-top: 8px; text-align: center; font-size: 15px; color: #71717a; }
"""


def tile(icon: str, color: str, size: int) -> str:
    top, bottom = GRADIENTS[color]
    glyph = round(size * 0.56)
    return (
        f'<div class="tile" style="width:{size}px;height:{size}px;border-radius:{round(size * 0.23)}px;'
        f'background:linear-gradient(160deg,{top},{bottom})"><svg viewBox="0 0 24 24" width="{glyph}" '
        f'height="{glyph}" fill="none" stroke="white" stroke-width="2.2" stroke-linecap="round" '
        f'stroke-linejoin="round">{ICONS[icon]}</svg></div>'
    )


def item(icon: str, color: str, title: str, detail: str, tag: str = "") -> str:
    return (
        f'<div class="it">{tile(icon, color, 54)}<div class="grow"><b>{title}</b><span>{detail}</span></div>{tag}</div>'
    )


def page(body: str, extra_css: str = "") -> str:
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><style>{CSS}{extra_css}</style></head>'
        f"<body>{body}</body></html>\n"
    )


QUESTION = "how do we keep a copy of the database in case it gets lost"
MEASURED = "Measured: <b>the right file first for 28 of 30 questions, in the top five for all 30</b>"


def glyph(icon: str, color: str, size: int) -> str:
    """An outline symbol in one colour, for the architecture picture."""
    return (
        f'<svg viewBox="0 0 24 24" width="{size}" height="{size}" fill="none" stroke="{color}" stroke-width="1.8" '
        f'stroke-linecap="round" stroke-linejoin="round">{ICONS[icon]}</svg>'
    )


ARCH_CSS = """
body { width: 1600px; padding: 40px 0 44px; background: radial-gradient(1100px 600px at 50% 0%, #0d1424, #05060a 70%); }
h1 { font-size: 58px; letter-spacing: 2px; color: #38bdf8; text-shadow: 0 0 28px rgba(56,189,248,.35); }
.sub { color: #e4e4e7; font-size: 23px; margin: 6px 0 0; }
.stage { position: relative; height: 900px; }
.box { position: absolute; border: 2px solid; border-radius: 20px; padding: 24px; }
.box.blue { border-color: #3b82f6; background: rgba(37,99,235,.07); box-shadow: 0 0 30px rgba(59,130,246,.25); }
.box.purple { border-color: #a855f7; background: rgba(147,51,234,.07); box-shadow: 0 0 30px rgba(168,85,247,.25); }
.box.amber { border-color: #f59e0b; background: rgba(245,158,11,.07); box-shadow: 0 0 30px rgba(245,158,11,.3); }
.bh { display: flex; gap: 16px; align-items: center; margin-bottom: 18px; }
.bh b { display: block; font-size: 29px; font-weight: 800; letter-spacing: 1px; }
.bh span { color: #d4d4d8; font-size: 18px; }
.blue .bh b { color: #60a5fa; } .purple .bh b { color: #c084fc; } .amber .bh b { color: #fbbf24; }
.card { display: flex; gap: 16px; align-items: center; border: 1.5px solid #27324a; background: rgba(15,23,42,.8);
        border-radius: 12px; padding: 16px 18px; margin-top: 14px; }
.card b { display: block; font-size: 21px; } .card span { color: #cbd5e1; font-size: 17px; display: block; }
.card .warn { color: #fbbf24; font-weight: 600; }
.step { position: absolute; left: 24px; width: 250px; border: 2px solid; border-radius: 12px; padding: 12px 16px;
        background: rgba(10,10,20,.6); text-align: center; }
.step b { font-size: 21px; } .step span { display: block; color: #e4e4e7; font-size: 16.5px; margin-top: 3px; }
.note { position: absolute; left: 300px; width: 150px; font-size: 15.5px; font-weight: 600; }
.mono { font-family: "DejaVu Sans Mono", monospace; }
.code { position: absolute; right: 22px; top: 22px; bottom: 22px; width: 330px; border: 1.5px solid #3f3f46;
        border-radius: 10px; background: #0a0a0f; padding: 16px 18px; font: 15px/1.6 "DejaVu Sans Mono", monospace;
        color: #e4e4e7;
        white-space: pre; }
.code .ok { color: #4ade80; } .code .dim { color: #a1a1aa; } .code .p { color: #c084fc; }
.feat { display: flex; gap: 12px; align-items: center; font-size: 18.5px; margin: 10px 0; }
.lbl { position: absolute; font-size: 18px; font-weight: 700; text-align: center; }
.banner { margin: 0 auto; width: 1040px; border: 2px solid #22c55e; border-radius: 14px;
          background: rgba(34,197,94,.08);
          display: flex; gap: 16px; align-items: center; justify-content: center; padding: 16px; font-size: 22px;
          font-weight: 700; }
.dot { width: 34px; height: 34px; border-radius: 50%; background: #22c55e; display: flex; align-items: center;
       justify-content: center; }
"""


def architecture() -> str:
    folder = (
        '<div class="box blue" style="left:150px;top:30px;width:560px;height:520px">'
        f'<div class="bh">{glyph("folder", "#60a5fa", 52)}<div><b>YOUR FOLDER</b><span>What hermes-scout reads</span>'
        "</div></div>"
        f'<div class="card">{glyph("doc", "#60a5fa", 40)}<div><b>Notes, docs and code</b>'
        "<span>.md .txt .py .ts .go .json .yaml and more</span></div></div>"
        f'<div class="card">{glyph("doc", "#c084fc", 40)}<div><b>PDF and Word files</b>'
        "<span>text read on your machine, with page numbers</span></div></div>"
        f'<div class="card">{glyph("shield", "#fbbf24", 40)}<div><b>Skipped on purpose</b>'
        '<span>.gitignore matches, hidden and binary files</span><span class="warn">.env and secrets, never read</span>'
        "</div></div>"
        f'<div class="card">{glyph("search", "#4ade80", 40)}<div><b>Filters when you want them</b>'
        "<span>only *.md, docs/ or src/**/*.py, no re-indexing</span></div></div></div>"
    )
    steps = [
        ("#3b82f6", "#60a5fa", 112, "Chunks", "whole lines, about 1,200 characters", "Neighbours share two lines"),
        (
            "#a855f7",
            "#c084fc",
            262,
            "Meaning vectors",
            "from your embeddings server",
            "Ollama on your machine by default",
        ),
        ("#22c55e", "#4ade80", 412, "Keyword index", "SQLite full-text search, BM25", "Exact names like E4021"),
    ]
    chain = "".join(
        f'<div class="step" style="top:{top}px;border-color:{border}"><b style="color:{text}">{title}</b>'
        f'<span>{detail}</span></div><div class="note" style="top:{top + 18}px;color:{text}">{note}</div>'
        for border, text, top, title, detail, note in steps
    )
    pipeline = (
        '<div class="box purple" style="left:890px;top:30px;width:560px;height:520px">'
        f'<div class="bh">{glyph("layers", "#c084fc", 52)}<div><b>INDEX PIPELINE</b>'
        f"<span>Only changed files are read again</span></div></div>{chain}</div>"
    )
    code = (
        '<div class="code"><span class="p">$</span> hermes-scout search\n'
        '  <span class="dim">"how do we keep a copy of\n'
        '   the database in case it\n   gets lost"</span>\n<span class="ok">0.63  docs/backups.md:1-15</span>\n'
        '<span class="dim">      # Backups and restores</span></div>'
    )
    store = (
        '<div class="box amber" style="left:390px;top:640px;width:1060px;height:240px;padding:28px 32px">'
        f'<div style="display:flex;gap:24px;align-items:center;height:100%">{glyph("db", "#fbbf24", 84)}'
        '<div style="width:230px"><div style="font-size:30px;font-weight:800;color:#fbbf24;letter-spacing:1px">'
        'SQLITE INDEX</div><div class="mono" style="font-size:19px;color:#d4d4d8;margin-top:10px">SQLite + FTS5</div>'
        '<div style="font-size:16px;color:#a1a1aa;margin-top:6px">one file per folder and model</div></div>'
        '<div style="border-left:1.5px solid #78350f;padding-left:28px;height:150px;display:flex;flex-direction:column;'
        f'justify-content:center"><div class="feat">{glyph("shield", "#fbbf24", 26)}Stays on your machine</div>'
        f'<div class="feat">{glyph("search", "#fbbf24", 26)}Meaning and keywords</div>'
        f'<div class="feat">{glyph("layers", "#fbbf24", 26)}Models never mixed</div></div></div>{code}</div>'
    )
    tools = (
        f'<div style="position:absolute;left:20px;top:690px;width:240px;text-align:center">'
        f'{glyph("search", "#4ade80", 64)}<div class="mono" style="color:#4ade80;font-size:21px;margin-top:8px">'
        'scout_search /<br>scout_similar</div><div style="font-size:17px;color:#e4e4e7;margin-top:8px">'
        "Rank every question,<br>return file, lines, score</div></div>"
    )
    marker = (
        '<marker id="ab" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">'
        '<path d="M0 0L10 5L0 10z" fill="#3b82f6"/></marker>'
        '<marker id="ap" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">'
        '<path d="M0 0L10 5L0 10z" fill="#a855f7"/></marker>'
        '<marker id="ag" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">'
        '<path d="M0 0L10 5L0 10z" fill="#22c55e"/></marker>'
    )
    links = "".join(
        f'<line x1="1065" y1="{y1}" x2="1065" y2="{y2}" stroke="{c}" stroke-width="2.5" stroke-dasharray="3 5"/>'
        f'<circle cx="1065" cy="{y1}" r="5" fill="{c}"/><circle cx="1065" cy="{y2}" r="5" fill="{c}"/>'
        for y1, y2, c in ((242, 290, "#60a5fa"), (392, 440, "#c084fc"))
    )
    wires = (
        f'<svg width="1600" height="900" style="position:absolute;left:0;top:0"><defs>{marker}</defs>'
        '<line x1="714" y1="290" x2="880" y2="290" stroke="#3b82f6" stroke-width="3" stroke-dasharray="10 8" '
        'marker-end="url(#ab)"/>'
        f"{links}"
        '<path d="M1065 552 L1065 630" stroke="#a855f7" stroke-width="3" stroke-dasharray="8 7" fill="none" '
        'marker-end="url(#ap)"/>'
        '<path d="M262 760 C 300 760, 340 760, 382 760" stroke="#22c55e" stroke-width="3" stroke-dasharray="8 7" '
        'fill="none" marker-end="url(#ag)"/>'
        "</svg>"
    )
    labels = (
        '<div class="lbl" style="left:716px;top:225px;width:162px;color:#60a5fa">read, split<br>&amp; embed</div>'
        '<div class="lbl" style="left:1085px;top:575px;color:#c084fc">saved to</div>'
    )
    return page(
        '<h1>HERMES-SCOUT ARCHITECTURE</h1><p class="sub">Your files stay on your machine. hermes-scout keeps a '
        f'searchable index next to them.</p><div class="stage">{wires}{folder}{pipeline}{store}{tools}{labels}</div>'
        f'<div class="banner"><div class="dot">{glyph("check", "#fff", 22)}</div>'
        "Questions in words rank by meaning. Code names find exact matches first.</div>",
        ARCH_CSS,
    )


def card(title: str, subtitle: str, entries: list[str], foot: str, note: str) -> str:
    return page(
        f'<h1>{title}</h1><p class="sub">{subtitle}</p><div class="fold">'
        + "".join(entries)
        + f'</div><p class="foot">{foot}</p><p class="note">{note}</p>',
        ".fold .it:first-child{margin-top:0}",
    )


def problem() -> str:
    return card(
        "Keyword search",
        "Only finds the words you remember.",
        [
            item("chat", "purple", "The question", f"&ldquo;{QUESTION}&rdquo;"),
            item(
                "doc",
                "blue",
                "The answer is in docs/backups.md, in other words",
                '<span class="mono">A scheduled job runs pg_dump at 02:00 UTC ... Files are kept for 30 days</span>',
            ),
            item(
                "cross",
                "red",
                "Keyword results",
                '<span class="mono">src/uploads/images.py &nbsp; src/storage/cache.py &nbsp; notes/hiring.md</span>',
                '<span class="tag bad">MISSED</span>',
            ),
        ],
        "The right file shares no words with the question, so it is not found at all.",
        "Real output of hermes-scout search --ranking keyword on the benchmark project.",
    )


def solution() -> str:
    return card(
        "hermes-scout",
        "Finds what you meant, and still finds exact names.",
        [
            item("chat", "purple", "The same question", f"&ldquo;{QUESTION}&rdquo;"),
            item(
                "spark",
                "pink",
                "Compared by meaning",
                "The question and every passage become embedding vectors; the closest come first.",
            ),
            item(
                "check",
                "green",
                "First result",
                '<span class="mono">0.63 &nbsp;docs/backups.md:1-15 &nbsp;# Backups and restores</span>',
                '<span class="tag good">FOUND</span>',
            ),
            item(
                "code",
                "yellow",
                "Code names still work",
                '<span class="mono">E4021 &rarr; 0.56 &nbsp;src/billing/errors.py</span>',
            ),
        ],
        MEASURED,
        "Real output with nomic-embed-text on Ollama, from the recorded demo and the benchmark workflow.",
    )


def cover(icon: str, color: str, name: str, line: str, rows: list[tuple[str, str]]) -> str:
    lines = "".join(
        f'<div class="ln"><span class="k">{left}</span><span class="v">{right}</span></div>' for left, right in rows
    )
    return page(
        f'<div class="top">{tile(icon, color, 124)}<div><div class="nm mono">{name}</div>'
        f'<div class="ln1">{line}</div></div></div><div class="fold box">{lines}</div>',
        "body{width:1200px;height:600px;padding:0 64px;display:flex;flex-direction:column;justify-content:center;"
        "background:radial-gradient(900px 420px at 15% 0%,#232329,#000 70%)}"
        ".top{display:flex;gap:30px;align-items:center}.nm{font-size:54px;font-weight:700}"
        ".ln1{font-size:29px;color:#a1a1aa;margin-top:8px}.box{margin-top:40px;padding:16px 28px}"
        ".ln{display:flex;justify-content:space-between;gap:20px;font-family:'DejaVu Sans Mono',monospace;"
        "font-size:26px;padding:15px 0;border-bottom:1px solid #2c2c2e}.ln:last-child{border-bottom:0}"
        ".k{color:#e4e4e7}.v{color:#7dd3fc;white-space:nowrap}",
    )


def covers() -> dict[str, str]:
    return {
        "cover-search": cover(
            "search",
            "purple",
            "scout_search",
            "Find passages by meaning and by exact names",
            [
                ("keep a copy of the database", "0.63 docs/backups.md"),
                ("E4021", "0.56 src/billing/errors.py"),
                ("--ranking", "hybrid &middot; semantic &middot; keyword"),
            ],
        ),
        "cover-similar": cover(
            "link",
            "pink",
            "scout_similar",
            "Find the files most related to a file or a passage",
            [
                ("src/auth/tokens.py", "0.63 docs/security.md"),
                ("", "0.63 docs/incident-2026-03.md"),
                ("", "0.61 src/client/backoff.py"),
            ],
        ),
        "cover-command": cover(
            "pulse",
            "green",
            "/scout",
            "Check your setup and look after the index",
            [
                ("/scout doctor", "checks, with the fix"),
                ("/scout status", "indexed folders"),
                ("/scout index &middot; clear", "build or forget"),
            ],
        ),
        "cover-cli": cover(
            "terminal",
            "orange",
            "hermes-scout",
            "The same search in any terminal, no Hermes needed",
            [
                ("pipx install hermes-scout", "from PyPI"),
                ('hermes-scout search "..."', "--json for scripts"),
                ("hermes-scout similar FILE", "doctor &middot; status"),
            ],
        ),
    }


def banner() -> str:
    results = [
        ("check", "green", "0.63", "docs/backups.md:1-15", "# Backups and restores"),
        ("code", "blue", "0.57", "src/storage/cache.py:1-19", "Read-through cache in front of the primary store."),
        ("doc", "purple", "0.54", "notes/meeting-2026-05-12.md:1-15", "# Platform meeting, 12 May"),
    ]
    rows = "".join(
        f'<div class="it">{tile(icon, color, 46)}<div class="grow"><b class="mono">{path}</b>'
        f'<span>{note}</span></div><span class="score mono">{score}</span></div>'
        for icon, color, score, path, note in results
    )
    return page(
        f'<div class="left">{tile("search", "purple", 112)}<div class="name">hermes-scout</div>'
        '<div class="pitch">Search your local files<br>by meaning, not just keywords.</div>'
        '<div class="chips"><span>Hermes Agent plugin</span><span>CLI</span><span>Local-first</span></div></div>'
        f'<div class="fold right"><div class="q mono">&gt; {QUESTION}</div>'
        f"{rows}</div>",
        "body{width:1200px;height:600px;padding:0 60px;display:flex;align-items:center;gap:44px;"
        "background:radial-gradient(700px 500px at 80% 40%,#2a1846,#000 70%)}"
        ".left{flex:0 0 430px}.name{font-size:62px;font-weight:800;letter-spacing:-1.5px;margin-top:26px}"
        ".pitch{font-size:25px;color:#d4d4d8;margin-top:10px;line-height:1.35}"
        ".chips{display:flex;gap:10px;margin-top:26px}.chips span{background:#1c1c1e;border-radius:999px;"
        "padding:8px 14px;font-size:15px;color:#e4e4e7}"
        ".right{flex:1;padding:22px}.q{font-size:15.5px;color:#c084fc;margin-bottom:6px}"
        ".it b{font-size:16px}.it .score{font-size:20px;color:#4ade80;font-weight:700}",
    )


def pictures() -> dict[str, tuple[str, int, int]]:
    """Name to (HTML, width, minimum height); the picture grows to fit its content."""
    out = {
        "architecture": (architecture(), 1600, 100),
        "problem": (problem(), 1240, 100),
        "solution": (solution(), 1240, 100),
    }
    out["banner"] = (banner(), 1200, 600)
    for name, html in covers().items():
        out[name] = (html, 1200, 600)
    return out


RENDER = """
const { chromium } = require('playwright');
(async () => {
  const jobs = JSON.parse(process.argv[1]);
  const browser = await chromium.launch();
  for (const job of jobs) {
    const page = await browser.newPage({ viewport: { width: job.w, height: job.h }, deviceScaleFactor: 2 });
    await page.goto('file://' + job.src);
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: job.out, fullPage: true });
    await page.close();
    console.log('wrote ' + job.name);
  }
  await browser.close();
})();
"""


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = []
    for name, (html, width, height) in pictures().items():
        source = OUT / f"{name}.html"
        source.write_text(html, encoding="utf-8")
        target = ROOT / "docs" / f"{name}.png"
        jobs.append({"src": str(source), "out": str(target), "w": width, "h": height, "name": f"docs/{name}.png"})
    env = dict(os.environ)
    if "NODE_PATH" not in env:
        npm_root = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True, check=False).stdout.strip()
        env["NODE_PATH"] = npm_root
    subprocess.run(["node", "-e", RENDER, json.dumps(jobs)], check=True, env=env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
