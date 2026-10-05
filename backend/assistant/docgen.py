"""Fill UC-ASS-05 templates and emit downloadable office files."""

from __future__ import annotations

import io
import re
import struct
import zipfile
from pathlib import Path
from typing import Any, Mapping, Sequence
from xml.sax.saxutils import escape

from hub.models import AssistantDocumentTemplate

FIELD_RE = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")
_FONT_CANDIDATES = (
    Path(r"C:\Windows\Fonts\arial.ttf"),
    Path(r"C:\Windows\Fonts\calibri.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    Path("/usr/share/fonts/truetype/freefont/FreeSans.ttf"),
)


class DocgenError(ValueError):
    """Invalid template fields or payload."""


def render_body(
    template: AssistantDocumentTemplate,
    values: Mapping[str, Any],
    *,
    strict: bool = True,
) -> str:
    missing: list[str] = []
    for item in template.fields or []:
        if not isinstance(item, Mapping):
            continue
        field_id = str(item.get("id") or "").strip()
        if not field_id:
            continue
        if item.get("required") and not str(values.get(field_id) or "").strip():
            missing.append(str(item.get("label") or field_id))
    if missing and strict:
        raise DocgenError("заполните: " + ", ".join(missing))

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        return str(values.get(key) or "").strip()

    return FIELD_RE.sub(replace, template.body or "").strip()


def _xml_text(value: str) -> str:
    cleaned = "".join(
        char for char in value if char in "\t\n\r" or ord(char) >= 32
    )
    return escape(cleaned)


def _docx_bytes(text: str) -> bytes:
    paragraphs = text.splitlines() or [""]
    runs = []
    for line in paragraphs:
        body = _xml_text(line)
        if body:
            runs.append(
                "<w:p><w:r><w:t xml:space=\"preserve\">"
                f"{body}</w:t></w:r></w:p>"
            )
        else:
            runs.append("<w:p/>")
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<w:body>{''.join(runs)}"
        "<w:sectPr>"
        '<w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1134" w:right="850" w:bottom="1134" w:left="1701" '
        'w:header="708" w:footer="708" w:gutter="0"/>'
        "</w:sectPr></w:body></w:document>"
    )
    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:docDefaults><w:rPrDefault><w:rPr>"
        '<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/>'
        '<w:sz w:val="22"/><w:szCs w:val="22"/>'
        "</w:rPr></w:rPrDefault></w:docDefaults>"
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
        '<w:name w:val="Normal"/><w:qFormat/>'
        "</w:style></w:styles>"
    )
    settings_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:zoom w:percent="100"/>'
        "</w:settings>"
    )
    core_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties '
        'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<dc:title>Документ</dc:title><dc:creator>Суфлёр</dc:creator>"
        "</cp:coreProperties>"
    )
    app_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
        "<Application>Суфлёр</Application></Properties>"
    )
    types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        '<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        "</Relationships>"
    )
    document_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>'
        "</Relationships>"
    )
    parts = {
        "[Content_Types].xml": types,
        "_rels/.rels": rels,
        "word/document.xml": document_xml,
        "word/_rels/document.xml.rels": document_rels,
        "word/styles.xml": styles_xml,
        "word/settings.xml": settings_xml,
        "docProps/core.xml": core_xml,
        "docProps/app.xml": app_xml,
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in parts.items():
            archive.writestr(name, payload.encode("utf-8"))
    return buffer.getvalue()


def _pdf_assemble(objects: list[bytes]) -> bytes:
    header = b"%PDF-1.4\n"
    offsets = [0]
    body = bytearray()
    cursor = len(header)
    for obj in objects:
        offsets.append(cursor)
        body.extend(obj)
        cursor += len(obj)
    xref_pos = cursor
    count = len(objects) + 1
    xref = [f"xref\n0 {count}\n0000000000 65535 f \n".encode("ascii")]
    for offset in offsets[1:]:
        xref.append(f"{offset:010d} 00000 n \n".encode("ascii"))
    trailer = (
        f"trailer << /Size {count} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n"
    ).encode("ascii")
    return header + bytes(body) + b"".join(xref) + trailer


def _pdf_helvetica(text: str) -> bytes:
    lines = (text.splitlines() or [""])[:40]
    content_lines = ["BT", "/F1 12 Tf", "50 780 Td"]
    for index, line in enumerate(lines):
        safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        if index:
            content_lines.append("0 -16 Td")
        content_lines.append(f"({safe}) Tj")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1", errors="replace")
    return _pdf_assemble(
        [
            b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
            b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
            (
                b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
            ),
            (
                b"4 0 obj << /Length "
                + str(len(stream)).encode("ascii")
                + b" >> stream\n"
                + stream
                + b"\nendstream endobj\n"
            ),
            b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
        ]
    )


def _ttf_table(data: bytes, tag: bytes) -> bytes:
    count = struct.unpack_from(">H", data, 4)[0]
    for index in range(count):
        offset = 12 + index * 16
        if data[offset : offset + 4] == tag:
            start = struct.unpack_from(">I", data, offset + 8)[0]
            length = struct.unpack_from(">I", data, offset + 12)[0]
            return data[start : start + length]
    raise ValueError(f"ttf table {tag!r} missing")


def _ttf_cmap(data: bytes) -> dict[int, int]:
    cmap = _ttf_table(data, b"cmap")
    num = struct.unpack_from(">H", cmap, 2)[0]
    records: list[tuple[int, int, int]] = []
    for index in range(num):
        platform, encoding, offset = struct.unpack_from(">HHI", cmap, 4 + index * 8)
        records.append((platform, encoding, offset))
    preferred = [
        rec for rec in records if rec[0] == 3 and rec[1] in {1, 10}
    ] or records
    mapping: dict[int, int] = {}
    for _platform, _encoding, offset in preferred:
        fmt = struct.unpack_from(">H", cmap, offset)[0]
        if fmt == 4:
            seg_count = struct.unpack_from(">H", cmap, offset + 6)[0] // 2
            end_off = offset + 14
            start_off = end_off + 2 * seg_count + 2
            delta_off = start_off + 2 * seg_count
            range_off = delta_off + 2 * seg_count
            range_off + 2 * seg_count
            for seg in range(seg_count):
                end = struct.unpack_from(">H", cmap, end_off + 2 * seg)[0]
                start = struct.unpack_from(">H", cmap, start_off + 2 * seg)[0]
                delta = struct.unpack_from(">h", cmap, delta_off + 2 * seg)[0]
                range_offset = struct.unpack_from(">H", cmap, range_off + 2 * seg)[0]
                for code in range(start, end + 1):
                    if range_offset == 0:
                        glyph = (code + delta) & 0xFFFF
                    else:
                        index_off = (
                            range_off
                            + 2 * seg
                            + range_offset
                            + 2 * (code - start)
                        )
                        if index_off + 2 > len(cmap):
                            continue
                        glyph = struct.unpack_from(">H", cmap, index_off)[0]
                        if glyph:
                            glyph = (glyph + delta) & 0xFFFF
                    if glyph:
                        mapping[code] = glyph
            if mapping:
                return mapping
        if fmt == 12:
            n_groups = struct.unpack_from(">I", cmap, offset + 12)[0]
            pos = offset + 16
            for _ in range(n_groups):
                start, end, glyph_start = struct.unpack_from(">III", cmap, pos)
                for code in range(start, end + 1):
                    mapping[code] = glyph_start + (code - start)
                pos += 12
            if mapping:
                return mapping
    return mapping


def _ttf_metrics(data: bytes) -> tuple[int, int, int, tuple[int, int, int, int], list[int]]:
    head = _ttf_table(data, b"head")
    units = struct.unpack_from(">H", head, 18)[0] or 1000
    bbox = struct.unpack_from(">hhhh", head, 36)
    hhea = _ttf_table(data, b"hhea")
    ascent = struct.unpack_from(">h", hhea, 4)[0]
    descent = struct.unpack_from(">h", hhea, 6)[0]
    num_h = struct.unpack_from(">H", hhea, 34)[0]
    maxp = _ttf_table(data, b"maxp")
    num_glyphs = struct.unpack_from(">H", maxp, 4)[0]
    hmtx = _ttf_table(data, b"hmtx")
    widths: list[int] = []
    last = 0
    for index in range(num_glyphs):
        if index < num_h:
            last = struct.unpack_from(">H", hmtx, index * 4)[0]
        widths.append(round(last * 1000 / units))
    scale = 1000 / units
    return (
        round(ascent * scale),
        round(descent * scale),
        units,
        tuple(round(value * scale) for value in bbox),
        widths,
    )


def _pdf_unicode_cmap(used: Mapping[int, int]) -> bytes:
    ranges = []
    for glyph, code in used.items():
        ranges.append(f"<{glyph:04X}> <{code:04X}>")
    body = (
        "/CIDInit /ProcSet findresource begin\n"
        "12 dict begin\nbegincmap\n"
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
        "/CMapName /Adobe-Identity-UCS def\n/CMapType 2 def\n"
        "1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n"
        f"{len(ranges)} beginbfchar\n"
        + "\n".join(ranges)
        + "\nendbfchar\nendcmap\nCMapName currentdict /CMap defineresource pop\nend\nend"
    )
    return body.encode("ascii")


def _pdf_embedded_ttf(text: str, font_path: Path) -> bytes:
    data = font_path.read_bytes()
    cmap = _ttf_cmap(data)
    ascent, descent, _units, bbox, widths = _ttf_metrics(data)
    lines = (text.splitlines() or [""])[:40]
    used: dict[int, int] = {}
    content = ["BT", "/F1 12 Tf", "50 780 Td"]
    for index, line in enumerate(lines):
        hex_parts: list[str] = []
        for char in line:
            glyph = cmap.get(ord(char), cmap.get(32, 0))
            if glyph:
                used[glyph] = ord(char)
                hex_parts.append(f"{glyph:04X}")
        if index:
            content.append("0 -16 Td")
        content.append(f"<{''.join(hex_parts)}> Tj")
    content.append("ET")
    stream = "\n".join(content).encode("ascii")
    to_unicode = _pdf_unicode_cmap(used)
    width_pairs = " ".join(
        f"{glyph} [{widths[glyph] if glyph < len(widths) else 600}]"
        for glyph in sorted(used)
    )
    font_stream = (
        f"8 0 obj << /Length {len(data)} /Length1 {len(data)} >> stream\n".encode("ascii")
        + data
        + b"\nendstream endobj\n"
    )
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        (
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
        ),
        (
            b"4 0 obj << /Length "
            + str(len(stream)).encode("ascii")
            + b" >> stream\n"
            + stream
            + b"\nendstream endobj\n"
        ),
        (
            b"5 0 obj << /Type /Font /Subtype /Type0 /BaseFont /SuflerSans "
            b"/Encoding /Identity-H /DescendantFonts [6 0 R] /ToUnicode 9 0 R >> endobj\n"
        ),
        (
            (
                "6 0 obj << /Type /Font /Subtype /CIDFontType2 /BaseFont /SuflerSans "
                "/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> "
                f"/FontDescriptor 7 0 R /DW 600 /W [{width_pairs}] /CIDToGIDMap /Identity >> endobj\n"
            ).encode("ascii")
        ),
        (
            (
                "7 0 obj << /Type /FontDescriptor /FontName /SuflerSans /Flags 32 "
                f"/FontBBox [{bbox[0]} {bbox[1]} {bbox[2]} {bbox[3]}] "
                f"/ItalicAngle 0 /Ascent {ascent} /Descent {descent} "
                f"/CapHeight {ascent} /StemV 80 /FontFile2 8 0 R >> endobj\n"
            ).encode("ascii")
        ),
        font_stream,
        (
            b"9 0 obj << /Length "
            + str(len(to_unicode)).encode("ascii")
            + b" >> stream\n"
            + to_unicode
            + b"\nendstream endobj\n"
        ),
    ]
    return _pdf_assemble(objects)


def _find_cyrillic_font() -> Path | None:
    for path in _FONT_CANDIDATES:
        if path.is_file():
            return path
    return None


def _pdf_bytes(text: str) -> bytes:
    font_path = _find_cyrillic_font()
    if font_path is None:
        return _pdf_helvetica(text)
    try:
        return _pdf_embedded_ttf(text, font_path)
    except Exception:
        return _pdf_helvetica(text)


def _xlsx_bytes(text: str) -> bytes:
    rows = []
    for index, line in enumerate(text.splitlines() or [""], start=1):
        rows.append(
            f'<row r="{index}"><c r="A{index}" t="inlineStr"><is><t>'
            f"{escape(line)}</t></is></c></row>"
        )
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(rows)}</sheetData></worksheet>"
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Документ" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    wb_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return buffer.getvalue()


def _split_slides(text: str) -> list[tuple[str, list[str]]]:
    chunks: list[tuple[str, list[str]]] = []
    title = "Слайд"
    lines: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            if lines or chunks:
                chunks.append((title, lines))
            title = line[3:].strip() or "Слайд"
            lines = []
            continue
        lines.append(line)
    chunks.append((title, lines))
    return chunks or [("Слайд", [""])]


_NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
_NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_NS_REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def _run(text: str, size: int = 1800, bold: bool = False) -> str:
    value = escape(text if text else " ")
    bold_attr = ' b="1"' if bold else ""
    return (
        f'<a:r><a:rPr lang="ru-RU" sz="{size}"{bold_attr}>'
        '<a:solidFill><a:srgbClr val="1F2937"/></a:solidFill>'
        '<a:latin typeface="Calibri"/><a:ea typeface="Calibri"/>'
        f'</a:rPr><a:t xml:space="preserve">{value}</a:t></a:r>'
    )


def _paragraphs(lines: list[str], size: int, bold: bool = False) -> str:
    items = [line for line in lines if str(line).strip()] or [""]
    parts = []
    for line in items:
        parts.append(
            "<a:p><a:pPr algn=\"l\"/>"
            f"{_run(line, size=size, bold=bold)}"
            f'<a:endParaRPr lang="ru-RU" sz="{size}"/></a:p>'
        )
    return "".join(parts)


def _placeholder(
    *,
    shape_id: int,
    name: str,
    ph_type: str,
    idx: str | None,
    x: int,
    y: int,
    cx: int,
    cy: int,
    paragraphs: str,
    on_layout: bool,
) -> str:
    idx_attr = f' idx="{idx}"' if idx is not None else ""
    geom = (
        f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/>'
        "</a:xfrm><a:prstGeom prst=\"rect\"><a:avLst/></a:prstGeom></p:spPr>"
        if on_layout
        else "<p:spPr/>"
    )
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{shape_id}" name="{escape(name)}"/>'
        "<p:cNvSpPr><a:spLocks noGrp=\"1\"/></p:cNvSpPr>"
        f'<p:nvPr><p:ph type="{ph_type}"{idx_attr}/></p:nvPr></p:nvSpPr>'
        f"{geom}<p:txBody><a:bodyPr/><a:lstStyle/>{paragraphs}</p:txBody></p:sp>"
    )


def _shape_tree(*shapes: str) -> str:
    return (
        "<p:spTree>"
        '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
        '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
        f"{''.join(shapes)}</p:spTree>"
    )


def _slide_xml(index: int, title: str, lines: list[str]) -> str:
    title_box = _placeholder(
        shape_id=2,
        name=f"Title {index}",
        ph_type="title",
        idx=None,
        x=457200,
        y=274638,
        cx=8229600,
        cy=1143000,
        paragraphs=_paragraphs([title or "Слайд"], size=3200, bold=True),
        on_layout=True,
    )
    body_box = _placeholder(
        shape_id=3,
        name=f"Content {index}",
        ph_type="body",
        idx="1",
        x=457200,
        y=1600200,
        cx=8229600,
        cy=3200400,
        paragraphs=_paragraphs([line for line in lines if line.strip()] or [""], size=2000),
        on_layout=True,
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<p:sld xmlns:a="{_NS_A}" xmlns:p="{_NS_P}" xmlns:r="{_NS_R}">'
        f"<p:cSld>{_shape_tree(title_box, body_box)}</p:cSld>"
        "<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>"
    )


def _pptx_theme() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<a:theme xmlns:a="{_NS_A}" name="Sufler">'
        "<a:themeElements><a:clrScheme name=\"Office\">"
        '<a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>'
        '<a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>'
        '<a:dk2><a:srgbClr val="1F2937"/></a:dk2>'
        '<a:lt2><a:srgbClr val="EEECE1"/></a:lt2>'
        '<a:accent1><a:srgbClr val="4F81BD"/></a:accent1>'
        '<a:accent2><a:srgbClr val="C0504D"/></a:accent2>'
        '<a:accent3><a:srgbClr val="9BBB59"/></a:accent3>'
        '<a:accent4><a:srgbClr val="8064A2"/></a:accent4>'
        '<a:accent5><a:srgbClr val="4BACC6"/></a:accent5>'
        '<a:accent6><a:srgbClr val="F79646"/></a:accent6>'
        '<a:hlink><a:srgbClr val="0000FF"/></a:hlink>'
        '<a:folHlink><a:srgbClr val="800080"/></a:folHlink>'
        "</a:clrScheme>"
        '<a:fontScheme name="Office"><a:majorFont>'
        '<a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/>'
        "</a:majorFont><a:minorFont>"
        '<a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/>'
        "</a:minorFont></a:fontScheme>"
        '<a:fmtScheme name="Office"><a:fillStyleLst>'
        '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
        '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
        '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
        "</a:fillStyleLst><a:lnStyleLst>"
        '<a:ln w="9525" cap="flat" cmpd="sng" algn="ctr">'
        '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/>'
        '</a:ln><a:ln w="9525" cap="flat" cmpd="sng" algn="ctr">'
        '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/>'
        '</a:ln><a:ln w="9525" cap="flat" cmpd="sng" algn="ctr">'
        '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/>'
        "</a:ln></a:lnStyleLst>"
        "<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle>"
        "<a:effectStyle><a:effectLst/></a:effectStyle>"
        "<a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>"
        '<a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
        '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
        '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:bgFillStyleLst>'
        "</a:fmtScheme></a:themeElements><a:objectDefaults/><a:extraClrSchemeLst/>"
        "</a:theme>"
    )


def _pptx_layout() -> str:
    title = _placeholder(
        shape_id=2,
        name="Title 1",
        ph_type="title",
        idx=None,
        x=457200,
        y=274638,
        cx=8229600,
        cy=1143000,
        paragraphs=_paragraphs(["Заголовок"], size=3200, bold=True),
        on_layout=True,
    )
    body = _placeholder(
        shape_id=3,
        name="Content Placeholder 2",
        ph_type="body",
        idx="1",
        x=457200,
        y=1600200,
        cx=8229600,
        cy=3200400,
        paragraphs=_paragraphs(["Текст слайда"], size=2000),
        on_layout=True,
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<p:sldLayout xmlns:a="{_NS_A}" xmlns:p="{_NS_P}" xmlns:r="{_NS_R}" '
        'type="tx" preserve="1">'
        f'<p:cSld name="Title and Content">{_shape_tree(title, body)}</p:cSld>'
        "<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>"
    )


def _pptx_master() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<p:sldMaster xmlns:a="{_NS_A}" xmlns:p="{_NS_P}" xmlns:r="{_NS_R}">'
        "<p:cSld><p:bg><p:bgRef idx=\"1001\"><a:schemeClr val=\"bg1\"/></p:bgRef></p:bg>"
        "<p:spTree>"
        '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
        '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
        "</p:spTree></p:cSld>"
        '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" '
        'accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" '
        'accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
        '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>'
        "<p:txStyles><p:titleStyle><a:lvl1pPr algn=\"l\">"
        '<a:defRPr sz="3200" b="1"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill>'
        '<a:latin typeface="Calibri"/></a:defRPr></a:lvl1pPr></p:titleStyle>'
        "<p:bodyStyle><a:lvl1pPr algn=\"l\">"
        '<a:defRPr sz="2000"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill>'
        '<a:latin typeface="Calibri"/></a:defRPr></a:lvl1pPr></p:bodyStyle>'
        "<p:otherStyle><a:lvl1pPr algn=\"l\">"
        '<a:defRPr sz="1800"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill>'
        '<a:latin typeface="Calibri"/></a:defRPr></a:lvl1pPr></p:otherStyle></p:txStyles>'
        "</p:sldMaster>"
    )


def _rels(items: list[tuple[str, str, str]]) -> str:
    body = "".join(
        f'<Relationship Id="{rel_id}" Type="{rel_type}" Target="{target}"/>'
        for rel_id, rel_type, target in items
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{_NS_REL}">{body}</Relationships>'
    )


def _pptx_bytes(text: str) -> bytes:
    slides = _split_slides(text)
    slide_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"
    master_ns = (
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster"
    )
    sld_ids = []
    pres_rels = [
        ("rId1", master_ns, "slideMasters/slideMaster1.xml"),
        (
            "rId2",
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/presProps",
            "presProps.xml",
        ),
        (
            "rId3",
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/viewProps",
            "viewProps.xml",
        ),
        (
            "rId4",
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/tableStyles",
            "tableStyles.xml",
        ),
    ]
    files: list[tuple[str, str]] = []
    overrides = [
        '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>',
        '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>',
        '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>',
        '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>',
        '<Override PartName="/ppt/presProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presProps+xml"/>',
        '<Override PartName="/ppt/viewProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.viewProps+xml"/>',
        '<Override PartName="/ppt/tableStyles.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml"/>',
    ]
    for index, (title, lines) in enumerate(slides, start=1):
        rel_id = f"rId{index + 4}"
        sld_ids.append(f'<p:sldId id="{255 + index}" r:id="{rel_id}"/>')
        pres_rels.append((rel_id, slide_ns, f"slides/slide{index}.xml"))
        overrides.append(
            f'<Override PartName="/ppt/slides/slide{index}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        )
        files.append((f"ppt/slides/slide{index}.xml", _slide_xml(index, title, lines)))
        files.append(
            (
                f"ppt/slides/_rels/slide{index}.xml.rels",
                _rels(
                    [
                        (
                            "rId1",
                            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout",
                            "../slideLayouts/slideLayout1.xml",
                        )
                    ]
                ),
            )
        )
    presentation = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<p:presentation xmlns:a="{_NS_A}" xmlns:p="{_NS_P}" xmlns:r="{_NS_R}">'
        '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
        f'<p:sldIdLst>{"".join(sld_ids)}</p:sldIdLst>'
        '<p:sldSz cx="9144000" cy="5143500" type="screen16x9"/>'
        '<p:notesSz cx="6858000" cy="9144000"/></p:presentation>'
    )
    types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        + "".join(overrides)
        + "</Types>"
    )
    files.extend(
        [
            ("[Content_Types].xml", types),
            (
                "_rels/.rels",
                _rels(
                    [
                        (
                            "rId1",
                            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument",
                            "ppt/presentation.xml",
                        )
                    ]
                ),
            ),
            ("ppt/presentation.xml", presentation),
            ("ppt/_rels/presentation.xml.rels", _rels(pres_rels)),
            (
                "ppt/presProps.xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<p:presentationPr xmlns:a="{_NS_A}" xmlns:p="{_NS_P}" xmlns:r="{_NS_R}"/>',
            ),
            (
                "ppt/viewProps.xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<p:viewPr xmlns:a="{_NS_A}" xmlns:p="{_NS_P}" xmlns:r="{_NS_R}">'
                "<p:slideViewPr><p:cSldViewPr><p:cViewPr varScale=\"1\">"
                '<p:scale><a:sx n="100" d="100"/><a:sy n="100" d="100"/></p:scale>'
                '<p:origin x="0" y="0"/></p:cViewPr></p:cSldViewPr></p:slideViewPr>'
                "</p:viewPr>",
            ),
            (
                "ppt/tableStyles.xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<a:tblStyleLst xmlns:a="{_NS_A}" '
                'def="{5C22544A-7EE6-4342-B047-A184337B970F}"/>',
            ),
            ("ppt/theme/theme1.xml", _pptx_theme()),
            ("ppt/slideLayouts/slideLayout1.xml", _pptx_layout()),
            (
                "ppt/slideLayouts/_rels/slideLayout1.xml.rels",
                _rels(
                    [
                        (
                            "rId1",
                            master_ns,
                            "../slideMasters/slideMaster1.xml",
                        )
                    ]
                ),
            ),
            ("ppt/slideMasters/slideMaster1.xml", _pptx_master()),
            (
                "ppt/slideMasters/_rels/slideMaster1.xml.rels",
                _rels(
                    [
                        (
                            "rId1",
                            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout",
                            "../slideLayouts/slideLayout1.xml",
                        ),
                        (
                            "rId2",
                            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme",
                            "../theme/theme1.xml",
                        ),
                    ]
                ),
            ),
        ]
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in files:
            archive.writestr(name, payload)
    return buffer.getvalue()


def _bpmn_bytes(text: str) -> bytes:
    """BPMN 2.0 with diagram coordinates. bpmn.io hides a file that has no DI."""
    steps = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if not steps:
        steps = ["Задача"]
    steps = steps[:12]
    task_w, task_h = 220, 80
    event = 36
    gap = 46
    left = 160
    top = 40
    nodes: list[tuple[str, str, str, int, int, int, int]] = []
    y = top
    start_x = left + (task_w - event) // 2
    nodes.append(("start", "Старт", "startEvent", start_x, y, event, event))
    y += event + gap
    for index, step in enumerate(steps, start=1):
        nodes.append((f"task{index}", step[:120], "userTask", left, y, task_w, task_h))
        y += task_h + gap
    end_x = left + (task_w - event) // 2
    nodes.append(("end", "Финиш", "endEvent", end_x, y, event, event))

    flow_xml: list[str] = []
    edge_xml: list[str] = []
    for index in range(len(nodes) - 1):
        source_id, _, _, sx, sy, sw, sh = nodes[index]
        target_id, _, _, tx, ty, tw, _th = nodes[index + 1]
        flow_id = f"flow{index + 1}"
        flow_xml.append(
            f'<sequenceFlow id="{flow_id}" sourceRef="{source_id}" targetRef="{target_id}"/>'
        )
        x1 = sx + sw // 2
        y1 = sy + sh
        x2 = tx + tw // 2
        y2 = ty
        edge_xml.append(
            f'<bpmndi:BPMNEdge id="edge_{flow_id}" bpmnElement="{flow_id}">'
            f'<di:waypoint x="{x1}" y="{y1}"/>'
            f'<di:waypoint x="{x2}" y="{y2}"/>'
            "</bpmndi:BPMNEdge>"
        )

    node_xml: list[str] = []
    shape_xml: list[str] = []
    for node_id, name, kind, x, y, w, h in nodes:
        label = escape(name)
        if kind == "userTask":
            node_xml.append(
                f'<userTask id="{node_id}" name="{label}">'
                f"<documentation>{label}</documentation></userTask>"
            )
        else:
            node_xml.append(f'<{kind} id="{node_id}" name="{label}"/>')
        shape_xml.append(
            f'<bpmndi:BPMNShape id="shape_{node_id}" bpmnElement="{node_id}">'
            f'<dc:Bounds x="{x}" y="{y}" width="{w}" height="{h}"/>'
            "</bpmndi:BPMNShape>"
        )

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" '
        'xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" '
        'xmlns:di="http://www.omg.org/spec/DD/20100524/DI" '
        'id="definitions" targetNamespace="http://sufler.local/bpmn">'
        '<process id="Process_1" name="Процесс" isExecutable="false">'
        + "".join(node_xml)
        + "".join(flow_xml)
        + "</process>"
        '<bpmndi:BPMNDiagram id="Diagram_1">'
        '<bpmndi:BPMNPlane id="Plane_1" bpmnElement="Process_1">'
        + "".join(shape_xml)
        + "".join(edge_xml)
        + "</bpmndi:BPMNPlane></bpmndi:BPMNDiagram></definitions>"
    )
    return xml.encode("utf-8")


_STUB_MARKERS = ("запрос принят", "используйте подтверждённые")


_PROMPT_NOISE = re.compile(
    r"(?i)\b("
    r"сделай|сделать|сгенерир\w*|подготов\w*|напиш\w*|создай|создать|"
    r"собери|нужн\w*|презентац\w*|слайд\w*|документ\w*|файл\w*|"
    r"про|для|это|меня|мне|пожалуйста|только|как"
    r")\b"
)
_KB_NAME_NOISE = frozenset(
    {
        "беларусбанк",
        "беларусбанка",
        "оао",
        "асб",
        "банк",
        "сайта",
        "сайт",
    }
)


def _topic_query(prompt: str) -> str:
    """Drop «сделай презентацию про», keep the product the user named."""
    cleaned = _PROMPT_NOISE.sub(" ", prompt or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,!?:;—-")
    return cleaned or (prompt or "").strip()


def _name_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for token in re.findall(r"[a-zа-я0-9]{3,}", (text or "").casefold().replace("ё", "е")):
        if token in _KB_NAME_NOISE:
            continue
        tokens.add(token)
        if len(token) > 5:
            tokens.add(token[:5])
    return tokens


def _catalog_names(kb_slugs: Sequence[str] | None) -> list[tuple[str, str]]:
    from hub.models import AssistantKnowledgeBase, ContactCenterKnowledgeBase

    wanted = {slug for slug in (kb_slugs or []) if slug}
    cc = ContactCenterKnowledgeBase.objects.all()
    assistant = AssistantKnowledgeBase.objects.all()
    if wanted:
        cc = cc.filter(slug__in=wanted)
        assistant = assistant.filter(slug__in=wanted)
    rows = [(kb.slug, kb.name or "") for kb in cc]
    rows.extend((kb.slug, kb.name or "") for kb in assistant)
    return rows


def _focus_slugs(query: str, kb_slugs: Sequence[str] | None) -> Sequence[str] | None:
    """If one selected base is named like the prompt, search only that base."""
    topic_tokens = _name_tokens(_topic_query(query))
    if not topic_tokens:
        return kb_slugs
    scored: list[tuple[int, str]] = []
    for slug, name in _catalog_names(kb_slugs):
        overlap = topic_tokens & _name_tokens(name)
        if overlap:
            scored.append((len(overlap), slug))
    if not scored:
        return kb_slugs
    scored.sort(key=lambda item: (-item[0], item[1]))
    best = scored[0][0]
    if best < 1:
        return kb_slugs
    winners = [slug for hits, slug in scored if hits == best]
    if len(winners) != 1:
        return kb_slugs
    return winners


def _matching_article_chunks(
    query: str,
    article_id: Any,
    kb_slug: str,
) -> list[tuple[str, str]]:
    """Chunks of the winning article, ordered by overlap with the prompt."""
    if article_id is None:
        return []
    try:
        from qu.service import _lexical_score

        if str(kb_slug).startswith("assistant_"):
            from ingest.models import AssistantProductionChunk

            rows = AssistantProductionChunk.objects.filter(
                is_active=True,
                article_id=article_id,
                kb_slug=kb_slug,
            )
        else:
            from ingest.models import CCProductionChunk

            rows = CCProductionChunk.objects.filter(
                is_active=True,
                article_id=article_id,
            )
        folded_query = query.casefold()
        wants_steps = any(
            word in folded_query for word in ("как ", "оформ", "порядок", "шаг")
        )
        scored: list[tuple[float, int, str, str]] = []
        for row in rows:
            content = row.content or ""
            if not content.strip():
                continue
            score = _lexical_score(query, row.title or "", content)
            folded = content.casefold()
            if wants_steps and "шаг " in folded:
                score += 0.35
            if folded.count("http") >= 3:
                score -= 0.4
            scored.append(
                (
                    score,
                    int(row.chunk_index),
                    (row.title or "Статья").strip(),
                    content,
                )
            )
        scored.sort(key=lambda item: (-item[0], item[1]))
        picked = [item for item in scored if item[0] > 0][:6] or scored[:6]
        return [(title, content) for _score, _index, title, content in picked]
    except Exception:
        return []


def _article_in_order(article_id: Any, kb_slug: str) -> list[tuple[str, str]]:
    """Every chunk of the article, in reading order, so slide count can follow it."""
    if article_id is None:
        return []
    try:
        if str(kb_slug).startswith("assistant_"):
            from ingest.models import AssistantProductionChunk

            rows = AssistantProductionChunk.objects.filter(
                is_active=True,
                article_id=article_id,
                kb_slug=kb_slug,
            )
        else:
            from ingest.models import CCProductionChunk

            rows = CCProductionChunk.objects.filter(
                is_active=True,
                article_id=article_id,
            )
        ordered = sorted(rows, key=lambda row: int(row.chunk_index))
        chunks: list[tuple[str, str]] = []
        for row in ordered:
            content = (row.content or "").strip()
            if not content:
                continue
            chunks.append(((row.title or "Статья").strip(), content[:700]))
        return chunks
    except Exception:
        return []


def _kb_context(
    query: str,
    kb_slugs: Sequence[str] | None,
    *,
    full_article: bool = False,
) -> str:
    """Retrieval for the product named in the prompt, then that article only."""
    topic = _topic_query(query)
    focused = _focus_slugs(query, kb_slugs)
    try:
        from assistant.chat import retrieve_assistant_context

        documents, _threshold = retrieve_assistant_context(
            [{"role": "user", "content": topic or query}],
            kb_slugs=focused,
            limit=8,
        )
    except Exception:
        return ""
    if not documents:
        return ""
    best = max(float(document.get("relevance_score") or 0) for document in documents)
    focused = [
        document
        for document in documents
        if float(document.get("relevance_score") or 0) >= best - 0.2
    ] or documents[:3]
    winner = focused[0]
    article_id = winner.get("article_id")
    kb_slug = str(winner.get("kb_slug") or "")
    chunks = (
        _article_in_order(article_id, kb_slug)
        if full_article
        else _matching_article_chunks(topic or query, article_id, kb_slug)
    )
    if not chunks:
        chunks = [
            (
                str(document.get("title") or "Статья").strip(),
                str(document.get("content") or ""),
            )
            for document in focused
        ]
    parts: list[str] = []
    for index, (title, content) in enumerate(chunks, start=1):
        compact = re.sub(r"\s+", " ", content).strip()
        if not compact:
            continue
        parts.append(f"[{index}] {title}\n{compact[:1600]}")
    return "\n\n".join(parts)


def _model_document_text(
    fmt: str,
    prompt: str,
    template_hint: str,
    fragments: str = "",
) -> str:
    shapes = {
        "pptx": (
            "Верни только слайды. Каждый слайд начинается строкой '## Заголовок', "
            "под ним короткие тезисы из статьи. "
            "Число слайдов не задано: его определяет объём статьи. "
            "Глава или отдельный блок статьи — отдельный слайд. "
            "Если дан каркас шаблона, порядок такой: первый блок — один слайд введения; "
            "блок «Содержание» замени любым числом слайдов по статье; "
            "блоки после содержания — снова по одному слайду, факты только из статьи. "
            "Не копируй пример и не ограничивай презентацию фиксированным числом слайдов."
        ),
        "bpmn": (
            "Верни только шаги процесса из статьи, один шаг на строку, от 5 до 8. "
            "Без нумерации и без пояснений."
        ),
        "xlsx": (
            "Верни таблицу по статье. Первая строка — заголовки через ' | '. "
            "Дальше строки с фактами из фрагментов. Без текста вокруг таблицы."
        ),
        "mmd": (
            "Верни только mermaid flowchart TD по шагам из статьи. Без пояснений."
        ),
    }
    instruction = shapes.get(
        fmt,
        "Напиши документ только по фрагментам статьи: суть, документы, "
        "порядок, сроки и суммы. Обычный текст, без markdown.",
    )
    user = prompt.strip()
    if fragments.strip():
        instruction += (
            " Ниже фрагменты статьи из базы знаний по этому запросу. "
            "Это и есть нужная статья. Перескажи её. "
            "Не пиши, что статьи нет, и не подставляй другой продукт. "
            "Не описывай работу ассистента. "
            "Не добавляй шаги, суммы и документы, которых во фрагментах нет."
        )
        user = (
            f"Запрос:\n{user}\n\n"
            "Фрагменты статьи. Документ строится только по ним:\n"
            f"{fragments}"
        )
        hint = (template_hint or "").strip()
        if fmt == "pptx" and hint:
            user += f"\n\nКаркас шаблона, не текст слайдов:\n{hint[:2000]}"
    else:
        instruction += (
            " Фрагментов базы знаний нет. "
            "Напиши только, что в базе знаний статьи по запросу нет."
        )
        user += "\n\nФрагментов базы знаний по запросу нет."
    from core.model_gateway import ModelGateway, ModelGatewayError

    result = ModelGateway.from_registry().chat(
        "assistant_bank",
        [
            {"role": "system", "content": instruction},
            {"role": "user", "content": user},
        ],
        temperature=0.4,
        max_tokens=4000 if fmt == "pptx" else 1200,
    )
    choices = result.get("choices") if isinstance(result, Mapping) else None
    if not isinstance(choices, list) or not choices:
        raise ModelGatewayError("empty completion")
    message = choices[0].get("message") if isinstance(choices[0], Mapping) else None
    content = message.get("content") if isinstance(message, Mapping) else None
    if not isinstance(content, str):
        raise ModelGatewayError("empty completion")
    return content.strip()


def _from_fragments(fmt: str, prompt: str, fragments: str) -> str:
    topic = re.sub(r"\s+", " ", prompt).strip()
    blocks = [block.strip() for block in fragments.split("\n\n") if block.strip()]
    if fmt == "bpmn":
        steps: list[str] = []
        for block in blocks:
            body = block.split("\n", 1)[-1]
            for sentence in re.split(r"(?<=[.!?])\s+", body):
                item = sentence.strip()
                if len(item) >= 12:
                    steps.append(item[:140])
                if len(steps) >= 8:
                    break
            if len(steps) >= 8:
                break
        return "\n".join(steps or [topic])
    if fmt == "xlsx":
        rows = ["Факт | Из статьи"]
        for block in blocks[:8]:
            title, _, body = block.partition("\n")
            rows.append(f"{title[:80]} | {body[:180]}")
        return "\n".join(rows)
    if fmt == "mmd":
        lines = ["flowchart TD"]
        previous = "S"
        lines.append(f"  S[{topic[:40]}]")
        for index, block in enumerate(blocks[:6], start=1):
            title = block.split("\n", 1)[0][:40]
            node = f"N{index}"
            safe = title.replace("[", "").replace("]", "")
            lines.append(f"  {previous} --> {node}[{safe}]")
            previous = node
        return "\n".join(lines)
    if fmt == "pptx":
        slides: list[str] = []
        for block in blocks:
            title, _, body = block.partition("\n")
            slides.append(f"## {title[:80]}")
            sentences = [
                item.strip()
                for item in re.split(r"(?<=[.!?])\s+", body)
                if item.strip()
            ]
            slides.extend(sentences[:4] or [body[:400]])
        return "\n".join(slides)
    return f"{topic}\n\n{fragments}"


def _local_document_text(fmt: str, prompt: str, fragments: str = "") -> str:
    if fragments.strip():
        return _from_fragments(fmt, prompt, fragments)
    topic = re.sub(r"\s+", " ", prompt).strip()
    if fmt == "pptx":
        return (
            f"## {topic[:80]}\n"
            "В базе знаний нет статьи, из которой можно собрать слайды.\n"
        )
    if fmt == "bpmn":
        return "\n".join(
            [
                f"Принять обращение: {topic[:80]}",
                "Проверить личность и комплект документов",
                "Найти регламент в базе знаний",
                "Сверить срок, сумму и список документов",
                "Согласовать исключение с руководителем, если норма не покрывает случай",
                "Сообщить клиенту решение и что принести",
                "Зафиксировать результат и оценку подсказки",
            ]
        )
    if fmt == "xlsx":
        return "\n".join(
            [
                "Шаг | Кто | Срок | Результат",
                f"Принять обращение | Оператор | сразу | {topic[:60]}",
                "Проверить документы | Оператор | 5 минут | комплект сверен",
                "Найти статью | Суфлёр | 1–2 секунды | источник на экране",
                "Сверить цифры | Оператор | 2 минуты | срок и сумма названы по статье",
                "Согласовать исключение | Руководитель | в ту же смену | да или нет",
                "Ответить клиенту | Оператор | до конца звонка | что сделать дальше",
                "Оценить подсказку | Оператор | после диалога | полезно или нет",
                "Разобрать ошибку | Супервизор | следующий день | правка сценария",
            ]
        )
    if fmt == "mmd":
        return (
            "flowchart TD\n"
            "  A[Обращение клиента] --> B[Проверка документов]\n"
            "  B --> C[Поиск в базе знаний]\n"
            "  C --> D{Норма покрывает случай}\n"
            "  D -->|да| E[Ответ клиенту]\n"
            "  D -->|нет| F[Согласование руководителя]\n"
            "  F --> E\n"
            "  E --> G[Оценка подсказки]\n"
        )
    return (
        f"{topic}\n\n"
        "Суть. Обращение разбирает оператор. Ответ берётся из базы знаний "
        "и сценария, а не из догадки.\n\n"
        "Шаги.\n"
        "1. Зафиксировать, о чём просит клиент.\n"
        "2. Открыть подсказку и прочитать фрагмент источника.\n"
        "3. Назвать срок, сумму или список документов так, как они записаны.\n"
        "4. Если нормы нет — передать вопрос руководителю в ту же смену.\n"
        "5. После диалога отметить, помогла ли подсказка.\n\n"
        "Сроки. Подсказка на экране — 1–2 секунды. Проверка комплекта — около "
        "5 минут. Разбор ошибочной подсказки — на следующий рабочий день.\n\n"
        "Ответственные. Оператор отвечает клиенту. Супервизор разбирает спорные "
        "случаи. Администратор базы обновляет статью, когда меняется продукт.\n\n"
        "Итог. Клиент получает проверяемый ответ, а не общий пересказ."
    )


def compose_document_text(
    fmt: str,
    prompt: str,
    template_hint: str = "",
    kb_slugs: Sequence[str] | None = None,
) -> str:
    """Turn a free prompt into the text the file builder expects."""
    cleaned = prompt.strip()
    if not cleaned:
        raise DocgenError("введите промпт или заполните поля бланка")
    fragments = _kb_context(cleaned, kb_slugs, full_article=(fmt == "pptx"))
    try:
        raw = _model_document_text(fmt, cleaned, template_hint, fragments)
    except Exception:
        raw = ""
    folded = raw.casefold()
    if raw and not any(marker in folded for marker in _STUB_MARKERS):
        if fmt == "pptx" and "## " not in raw:
            paragraphs = [part.strip() for part in re.split(r"\n\s*\n", raw) if part.strip()]
            if len(paragraphs) >= 2:
                slides = [f"## {paragraphs[0][:80]}"]
                slides.append(paragraphs[0])
                for part in paragraphs[1:]:
                    first, _, rest = part.partition("\n")
                    slides.append(f"## {first[:80]}")
                    slides.append(rest or first)
                return "\n".join(slides)
        if fmt == "bpmn":
            lines = []
            for line in raw.splitlines():
                item = re.sub(r"^\s*(\d+[\).\]]|[-*•])\s*", "", line).strip()
                if item:
                    lines.append(item)
            if len(lines) >= 3:
                return "\n".join(lines[:12])
        if fmt != "bpmn":
            return raw.strip()
    return _local_document_text(fmt, cleaned, fragments)


def _txt_bytes(text: str) -> bytes:
    return (text or "").encode("utf-8")


def _mmd_bytes(text: str) -> bytes:
    body = (text or "").strip()
    if not body.startswith("erDiagram") and not body.startswith("flowchart"):
        entities = [line.strip() for line in body.splitlines() if line.strip()]
        if len(entities) >= 2:
            lines = ["erDiagram"]
            for index, name in enumerate(entities[:-1]):
                nxt = entities[index + 1]
                safe = re.sub(r"[^A-Za-zА-Яа-я0-9_]+", "_", name) or f"E{index}"
                safe_n = re.sub(r"[^A-Za-zА-Яа-я0-9_]+", "_", nxt) or f"E{index+1}"
                lines.append(f"  {safe} ||--o{{ {safe_n} : related")
            body = "\n".join(lines)
        else:
            body = "flowchart TD\n  A[" + (body or "Процесс").replace("]", "") + "]"
    return body.encode("utf-8")


CONTENT_TYPES = {
    AssistantDocumentTemplate.FORMAT_DOCX: (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
    AssistantDocumentTemplate.FORMAT_PDF: "application/pdf",
    AssistantDocumentTemplate.FORMAT_XLSX: (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ),
    AssistantDocumentTemplate.FORMAT_PPTX: (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ),
    AssistantDocumentTemplate.FORMAT_BPMN: "application/xml",
    AssistantDocumentTemplate.FORMAT_TXT: "text/plain; charset=utf-8",
    AssistantDocumentTemplate.FORMAT_MMD: "text/plain; charset=utf-8",
}


def build_document(
    template: AssistantDocumentTemplate,
    values: Mapping[str, Any],
    *,
    strict: bool = True,
    prompt: str = "",
    kb_slugs: Sequence[str] | None = None,
) -> tuple[bytes, str, str]:
    if prompt.strip():
        text = compose_document_text(
            template.output_format,
            prompt,
            template.body or "",
            kb_slugs,
        )
    else:
        text = render_body(template, values, strict=strict)
    fmt = template.output_format
    builders = {
        AssistantDocumentTemplate.FORMAT_DOCX: _docx_bytes,
        AssistantDocumentTemplate.FORMAT_PDF: _pdf_bytes,
        AssistantDocumentTemplate.FORMAT_XLSX: _xlsx_bytes,
        AssistantDocumentTemplate.FORMAT_PPTX: _pptx_bytes,
        AssistantDocumentTemplate.FORMAT_BPMN: _bpmn_bytes,
        AssistantDocumentTemplate.FORMAT_TXT: _txt_bytes,
        AssistantDocumentTemplate.FORMAT_MMD: _mmd_bytes,
    }
    builder = builders.get(fmt)
    if builder is None:
        raise DocgenError(f"неизвестный формат: {fmt}")
    slug = re.sub(r"[^A-Za-zА-Яа-я0-9._-]+", "_", template.name).strip("_") or "document"
    filename = f"{slug}.{fmt}"
    return builder(text), filename, CONTENT_TYPES[fmt]
