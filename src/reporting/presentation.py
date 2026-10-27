"""Local 16:9 Markdown slides using the report's fonts, tokens and ChartStyle.

No agent, gateway, data lookup or external resource loading. See
06_design/presentationsmall.md for the deliberately limited Markdown grammar.
"""

from __future__ import annotations

import argparse
import io
import math
import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from reportlab.graphics import renderPDF
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

from reporting.template import (
    DEFAULT_FONTS,
    TOKENS,
    C,
    ChartStyle,
    Fonts,
    markup,
    register_dm_sans,
)

TEMPLATE_VERSION = "1.0"
W, H = 960, 540
M, CW = 48, W - 96
BODY = TOKENS["typography"]["presentation_body_pt"]
DARK = {
    key: colors.HexColor(value) for key, value in TOKENS["presentation_dark"].items()
}
MARKER = re.compile(
    r"^<!-- slide: ([a-z][a-z0-9_-]*) \| (title|content|kpis|table|chart) \| (.+?) -->$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class Slide:
    ident: str
    layout: str
    title: str
    body: str
    notes: tuple[str, ...]


@dataclass(frozen=True)
class Deck:
    metadata: dict[str, str]
    slides: tuple[Slide, ...]


def parse(content: str) -> Deck:
    """Read explicit slide boundaries and YAML metadata, rejecting lost content."""
    content = content.replace("\r\n", "\n")
    front = re.match(r"\A---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not front:
        raise ValueError("Presentation needs YAML front matter")
    metadata = yaml.safe_load(front[1])
    required = {"title", "period", "date", "version", "author", "source"}
    if (
        not isinstance(metadata, dict)
        or set(metadata) != required
        or any(
            not isinstance(value, str) or not value.strip()
            for value in metadata.values()
        )
    ):
        raise ValueError(
            "Metadata needs nonempty strings: " + ", ".join(sorted(required))
        )
    text = content[front.end() :]
    markers = list(MARKER.finditer(text))
    if not markers or text[: markers[0].start()].strip():
        raise ValueError("Expected <!-- slide: id | layout | title --> before content")
    slides = []
    for i, marker in enumerate(markers):
        body = text[
            marker.end() : markers[i + 1].start() if i + 1 < len(markers) else len(text)
        ]
        lines, notes = [], []
        for line in body.strip().splitlines():
            if line.startswith("> "):
                notes.append(line[2:])
            else:
                lines.append(line)
        body = "\n".join(lines).strip()
        if not body or "<!--" in body:
            raise ValueError("Each slide needs content and valid slide markers")
        slides.append(Slide(*marker.groups(), body, tuple(notes)))
    if len({slide.ident for slide in slides}) != len(slides):
        raise ValueError("Slide ids must be unique")
    return Deck(metadata, tuple(slides))


def table_data(body: str) -> tuple[list[list[str]], list[str]]:
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if len(lines) < 3 or any(
        not (line.startswith("|") and line.endswith("|")) for line in lines
    ):
        raise ValueError("Expected a Markdown table with header, separator and data")
    rows = [[cell.strip() for cell in line[1:-1].split("|")] for line in lines]
    n = len(rows[0])
    if any(len(row) != n or any(not cell for cell in row) for row in rows):
        raise ValueError(
            "Table cells must be nonempty and rows must have the same width"
        )
    if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in rows[1]):
        raise ValueError("Invalid Markdown table separator")
    alignments = ["RIGHT" if cell.endswith(":") else "LEFT" for cell in rows[1]]
    return [rows[0], *rows[2:]], alignments


def chart_values(rows: list[list[str]]) -> list[float | None]:
    if not rows or len(rows[0]) != 2 or not 1 <= len(rows) - 1 <= 6:
        raise ValueError("Chart needs two columns and one to six categories")
    values = []
    for _, raw in rows[1:]:
        if raw.casefold() == "ej beräknat":
            values.append(None)
            continue
        try:
            value = float(raw.replace(" ", "").replace(",", "."))
        except ValueError as exc:
            raise ValueError("Chart values must be numbers or 'ej beräknat'") from exc
        if not math.isfinite(value) or value < 0:
            raise ValueError("Chart values must be finite and nonnegative")
        values.append(value)
    return values


class Presentation:
    def __init__(self, *, fonts: Fonts = DEFAULT_FONTS):
        self.fonts = fonts
        self.audit: list[dict] = []

    def paragraph(
        self, text, x, top, width, height, *, size=BODY, color=None, bold=False
    ):
        font = self.fonts.bold if bold else self.fonts.regular
        # Paragraph can otherwise paint an unbreakable word outside its box.
        plain = text.replace("**", "")
        if any(
            max(
                pdfmetrics.stringWidth(word, name, size)
                for name in (font, self.fonts.bold)
            )
            > width
            for word in plain.split()
        ):
            raise ValueError("Text contains a word wider than its reserved area")
        style = ParagraphStyle(
            "SlideText",
            fontName=font,
            fontSize=size,
            leading=size * TOKENS["typography"]["body_line_height"],
            textColor=color or C["text"],
            splitLongWords=False,
        )
        p = Paragraph(markup(text), style)
        _, used = p.wrap(width, H)
        if used > height + 0.01:
            raise ValueError(
                "Text exceeds its reserved area; shorten or split the slide"
            )
        p.drawOn(self.c, x, top - used)
        return used

    def label(self, text, x, y, width, *, size=12, color=None, bold=False):
        font = self.fonts.bold if bold else self.fonts.regular
        if pdfmetrics.stringWidth(text, font, size) > width:
            raise ValueError("Label exceeds its reserved area")
        self.c.setFont(font, size)
        self.c.setFillColor(color or C["text_muted"])
        self.c.drawString(x, y, text)

    def chart(self, rows, top, available):
        values = chart_values(rows)
        height = 244
        if available < height:
            raise ValueError("Chart exceeds its reserved area")
        drawing = Drawing(CW, height)
        style = ChartStyle(self.fonts)
        # All chart colors and primitives come from the report template.
        left, bottom, plot_h = 80, 52, 144
        known = [value for value in values if value is not None]
        maximum = max(known, default=0) or 1
        if pdfmetrics.stringWidth(rows[0][1], self.fonts.bold, 20) > CW:
            raise ValueError("Chart heading exceeds its reserved area")
        for tick in range(5):
            if not known:
                break
            y = bottom + plot_h * tick / 4
            style.line(drawing, left, y, CW, y)
            tick_label = f"{maximum * (tick / 4):g}".replace(".", ",")
            if pdfmetrics.stringWidth(tick_label, self.fonts.regular, 18) > left - 12:
                raise ValueError(
                    "Chart axis label exceeds its reserved area; use a larger unit"
                )
            style.text(
                drawing,
                left - 12,
                y - 6,
                tick_label,
                size=18,
                color=C["text_muted"],
                anchor="end",
            )
        style.text(drawing, 0, height - 20, rows[0][1], size=20, bold=True)
        slot = (CW - left) / len(values)
        for i, ((label, raw), value) in enumerate(zip(rows[1:], values)):
            x = left + (i + 0.5) * slot
            if any(
                pdfmetrics.stringWidth(s, self.fonts.regular, 18) > slot - 8
                for s in (label, raw)
            ):
                raise ValueError("Chart category label exceeds its reserved area")
            style.text(drawing, x, 20, label, size=18, anchor="middle")
            if value is None:
                style.text(
                    drawing,
                    x,
                    bottom + 12,
                    "Ej beräknat",
                    size=16,
                    color=C["text_muted"],
                    anchor="middle",
                )
            else:
                bar_h = plot_h * (value / maximum)
                style.rect(
                    drawing, x - slot * 0.25, bottom, slot * 0.5, bar_h, C["brand"]
                )
                style.text(
                    drawing, x, bottom + bar_h + 9, raw, size=18, anchor="middle"
                )
        renderPDF.draw(drawing, self.c, M, top - height)
        return height

    def table(self, rows, alignments, top, available):
        if not 1 <= len(rows[0]) <= 5:
            raise ValueError("Table supports one to five columns")
        width = CW / len(rows[0])
        rendered = []
        for i, row in enumerate(rows):
            cells = []
            for j, cell in enumerate(row):
                font = self.fonts.bold if i == 0 else self.fonts.regular
                if any(
                    pdfmetrics.stringWidth(word, self.fonts.bold, 20) > width - 24
                    for word in cell.replace("**", "").split()
                ):
                    raise ValueError("Table cell contains a word wider than its column")
                cells.append(
                    Paragraph(
                        markup(cell),
                        ParagraphStyle(
                            "Cell",
                            fontName=font,
                            fontSize=20,
                            leading=26,
                            textColor=C["text"],
                            alignment=2 if alignments[j] == "RIGHT" else 0,
                        ),
                    )
                )
            rendered.append(cells)
        table = Table(rendered, colWidths=[width] * len(rows[0]))
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), C["accent_soft"]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.6, C["border"]),
                ]
            )
        )
        _, height = table.wrap(CW, H)
        if height > available:
            raise ValueError("Table exceeds its reserved area; split the slide")
        table.drawOn(self.c, M, top - height)
        return height

    def kpis(self, rows, top, available):
        if len(rows[0]) != 3 or not 1 <= len(rows) - 1 <= 3:
            raise ValueError("KPIs need three columns and one to three data rows")
        height, gap = 200, 24
        if height > available:
            raise ValueError("KPIs exceed their reserved area")
        width = (CW - gap * (len(rows) - 2)) / (len(rows) - 1)
        for i, (label, value, note) in enumerate(rows[1:]):
            x = M + i * (width + gap)
            self.c.setFillColor(C["accent_soft"])
            self.c.roundRect(
                x,
                top - height,
                width,
                height,
                TOKENS["radius_px"]["card"],
                fill=1,
                stroke=0,
            )
            self.paragraph(label, x + 20, top - 18, width - 40, 60, size=20)
            self.paragraph(value, x + 20, top - 80, width - 40, 60, size=38, bold=True)
            self.paragraph(
                note, x + 20, top - 146, width - 40, 54, size=18, color=C["text_muted"]
            )
        return height

    def render(self, content: str, path: Path):
        """Write a PDF only after every slide passes its layout checks."""
        deck = parse(content)
        self.audit = []
        stream = io.BytesIO()
        self.c = canvas.Canvas(stream, pagesize=(W, H), invariant=1, pageCompression=1)
        meta = deck.metadata
        self.c.setTitle(meta["title"])
        self.c.setAuthor(meta["author"])
        self.c.setSubject(
            f"Digital klarhet {TOKENS['version']} / {TOKENS['decision']} / mall {TEMPLATE_VERSION}"
        )
        for number, slide in enumerate(deck.slides, 1):
            dark = slide.layout == "title"
            text = DARK["text"] if dark else C["text"]
            muted = DARK["text_muted"] if dark else C["text_muted"]
            self.c.setFillColor(DARK["background"] if dark else C["surface"])
            self.c.rect(0, 0, W, H, fill=1, stroke=0)
            self.c.bookmarkPage(slide.ident)
            self.c.addOutlineEntry(slide.title, slide.ident, 0)
            self.c.setFillColor(C["brand"])
            self.c.roundRect(M, H - 39, 10, 10, 2, fill=1, stroke=0)
            self.label(
                meta["author"], M + 20, H - 38, CW * 0.6, size=14, color=text, bold=True
            )
            self.label(meta["period"], W - M - 230, H - 38, 230, size=14, color=muted)
            footer = f"{meta['date']} / v{meta['version']} / Digital klarhet {TOKENS['version']} / mall {TEMPLATE_VERSION}"
            if self.fonts == Fonts.helvetica():
                footer += " / HELVETICA"
            self.label(footer, M, 22, CW - 105, size=11, color=muted)
            self.label(
                f"{number:02d} / {len(deck.slides):02d}",
                W - M - 65,
                22,
                65,
                size=11,
                color=muted,
            )
            notes = " ".join(("Källa: " + meta["source"], *slide.notes))
            notes_h = self.paragraph(notes, M, 99, CW, 54, size=12, color=muted)
            bottom = 115
            title_top = 446 if dark else 464
            title_h = self.paragraph(
                slide.title,
                M,
                title_top,
                CW,
                120 if dark else 108,
                size=40 if dark else 36,
                color=text,
                bold=True,
            )
            top = title_top - title_h - 24
            available = top - bottom
            if slide.layout in {"title", "content"}:
                used = 0
                for block in re.split(r"\n\s*\n", slide.body):
                    if block.startswith("- "):
                        paragraphs = [
                            "• " + line[2:]
                            for line in block.splitlines()
                            if line.startswith("- ")
                        ]
                        if len(paragraphs) != len(block.splitlines()):
                            raise ValueError("Lists must contain only '- ' items")
                    else:
                        if any(
                            line.startswith(("#", "|", "![", "```"))
                            for line in block.splitlines()
                        ):
                            raise ValueError("Unsupported Markdown in text slide")
                        paragraphs = [" ".join(block.splitlines())]
                    for paragraph in paragraphs:
                        used += (
                            self.paragraph(
                                paragraph,
                                M,
                                top - used,
                                CW,
                                available - used,
                                color=text,
                            )
                            + 12
                        )
            else:
                rows, alignments = table_data(slide.body)
                used = (
                    self.kpis(rows, top, available)
                    if slide.layout == "kpis"
                    else self.chart(rows, top, available)
                    if slide.layout == "chart"
                    else self.table(rows, alignments, top, available)
                )
            self.audit.append(
                {
                    "slide": number,
                    "id": slide.ident,
                    "layout": slide.layout,
                    "remaining_pt": round(available - used, 2),
                    "notes_height_pt": notes_h,
                }
            )
            self.c.showPage()
        self.c.save()
        path.write_bytes(stream.getvalue())
        return self.audit


def main():
    parser = argparse.ArgumentParser(
        description="Lokal Markdown → 16:9-PDF, Digital klarhet"
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    fonts = parser.add_mutually_exclusive_group()
    fonts.add_argument("--font-dir", type=Path, default=Path("tmp/pdfs/fonts"))
    fonts.add_argument(
        "--helvetica",
        action="store_true",
        help="Uttryckligt tekniskt prov utan DM Sans",
    )
    args = parser.parse_args()
    selected = Fonts.helvetica() if args.helvetica else register_dm_sans(args.font_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    deck = Presentation(fonts=selected)
    audit = deck.render(args.source.read_text(encoding="utf-8"), args.output)
    print(
        f"{args.output}: {len(audit)} bilder, {selected.regular}, mall {TEMPLATE_VERSION}"
    )


if __name__ == "__main__":
    main()
