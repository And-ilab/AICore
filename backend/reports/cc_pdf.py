"""Minimal PDF builder (no external deps) for CC report export."""

from __future__ import annotations

from typing import Any


def _escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
    )


def build_pdf_export(analytics: dict[str, Any], title: str = "CC reports") -> bytes:
    lines = [
        title,
        f"Period: {analytics.get('filters', {}).get('date_from')} — "
        f"{analytics.get('filters', {}).get('date_to')}",
        f"Source: {analytics.get('source', '')}",
        "",
    ]
    summary = analytics.get("summary") or {}
    for key, value in summary.items():
        lines.append(f"{key}: {value}")
    lines.append("")
    rows = analytics.get("rows") or []
    if rows:
        headers = list(rows[0].keys())
        lines.append(" | ".join(headers))
        for row in rows[:40]:
            lines.append(" | ".join(str(row.get(h, "")) for h in headers))

    # Build a single-page PDF with Helvetica (Latin); Cyrillic may show as boxes
    # in some viewers — CSV/XLSX remain primary formats for RU text.
    content_lines = ["BT", "/F1 10 Tf", "50 800 Td", "14 TL"]
    for idx, line in enumerate(lines[:55]):
        safe = _escape(line[:110])
        if idx == 0:
            content_lines.append(f"({safe}) Tj")
        else:
            content_lines.append("T*")
            content_lines.append(f"({safe}) Tj")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1", errors="replace")

    objects: list[bytes] = []
    objects.append(b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
    objects.append(b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n")
    objects.append(
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n"
    )
    objects.append(
        f"4 0 obj<< /Length {len(stream)} >>stream\n".encode("ascii")
        + stream
        + b"\nendstream\nendobj\n"
    )
    objects.append(
        b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n"
    )

    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(output))
        output.extend(obj)
    xref_pos = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer<< /Size {len(offsets)} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n".encode("ascii")
    )
    return bytes(output)
