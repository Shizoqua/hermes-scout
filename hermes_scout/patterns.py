"""Git-style path patterns: ``.gitignore`` rules and search filters. Standard library only.

Paths are relative to the searched folder and use ``/`` on every platform.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


def glob_to_regex(pattern: str) -> str:
    """Regex body for a git-style glob: ``*`` and ``?`` stay within one path segment, ``**`` crosses
    segments (``**/`` also matches no segment at all), ``[...]`` is a character class."""
    out: list[str] = []
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if char == "*":
            if pattern.startswith("**", i):
                i += 2
                if pattern.startswith("/", i):
                    out.append("(?:.*/)?")
                    i += 1
                else:
                    out.append(".*")
                continue
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        elif char == "[":
            close = pattern.find("]", i + 2)
            if close == -1:
                out.append(re.escape(char))
            else:
                body = pattern[i + 1 : close]
                if body[0] in "!^":
                    body = "^" + body[1:]
                out.append("[" + body.replace("\\", "\\\\") + "]")
                i = close + 1
                continue
        elif char == "\\" and i + 1 < len(pattern):
            out.append(re.escape(pattern[i + 1]))
            i += 2
            continue
        else:
            out.append(re.escape(char))
        i += 1
    return "".join(out)


def _compile(pattern: str) -> re.Pattern[str]:
    """A pattern with a ``/`` before its end is anchored to its base folder; one without matches a
    name at any depth."""
    if "/" in pattern:
        return re.compile("^" + glob_to_regex(pattern.lstrip("/")) + "$")
    return re.compile("^(?:.*/)?" + glob_to_regex(pattern) + "$")


@dataclass(frozen=True)
class Rule:
    regex: re.Pattern[str]
    negate: bool
    dir_only: bool
    base: str  # folder of the .gitignore that holds the rule, relative to the root ("" for the root)


def parse_gitignore(text: str, base: str = "") -> list[Rule]:
    """The rules in one ``.gitignore`` file whose folder is ``base`` (relative to the root)."""
    rules: list[Rule] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.startswith("#"):
            continue
        negate = line.startswith("!")
        if negate or line.startswith("\\"):  # "\#" and "\!" escape a literal first character
            line = line[1:]
        dir_only = line.endswith("/")
        line = line.rstrip("/")
        if line:
            rules.append(Rule(_compile(line), negate, dir_only, base))
    return rules


def load_gitignore(folder: Path, base: str) -> list[Rule]:
    """Rules from ``folder/.gitignore``, or none when it is missing or unreadable."""
    try:
        text = (folder / ".gitignore").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return parse_gitignore(text, base)


def is_ignored(rules: list[Rule], rel_path: str, is_dir: bool) -> bool:
    """Whether ``rel_path`` is ignored. The last matching rule wins, so ``!pattern`` re-includes."""
    ignored = False
    for rule in rules:
        if rule.dir_only and not is_dir:
            continue
        if rule.base:
            if not rel_path.startswith(rule.base + "/"):
                continue
            sub = rel_path[len(rule.base) + 1 :]
        else:
            sub = rel_path
        if rule.regex.match(sub):
            ignored = not rule.negate
    return ignored


class PathFilter:
    """Search filter from comma-separated globs such as ``*.md``, ``docs/`` or ``src/**/*.py``.

    A path matches when any glob matches it. A glob ending in ``/`` means everything in that folder.
    """

    def __init__(self, spec: str | list[str] | None):
        parts = spec if isinstance(spec, list) else str(spec or "").split(",")
        self.globs = [p.strip() for p in parts if p and p.strip()]
        self._regexes = [_compile(g + "**" if g.endswith("/") else g) for g in self.globs]

    def __bool__(self) -> bool:
        return bool(self._regexes)

    def matches(self, rel_path: str) -> bool:
        return not self._regexes or any(r.match(rel_path) for r in self._regexes)
