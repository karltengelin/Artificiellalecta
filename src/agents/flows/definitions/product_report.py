"""Flödet `product_report` – produktrapporten för PR-ITP1, version 0 (A2, B-042).

    definition = product_report_definition(renderer, DeliveryStore())

Fyra steg, i samma form som bolagsfrågan (`company_question.py`):

1. `summary` – aktuarien läser bestånd och premier och sammanfattar enligt `ProductReportSummary`.
2. `render` – betrodd kod bygger rapporten: tabellerna ur verktygens svar i steg 1, känsligheten
   (avsnitt 8) och typfallen (avsnitt 9) ur tjänstelagret, och de avsnitt som ännu inte kan
   beräknas markeras som ej beräknade med orsak (AKTUARIETEAM_PLAN.md §7). Leveransen sparas med
   kontrollsummor.
3. `review` – operatören granskar; grinden binder sammanfattningen och leveransen.
4. `deliver` – leveransen kontrolleras mot kontrollsummorna och markeras godkänd.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agents.assignments import PRODUCT_REPORT_FIXED_LIMITATIONS, request_for_product_report
from agents.deliveries import DeliveryError, DeliveryStore
from agents.flows.definition import AgentStep, FlowContext, FlowDefinition, GateStep, SystemOutcome, SystemStep
from agents.flows.definitions.company_question import Renderer, _text, _trace_lines
from agents.trace import read_run_trace
from reporting.template import TOKENS, ReportMetadata
from services import Actor, OperationContext, ServiceLayer
from services.errors import ServiceError
from services.operations import common
from services.operations.product_parameters import first_of_next_month
from services.operations.product_report_data import FIRST_YEAR

FLOW_TYPE = "product_report"
TEAM = "aktuarie"
REPORT_VERSION = "0"
TEMPLATE_REF = f"A4 rapportmall, Digital klarhet v{TOKENS['version']}"
#: Avsnitt 9: typlöner för premien per månad (kronor)
TYPICAL_SALARIES = (30_000, 45_000, 60_000, 80_000, 120_000)
#: Avsnitt 8: premiesatsen under brytpunkten höjs med en halv procentenhet i tre år
SENSITIVITY_KEY, SENSITIVITY_STEP, SENSITIVITY_YEARS = "premium_rate_low", Decimal("0.005"), 3
NOT_CALCULATED = {
    "4. Kapital och avkastning": "kräver pensionskapital per försäkring (startbestånd S-04, steg A5).",
    "5. Avgifter och kostnader": "kräver ekonomins kostnadsunderlag (V-10).",
    "6. Garanti och återbäring": "kräver värderingsmotorn för FTA, villkorad återbäring och underskott (steg A6, B-042).",
    "7. Risk- och dödlighetsutfall": "kräver utbetalningar, dödsfall och arvsvinstfördelning (paket B).",
}
OPEN_ITEMS = (
    "Begreppen kundkapital och villkorad återbäring stäms av i produktdokumenten före FTA-motorn (projekt 4, B-042).",
    "FI:s ändrade metod för diskonteringsräntan 2026 prövas som källändring (compliance, B-042).",
    "Värderingskontraktet A1 är fastställt; antagandebiblioteket (A4) är nästa byggsteg för FTA.",
)
SYSTEM = Actor.system("product_report")


class ProductReportOrder(BaseModel):
    """Beställningen. Miljö, dataset och körbild binds av betrodd kod, inte av formuläret."""

    model_config = ConfigDict(extra="forbid")

    year: int = Field(ge=FIRST_YEAR)
    note: str = Field(default="", max_length=500)
    environment_id: str = Field(min_length=1, max_length=100)
    dataset_ref: str = Field(min_length=1, max_length=200)
    policy_ref: str = Field(min_length=1, max_length=200)
    supersedes: str | None = Field(default=None, pattern=r"^FLOW-\d{6}$")


def _sek(value: Any) -> str:
    return f"{Decimal(str(value)):,.2f}".replace(",", " ").replace(".", ",") + " kr"


def _int(value: Any) -> str:
    return f"{value:,}".replace(",", " ")


def _count(value: int | None) -> str:
    return "dold" if value is None else _int(value)


def _pct(value: Decimal) -> str:
    return f"{value * 100:.1f}".replace(".", ",") + " %"


def _snapshot_lines(s: dict[str, Any] | None) -> list[str]:
    if s is None:
        return ["Ej läst – sammanfattningen saknar en godkänd läsning av beståndet."]
    lines = [f"Beståndet gäller läsdagen {s['as_of_date']}. Rörelserna gäller {s['year']} till och med läsdagen.", "",
             "| Läge | Försäkringar |", "|---|---|"]
    lines += [f"| {c['label']} | {_count(c['policies'])} |" for c in s["by_state"]]
    lines += [f"| **Totalt** | {_count(s['policies_total'])} |", "",
              "| Födelsedecennium (ej avslutade) | Försäkringar |", "|---|---|"]
    lines += [f"| {c['label']} | {_count(c['policies'])} |" for c in s["by_cohort"]]
    lines += [f"| **I beståndet** | {_count(s['policies_in_force'])} |", "",
              f"- Personer med minst en försäkring i beståndet: {_count(s['insured_in_force'])}",
              f"- Nya försäkringar under året: {_count(s['entered_in_year'])}",
              f"- Nya fribrev under året: {_count(s['paid_up_in_year'])}"]
    if any(c["policies"] is None for c in s["by_state"] + s["by_cohort"]):
        lines.append(f"- Celler med färre än {s['min_cell_size']} försäkringar döljs, och fler celler döljs "
                     "så att en dold cell inte kan räknas fram ur totalen")
    return lines


def _flow_lines(f: dict[str, Any] | None) -> list[str]:
    if f is None:
        return ["Ej läst – sammanfattningen saknar en godkänd läsning av premierna."]
    if f["total_state"] == "no_months":
        return [f"Inga avslutade månader under {f['year']} ännu."]
    if f["total_state"] == "failed":
        return ["Ej redovisat – premieunderlaget innehåller betalmarkeringar utan giltig betaldag."]
    lines = ["| Månad | Betalmarkerat | Personer |", "|---|---|---|"]
    lines += [f"| {m['month'][:7]} | {'dolt' if m['paid_sek'] is None else _sek(m['paid_sek'])} | "
              f"{_count(m['persons'])} |" for m in f["months"]]
    total = "dolt" if f["total_paid_sek"] is None else _sek(f["total_paid_sek"])
    lines += [f"| **Summa** | {total} | {_count(f['total_persons'])} |", "",
              f"- Period {f['period_from']} till {f['period_to']} (slutet ingår inte); innevarande månad ingår inte",
              f"- {f['definition']}", f"- Antal personer i summan är unika personer under perioden. {f['transfers_note']}"]
    return lines


def _sensitivity_lines(trusted: ServiceLayer, today: date) -> list[str]:
    ctx = OperationContext(actor=SYSTEM)
    try:
        current = trusted.execute("get_product_parameters", ctx, {}).output.effective[SENSITIVITY_KEY]
        valid_from = first_of_next_month(today)
        estimate = trusted.execute("estimate_parameter_change_impact", ctx, {
            "key": SENSITIVITY_KEY, "value": str(current + SENSITIVITY_STEP), "valid_from": valid_from.isoformat(),
            "horizon_years": SENSITIVITY_YEARS}).output
    except ServiceError as exc:
        return [f"Ej beräknat – {exc}"]
    lines = [f"Premiesatsen under brytpunkten höjs från {_pct(current)} till {_pct(current + SENSITIVITY_STEP)} "
             f"från {valid_from}, för dagens aktiva försäkrade med dagens lön.", "",
             "| År | Berörda | Extra premievolym |", "|---|---|---|"]
    for y in estimate.years:
        volume = "dold" if y.extra_premium_volume_sek is None else _sek(y.extra_premium_volume_sek)
        lines.append(f"| {y.year} | {_count(y.affected_persons)} | {volume} |")
    lines += ["", *[f"- {a}" for a in estimate.assumptions],
              "- Känsligheten gäller premieinflödet, inte värderingen av åtagandena"]
    return lines


def _typical_lines(trusted: ServiceLayer, today: date) -> list[str]:
    ctx = OperationContext(actor=SYSTEM)
    month = today.replace(day=1)
    lines = [f"Premie per månad för typlöner i {month.strftime('%Y-%m')} enligt premietrappan (PR-ITP1-001).", "",
             "| Månadslön | Premie per månad | Under brytpunkten | Över brytpunkten |", "|---|---|---|---|"]
    assumed = None
    for salary in TYPICAL_SALARIES:
        try:
            p = trusted.execute("calculate_premium_preview", ctx, {
                "monthly_salary_sek": str(salary), "period_month": month.isoformat(),
                "latest_base_amount": True}).output
        except ServiceError as exc:
            return [f"Ej beräknat – {exc}"]
        assumed = assumed or p.base_amount_assumed_from
        lines.append(f"| {_sek(salary)} | {_sek(p.total_premium_sek)} | {_sek(p.amount_low_sek)} | "
                     f"{_sek(p.amount_high_sek)} |")
    lines.append("")
    if assumed:
        lines.append(f"- Inkomstbasbeloppet för {assumed} används eftersom årets inte är fastställt")
    lines += ["- Kapitalavgiften är 0,20 % per år av pensionskapitalet; inga andra avgifter (PR-ITP1-022)",
              "- Prognostiserad pension per typfall: ej beräknat – kräver pensionskapital och prognosmotor"]
    return lines


def report_markdown(order: ProductReportOrder, *, flow_id: str, summary: dict[str, Any] | None,
                    evidence: dict[str, Any], run: dict[str, Any], sensitivity: list[str], typical: list[str],
                    trace=None) -> str:
    """Rapportens Markdown: sammanfattningen först, tabellerna ur verktygens svar, spårbarheten sist."""
    lines = [f"# Produktrapport PR-ITP1 {order.year}", "",
             f"Uppdrag {flow_id} · Aktuarieteamet · Version {REPORT_VERSION} (avsnitt 1–3, 8 och 9 beräknade)", "",
             "## 1. Sammanfattning", ""]
    if summary is None:
        lines += ["Aktuarien lämnade ingen sammanfattning som kunde godtas."]
    else:
        lines += [_text(summary["conclusion"])]
        for title, key in (("Iakttagelser", "key_findings"), ("Rekommendationer", "recommendations")):
            if summary[key]:
                lines += ["", f"**{title}**", ""] + [f"- {_text(t)}" for t in summary[key]]
    lines += ["", "## 2. Bestånd och rörelser", "", *_snapshot_lines(evidence.get("snapshot")),
              "", "## 3. Premier", "", *_flow_lines(evidence.get("premium_flows"))]
    for title, reason in NOT_CALCULATED.items():
        lines += ["", f"## {title}", "", f"Ej beräknat – {reason}"]
    lines += ["", "## 8. Känslighet för produktparametrar", "", *sensitivity,
              "", "## 9. Kundutfall och värde", "", *typical,
              "", "## 10. Avvikelser och åtgärder", "", *[f"- {t}" for t in OPEN_ITEMS],
              "", "## Begränsningar", "", *[f"- {t}" for t in PRODUCT_REPORT_FIXED_LIMITATIONS]]
    fixed = set(PRODUCT_REPORT_FIXED_LIMITATIONS)
    lines += [f"- {_text(t)}" for t in (summary or {}).get("limitations", []) if _text(t) not in fixed]
    lines += ["", "## Så togs rapporten fram", "",
              f"- Uppdrag `{flow_id}`, produktrapport version {REPORT_VERSION} enligt AKTUARIETEAM_PLAN.md §7 och "
              "B-042. Rapporten granskas i uppdraget; beslut, granskare och datum registreras där",
              *_trace_lines(run, trace),
              f"- Miljö `{order.environment_id}`, dataset `{order.dataset_ref}`, körbild `{order.policy_ref}`",
              "- Avsnitt 2 och 3 ur aktuariens läsningar, avsnitt 8 och 9 ur tjänstelagret i betrodd kod",
              f"- Mall: {TEMPLATE_REF}"]
    if order.note.strip():
        lines.append(f"- Operatörens precisering: {_text(order.note)}")
    if order.supersedes:
        lines.append(f"- Ersätter det avslagna uppdraget `{order.supersedes}`")
    return "\n".join(lines) + "\n"


def product_report_definition(
    renderer: Renderer, store: DeliveryStore, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    journal_dir: Path | None = None,
) -> FlowDefinition:
    def request(ctx: FlowContext):
        order = ProductReportOrder.model_validate(ctx.input)
        return request_for_product_report(order.year, order.note, task_id=f"task-{ctx.flow_id}")

    def render(ctx: FlowContext, trusted: ServiceLayer) -> SystemOutcome:
        order = ProductReportOrder.model_validate(ctx.input)
        step = ctx.result("summary")
        output = step.get("output") or {}
        summary = output.get("result")
        if summary is not None and summary["year"] != order.year:
            return SystemOutcome(result={"error": "year"},
                                 error=f"Sammanfattningen gäller {summary['year']}, beställningen {order.year}")
        now = clock()
        run = step.get("run") or {}
        trace = read_run_trace(journal_dir, run.get("run_id")) if journal_dir is not None else None
        markdown = report_markdown(order, flow_id=ctx.flow_id, summary=summary, evidence=output.get("evidence") or {},
                                   run=run, sensitivity=_sensitivity_lines(trusted, common.today()),
                                   typical=_typical_lines(trusted, common.today()), trace=trace)
        metadata = ReportMetadata(title=f"Produktrapport PR-ITP1 {order.year}", header=f"Uppdrag {ctx.flow_id}",
                                  footer=f"Produktrapport v{REPORT_VERSION} · B-042", eyebrow="PRODUKTRAPPORT / ITP1")
        try:
            pdf = renderer(markdown, metadata)
        except Exception as exc:  # noqa: BLE001 – exporten misslyckades innan något skrevs; utfallet är känt
            return SystemOutcome(result={"error": "export"}, error=f"Exporten misslyckades: {type(exc).__name__}")
        manifest = {"report": f"produktrapport v{REPORT_VERSION}", "template": TEMPLATE_REF, "team": TEAM,
                    "run_id": run.get("run_id"), "created_at": now.isoformat(), "year": order.year,
                    "environment_id": order.environment_id, "dataset_ref": order.dataset_ref,
                    "policy_ref": order.policy_ref, "status": "för granskning"}
        try:
            receipt = store.publish(ctx.flow_id, {"rapport.md": markdown.encode("utf-8"), "rapport.pdf": pdf}, manifest)
        except DeliveryError as exc:
            return SystemOutcome(result={"error": "store"}, error=str(exc))
        return SystemOutcome(result={"delivery": receipt, "summarized": summary is not None})

    def deliver(ctx: FlowContext, trusted: ServiceLayer) -> SystemOutcome:
        receipt = ctx.result("render")["delivery"]
        try:
            for name, checksum in receipt["files"].items():
                store.read(ctx.flow_id, receipt["version"], name, checksum)
        except DeliveryError as exc:
            return SystemOutcome(result={"error": "delivery"}, error=str(exc))
        return SystemOutcome(result={"delivery_id": f"{ctx.flow_id}-v{receipt['version']}",
                                     "accepted_version": receipt["version"], "files": receipt["files"],
                                     "status": "accepted"})

    return FlowDefinition(
        flow_type=FLOW_TYPE,
        version="1",
        title="Produktrapport PR-ITP1",
        input_model=ProductReportOrder,
        steps=(
            AgentStep(key="summary", title="Aktuarien sammanfattar bestånd och premier", team=TEAM, request=request),
            SystemStep(key="render", title="Rapporten skapas", run=render),
            GateStep(key="review", title="Operatören granskar rapporten", binds=("summary", "render")),
            SystemStep(key="deliver", title="Leveransen godkänns", run=deliver),
        ),
    )
