"""Webbens designvärden (B-034) – en källa: tokenfilen, genererad tokens.css och inga egna färger i app.css."""

import re

from design.web_css import (
    WEB_TOKENS_PATH,
    load_tokens,
    render_web_tokens,
    web_variables,
)
from web.handler import STATIC_DIR

HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")


def test_tokens_css_i_repot_ar_genererad_ur_aktuell_tokenfil():
    assert WEB_TOKENS_PATH.exists(), "kör python scripts/web/build_design_tokens.py"
    assert WEB_TOKENS_PATH.read_text(encoding="utf-8") == render_web_tokens(), (
        "src/web/static/tokens.css är inte aktuell – kör python scripts/web/build_design_tokens.py"
    )
    assert "Genererad" in render_web_tokens().splitlines()[1]


def test_alla_ljusa_webbvarden_finns_med():
    tokens = load_tokens()
    names = dict(web_variables(tokens))
    assert names["--color-brand"] == tokens["color"]["brand"]
    assert names["--status-error-bg"] == tokens["status"]["error"]["background"]
    assert names["--font-family"].startswith('"DM Sans", system-ui')
    assert names["--radius-card"] == "12px"
    assert names["--focus-color"] == "var(--color-brand)"
    assert not any(name.startswith("--presentation") for name in names)


def test_app_css_har_inga_egna_fargvarden_och_bara_kanda_variabler():
    css = (STATIC_DIR / "app.css").read_text(encoding="utf-8")
    assert HEX.findall(css) == [], "färger hör hemma i tokenfilen – använd var(--color-…)/var(--status-…)"
    defined = {name for name, _ in web_variables(load_tokens())}
    defined |= set(re.findall(r"(--[a-z0-9-]+)\s*:", css))
    used = set(re.findall(r"var\((--[a-z0-9-]+)", css))
    assert used - defined == set()


def test_basmallen_laddar_tokens_fore_stilarket():
    base = (STATIC_DIR.parent / "templates" / "base.html").read_text(encoding="utf-8")
    assert base.index("/static/tokens.css") < base.index("/static/app.css")


def test_stilarken_lankas_med_innehallsversion_sa_att_gammal_cache_inte_anvands():
    from web.handler import static_version, templates

    version = templates.env.globals["static_version"]
    assert version == static_version() and len(version) == 12
    html = templates.env.get_template("base.html").render(
        request=type("R", (), {"url": type("U", (), {"path": "/"})()})(),
        settings=type("S", (), {"is_production": False, "database": "demo", "database_label": "Demo", "handler_id": "karl"})(),
        pending_approvals=0,
        environment_choices={},
    )
    assert f'href="/static/app.css?v={version}"' in html
    assert f'href="/static/tokens.css?v={version}"' in html
