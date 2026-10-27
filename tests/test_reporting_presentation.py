"""Real PDF output, strict Markdown input and slide overflow without font files."""

import base64
import re
import subprocess
import sys
import zlib
from decimal import Decimal
from pathlib import Path

import pytest

from reporting import presentation, template
from reporting.presentation import Presentation, chart_values, parse, table_data
from reporting.template import Fonts

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "06_design/exempel/presentationsunderlag.md"
FRONT = """---
title: "Independent deck"
period: "Q3 2026"
date: "2026-10-27"
version: "1.0"
author: "Finance team"
source: "Synthetic test data"
---
"""


def source(layout, body, title="A short conclusion"):
    return FRONT + f"<!-- slide: independent | {layout} | {title} -->\n{body}"


def streams(path):
    return [
        zlib.decompress(base64.a85decode(s.strip(), adobe=True))
        for s in re.findall(rb"stream\r?\n(.*?)endstream", path.read_bytes(), re.DOTALL)
    ]


@pytest.fixture
def deck():
    return Presentation(fonts=Fonts.helvetica())


def test_example_renders_five_widescreen_slides_and_visible_font_choice(tmp_path, deck):
    path = tmp_path / "example.pdf"
    audit = deck.render(EXAMPLE.read_text(encoding="utf-8"), path)
    pages = streams(path)
    assert len(pages) == 5
    assert [row["layout"] for row in audit] == [
        "title",
        "content",
        "kpis",
        "table",
        "chart",
    ]
    assert all(row["remaining_pt"] >= 0 for row in audit)
    assert path.read_bytes().count(b"/MediaBox [ 0 0 960 540 ]") == 5
    assert b"/Outlines" in path.read_bytes()
    assert all(
        b"HELVETICA" in page and b"Digital klarhet 1.0" in page for page in pages
    )
    assert all(b"Artificiellalecta" in page and b"Syntetiskt" in page for page in pages)
    assert b"8,1 Mkr" in pages[2] and b"+25 %" in pages[2]
    assert b"8,1" in pages[3] and b"3,0" in pages[4]
    assert b"DMSans" not in path.read_bytes()
    # Reproducible binary export from the same Markdown and selected font.
    second = tmp_path / "second.pdf"
    deck.render(EXAMPLE.read_text(encoding="utf-8"), second)
    assert second.read_bytes() == path.read_bytes()


def test_independent_content_and_shared_components(tmp_path, deck, monkeypatch):
    assert presentation.Fonts is template.Fonts
    assert presentation.ChartStyle is template.ChartStyle
    assert presentation.TOKENS is template.TOKENS
    assert presentation.register_dm_sans is template.register_dm_sans
    calls = []
    original = template.ChartStyle.rect

    def capture(style, drawing, x, y, width, height, color):
        calls.append((height, color, style.fonts))
        return original(style, drawing, x, y, width, height, color)

    monkeypatch.setattr(template.ChartStyle, "rect", capture)
    path = tmp_path / "other.pdf"
    deck.render(
        source(
            "chart",
            "| Category | Amount (units) |\n| --- | ---: |\n| Alpha | 7 |\n| Beta | ej beräknat |\n| Gamma | 0 |",
        ),
        path,
    )
    assert [height for height, _, _ in calls] == [144, 0]
    assert all(
        color == template.C["brand"] and fonts == deck.fonts
        for _, color, fonts in calls
    )
    assert b"Finance team" in streams(path)[0] and b"Alpha" in streams(path)[0]
    assert b"Ej ber" in streams(path)[0]


def test_synthetic_example_totals_and_comparison_have_independent_arithmetic():
    slides = {
        slide.layout: slide
        for slide in parse(EXAMPLE.read_text(encoding="utf-8")).slides
    }
    chart, _ = table_data(slides["chart"].body)
    values = [Decimal(row[1].replace(",", ".")) for row in chart[1:]]
    assert sum(values) == Decimal("8.1")
    assert (values[-1] / values[0] - 1) * 100 == Decimal(25)
    table, _ = table_data(slides["table"].body)
    assert table[1:-1] == chart[1:]
    assert Decimal(table[-1][1].replace(",", ".")) == sum(values)
    kpis, _ = table_data(slides["kpis"].body)
    assert [row[1] for row in kpis[1:]] == ["8,1 Mkr", "3,0 Mkr", "+25 %"]


@pytest.mark.parametrize(
    "content",
    [
        "No front matter",
        FRONT + "No slide markers",
        FRONT.replace('source: "Synthetic test data"', "source: 42")
        + "<!-- slide: a | title | Title -->\nText",
        FRONT.replace('date: "2026-10-27"', "date: 2026-10-27")
        + "<!-- slide: a | title | Title -->\nText",
        FRONT + "Text before first slide\n<!-- slide: a | title | Title -->\nText",
        FRONT + "<!-- slide: a | unknown | Title -->\nText",
        source("content", ""),
        source("content", "<!-- slide: broken -->"),
        source("content", "Text")
        + "\n<!-- slide: independent | content | Duplicate -->\nMore",
    ],
)
def test_invalid_structure_rejected(content):
    with pytest.raises(ValueError):
        parse(content)


@pytest.mark.parametrize(
    "body",
    [
        "| A | B |\n| --- | --- |\n| one |",
        "| A |\n| bad |\n| one |",
        "| A |\n| --- |\n| |",
        "| A |\n| --- |",
        "Text\n| A |\n| --- |\n| one |",
    ],
)
def test_bad_tables_rejected(body):
    with pytest.raises(ValueError):
        table_data(body)


def test_table_alignment_and_missing_values_are_explicit():
    rows, alignment = table_data(
        "| Category | Value |\n| :--- | ---: |\n| Alpha | ej beräknat |"
    )
    assert alignment == ["LEFT", "RIGHT"]
    assert chart_values(rows) == [None]
    assert chart_values(
        [["Category", "Value"], ["Zero", "0"], ["Decimal", "1 234,5"]]
    ) == [0, 1234.5]


def test_windows_line_endings_and_wrapped_title(tmp_path, deck):
    text = source(
        "title",
        "Two lines of title can fit.",
        "An independent presentation title that wraps onto another line",
    )
    assert parse(text.replace("\n", "\r\n")) == parse(text)
    deck.render(text, tmp_path / "wrapped.pdf")
    assert deck.audit[0]["remaining_pt"] >= 0


def test_chart_without_any_known_values_has_no_numeric_axis(tmp_path, deck):
    path = tmp_path / "missing.pdf"
    deck.render(
        source(
            "chart", "| Category | Amount |\n| --- | ---: |\n| Alpha | ej beräknat |"
        ),
        path,
    )
    page = streams(path)[0]
    assert b"Ej ber" in page
    assert b"(0,25)" not in page and b"(0,5)" not in page and b"(0,75)" not in page


def test_wide_axis_numbers_require_a_readable_unit(tmp_path, deck):
    with pytest.raises(ValueError, match="axis label"):
        deck.render(
            source(
                "chart", "| Category | Amount |\n| --- | ---: |\n| Alpha | 1234567 |"
            ),
            tmp_path / "wide-axis.pdf",
        )


@pytest.mark.parametrize("value", ["-1", "NaN", "inf", "1e309", "unknown", ""])
def test_misleading_chart_values_rejected(value):
    with pytest.raises(ValueError):
        chart_values([["Category", "Value"], ["Alpha", value]])


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [["A", "B", "C"], ["a", "1", "2"]],
        [["A", "B"], *[[str(i), "1"] for i in range(7)]],
    ],
)
def test_chart_category_limits(rows):
    with pytest.raises(ValueError):
        chart_values(rows)


@pytest.mark.parametrize(
    "layout, body, title",
    [
        ("content", "Long paragraph " * 180, "Overflow"),
        ("title", "Text", "Very long title " * 35),
        ("content", "W" * 200, "Long word"),
        ("content", "Text\n\n> " + "Long source " * 200, "Long note"),
        ("table", "| A | B |\n| --- | --- |\n" + "| Alpha | 42 |\n" * 12, "Tall table"),
        ("table", "| A |\n| --- |\n| " + "W" * 200 + " |", "Wide cell"),
        (
            "kpis",
            "| A | B | C |\n| --- | --- | --- |\n| Label | 123 | "
            + "Note " * 100
            + " |",
            "Long KPI note",
        ),
        (
            "kpis",
            "| A | B | C |\n| --- | --- | --- |\n" + "| Label | 1 | Note |\n" * 4,
            "Too many KPIs",
        ),
        (
            "chart",
            "| A | B |\n| --- | --- |\n| " + "W" * 100 + " | 1 |",
            "Wide chart label",
        ),
        ("content", "![External](https://example.com/chart.png)", "Unsupported image"),
    ],
)
def test_failed_export_preserves_existing_output(tmp_path, deck, layout, body, title):
    path = tmp_path / "existing.pdf"
    path.write_bytes(b"previous output")
    with pytest.raises(ValueError):
        deck.render(source(layout, body, title), path)
    assert path.read_bytes() == b"previous output"


def test_cli_generates_without_database_or_font_files_from_other_directory(tmp_path):
    path = tmp_path / "nested/proof.pdf"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/documentation/build_presentation.py"),
            str(EXAMPLE),
            str(path),
            "--helvetica",
        ],
        check=False,
        cwd=tmp_path,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert b"Helvetica" in result.stdout
    assert len(streams(path)) == 5


def test_default_font_policy_fails_instead_of_substituting(tmp_path):
    with pytest.raises(FileNotFoundError, match="DM-Sans-Regular.ttf"):
        presentation.register_dm_sans(tmp_path)
