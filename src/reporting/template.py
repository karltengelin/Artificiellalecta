"""Reusable A4 report components in Digital klarhet (B-034).

Only rendering lives here. Facts, calculations and chart series belong to callers.
DM Sans must be registered explicitly; tests may select Fonts.helvetica().
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from html import escape
from pathlib import Path

from reportlab.graphics import renderPDF
from reportlab.graphics.shapes import Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

TOKENS = json.loads(
    (
        Path(__file__).resolve().parents[1] / "design/digital_clarity.tokens.json"
    ).read_text(encoding="utf-8")
)
C = {k: colors.HexColor(v) for k, v in TOKENS["color"].items()}
NAVY, PURPLE, LIGHT = C["text"], C["brand"], C["accent_soft"]
WHITE = C["surface"]
W, H = A4
M = 48
CW = W - 2 * M


@dataclass(frozen=True)
class Fonts:
    regular: str = "DMSans"
    medium: str = "DMSans-Medium"
    bold: str = "DMSans-Bold"

    @classmethod
    def helvetica(cls) -> Fonts:
        """Explicit built-in alternative; requires no font files."""
        return cls("Helvetica", "Helvetica", "Helvetica-Bold")


DEFAULT_FONTS = Fonts()


def register_dm_sans(font_dir: Path) -> Fonts:
    """Register local static TTF files; never download or silently substitute fonts."""
    fonts = Fonts()
    files = [
        (fonts.regular, font_dir / "DM-Sans-Regular.ttf"),
        (fonts.medium, font_dir / "DM-Sans-Medium.ttf"),
        (fonts.bold, font_dir / "DM-Sans-Bold.ttf"),
    ]
    for _, path in files:
        if not path.is_file():
            raise FileNotFoundError(
                f"Saknar DM Sans: {path}. Hämta typsnittet för att återskapa rapporten."
            )
    for name, path in files:
        pdfmetrics.registerFont(TTFont(name, str(path)))
    pdfmetrics.registerFontFamily(
        fonts.regular,
        normal=fonts.regular,
        bold=fonts.bold,
        italic=fonts.regular,
        boldItalic=fonts.bold,
    )
    return fonts


@dataclass(frozen=True)
class ReportMetadata:
    title: str
    header: str = ""
    footer: str = ""
    author: str = "Artificiellalecta"
    subject: str = f"Digital klarhet v{TOKENS['version']} / {TOKENS['decision']}."
    eyebrow: str = "BESTÅNDSÖVERSIKT / RAPPORT"  # sidhuvudets etikett i rapportexporten


@dataclass(frozen=True)
class Cover:
    eyebrow: str
    title_lines: tuple[str, ...]
    description: str
    highlight_value: str
    highlight_label: str
    highlight_detail: str
    highlight_note: str
    metrics: tuple[tuple[str, str], ...]
    note: str
    footer: str


@dataclass(frozen=True)
class ChartStyle:
    """Shared text, grid, bars and legends for caller-defined vector charts."""

    fonts: Fonts = DEFAULT_FONTS

    def text(self, d, x, y, value, size=9, color=None, anchor="start", bold=False):
        d.add(
            String(
                x,
                y,
                str(value),
                fontName=self.fonts.bold if bold else self.fonts.regular,
                fontSize=size,
                fillColor=color or NAVY,
                textAnchor=anchor,
            )
        )

    def line(self, d, x1, y1, x2, y2, color=None, width=0.6):
        d.add(Line(x1, y1, x2, y2, strokeColor=color or C["border"], strokeWidth=width))

    def rect(self, d, x, y, w, h, color):
        d.add(Rect(x, y, w, h, fillColor=color, strokeColor=None))

    def legend(self, d, items, y):
        x = 0
        for label, color in items:
            self.rect(d, x, y - 1, 8, 8, color)
            self.text(d, x + 13, y, label, 9, C["text_muted"])
            x += pdfmetrics.stringWidth(label, self.fonts.regular, 9) + 29


def markup(s):
    s = escape(s)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)


class Report:
    def __init__(self, path, metadata: ReportMetadata, *, fonts: Fonts = DEFAULT_FONTS):
        target = path if hasattr(path, "write") else str(path)
        self.c = canvas.Canvas(target, pagesize=A4, invariant=1, pageCompression=1)
        self.metadata = metadata
        self.fonts = fonts
        self.c.setTitle(metadata.title)
        self.c.setAuthor(metadata.author)
        self.c.setSubject(metadata.subject)
        self.page = 0
        self.audit = []
        self.style = ParagraphStyle(
            "Body",
            fontName=fonts.regular,
            fontSize=TOKENS["typography"]["report_body_pt"],
            leading=15.3,
            textColor=NAVY,
            spaceAfter=8,
        )
        self.cellstyle = ParagraphStyle(
            "Cell", parent=self.style, fontSize=9, leading=12
        )
        self.y = 0

    def label(self, x, y, s, size=9, color=None, font=None):
        self.c.setFillColor(color or NAVY)
        self.c.setFont(font or self.fonts.regular, size)
        self.c.drawString(x, y, s)

    def paragraph(self, s):
        p = Paragraph(markup(s), self.style)
        _, hh = p.wrap(CW, 1000)
        self.place(hh + 8)
        p.drawOn(self.c, M, self.y - hh)
        self.y -= hh + 8

    def place(self, height):
        if self.y - height < 57:
            raise ValueError(
                f"Page {self.page}: content extends below footer by {57 - (self.y - height):.1f} pt"
            )

    def begin(self, ident, kicker, title, *, show_title=True):
        self.page += 1
        c = self.c
        c.setFillColor(WHITE)
        c.rect(0, 0, W, H, fill=1, stroke=0)
        c.bookmarkPage(ident)
        c.addOutlineEntry(title, ident, level=0)
        c.setFillColor(PURPLE)
        c.roundRect(M, H - 47, 9, 9, 2, fill=1, stroke=0)
        self.label(M + 16, H - 45, self.metadata.author, 11, font=self.fonts.bold)
        c.setFont(self.fonts.regular, 9)
        c.setFillColor(C["text_muted"])
        c.drawRightString(W - M, H - 44, self.metadata.header)
        if show_title:
            self.label(M, H - 85, kicker, 9, PURPLE, self.fonts.medium)
            p = Paragraph(
                markup(title),
                ParagraphStyle(
                    "Title",
                    fontName=self.fonts.bold,
                    fontSize=27,
                    leading=30,
                    textColor=NAVY,
                ),
            )
            _, h = p.wrap(CW, 200)
            p.drawOn(c, M, H - 103 - h)
            self.y = H - 103 - h - 21
        else:
            self.y = H - 75
        self.place(0)
        c.setStrokeColor(C["border"])
        c.setLineWidth(0.5)
        c.line(M, 48, W - M, 48)
        self.label(M, 31, self.metadata.footer, 9, C["text_muted"])
        c.setFillColor(C["text_muted"])
        c.setFont(self.fonts.regular, 9)
        c.drawRightString(
            W - M, 31, f"Digital klarhet {TOKENS['version']}  /  {self.page:02d}"
        )

    def section(self, s):
        self.place(24)
        self.y -= 6
        self.label(M, self.y - 10, s, 12, NAVY, self.fonts.bold)
        self.y -= 23

    def table(self, lines, *, widths: Sequence[float] | None = None):
        rows = [
            [s.strip() for s in line.strip().strip("|").split("|")] for line in lines
        ]
        rows = [r for r in rows if not all(re.fullmatch(r":?-+:?", z) for z in r)]
        if not rows or not rows[0]:
            raise ValueError("A table needs a header row")
        n = len(rows[0])
        if any(len(row) != n for row in rows):
            raise ValueError("Every table row must have the same number of cells")
        widths = list(widths) if widths is not None else [CW / n] * n
        if (
            len(widths) != n
            or any(not math.isfinite(w) or w <= 0 for w in widths)
            or not math.isclose(sum(widths), CW, abs_tol=0.01)
        ):
            raise ValueError(
                "Table widths must be positive, match the columns and fill the content width"
            )
        rendered = []
        for i, row in enumerate(rows):
            cells = []
            for cell in row:
                st = ParagraphStyle(
                    "CellLocal",
                    parent=self.cellstyle,
                    fontName=self.fonts.medium if i == 0 else self.fonts.regular,
                )
                # Right-align genuinely numeric columns, not mixed explanatory text.
                if i and re.match(r"^[+\-]?[\d\s,.]+(?: %| kr)?$", cell):
                    st.alignment = 2
                cells.append(Paragraph(markup(cell), st))
            rendered.append(cells)
        table = Table(rendered, colWidths=widths, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 9),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.35, C["border"]),
                ]
            )
        )
        _, hh = table.wrap(CW, 1000)
        self.place(hh + 12)
        table.drawOn(self.c, M, self.y - hh)
        self.y -= hh + 12

    def chart(self, drawing):
        if drawing.width > CW:
            raise ValueError("Chart exceeds the report content width")
        self.place(drawing.height + 12)
        renderPDF.draw(drawing, self.c, M, self.y - drawing.height)
        self.y -= drawing.height + 12

    def kpis(self, items: Sequence[tuple[str, str, str]], *, columns: int = 3):
        if columns < 1 or columns > 3:
            raise ValueError("KPI columns must be between 1 and 3")
        if not items:
            return
        height = math.ceil(len(items) / columns) * 77 - 5
        self.place(height + 10)
        gap = 12
        width = (CW - (columns - 1) * gap) / columns
        for i, (label, value, note) in enumerate(items):
            xx = M + (i % columns) * (width + gap)
            yy = self.y - (i // columns) * 77 - 69
            self.c.setFillColor(LIGHT)
            self.c.roundRect(
                xx, yy, width, 69, TOKENS["radius_px"]["control"], stroke=0, fill=1
            )
            self.label(xx + 12, yy + 50, label, 9, C["text_muted"])
            self.label(xx + 12, yy + 25, value, 22, NAVY, self.fonts.bold)
            self.label(xx + 12, yy + 10, note, 9, C["text_muted"])
        self.y -= height + 10

    def cover(self, content: Cover):
        if not 1 <= len(content.title_lines) <= 3 or len(content.metrics) != 3:
            raise ValueError("Cover needs one to three title lines and three metrics")
        c = self.c
        self.page += 1
        c.bookmarkPage("cover")
        c.addOutlineEntry("Omslag", "cover", 0)
        c.setFillColor(WHITE)
        c.rect(0, 0, W, H, fill=1, stroke=0)
        c.setFillColor(PURPLE)
        c.roundRect(M, H - 60, 12, 12, 3, fill=1, stroke=0)
        self.label(M + 22, H - 58, self.metadata.author, 14, NAVY, self.fonts.bold)
        self.label(M, H - 105, content.eyebrow, 10, PURPLE, self.fonts.medium)
        for i, title in enumerate(content.title_lines):
            self.label(M, H - 163 - i * 45, title, 39, NAVY, self.fonts.bold)
        self.y = H - 283
        self.paragraph(content.description)
        if self.y < 466:
            raise ValueError("Cover description overlaps the highlight panel")
        c.setFillColor(LIGHT)
        c.roundRect(
            M, 279, CW, 171, TOKENS["radius_px"]["large_surface"], fill=1, stroke=0
        )
        self.label(M + 24, 395, content.highlight_value, 64, PURPLE, self.fonts.bold)
        self.label(M + 24, 368, content.highlight_label, 15, NAVY, self.fonts.medium)
        self.label(M + 24, 337, content.highlight_detail, 12, NAVY)
        self.label(
            M + 24,
            315,
            content.highlight_note,
            11,
            C["text_muted"],
        )
        c.setFillColor(NAVY)
        c.roundRect(M, 163, CW, 92, TOKENS["radius_px"]["card"], fill=1, stroke=0)
        for i, (val, label) in enumerate(content.metrics):
            xx = M + 22 + i * (CW - 20) / 3
            self.label(xx, 215, val, 22, WHITE, self.fonts.bold)
            self.label(
                xx,
                191,
                label,
                10,
                colors.HexColor(TOKENS["presentation_dark"]["text_muted"]),
            )
        self.y = 137
        st = ParagraphStyle("CoverNote", parent=self.style, fontSize=9.5, leading=13)
        p = Paragraph(
            markup(content.note),
            st,
        )
        _, hh = p.wrap(CW, 100)
        if self.y - hh < 69:
            raise ValueError("Cover note extends below the reserved text area")
        p.drawOn(c, M, self.y - hh)
        self.label(
            M,
            51,
            content.footer,
            9,
            C["text_muted"],
        )
        c.showPage()
        self.audit.append({"page": self.page, "id": "cover", "remaining_pt": 0})

    def body(self, body, drawings, *, kpis=(), table_widths=None):
        lines = body.strip().splitlines()
        i = 0
        while i < len(lines):
            line0 = lines[i].strip()
            if not line0:
                i += 1
                continue
            if line0.startswith("<!-- kpis:"):
                self.kpis(kpis)
                i += 1
            elif line0.startswith("## "):
                self.section(line0[3:])
                i += 1
            elif line0.startswith("!["):
                match = re.search(r"figures/(.+?)\.svg", line0)
                if match is None:
                    raise ValueError("Charts must reference figures/<key>.svg")
                key = match.group(1)
                if key not in drawings:
                    raise ValueError(f"Missing chart drawing: {key}")
                self.chart(drawings[key])
                i += 1
            elif line0.startswith("|"):
                rows = []
                while i < len(lines) and lines[i].strip().startswith("|"):
                    rows.append(lines[i])
                    i += 1
                header = [s.strip() for s in rows[0].strip().strip("|").split("|")]
                self.table(rows, widths=table_widths(header) if table_widths else None)
            elif line0.startswith("- "):
                self.paragraph("• " + line0[2:])
                i += 1
            else:
                para = [line0]
                i += 1
                while (
                    i < len(lines)
                    and lines[i].strip()
                    and not lines[i].startswith(("## ", "|", "![", "<!--", "- "))
                ):
                    para.append(lines[i].strip())
                    i += 1
                self.paragraph(" ".join(para))

    def finish(self, ident):
        self.audit.append(
            {"page": self.page, "id": ident, "remaining_pt": round(self.y - 57, 1)}
        )
        self.c.showPage()

    def render(
        self, content: str, *, drawings=None, kpis=(), cover=None, table_widths=None
    ):
        """Render the documented Markdown subset with explicit page boundaries.

        See 06_design/rapportmall.md. No pagination or data lookup is implicit:
        content that reaches the footer raises ValueError.
        """
        sections = re.split(r"<!-- page: (.+?) \| (.+?) \| (.+?) -->", content)[1:]
        if not sections:
            raise ValueError(
                "A report needs at least one <!-- page: id | kicker | title --> marker"
            )
        for i in range(0, len(sections), 4):
            ident, kicker, title, body = sections[i : i + 4]
            if ident == "cover":
                if cover is None:
                    raise ValueError("A cover page needs Cover content")
                self.cover(cover)
                continue
            self.begin(ident, kicker, title)
            self.body(body, drawings or {}, kpis=kpis, table_widths=table_widths)
            self.finish(ident)
        self.c.save()
