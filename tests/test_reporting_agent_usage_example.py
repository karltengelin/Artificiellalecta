"""Regression for the example's content, figures and original page layout."""

import json
import re

import pytest

from reporting import agent_usage_example as example
from reporting import template
from reporting.template import ChartStyle, Fonts


def test_example_uses_template_without_font_files(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Example regression must not load external fonts")

    monkeypatch.setattr(template, "TTFont", forbidden)
    x = example.metrics(json.loads(example.DATA.read_text(encoding="utf-8")))
    content = example.SOURCE.read_text(encoding="utf-8")
    for key, value in example.replacements(x).items():
        content = content.replace("{{" + key + "}}", value)
    assert "{{" not in content
    assert content == (example.OUT / (example.NAME + ".md")).read_text(encoding="utf-8")
    assert x["totals"]["tokens"] == 168
    assert x["totals"]["cost"] == 25820
    assert x["human"] == pytest.approx(963.6)
    assert x["net"] == pytest.approx(658)

    fonts = Fonts.helvetica()
    drawings = {
        name: draw(x, ChartStyle(fonts)) for name, draw in example.CHARTS.items()
    }
    assert len(drawings) == 10
    for name, drawing in drawings.items():
        svg = drawing.asString("svg")
        assert "<svg" in svg and "DMSans" not in svg, name

    path = tmp_path / "example.pdf"
    report = example.build_report(path, x, content, drawings, fonts=fonts)
    # Captured from the original generator with Helvetica replacing DM Sans.
    # This checks the whole report, including editorial table widths and cover.
    expected = [
        ("cover", 0),
        ("executive", 122.7),
        ("cases", 59.2),
        ("processes", 44.1),
        ("tokens", 27.2),
        ("agents", 18.6),
        ("costs", 31.8),
        ("network", 73.5),
        ("handoffs", 102.9),
        ("reliability", 107.9),
        ("quality", 143.2),
        ("capacity", 33.9),
        ("economics", 117.9),
        ("optimization", 234.6),
        ("actions", 75.9),
        ("method", 27.4),
    ]
    assert report.audit == [
        {"page": i, "id": ident, "remaining_pt": remaining}
        for i, (ident, remaining) in enumerate(expected, start=1)
    ]
    data = path.read_bytes()
    assert data.startswith(b"%PDF-")
    assert len(re.findall(rb"/Type /Page\b", data)) == 16
    assert b"Helvetica" in data and b"DMSans" not in data
