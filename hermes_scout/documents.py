"""Plain text from PDF, Word, Excel, PowerPoint and OpenDocument files, with the standard library only.

Best effort by design: text-based PDFs (the common case for exported documents), .docx, .xlsx and
.pptx files and OpenDocument text, spreadsheets and presentations (.odt, .ods, .odp) are read;
scanned PDFs (pictures of pages), encrypted files and fonts without a text mapping yield little or
no text and are skipped. Every size is capped, so a hostile file cannot exhaust memory.

Each page, slide or sheet starts with a marker line such as ``[page 3]``, ``[slide 2]`` or
``[sheet Budget]``, so a search result can say where in the document it came from.
"""

from __future__ import annotations

import posixpath
import re
import zipfile
import zlib
from collections.abc import Callable, Iterator
from pathlib import Path
from xml.etree import ElementTree

DOCUMENT_EXTENSIONS = frozenset({".pdf", ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp"})
MAX_DOCUMENT_BYTES = 20 * 1024 * 1024  # largest document read at all
_MAX_EXPANDED_BYTES = 64 * 1024 * 1024  # total decompressed data allowed per document
_MAX_TEXT_CHARS = 2_000_000  # extracted text kept per document
LOCATION = re.compile(r"^\[(?:page|slide|sheet) [^\]\n]+\]$")  # a marker line, as written below


class DocumentError(Exception):
    """The file is not a readable document; the message says why."""


def extract_text(path: Path) -> str:
    """The text of the document at ``path``. Raises ``DocumentError`` when it cannot be read."""
    suffix = path.suffix.lower()
    if suffix not in DOCUMENT_EXTENSIONS:
        raise DocumentError(f"not a supported document type: {path.name}")
    try:
        size = path.stat().st_size
        if size > MAX_DOCUMENT_BYTES:
            raise DocumentError(f"{path.name} is larger than {MAX_DOCUMENT_BYTES // 1_048_576} MB")
        if suffix == ".pdf":
            return pdf_text(path.read_bytes())
        reader = {".docx": docx_text, ".xlsx": xlsx_text, ".pptx": pptx_text}.get(suffix, odf_text)
        return reader(path)[:_MAX_TEXT_CHARS]
    except OSError as err:
        raise DocumentError(f"cannot read {path.name}: {err}") from err


# --- zip-based formats --------------------------------------------------------------------------


class _Package:
    """The parts of a zip-based document, read with one budget for the total decompressed size."""

    def __init__(self, archive: zipfile.ZipFile, name: str, kind: str) -> None:
        self.archive, self.name, self.kind = archive, name, kind
        self.sizes = {info.filename: info.file_size for info in archive.infolist()}
        self.expanded = 0

    def __contains__(self, part: str) -> bool:
        return part in self.sizes

    def xml(self, part: str) -> ElementTree.Element:
        self.expanded += self.sizes[part]
        if self.expanded > _MAX_EXPANDED_BYTES:
            raise DocumentError(f"{self.name} expands to more than {_MAX_EXPANDED_BYTES // 1_048_576} MB")
        return _parse_xml(self.archive.read(part))


def _read_package(path: Path, kind: str, required: str, read: Callable[[_Package], str]) -> str:
    """Open ``path`` as a zip package that must hold ``required`` and pass it to ``read``."""
    try:
        with zipfile.ZipFile(path) as archive:
            package = _Package(archive, path.name, kind)
            if required not in package:
                raise DocumentError(f"{path.name} has no {required}; is it a {kind}?")
            return read(package)
    except (zipfile.BadZipFile, KeyError, ValueError) as err:
        raise DocumentError(f"{path.name} is not a valid {kind}: {err}") from err


def _parse_xml(xml: bytes) -> ElementTree.Element:
    # Office writers never declare a DOCTYPE; refusing one rules out entity-expansion tricks.
    if b"<!DOCTYPE" in xml[:4096].upper():
        raise DocumentError("document XML declares a DOCTYPE")
    try:
        return ElementTree.fromstring(xml)
    except ElementTree.ParseError as err:
        raise DocumentError(f"document XML is malformed: {err}") from err


def _targets(package: _Package, rels_part: str, base: str) -> dict[str, str]:
    """Relationship id to part name, from a ``.rels`` part, resolved against the folder ``base``."""
    if rels_part not in package:
        return {}
    out = {}
    for rel in package.xml(rels_part):
        target = rel.get("Target", "")
        if rel.get("TargetMode") == "External" or not target:
            continue
        full = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(base, target))
        out[rel.get("Id", "")] = full
    return out


def _number(name: str) -> int:
    match = re.search(r"(\d+)\.xml$", name)
    return int(match.group(1)) if match else 0


# --- Word ---------------------------------------------------------------------------------------

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_DOCX_PARTS = ("word/document.xml", "word/footnotes.xml", "word/endnotes.xml")


def docx_text(path: Path) -> str:
    """Paragraph text of the main document, footnotes and endnotes, one paragraph per line."""

    def read(package: _Package) -> str:
        parts = [_docx_lines(package.xml(name)) for name in _DOCX_PARTS if name in package]
        return "\n".join(part for part in parts if part)

    return _read_package(path, "Word document", _DOCX_PARTS[0], read)


def _docx_part(xml: bytes) -> str:
    """The text of one Word XML part (kept separate so it can be fuzzed on its own)."""
    return _docx_lines(_parse_xml(xml))


def _docx_lines(root: ElementTree.Element) -> str:
    lines = []
    for paragraph in root.iter(f"{_W}p"):
        pieces = []
        for node in paragraph.iter():
            if node.tag == f"{_W}t" and node.text:
                pieces.append(node.text)
            elif node.tag == f"{_W}tab":
                pieces.append("\t")
            elif node.tag in (f"{_W}br", f"{_W}cr"):
                pieces.append("\n")
        lines.append("".join(pieces))
    return "\n".join(lines).strip()


# --- Excel --------------------------------------------------------------------------------------

_S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def xlsx_text(path: Path) -> str:
    """Every sheet in workbook order: a ``[sheet Name]`` line, then one line per row with its cells
    separated by tabs. Cells show their stored value: text, numbers and formula results as last
    saved (dates appear as the number Excel stores)."""

    def read(package: _Package) -> str:
        shared = []
        if "xl/sharedStrings.xml" in package:
            shared = [
                "".join(t.text or "" for t in item.iter(f"{_S}t")) for item in package.xml("xl/sharedStrings.xml")
            ]
        targets = _targets(package, "xl/_rels/workbook.xml.rels", "xl")
        sheets = package.xml("xl/workbook.xml").iter(f"{_S}sheet")
        blocks = []
        for sheet in sheets:
            part = targets.get(sheet.get(f"{_R}id", ""), "")
            if part not in package:
                continue
            rows = [_xlsx_row(row, shared) for row in package.xml(part).iter(f"{_S}row")]
            body = "\n".join(row for row in rows if row)
            if body:
                blocks.append(f"[sheet {_label(sheet.get('name'))}]\n{body}")
        return "\n\n".join(blocks)

    return _read_package(path, "Excel workbook", "xl/workbook.xml", read)


def _xlsx_row(row: ElementTree.Element, shared: list[str]) -> str:
    cells = []
    for cell in row.iter(f"{_S}c"):
        kind, value = cell.get("t"), cell.find(f"{_S}v")
        raw = value.text if value is not None and value.text else ""
        if kind == "s":
            text = shared[int(raw)] if raw.isdecimal() and int(raw) < len(shared) else ""
        elif kind == "inlineStr":
            text = "".join(t.text or "" for t in cell.iter(f"{_S}t"))
        elif kind == "b":
            text = {"1": "TRUE", "0": "FALSE"}.get(raw, "")
        elif kind == "e":
            text = ""  # an error value such as #DIV/0! carries no meaning to search for
        else:
            text = raw
        if text.strip():
            cells.append(text.strip())
    return "\t".join(cells)


def _label(name: str | None) -> str:
    """A sheet name safe to put inside a marker line."""
    return re.sub(r"[\]\n\r]+", " ", name or "").strip() or "?"


# --- PowerPoint ---------------------------------------------------------------------------------

_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"


def pptx_text(path: Path) -> str:
    """The text on each slide in presentation order, after a ``[slide N]`` line. Speaker notes are
    not read."""

    def read(package: _Package) -> str:
        targets = _targets(package, "ppt/_rels/presentation.xml.rels", "ppt")
        order = [targets.get(s.get(f"{_R}id", ""), "") for s in package.xml("ppt/presentation.xml").iter(f"{_P}sldId")]
        slides = [part for part in order if part in package]
        if not slides:  # no usable slide list: fall back to the slide parts by number
            slides = sorted((n for n in package.sizes if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)), key=_number)
        blocks = []
        for number, part in enumerate(slides, start=1):
            lines = [_drawing_paragraph(p) for p in package.xml(part).iter(f"{_A}p")]
            body = "\n".join(line for line in lines if line.strip())
            if body:
                blocks.append(f"[slide {number}]\n{body}")
        return "\n\n".join(blocks)

    return _read_package(path, "PowerPoint presentation", "ppt/presentation.xml", read)


def _drawing_paragraph(paragraph: ElementTree.Element) -> str:
    pieces = []
    for node in paragraph.iter():
        if node.tag == f"{_A}t" and node.text:
            pieces.append(node.text)
        elif node.tag == f"{_A}br":
            pieces.append("\n")
        elif node.tag == f"{_A}tab":
            pieces.append("\t")
    return "".join(pieces).strip()


# --- OpenDocument -------------------------------------------------------------------------------

_TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
_TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
_DRAW = "{urn:oasis:names:tc:opendocument:xmlns:drawing:1.0}"
_OFFICE = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"


def odf_text(path: Path) -> str:
    """OpenDocument text (.odt) as paragraphs, spreadsheets (.ods) as ``[sheet Name]`` blocks of
    tab-separated rows, presentations (.odp) as ``[slide N]`` blocks."""

    def read(package: _Package) -> str:
        body = package.xml("content.xml").find(f"{_OFFICE}body")
        if body is None:
            return ""
        blocks = []
        sheets = list(body.iter(f"{_TABLE}table")) if path.suffix.lower() == ".ods" else []
        pages = list(body.iter(f"{_DRAW}page"))
        for sheet in sheets:
            rows = [
                "\t".join(c for c in map(_odf_cell, row.iter(f"{_TABLE}table-cell")) if c)
                for row in sheet.iter(f"{_TABLE}table-row")
            ]
            text = "\n".join(row for row in rows if row)
            if text:
                blocks.append(f"[sheet {_label(sheet.get(f'{_TABLE}name'))}]\n{text}")
        for number, page in enumerate(pages, start=1):
            text = "\n".join(_odf_paragraphs(page))
            if text:
                blocks.append(f"[slide {number}]\n{text}")
        if not sheets and not pages:
            blocks.append("\n".join(_odf_paragraphs(body)))
        return "\n\n".join(block for block in blocks if block)

    return _read_package(path, "OpenDocument file", "content.xml", read)


def _odf_paragraphs(node: ElementTree.Element) -> list[str]:
    """The paragraphs and headings under ``node``, in order, without counting nested ones twice."""
    out: list[str] = []
    for child in node:
        if child.tag in (f"{_TEXT}p", f"{_TEXT}h"):
            text = _odf_inline(child).strip()
            if text:
                out.append(text)
        else:
            out.extend(_odf_paragraphs(child))
    return out


def _odf_inline(node: ElementTree.Element) -> str:
    pieces = [node.text or ""]
    for child in node:
        if child.tag == f"{_TEXT}s":
            count = child.get(f"{_TEXT}c", "1")
            pieces.append(" " * min(int(count) if count.isdecimal() else 1, 100))
        elif child.tag == f"{_TEXT}tab":
            pieces.append("\t")
        elif child.tag == f"{_TEXT}line-break":
            pieces.append("\n")
        else:
            pieces.append(_odf_inline(child))
        pieces.append(child.tail or "")
    return "".join(pieces)


def _odf_cell(cell: ElementTree.Element) -> str:
    return " ".join(_odf_paragraphs(cell)).strip()


# --- PDF ----------------------------------------------------------------------------------------

_OBJECT = re.compile(rb"(\d+)\s+(\d+)\s+obj\b(.*?)\bendobj", re.S)
_STREAM = re.compile(rb"stream\r?\n(.*?)\r?\n?endstream", re.S)
_REF = re.compile(rb"(\d+)\s+(\d+)\s+R\b")


def pdf_text(data: bytes) -> str:
    """Text of every page, in page order, with a ``[page N]`` line before each page."""
    if not data.startswith(b"%PDF"):
        raise DocumentError("not a PDF file")
    pdf = _Pdf(data)
    if pdf.encrypted:
        raise DocumentError("the PDF is encrypted")
    pages = []
    for number, page in enumerate(pdf.pages(), start=1):
        text = pdf.page_text(page).strip()
        if text:
            pages.append(f"[page {number}]\n{text}")
        if sum(len(p) for p in pages) > _MAX_TEXT_CHARS:
            break
    return "\n\n".join(pages)[:_MAX_TEXT_CHARS]


class _Pdf:
    def __init__(self, data: bytes) -> None:
        self.objects: dict[int, bytes] = {}
        self.expanded = 0
        for match in _OBJECT.finditer(data):
            self.objects[int(match.group(1))] = match.group(3)
        self.encrypted = re.search(rb"/Encrypt\s+\d+\s+\d+\s+R", data) is not None
        for body in list(self.objects.values()):
            if re.search(rb"/Type\s*/ObjStm\b", _dict_part(body)):
                self._unpack_object_stream(body)
        self.fonts: dict[int, dict[bytes, str]] = {}

    def _stream(self, body: bytes) -> bytes:
        match = _STREAM.search(body)
        if not match:
            return b""
        raw = match.group(1)
        head = _dict_part(body)
        filters = re.findall(rb"/(\w+)", _value(head, b"Filter") or b"")
        for name in filters:
            if name not in (b"FlateDecode", b"Fl"):
                return b""  # images and rarely used text encodings: nothing to read
            raw = self._inflate(raw)
        return raw

    def _inflate(self, raw: bytes) -> bytes:
        budget = _MAX_EXPANDED_BYTES - self.expanded
        if budget <= 0:
            raise DocumentError(f"the PDF expands to more than {_MAX_EXPANDED_BYTES // 1_048_576} MB")
        decoder = zlib.decompressobj()
        try:
            out = decoder.decompress(raw, budget)
        except zlib.error:
            return b""
        if decoder.unconsumed_tail:
            raise DocumentError(f"the PDF expands to more than {_MAX_EXPANDED_BYTES // 1_048_576} MB")
        self.expanded += len(out)
        return out

    def _unpack_object_stream(self, body: bytes) -> None:
        head = _dict_part(body)
        first = _int(_value(head, b"First"))
        content = self._stream(body)
        if first is None or not content:
            return
        numbers = [int(n) for n in re.findall(rb"\d+", content[:first])]
        pairs = list(zip(numbers[0::2], numbers[1::2], strict=False))
        for i, (num, offset) in enumerate(pairs):
            end = first + pairs[i + 1][1] if i + 1 < len(pairs) else len(content)
            self.objects.setdefault(num, content[first + offset : end])

    def resolve(self, value: bytes | None) -> bytes:
        """Follow ``n 0 R`` references (a few levels) to the object's body."""
        for _ in range(8):
            if value is None:
                return b""
            match = _REF.fullmatch(value.strip())
            if not match:
                return value
            value = self.objects.get(int(match.group(1)))
        return value or b""

    def pages(self) -> Iterator[tuple[bytes, bytes]]:
        """``(page body, inherited resources)`` in page order, following the page tree."""
        catalog = next((b for b in self.objects.values() if re.search(rb"/Type\s*/Catalog\b", _dict_part(b))), None)
        root = self.resolve(_value(_dict_part(catalog), b"Pages")) if catalog else b""
        seen: set[int] = set()
        if root:
            yield from self._walk(root, b"", seen, depth=0)
        if not seen:  # no usable page tree: fall back to every page object in file order
            for _num, body in sorted(self.objects.items()):
                if re.search(rb"/Type\s*/Page\b", _dict_part(body)):
                    yield body, b""

    def _walk(self, node: bytes, resources: bytes, seen: set[int], depth: int) -> Iterator[tuple[bytes, bytes]]:
        if depth > 32:
            return
        head = _dict_part(node)
        resources = _value(head, b"Resources") or resources
        if re.search(rb"/Type\s*/Page\b", head):
            seen.add(id(node))
            yield node, resources
            return
        for ref in _REF.finditer(_value(head, b"Kids") or b""):
            num = int(ref.group(1))
            if num in seen:
                continue
            seen.add(num)
            yield from self._walk(self.objects.get(num, b""), resources, seen, depth + 1)

    def page_text(self, page: tuple[bytes, bytes]) -> str:
        body, inherited = page
        head = _dict_part(body)
        resources = _dict_part(self.resolve(_value(head, b"Resources") or inherited))
        fonts = self._fonts(_dict_part(self.resolve(_value(resources, b"Font"))))
        contents = self.resolve(_value(head, b"Contents"))
        refs = _REF.findall(contents) if contents.lstrip().startswith(b"[") else []
        streams = [self._stream(self.objects.get(int(num), b"")) for num, _ in refs] or [self._stream(contents)]
        return _content_text(b"\n".join(streams), fonts)

    def _fonts(self, font_dict: bytes) -> dict[bytes, dict[bytes, str]]:
        """Resource name (``F1``) to the font's code-to-text map (empty when it has none)."""
        out: dict[bytes, dict[bytes, str]] = {}
        for name, num in re.findall(rb"/([^\s/<>\[\]()]+)\s+(\d+)\s+\d+\s+R", font_dict):
            key = int(num)
            if key not in self.fonts:
                font = _dict_part(self.objects.get(key, b""))
                cmap = self.resolve(_value(font, b"ToUnicode"))
                self.fonts[key] = _parse_cmap(self._stream(cmap)) if cmap else {}
            out[name] = self.fonts[key]
        return out


def _dict_part(body: bytes | None) -> bytes:
    """The object's dictionary, without any stream data."""
    if not body:
        return b""
    cut = body.find(b"stream")
    return body if cut < 0 else body[:cut]


def _value(head: bytes, key: bytes) -> bytes | None:
    """The raw value of ``/key`` in a dictionary: a reference, array, name, number or nested dict."""
    match = re.search(rb"/" + key + rb"(?![A-Za-z0-9])\s*", head)
    if not match:
        return None
    rest = head[match.end() :]
    if ref := re.match(rb"\d+\s+\d+\s+R\b", rest):
        return ref.group(0)
    for opening, closing in ((b"<<", b">>"), (b"[", b"]")):
        if rest.startswith(opening):
            depth, i = 0, 0
            while i < len(rest):
                if rest.startswith(opening, i):
                    depth, i = depth + 1, i + len(opening)
                elif rest.startswith(closing, i):
                    depth, i = depth - 1, i + len(closing)
                    if depth == 0:
                        return rest[:i]
                else:
                    i += 1
            return rest
    token = re.match(rb"/?[^\s/<>\[\]()]+", rest)
    return token.group(0) if token else None


def _int(value: bytes | None) -> int | None:
    return int(value) if value and value.isdigit() else None


def _parse_cmap(data: bytes) -> dict[bytes, str]:
    """A ToUnicode CMap's ``bfchar`` and ``bfrange`` entries: character code bytes to text."""
    out: dict[bytes, str] = {}
    for block in re.findall(rb"beginbfchar(.*?)endbfchar", data, re.S):
        for src, dst in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]*)>", block):
            out[bytes.fromhex(_even(src))] = _utf16(dst)
    for block in re.findall(rb"beginbfrange(.*?)endbfrange", data, re.S):
        for lo, hi, dst in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(<[0-9A-Fa-f]*>|\[[^\]]*\])", block):
            start, end, width = int(lo, 16), int(hi, 16), len(_even(lo)) // 2
            if end - start > 65535:
                continue
            if dst.startswith(b"["):
                targets = re.findall(rb"<([0-9A-Fa-f]*)>", dst)
                for offset, target in enumerate(targets[: end - start + 1]):
                    out[(start + offset).to_bytes(width, "big")] = _utf16(target)
            else:
                base = bytes.fromhex(_even(dst[1:-1]))
                for offset in range(end - start + 1):
                    code = (int.from_bytes(base, "big") + offset).to_bytes(max(len(base), 2), "big")
                    out[(start + offset).to_bytes(width, "big")] = code.decode("utf-16-be", "replace")
    return out


def _even(hexdigits: bytes) -> str:
    text = hexdigits.decode("ascii")
    return text + "0" if len(text) % 2 else text


def _utf16(hexdigits: bytes) -> str:
    return bytes.fromhex(_even(hexdigits)).decode("utf-16-be", "replace")


_TOKEN = re.compile(
    rb"\((?:\\.|[^\\()]|\((?:\\.|[^\\()])*\))*\)"  # literal string, one level of nested brackets
    rb"|<[0-9A-Fa-f\s]*>"  # hex string
    rb"|\[|\]"
    rb"|/[^\s/<>\[\]()]*"  # name
    rb"|[+-]?\d*\.?\d+"  # number
    rb"|[A-Za-z'\"*]+",  # operator
    re.S,
)
_ESCAPES = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f", b"(": b"(", b")": b")", b"\\": b"\\"}


def _literal(token: bytes) -> bytes:
    body, out, i = token[1:-1], bytearray(), 0
    while i < len(body):
        char = body[i : i + 1]
        if char != b"\\":
            out += char
            i += 1
            continue
        nxt = body[i + 1 : i + 2]
        if nxt in _ESCAPES:
            out += _ESCAPES[nxt]
            i += 2
        elif nxt.isdigit():
            octal = re.match(rb"[0-7]{1,3}", body[i + 1 :])
            digits = octal.group(0) if octal else b"0"
            out.append(int(digits, 8) & 0xFF)
            i += 1 + len(digits)
        else:  # line continuation or unknown escape: drop the backslash
            i += 2 if nxt in (b"\n", b"\r") else 1
    return bytes(out)


def _decode(raw: bytes, cmap: dict[bytes, str]) -> str:
    if not cmap:
        return raw.decode("cp1252", "replace")
    widths = sorted({len(code) for code in cmap}, reverse=True)
    out, i = [], 0
    while i < len(raw):
        for width in widths:
            piece = raw[i : i + width]
            if piece in cmap:
                out.append(cmap[piece])
                i += width
                break
        else:
            i += 1  # a code with no mapping: skip it rather than guess
    return "".join(out)


def _content_text(content: bytes, fonts: dict[bytes, dict[bytes, str]]) -> str:
    """Text shown by a page's content stream: Tj, TJ, ' and " operators, with line breaks for line
    moves and spaces for wide gaps in TJ arrays."""
    out: list[str] = []
    operands: list[bytes | list[bytes]] = []
    cmap: dict[bytes, str] = {}
    array: list[bytes] | None = None
    line_y: bytes | list[bytes] | None = None  # y position of the last text matrix (Tm)

    def show(raw: bytes) -> None:
        out.append(_decode(raw, cmap))

    for token in _TOKEN.findall(content):
        if token == b"[":
            array = []
        elif token == b"]":
            operands.append(array or [])
            array = None
        elif array is not None:
            array.append(token)
        elif token[:1] in b"(</+-.0123456789":
            operands.append(token)
        else:
            last = operands[-1] if operands else b""
            if token == b"Tf" and len(operands) >= 2 and isinstance(operands[-2], bytes):
                cmap = fonts.get(operands[-2][1:], {})
            elif token in (b"Tj", b"'", b'"') and isinstance(last, bytes):
                if token != b"Tj":
                    out.append("\n")
                show(_string(last))
            elif token == b"TJ" and isinstance(last, list):
                for item in last:
                    if item[:1] in (b"(", b"<"):
                        show(_string(item))
                    elif _is_number(item) and float(item) < -200:
                        out.append(" ")
            elif token in (b"Td", b"TD") and isinstance(last, bytes) and _is_number(last):
                out.append("\n" if float(last) != 0 else " ")
            elif token == b"Tm" and len(operands) >= 6 and all(isinstance(o, bytes) for o in operands[-6:]):
                y = operands[-1]
                out.append("\n" if line_y is not None and y != line_y else " ")
                line_y = y
            elif token in (b"T*", b"ET"):
                out.append("\n")
            operands = []
    text = "".join(out)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text)


def _string(token: bytes) -> bytes:
    if token.startswith(b"("):
        return _literal(token)
    if token.startswith(b"<"):
        return bytes.fromhex(_even(re.sub(rb"\s", b"", token[1:-1])))
    return b""


def _is_number(token: bytes) -> bool:
    return re.fullmatch(rb"[+-]?\d*\.?\d+", token) is not None
