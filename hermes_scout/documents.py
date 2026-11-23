"""Plain text from PDF and Word (.docx) files, with the standard library only.

Best effort by design: text-based PDFs (the common case for exported documents) and .docx files
are read; scanned PDFs (pictures of pages), encrypted PDFs and fonts without a text mapping yield
little or no text and are skipped. Every size is capped, so a hostile file cannot exhaust memory.
"""

from __future__ import annotations

import re
import zipfile
import zlib
from collections.abc import Iterator
from pathlib import Path
from xml.etree import ElementTree

DOCUMENT_EXTENSIONS = frozenset({".pdf", ".docx"})
MAX_DOCUMENT_BYTES = 20 * 1024 * 1024  # largest PDF or .docx read at all
_MAX_EXPANDED_BYTES = 64 * 1024 * 1024  # total decompressed data allowed per document
_MAX_TEXT_CHARS = 2_000_000  # extracted text kept per document


class DocumentError(Exception):
    """The file is not a readable PDF or .docx; the message says why."""


def extract_text(path: Path) -> str:
    """The text of a PDF or .docx file at ``path``. Raises ``DocumentError`` when it cannot be read."""
    suffix = path.suffix.lower()
    if suffix not in DOCUMENT_EXTENSIONS:
        raise DocumentError(f"not a PDF or .docx file: {path.name}")
    try:
        size = path.stat().st_size
        if size > MAX_DOCUMENT_BYTES:
            raise DocumentError(f"{path.name} is larger than {MAX_DOCUMENT_BYTES // 1_048_576} MB")
        if suffix == ".docx":
            return docx_text(path)
        return pdf_text(path.read_bytes())
    except OSError as err:
        raise DocumentError(f"cannot read {path.name}: {err}") from err


# --- Word ---------------------------------------------------------------------------------------

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_DOCX_PARTS = ("word/document.xml", "word/footnotes.xml", "word/endnotes.xml")


def docx_text(path: Path) -> str:
    """Paragraph text of the main document, footnotes and endnotes, one paragraph per line."""
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if _DOCX_PARTS[0] not in names:
                raise DocumentError(f"{path.name} has no word/document.xml; is it a Word document?")
            total = sum(info.file_size for info in archive.infolist() if info.filename in _DOCX_PARTS)
            if total > _MAX_EXPANDED_BYTES:
                raise DocumentError(f"{path.name} expands to more than {_MAX_EXPANDED_BYTES // 1_048_576} MB")
            parts = [_docx_part(archive.read(name)) for name in _DOCX_PARTS if name in names]
    except (zipfile.BadZipFile, KeyError) as err:
        raise DocumentError(f"{path.name} is not a valid .docx file: {err}") from err
    return "\n".join(part for part in parts if part)[:_MAX_TEXT_CHARS]


def _docx_part(xml: bytes) -> str:
    # Word never writes a DOCTYPE; refusing one rules out entity-expansion tricks before parsing.
    if b"<!DOCTYPE" in xml[:4096].upper():
        raise DocumentError("document XML declares a DOCTYPE")
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as err:
        raise DocumentError(f"document XML is malformed: {err}") from err
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
