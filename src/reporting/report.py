"""Deterministic Markdown → A4 bytes for company questions; no data or resource lookup."""

from __future__ import annotations

import io
import re

from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from reporting.template import C, CW, M, DEFAULT_FONTS, Fonts, Report, ReportMetadata, markup


def _inline(text: str) -> str:
    # The caller's Markdown is text, never ReportLab XML or an external resource.
    return markup(re.sub(r"`([^`]+)`", r"\1", text))


class _PaginatedReport(Report):
    def new_page(self):
        if self.page:
            self.finish(f"page-{self.page}")
        self.begin(f"page-{self.page + 1}", "BESTÅNDSÖVERSIKT / RAPPORT", self.metadata.title)

    def put(self, item):
        """Split paragraphs and table rows without drawing below the reserved footer."""
        pending = [item]
        while pending:
            current = pending.pop(0)
            available = self.y - 57
            _, height = current.wrap(CW, available)
            if height <= available:
                current.drawOn(self.c, M, self.y - height)
                self.y -= height
                continue
            parts = current.split(CW, available)
            if parts:
                first, *rest = parts
                _, height = first.wrap(CW, available)
                if height > available:
                    raise ValueError("Rapportdelen ryms inte på A4")
                first.drawOn(self.c, M, self.y - height)
                self.y -= height
                pending = rest + pending
            elif available >= self.page_capacity - 0.1:
                raise ValueError("Rapportdelen kan inte delas på A4")
            else:
                pending.insert(0, current)
            self.new_page()


def render_report(markdown: str, metadata: ReportMetadata, *, fonts: Fonts = DEFAULT_FONTS) -> bytes:
    """Render the documented OC-3a subset. Same content, metadata and fonts give identical bytes.

    DM Sans must already be registered with register_dm_sans. An explicit fonts argument
    allows technical exports with Helvetica; no font is silently substituted or downloaded.
    """
    if not isinstance(markdown, str) or not markdown.strip() or len(markdown.encode("utf-8")) > 100 * 1024:
        raise ValueError("Rapporten ska innehålla Markdown, högst 100 KiB")
    for name in (fonts.regular, fonts.medium, fonts.bold):
        try:
            pdfmetrics.getFont(name)
        except KeyError:
            raise ValueError("Registrera rapportens DM Sans-typsnitt före export") from None
    stream = io.BytesIO()
    report = _PaginatedReport(stream, metadata, fonts=fonts)
    report.new_page()
    report.page_capacity = report.y - 57
    heading = ParagraphStyle("ReportHeading", parent=report.style, fontName=fonts.bold,
                             fontSize=12, leading=16)
    lines = markdown.replace("\r\n", "\n").splitlines()
    i = 0
    while i < len(lines):
        text = lines[i].strip()
        i += 1
        if not text:
            continue
        if text.startswith("# ") and i == 1:
            if text[2:] != metadata.title:
                raise ValueError("Rapportens titel ska stämma med metadata")
            continue  # metadata carries the document title in the template's page heading
        if text.startswith("## "):
            if report.y - 57 < 65:
                report.new_page()
            report.put(Spacer(1, 8))
            report.put(Paragraph(_inline(text[3:]), heading))
            report.put(Spacer(1, 8))
        elif text.startswith("|"):
            rows = [text]
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i].strip())
                i += 1
            cells = [[cell.strip() for cell in row.strip("|").split("|")] for row in rows]
            if len(cells) < 2 or not all(re.fullmatch(r":?-+:?", cell) for cell in cells[1]):
                raise ValueError("Tabellen saknar giltig avskiljarrad")
            count = len(cells[0])
            if not 1 <= count <= 6 or any(len(row) != count for row in cells):
                raise ValueError("Tabellens rader ska ha samma antal kolumner (högst sex)")
            cells.pop(1)
            widths = [CW * part for part in (.21, .25, .16, .16, .22)] if count == 5 else [CW / count] * count
            data = [[Paragraph(_inline(cell), ParagraphStyle(
                "ReportCell", parent=report.cellstyle, fontName=fonts.bold if row == 0 else fonts.regular,
            )) for cell in values] for row, values in enumerate(cells)]
            table = Table(data, colWidths=widths, repeatRows=1, splitByRow=1, splitInRow=1)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), C["accent_soft"]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LINEBELOW", (0, 1), (-1, -1), .35, C["border"]),
            ]))
            report.put(table)
            report.put(Spacer(1, 12))
        else:
            if text.startswith(("#", "<!--", "![", "```")):
                raise ValueError("Markdown-formatet stöds inte av rapportexporten")
            if text.startswith("- "):
                text = "• " + text[2:]
            else:
                while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith(("#", "|", "- ", "<!--", "![", "```")):
                    text += " " + lines[i].strip()
                    i += 1
            report.put(Paragraph(_inline(text), report.style))
            report.put(Spacer(1, 8))
    report.finish(f"page-{report.page}")
    report.c.save()
    return stream.getvalue()
