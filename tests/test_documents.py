"""Document text extraction (PDF, Word, Excel, PowerPoint, OpenDocument), against small synthetic
files built here."""

import sqlite3
import zipfile
import zlib

import pytest
from test_engine import toy_embed

from hermes_scout import documents, engine

# --- builders -----------------------------------------------------------------------------------


def make_pdf(pages, *, fonts=None, compress=True, object_stream=False, extra=b""):
    """A minimal PDF: ``pages`` are content streams; ``fonts`` maps a resource name to a ToUnicode
    CMap (or None for a font without one). With ``object_stream`` the font dictionaries live inside a
    compressed object stream, as PDF 1.5+ writers do."""
    fonts = fonts or {b"F1": None}
    objects: dict[int, bytes] = {}
    loose: dict[int, bytes] = {}

    def stream(data, head=b""):
        if compress:
            data = zlib.compress(data)
            head += b" /Filter /FlateDecode"
        return b"<< /Length %d%s >>\nstream\n%s\nendstream" % (len(data), head, data)

    num = 10
    font_refs = []
    for name, cmap in fonts.items():
        font_num = num
        num += 1
        font = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica"
        if cmap is not None:
            objects[num] = stream(cmap)
            font += b" /ToUnicode %d 0 R" % num
            num += 1
        font += b" >>"
        (loose if object_stream else objects)[font_num] = font
        font_refs.append(b"/%s %d 0 R" % (name, font_num))
    resources = b"<< /Font << " + b" ".join(font_refs) + b" >> >>"
    kids = []
    for content in pages:
        objects[num] = stream(content)
        objects[num + 1] = b"<< /Type /Page /Parent 2 0 R /Contents %d 0 R >>" % num
        kids.append(num + 1)
        num += 2
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[2] = b"<< /Type /Pages /Resources %s /Kids [%s] /Count %d >>" % (
        resources,
        b" ".join(b"%d 0 R" % k for k in kids),
        len(kids),
    )
    if loose:
        offsets, body = [], b""
        for n, obj in loose.items():
            offsets.append(b"%d %d" % (n, len(body)))
            body += obj + b"\n"
        header = b" ".join(offsets) + b"\n"
        objects[num] = stream(header + body, b" /Type /ObjStm /N %d /First %d" % (len(loose), len(header)))
    out = b"%PDF-1.7\n"
    for n in sorted(objects):
        out += b"%d 0 obj\n%s\nendobj\n" % (n, objects[n])
    return out + extra + b"trailer\n<< /Root 1 0 R >>\n%%EOF\n"


def make_docx(path, body_xml, *, extra_parts=None):
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        document = f'<?xml version="1.0"?><w:document {ns}><w:body>{body_xml}</w:body></w:document>'
        archive.writestr("word/document.xml", document)
        for name, xml in (extra_parts or {}).items():
            archive.writestr(name, xml)
    return path


_SS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
_RNS = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
_PKG = 'xmlns="http://schemas.openxmlformats.org/package/2006/relationships"'


def make_xlsx(path, sheets, shared=()):
    """``sheets`` is a list of (name, rows XML); sheet 2 is listed first in the relationships file to
    check that workbook order, not file order, decides the output."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        listed = "".join(f'<sheet name="{n}" sheetId="{i}" r:id="rId{i}"/>' for i, (n, _) in enumerate(sheets, 1))
        archive.writestr("xl/workbook.xml", f"<workbook {_SS} {_RNS}><sheets>{listed}</sheets></workbook>")
        rels = "".join(
            f'<Relationship Id="rId{i}" Target="worksheets/sheet{i}.xml"/>' for i in reversed(range(1, len(sheets) + 1))
        )
        archive.writestr("xl/_rels/workbook.xml.rels", f"<Relationships {_PKG}>{rels}</Relationships>")
        for i, (_, rows) in enumerate(sheets, 1):
            archive.writestr(
                f"xl/worksheets/sheet{i}.xml", f"<worksheet {_SS}><sheetData>{rows}</sheetData></worksheet>"
            )
        if shared:
            items = "".join(f"<si><t>{t}</t></si>" for t in shared)
            archive.writestr("xl/sharedStrings.xml", f"<sst {_SS}>{items}</sst>")
    return path


_DML = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
_PML = 'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'


def make_pptx(path, slides, *, listed=True):
    """``slides`` are lists of paragraphs in presentation order; the slide files are numbered in reverse
    so that the presentation's own order has to be followed."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        count = len(slides)
        ids = "".join(f'<p:sldId id="{255 + i}" r:id="rId{i}"/>' for i in range(1, count + 1)) if listed else ""
        archive.writestr(
            "ppt/presentation.xml", f"<p:presentation {_PML} {_RNS}><p:sldIdLst>{ids}</p:sldIdLst></p:presentation>"
        )
        rels = "".join(
            f'<Relationship Id="rId{i}" Target="slides/slide{count + 1 - i}.xml"/>' for i in range(1, count + 1)
        )
        archive.writestr("ppt/_rels/presentation.xml.rels", f"<Relationships {_PKG}>{rels}</Relationships>")
        for i, paragraphs in enumerate(slides, 1):
            body = "".join(f"<a:p><a:r><a:t>{p}</a:t></a:r></a:p>" for p in paragraphs)
            shape = f"<p:sp><p:txBody>{body}</p:txBody></p:sp>"
            xml = f"<p:sld {_PML} {_DML}><p:cSld><p:spTree>{shape}</p:spTree></p:cSld></p:sld>"
            archive.writestr(f"ppt/slides/slide{count + 1 - i}.xml", xml)
    return path


_ODF_NS = (
    'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
    'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
    'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
    'xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"'
)


def make_odf(path, body):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", "application/vnd.oasis.opendocument")
        archive.writestr(
            "content.xml",
            f"<office:document-content {_ODF_NS}><office:body>{body}</office:body></office:document-content>",
        )
    return path


CMAP = b"""/CIDInit /ProcSet findresource begin
begincmap
1 begincodespacerange <0000> <FFFF> endcodespacerange
2 beginbfchar
<0001> <0042>
<0002> <00E9>
endbfchar
1 beginbfrange
<0010> <0012> <0061>
endbfrange
endcmap"""


# --- PDF ----------------------------------------------------------------------------------------


def test_pdf_text_with_line_moves_and_word_gaps(tmp_path):
    content = b"BT /F1 12 Tf 72 720 Td (Backups run nightly.) Tj 0 -14 Td [(Kept for)-300(30 days)] TJ ET"
    path = tmp_path / "plan.pdf"
    path.write_bytes(make_pdf([content]))
    assert documents.extract_text(path) == "[page 1]\nBackups run nightly.\nKept for 30 days"


def test_pdf_pages_come_in_page_order_with_markers():
    data = make_pdf([b"BT (first page) Tj ET", b"BT (second page) Tj ET"])
    assert documents.pdf_text(data) == "[page 1]\nfirst page\n\n[page 2]\nsecond page"


def test_pdf_tounicode_cmap_maps_two_byte_codes():
    content = b"BT /F1 10 Tf <0001000200100011 0012> Tj ET"
    data = make_pdf([content], fonts={b"F1": CMAP})
    assert documents.pdf_text(data) == "[page 1]\nBéabc"


def test_pdf_fonts_inside_a_compressed_object_stream():
    data = make_pdf([b"BT /F1 10 Tf <00010002> Tj ET"], fonts={b"F1": CMAP}, object_stream=True)
    assert documents.pdf_text(data) == "[page 1]\nBé"


def test_pdf_literal_string_escapes():
    content = rb"BT (a \(b\) c\\d \101\102 e) Tj ET"
    assert documents.pdf_text(make_pdf([content], compress=False)) == "[page 1]\na (b) c\\d AB e"


def test_pdf_quote_operator_starts_a_new_line():
    data = make_pdf([b"BT (one) Tj (two) ' ET"])
    assert documents.pdf_text(data) == "[page 1]\none\ntwo"


def test_pdf_without_text_is_empty_and_image_streams_are_ignored():
    image = b"5 0 obj\n<< /Length 3 /Filter /DCTDecode >>\nstream\nabc\nendstream\nendobj\n"
    assert documents.pdf_text(make_pdf([b"q 1 0 0 1 0 0 cm Q"], extra=image)) == ""


@pytest.mark.parametrize(
    "data,message",
    [
        (b"hello", "not a PDF"),
        (make_pdf([b"BT (x) Tj ET"], extra=b"trailer << /Encrypt 9 0 R >>\n"), "encrypted"),
    ],
)
def test_pdf_refusals(data, message):
    with pytest.raises(documents.DocumentError, match=message):
        documents.pdf_text(data)


def test_pdf_decompression_is_capped(monkeypatch):
    monkeypatch.setattr(documents, "_MAX_EXPANDED_BYTES", 1000)
    data = make_pdf([b"BT (" + b"x" * 5000 + b") Tj ET"])
    with pytest.raises(documents.DocumentError, match="expands to more than"):
        documents.pdf_text(data)


def test_pdf_with_a_corrupt_stream_is_empty_not_an_error():
    broken = b"%PDF-1.4\n1 0 obj\n<< /Type /Page /Contents 2 0 R >>\nendobj\n"
    broken += b"2 0 obj\n<< /Length 4 /Filter /FlateDecode >>\nstream\nnope\nendstream\nendobj\n"
    assert documents.pdf_text(broken) == ""


# --- Word ---------------------------------------------------------------------------------------


def test_docx_paragraphs_tabs_breaks_and_footnotes(tmp_path):
    body = (
        "<w:p><w:r><w:t>Restore drill</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>Monthly</w:t><w:tab/><w:t>first Monday</w:t><w:br/><w:t>on call</w:t></w:r></w:p>"
    )
    notes = (
        '<w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:footnote><w:p><w:r><w:t>See the runbook.</w:t></w:r></w:p></w:footnote></w:footnotes>"
    )
    path = make_docx(tmp_path / "drill.docx", body, extra_parts={"word/footnotes.xml": notes})
    assert documents.extract_text(path) == "Restore drill\nMonthly\tfirst Monday\non call\nSee the runbook."


def test_docx_refusals(tmp_path, monkeypatch):
    bad = tmp_path / "bad.docx"
    bad.write_bytes(b"not a zip")
    with pytest.raises(documents.DocumentError, match="not a valid Word document"):
        documents.extract_text(bad)

    empty = tmp_path / "empty.docx"
    with zipfile.ZipFile(empty, "w") as archive:
        archive.writestr("other.xml", "<x/>")
    with pytest.raises(documents.DocumentError, match="no word/document.xml"):
        documents.extract_text(empty)

    doctype = tmp_path / "doctype.docx"
    with zipfile.ZipFile(doctype, "w") as archive:
        archive.writestr("word/document.xml", '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><x/>')
    with pytest.raises(documents.DocumentError, match="DOCTYPE"):
        documents.extract_text(doctype)

    monkeypatch.setattr(documents, "_MAX_EXPANDED_BYTES", 10)
    big = make_docx(tmp_path / "big.docx", "<w:p><w:r><w:t>" + "x" * 100 + "</w:t></w:r></w:p>")
    with pytest.raises(documents.DocumentError, match="expands to more than"):
        documents.extract_text(big)


def test_extract_text_refuses_other_types_and_oversized_files(tmp_path, monkeypatch):
    with pytest.raises(documents.DocumentError, match="not a supported document type"):
        documents.extract_text(tmp_path / "notes.txt")
    path = tmp_path / "huge.pdf"
    path.write_bytes(make_pdf([b"BT (x) Tj ET"]))
    monkeypatch.setattr(documents, "MAX_DOCUMENT_BYTES", 10)
    with pytest.raises(documents.DocumentError, match="larger than"):
        documents.extract_text(path)
    with pytest.raises(documents.DocumentError, match="cannot read"):
        documents.extract_text(tmp_path / "missing.docx")


# --- Excel, PowerPoint, OpenDocument ------------------------------------------------------------


def test_xlsx_sheets_in_workbook_order_with_cell_types(tmp_path):
    budget = (
        '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
        '<row r="2"><c r="A2" t="inlineStr"><is><t>Backups</t></is></c><c r="B2"><v>1200</v></c>'
        '<c r="C2" t="b"><v>1</v></c><c r="D2" t="e"><v>#DIV/0!</v></c></row>'
        '<row r="3"/>'
    )
    notes = '<row r="1"><c r="A1" t="str"><f>A2</f><v>restore drill monthly</v></c></row>'
    path = make_xlsx(tmp_path / "plan.xlsx", [("Budget", budget), ("Notes", notes)], shared=("Item", "Cost"))
    assert documents.extract_text(path) == (
        "[sheet Budget]\nItem\tCost\nBackups\t1200\tTRUE\n\n[sheet Notes]\nrestore drill monthly"
    )


def test_pptx_slides_follow_the_presentation_order(tmp_path):
    path = make_pptx(tmp_path / "deck.pptx", [["Backups", "Nightly pg_dump"], [], ["Restore drill"]])
    assert documents.extract_text(path) == "[slide 1]\nBackups\nNightly pg_dump\n\n[slide 3]\nRestore drill"
    unlisted = make_pptx(tmp_path / "unlisted.pptx", [["first"], ["second"]], listed=False)
    assert documents.extract_text(unlisted) == "[slide 1]\nsecond\n\n[slide 2]\nfirst"  # by file number


def test_odt_paragraphs_spaces_tabs_and_breaks(tmp_path):
    body = (
        "<office:text><text:h>Backups</text:h>"
        '<text:p>nightly<text:s text:c="2"/>dump<text:tab/>02:00<text:line-break/>kept 30 days</text:p>'
        "<text:list><text:list-item><text:p>restore <text:span>drill</text:span></text:p></text:list-item></text:list>"
        "</office:text>"
    )
    path = make_odf(tmp_path / "plan.odt", body)
    assert documents.extract_text(path) == "Backups\nnightly  dump\t02:00\nkept 30 days\nrestore drill"


def test_ods_sheets_and_odp_slides(tmp_path):
    sheet = (
        '<office:spreadsheet><table:table table:name="Budget">'
        "<table:table-row><table:table-cell><text:p>Item</text:p></table:table-cell>"
        "<table:table-cell/><table:table-cell><text:p>Cost</text:p></table:table-cell></table:table-row>"
        "<table:table-row><table:table-cell/></table:table-row>"
        "</table:table></office:spreadsheet>"
    )
    assert documents.extract_text(make_odf(tmp_path / "b.ods", sheet)) == "[sheet Budget]\nItem\tCost"
    slides = (
        "<office:presentation><draw:page><draw:frame><draw:text-box><text:p>Backups</text:p>"
        "</draw:text-box></draw:frame></draw:page><draw:page><text:p>Restore drill</text:p></draw:page>"
        "</office:presentation>"
    )
    assert documents.extract_text(make_odf(tmp_path / "d.odp", slides)) == (
        "[slide 1]\nBackups\n\n[slide 2]\nRestore drill"
    )


@pytest.mark.parametrize(
    ("name", "message"),
    [("x.xlsx", "no xl/workbook.xml"), ("x.pptx", "no ppt/presentation.xml"), ("x.odt", "no content.xml")],
)
def test_office_refusals(tmp_path, name, message):
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("other.xml", "<x/>")
    with pytest.raises(documents.DocumentError, match=message):
        documents.extract_text(path)
    path.write_bytes(b"not a zip")
    with pytest.raises(documents.DocumentError, match="not a valid"):
        documents.extract_text(path)


def test_office_decompression_is_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(documents, "_MAX_EXPANDED_BYTES", 100)
    rows = '<row r="1"><c r="A1" t="inlineStr"><is><t>' + "x" * 200 + "</t></is></c></row>"
    with pytest.raises(documents.DocumentError, match="expands to more than"):
        documents.extract_text(make_xlsx(tmp_path / "big.xlsx", [("S", rows)]))


# --- indexing -----------------------------------------------------------------------------------


def test_documents_are_indexed_and_searchable(tmp_path):
    (tmp_path / "plan.pdf").write_bytes(make_pdf([b"BT (pasta boils in salted water) Tj ET"]))
    make_docx(tmp_path / "drill.docx", "<w:p><w:r><w:t>the restore drill runs monthly</w:t></w:r></w:p>")
    (tmp_path / "broken.pdf").write_bytes(b"%PDF-1.4 garbage")
    (tmp_path / "notes.md").write_text("retries back off", encoding="utf-8")

    files = list(engine.iter_files(tmp_path))
    assert sorted(p.name for p in files) == ["broken.pdf", "drill.docx", "notes.md", "plan.pdf"]
    assert sorted(p.name for p in engine.iter_files(tmp_path, read_documents=False)) == ["notes.md"]

    conn = sqlite3.connect(":memory:")
    engine.ensure_schema(conn)
    stats = engine.update_index(conn, tmp_path, "toy", toy_embed, files)
    assert stats["indexed_files"] == 4 and stats["chunks"] == 3  # the broken PDF has no text
    hits = engine.search(conn, tmp_path, "toy", toy_embed(["restore drill"])[0], 1, query="restore drill")
    assert hits[0]["path"] == "drill.docx" and "monthly" in hits[0]["text"]
    conn.close()


def test_every_document_result_names_its_page(tmp_path):
    pages = [b"BT (" + b"filler line " * 20 + b") Tj ET"] * 3 + [b"BT (the restore drill runs monthly) Tj ET"]
    (tmp_path / "plan.pdf").write_bytes(make_pdf(pages))
    make_pptx(tmp_path / "deck.pptx", [["intro"], ["the restore drill is on slide two"]])
    conn = sqlite3.connect(":memory:")
    engine.ensure_schema(conn)
    engine.update_index(conn, tmp_path, "toy", toy_embed, list(engine.iter_files(tmp_path)), max_chars=120)
    hits = engine.search(conn, tmp_path, "toy", None, 5, query="restore drill", ranking="keyword")
    texts = {hit["path"]: hit["text"] for hit in hits}
    assert texts["plan.pdf"].startswith("[page 4]\n") and "restore drill" in texts["plan.pdf"]
    assert texts["deck.pptx"].startswith("[slide 1]\nintro")  # a short deck fits in one passage
    assert "[slide 2]\nthe restore drill" in texts["deck.pptx"]
    conn.close()


def test_with_locations_keeps_line_numbers_and_existing_markers():
    text = "[page 1]\na\nb\n[page 2]\nc"
    chunks = [(1, 2, "[page 1]\na"), (3, 5, "b\n[page 2]\nc"), (5, 5, "c")]
    assert engine.with_locations(chunks, text) == [
        (1, 2, "[page 1]\na"),
        (3, 5, "[page 1]\nb\n[page 2]\nc"),
        (5, 5, "[page 2]\nc"),
    ]
