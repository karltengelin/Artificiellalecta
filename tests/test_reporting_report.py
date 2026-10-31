"""OC-3a's actual PDF export: determinism, pagination and preservation of contract text."""

import base64
import re
import zlib
from concurrent.futures import ThreadPoolExecutor

import pytest

from reporting import ReportMetadata, render_report
from reporting.template import Fonts


def streams(pdf):
    return [zlib.decompress(base64.a85decode(s.strip(), adobe=True))
            for s in re.findall(rb"stream\r?\n(.*?)endstream", pdf, re.DOTALL)]


def render(text):
    return render_report(text, ReportMetadata("Beståndsöversikt", header="FLOW-000001", footer="P2-FRAGA-001 v1.0"),
                         fonts=Fonts.helvetica())


def test_deterministic_in_memory_including_concurrent_exports():
    md = "# Beståndsöversikt\n\n## Svar\n\n35 personer.\n\n| Mått | Värde |\n|---|---|\n| Premier | 145 971,41 SEK |"
    pdf = render(md)
    with ThreadPoolExecutor(max_workers=3) as pool:
        assert all(value == pdf for value in pool.map(render, [md] * 6))
    assert pdf.startswith(b"%PDF-") and len(streams(pdf)) == 1
    assert b"145 971,41 SEK" in streams(pdf)[0]


def test_long_paragraphs_and_table_rows_split_and_preserve_end():
    text = "En lång begränsning som ska bevaras. " * 400
    table = "| Mått | Värde |\n|---|---|\n" + "".join(f"| Rad {i} | {text if i == 5 else i} |\n" for i in range(45))
    pdf = render("# Beståndsöversikt\n\n## Begränsningar\n\n" + text + "\n\n" + table + "\n\nSLUTMARKERING")
    pages = streams(pdf)
    assert len(pages) > 2
    assert b"SLUTMARKERING" in pages[-1]
    assert all(b"FLOW-000001" in page and b"P2-FRAGA-001" in page for page in pages)


def test_every_paragraph_survives_page_boundaries():
    markers = [f"PARAGRAPH-{i:03d}" for i in range(100)]
    pdf = render("# Beståndsöversikt\n\n" + "\n\n".join(markers))
    content = b"\n".join(streams(pdf))
    assert all(content.count(marker.encode()) == 1 for marker in markers)


def test_continuation_pages_keep_header_and_footer_without_repeating_title():
    pages = streams(render("# Beståndsöversikt\n\n" + "\n\n".join(f"Rad {i}" for i in range(100))))
    assert len(pages) > 1
    # ReportLab uses octal escapes for Swedish letters in its built-in font.
    title = rb"Best\345nds\366versikt"
    assert title in pages[0]
    assert all(title not in page for page in pages[1:])
    assert all(b"Artificiellalecta" in page and b"FLOW-000001" in page and b"P2-FRAGA-001" in page
               for page in pages)


def test_markup_is_text_and_cannot_load_images_or_links():
    pages = streams(render('# Beståndsöversikt\n\n<img src="https://example.invalid/leak"> & test\n\n`get_company_metrics`'))
    assert b"example.invalid/leak" in pages[0]
    assert b"get_company_metrics" in pages[0]


@pytest.mark.parametrize("md", ["", "x" * (100 * 1024 + 1), "![Bild](file:///secret)",
                                "<!-- page: x | y | z -->", "| A | B |\n|---|---|\n| missing |"],
                         ids=["empty", "oversized", "image", "page-marker", "bad-table"])
def test_rejects_invalid_or_unsupported_content(md):
    with pytest.raises(ValueError):
        render(md)


def test_missing_fonts_fail_without_silent_substitution():
    with pytest.raises(ValueError, match="DM Sans"):
        render_report("Text", ReportMetadata("Test"), fonts=Fonts("Missing-A", "Missing-B", "Missing-C"))
