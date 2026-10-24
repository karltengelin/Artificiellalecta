"""Exercise actual PDF/SVG rendering with built-in fonts, without font files."""

import base64
import re
import zlib
from dataclasses import replace

import pytest
from reportlab.graphics.shapes import Drawing

from reporting import template
from reporting.template import CW, C, ChartStyle, Cover, Fonts, Report, ReportMetadata


@pytest.fixture(autouse=True)
def no_font_files(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("These tests must not load TTF files")

    monkeypatch.setattr(template, "TTFont", forbidden)


def page_streams(path):
    """Decode ReportLab's standard ASCII85/Flate page streams using only stdlib."""
    return [
        zlib.decompress(base64.a85decode(stream.strip(), adobe=True))
        for stream in re.findall(
            rb"stream\r?\n(.*?)endstream", path.read_bytes(), re.DOTALL
        )
    ]


def new_report(path):
    return Report(
        path,
        ReportMetadata(
            title="Quarterly report",
            header="Q3 / 2026",
            footer="Internal draft",
            author="Finance team",
            subject="Synthetic test data",
        ),
        fonts=Fonts.helvetica(),
    )


def test_independent_report_renders_all_components(tmp_path):
    style = ChartStyle(Fonts.helvetica())
    chart = Drawing(CW, 75)
    style.line(chart, 0, 20, CW, 20)
    style.rect(chart, 0, 20, 90, 20, C["brand"])
    style.text(chart, 100, 25, "Chart result", bold=True)
    style.legend(chart, [("Volume", C["brand"])], 5)
    content = """<!-- page: overview | 01 / OVERVIEW | Quarterly result -->
**Conclusion** & <source>.

<!-- kpis: summary -->

## Breakdown

| Item | Amount |
| --- | ---: |
| Alpha | 1 200 kr |
| Beta | 42 % |

![Volume](figures/volume.svg)

- Follow up.

<!-- page: method | 02 / METHOD | Assumptions -->
Independent content.
"""
    path = tmp_path / "quarter.pdf"
    report = new_report(path)
    report.render(
        content, drawings={"volume": chart}, kpis=[("Items", "42", "Synthetic")]
    )
    pages = page_streams(path)
    assert len(pages) == 2
    assert all(b"Q3 / 2026" in page and b"Internal draft" in page for page in pages)
    assert all(b"Finance team" in page for page in pages)
    assert all(
        word in pages[0]
        for word in [
            b"Conclusion",
            b"source",
            b"Items",
            b"42",
            b"Alpha",
            b"Chart result",
        ]
    )
    assert b"Independent content" in pages[1]
    assert b"Helvetica-Bold" in path.read_bytes()
    assert b"DMSans" not in path.read_bytes()
    assert b"AGENT INSIGHT" not in path.read_bytes()
    assert [page["id"] for page in report.audit] == ["overview", "method"]
    assert all(page["remaining_pt"] >= 0 for page in report.audit)
    svg = chart.asString("svg")
    assert "Chart result" in svg and "Helvetica" in svg


@pytest.mark.parametrize(
    "component", ["paragraph", "table", "chart", "kpis", "section"]
)
def test_content_cannot_silently_cross_footer(tmp_path, component):
    report = new_report(tmp_path / "overflow.pdf")
    report.begin("overflow", "TEST", "Overflow")
    report.y = 60
    render = {
        "paragraph": lambda: report.paragraph("Too much text"),
        "table": lambda: report.table(["| Item | Value |", "| Alpha | 42 |"]),
        "chart": lambda: report.chart(Drawing(CW, 50)),
        "kpis": lambda: report.kpis([("Items", "42", "Test")]),
        "section": lambda: report.section("More content"),
    }[component]
    with pytest.raises(ValueError, match="Page 1: content extends below footer"):
        render()


@pytest.mark.parametrize(
    "widths", [[CW], [-1, CW + 1], [CW / 4, CW / 4], [float("nan"), CW]]
)
def test_invalid_table_widths_are_rejected(tmp_path, widths):
    report = new_report(tmp_path / "table.pdf")
    report.begin("table", "TEST", "Table")
    with pytest.raises(ValueError, match="Table widths"):
        report.table(["| Item | Value |", "| Alpha | 42 |"], widths=widths)


def test_tables_support_single_and_many_columns_and_custom_widths(tmp_path):
    path = tmp_path / "tables.pdf"
    report = new_report(path)
    report.begin("tables", "TEST", "Different tables")
    report.table(["| Note |", "| One column |"])
    report.table(["| A | B | C | D | E | F | G |", "| 1 | 2 | 3 | 4 | 5 | 6 | 7 |"])
    report.table(
        ["| Description | Value |", "| A wider first column | 42 |"],
        widths=[CW * 0.7, CW * 0.3],
    )
    report.finish("tables")
    report.c.save()
    assert b"One column" in page_streams(path)[0]
    assert b"A wider first column" in page_streams(path)[0]


def test_malformed_table_does_not_render_partial_rows(tmp_path):
    report = new_report(tmp_path / "table.pdf")
    report.begin("table", "TEST", "Table")
    with pytest.raises(ValueError, match="same number of cells"):
        report.table(["| A | B |", "| Missing cell |"])
    with pytest.raises(ValueError, match="header row"):
        report.table([])


def test_kpis_accept_variable_row_counts(tmp_path):
    path = tmp_path / "kpis.pdf"
    report = new_report(path)
    report.begin("kpis", "TEST", "Key figures")
    report.kpis([])
    report.kpis([("Only item", "1", "One column")], columns=1)
    report.kpis([(f"Item {i}", str(i), "Four items") for i in range(4)], columns=3)
    report.finish("kpis")
    report.c.save()
    page = page_streams(path)[0]
    assert b"Only item" in page
    assert all(f"Item {i}".encode() in page for i in range(4))


@pytest.mark.parametrize("columns", [0, 4])
def test_invalid_kpi_column_count(tmp_path, columns):
    with pytest.raises(ValueError, match="KPI columns"):
        new_report(tmp_path / "invalid.pdf").kpis([], columns=columns)


def test_missing_fonts_fail_explicitly_without_substitution(tmp_path):
    with pytest.raises(FileNotFoundError, match="DM-Sans-Regular.ttf"):
        template.register_dm_sans(tmp_path)


@pytest.mark.parametrize(
    "content, message",
    [
        ("No page marker", "at least one"),
        ("<!-- page: cover | COVER | Title -->", "Cover content"),
    ],
)
def test_missing_page_structure_fails_explicitly(tmp_path, content, message):
    with pytest.raises(ValueError, match=message):
        new_report(tmp_path / "invalid.pdf").render(content)


@pytest.mark.parametrize(
    "reference, message",
    [
        ("![Missing](figures/missing.svg)", "Missing chart drawing"),
        ("![Unsupported](image.png)", "Charts must reference"),
    ],
)
def test_chart_reference_errors_are_explicit(tmp_path, reference, message):
    with pytest.raises(ValueError, match=message):
        new_report(tmp_path / "invalid.pdf").render(
            "<!-- page: overview | TEST | Missing figure -->\n" + reference
        )


def test_chart_cannot_extend_past_right_margin(tmp_path):
    report = new_report(tmp_path / "invalid.pdf")
    report.begin("chart", "TEST", "Wide chart")
    with pytest.raises(ValueError, match="content width"):
        report.chart(Drawing(CW + 10, 20))


@pytest.mark.parametrize(
    "field, message",
    [
        ("description", "Cover description"),
        ("note", "Cover note"),
    ],
)
def test_cover_text_cannot_overlap_other_components(tmp_path, field, message):
    cover = Cover(
        eyebrow="DRAFT",
        title_lines=("Quarterly report",),
        description="Description",
        highlight_value="42",
        highlight_label="Items",
        highlight_detail="Synthetic",
        highlight_note="Assumption",
        metrics=(("1", "A"), ("2", "B"), ("3", "C")),
        note="Source",
        footer="Internal draft",
    )
    with pytest.raises(ValueError, match=message):
        new_report(tmp_path / "invalid.pdf").cover(
            replace(cover, **{field: "Long content " * 110})
        )
