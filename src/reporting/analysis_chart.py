"""Gemensamma dataförankrade vektordiagram i Digital klarhet, utan externa resurser."""

from __future__ import annotations

import json
import math
from html import escape
from pathlib import Path

TOKENS = json.loads((Path(__file__).resolve().parents[1] / "design/digital_clarity.tokens.json").read_text(encoding="utf-8"))


def render_analysis_chart(rows: list[dict], *, title: str, x: str, y: str,
                          kind: str = "line", unit: str = "", source: str = "",
                          lower: str | None = None, upper: str | None = None) -> str:
    """Renderar bara numeriska fält ur ett redan kontrollerat analysresultat.

    Dolda värden ger luckor, aldrig noll. Staplar har nollbas. Inga script,
    externa typsnitt eller modellerade tal ingår i SVG:n.
    """
    if kind not in {"line", "bar"} or not 1 <= len(rows) <= 250:
        raise ValueError("Välj line/bar och 1–250 rader")
    if bool(lower) != bool(upper):
        raise ValueError("Både undre och övre osäkerhetsgräns krävs")
    values = []
    for row in rows:
        if x not in row or y not in row:
            raise ValueError("Diagrammets fält finns inte i underlaget")
        for key in (y, lower, upper):
            v = row.get(key) if key else None
            if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)):
                raise ValueError("Diagramvärdet är inte ett ändligt tal")
            if v is not None:
                values.append(v)
        if lower and row[y] is not None and (row.get(lower) is None or row.get(upper) is None):
            raise ValueError("En synlig skattning behöver båda intervallgränserna")
        if lower and row[y] is not None and not (row[lower] <= row[y] <= row[upper]):
            raise ValueError("Osäkerhetsintervallet omsluter inte skattningen")
    if not values:
        raise ValueError("Alla diagramvärden är dolda eller saknas")
    low, high = min(0, min(values)), max(0, max(values))
    if high == low:
        high = low + 1
    width, height, left, top, plot_width, plot_height = 900, 460, 100, 78, 745, 270
    color = TOKENS["color"]
    def px(i):
        return left + (i+.5)*plot_width/len(rows)
    def py(value):
        return top + plot_height*(high-value)/(high-low)
    def text(xpos, ypos, value, size=12, anchor="start"):
        return f'<text x="{xpos:.2f}" y="{ypos:.2f}" font-size="{size}" text-anchor="{anchor}">{escape(str(value))}</text>'
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
           f'<title id="title">{escape(title)}</title><desc id="desc">{escape(source)}. Enhet: {escape(unit)}. Luckor betyder saknat eller dolt värde.</desc>',
           f'<rect width="900" height="460" fill="{color["surface"]}"/>',
           f'<g fill="{color["text"]}" font-family="DM Sans, Segoe UI, sans-serif">', text(30, 35, title[:110], 20),
           text(30, 58, unit[:100], 11)]
    for i in range(5):
        value = low+(high-low)*i/4
        yy = py(value)
        out += [f'<path d="M{left} {yy:.2f}H{left+plot_width}" stroke="{color["border"]}"/>',
                text(left-12, yy+4, f"{value:,.3g}".replace(",", " "), 11, "end")]
    if lower:
        for i, row in enumerate(rows):
            if row.get(lower) is not None and row.get(upper) is not None:
                out.append(f'<path d="M{px(i):.2f} {py(row[lower]):.2f}V{py(row[upper]):.2f}" stroke="{color["brand"]}" stroke-opacity="0.35" stroke-width="8"/>')
    previous = None
    for i, row in enumerate(rows):
        value = row[y]
        if value is None:
            previous = None
            continue
        xx, yy = px(i), py(value)
        if kind == "bar":
            bw = min(48, plot_width/len(rows)*.65)
            out.append(f'<rect x="{xx-bw/2:.2f}" y="{min(yy,py(0)):.2f}" width="{bw:.2f}" height="{abs(yy-py(0)):.2f}" fill="{color["brand"]}"/>')
        else:
            if previous is not None:
                out.append(f'<path d="M{previous[0]:.2f} {previous[1]:.2f}L{xx:.2f} {yy:.2f}" fill="none" stroke="{color["brand"]}" stroke-width="2.5"/>')
            out.append(f'<circle cx="{xx:.2f}" cy="{yy:.2f}" r="3" fill="{color["brand"]}"/>')
            previous = xx, yy
        if i % max(1, math.ceil(len(rows)/9)) == 0 or i == len(rows)-1:
            out.append(text(xx, top+plot_height+25, str(row[x])[:20], 11, "middle"))
    out += [text(30, 412, "Källa: "+source[:125], 10),
            text(30, 434, "Digital klarhet · Kontrollerat analysunderlag · Dolda värden återges som luckor", 10), "</g></svg>"]
    return "".join(out)


def analysis_drawing(svg: str, *, font_name="DMSans"):
    """Samma genererade diagram som ReportLab-vektorer för rapportens PDF.

    Accepterar bara den snäva SVG-dialekt som funktionen ovan producerar.
    Hämtar aldrig bilder, typsnitt, länkar eller resurser från SVG-innehållet.
    """
    import re
    from xml.etree import ElementTree

    from reportlab.graphics.shapes import Circle, Drawing, Rect, String
    from reportlab.graphics.shapes import Path as VectorPath
    from reportlab.lib.colors import HexColor

    height, drawing = 460, Drawing(900, 460)
    root = ElementTree.fromstring(svg)
    group = next(e for e in root if e.tag.endswith("}g"))
    for element in group:
        tag, a = element.tag.split("}")[-1], element.attrib
        color = HexColor(a.get("fill", TOKENS["color"]["text"])) if a.get("fill") != "none" else None
        if tag == "text":
            shape = String(float(a["x"]), height-float(a["y"]), element.text or "", fontName=font_name,
                           fontSize=float(a["font-size"]), fillColor=color,
                           textAnchor=a.get("text-anchor", "start"))
        elif tag == "rect":
            shape = Rect(float(a["x"]), height-float(a["y"])-float(a["height"]),
                         float(a["width"]), float(a["height"]), fillColor=color, strokeColor=None)
        elif tag == "circle":
            shape = Circle(float(a["cx"]), height-float(a["cy"]), float(a["r"]), fillColor=color, strokeColor=None)
        elif tag == "path":
            shape = VectorPath(strokeColor=HexColor(a["stroke"]), strokeWidth=float(a.get("stroke-width", 1)), fillColor=None)
            parts = re.findall(r"[MLHV]|-?\d+(?:\.\d+)?", a["d"])
            i, xx, yy = 0, 0.0, 0.0
            while i < len(parts):
                op = parts[i]
                i += 1
                if op in {"M", "L"}:
                    xx, yy = float(parts[i]), float(parts[i+1])
                    i += 2
                elif op == "H":
                    xx, i = float(parts[i]), i+1
                elif op == "V":
                    yy, i = float(parts[i]), i+1
                else:
                    raise ValueError("Okänd vektoroperation")
                if op == "M":
                    shape.moveTo(xx, height-yy)
                else:
                    shape.lineTo(xx, height-yy)
        else:
            raise ValueError("Diagrammet innehåller ett okänt element")
        drawing.add(shape)
    return drawing
