"""Fuzz the readers that take untrusted bytes: PDF text, the Office and OpenDocument XML readers and
the keyword query builder.

Each run feeds random and mutated inputs to the parsers. The only acceptable outcomes are text or a
``DocumentError``; any other exception is a bug. Needs Atheris (Linux, Python 3.12 to 3.14):

    python -m pip install --require-hashes -r .github/requirements/fuzz.txt
    python fuzz/fuzz_documents.py -max_total_time=60 fuzz/corpus
"""

from __future__ import annotations

import sys
from pathlib import Path

import atheris

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

with atheris.instrument_imports():
    from hermes_scout import documents, engine


def test_one_input(data: bytes) -> None:
    if not data:
        return
    target, rest = data[0] % 5, data[1:]  # the first byte picks the reader, the rest is its input
    if target == 0:
        try:
            text = documents.pdf_text(b"%PDF-1.7\n" + rest)
        except documents.DocumentError:
            return
        assert isinstance(text, str)
    elif target == 1:
        try:
            text = documents._docx_part(rest)
        except documents.DocumentError:
            return
        assert isinstance(text, str)
    elif target in (2, 3):
        try:
            root = documents._parse_xml(rest)
        except documents.DocumentError:
            return
        if target == 2:  # spreadsheet rows (Excel) and slide paragraphs (PowerPoint)
            rows = [documents._xlsx_row(row, ["shared"]) for row in root.iter(f"{documents._S}row")]
            lines = [documents._drawing_paragraph(p) for p in root.iter(f"{documents._A}p")]
            assert all(isinstance(line, str) for line in rows + lines)
        else:  # OpenDocument paragraphs, spaces, tabs and cells
            assert all(isinstance(line, str) for line in documents._odf_paragraphs(root))
    else:
        query = engine.keyword_query(rest.decode("utf-8", "replace"))
        assert query == "" or query.startswith('"')


def main() -> None:
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
