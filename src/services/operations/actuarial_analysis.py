"""Avgränsade aktuariella systemanalyser och källkontrollerade erfarenhetsdata.

Systemarbetaren använder tjänstelagret och lämnar bara aggregat. Agentens
databasroll får ingen läsrätt på individutdragen. Inga analyser ändrar en bas.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import replace
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from analytics.actuarial_experience import (
    behavior_experience,
    expense_experience,
    fit_mortality,
    mortality_experience,
)
from models import (
    ActuarialDataset,
    ValuationBasis,
    ValuationExtractRecord,
    ValuationRun,
)
from services import valuation_bases as vb
from services.contract import OperationContext, OperationKind, operation
from services.errors import (
    AccessDeniedError,
    BlockedError,
    ConflictError,
    NotFoundError,
)
from services.valuation import compute_valuation, policy_inputs
from services.valuation_extract import ValuationExtract
from skills.calculation import actuarial_annuity as aa
from skills.calculation import fta_valuation as fv


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class MortalityRow(Strict):
    year: int = Field(ge=1900, le=2200)
    age: int = Field(ge=0, le=120)
    lives: int = Field(ge=1, le=100000000)
    exposure_years: float = Field(gt=0, le=100000000)
    deaths: int = Field(ge=0, le=1000000)

    @model_validator(mode="after")
    def valid_exposure(self):
        if self.exposure_years > self.lives or self.deaths > self.lives:
            raise ValueError("Exponering och dödsfall får inte överstiga antalet personer i årscellen")
        return self


class ExpenseRow(Strict):
    year: int = Field(ge=1900, le=2200)
    state: Literal["deferred", "payout"]
    lives: int = Field(ge=1)
    exposure_years: float = Field(gt=0)
    actual_sek: float = Field(ge=0)
    expected_sek: float = Field(ge=0)


class BehaviorRow(Strict):
    year: int = Field(ge=1900, le=2200)
    event: Literal["retirement", "transfer", "pause", "paid_up", "temporary_payout"]
    eligible: int = Field(ge=1)
    events: int = Field(ge=0)
    expected_rate: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def valid_events(self):
        if self.events > self.eligible:
            raise ValueError("Händelserna överstiger de valberättigade")
        return self


ROW_MODELS = {"mortality": MortalityRow, "expenses": ExpenseRow, "behavior": BehaviorRow}


class DatasetInput(Strict):
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
    kind: Literal["mortality", "expenses", "behavior"]
    title: str = Field(min_length=3, max_length=200)
    source_ref: str = Field(min_length=3, max_length=300)
    definition: str = Field(min_length=10, max_length=3000,
                            description="Urval, exponering, tidstäckning, allokering och förväntansgrund")
    synthetic: bool
    rows_json: str = Field(min_length=2, max_length=500000,
                           description="JSON-lista av typade aggregat; inga personuppgifter")


class JsonResult(BaseModel):
    payload: dict


def validated_dataset(data: DatasetInput) -> dict:
    from agents.gateways.drafts import _check_content

    _check_content(data.title + data.source_ref + data.definition)
    rows = json.loads(data.rows_json)
    if not isinstance(rows, list) or not 1 <= len(rows) <= 5000:
        raise ValueError("Underlaget ska ha 1–5 000 rader")
    normalized = [ROW_MODELS[data.kind].model_validate(row).model_dump(mode="json") for row in rows]
    keys = [(r["year"], r.get("age", r.get("state", r.get("event")))) for r in normalized]
    if len(keys) != len(set(keys)):
        raise ValueError("Dubbla observationsceller; registrera ett avstämt underlag")
    return {**data.model_dump(exclude={"rows_json"}), "rows": normalized}


@operation(name="register_actuarial_dataset", description="Registrerar en oföränderlig version av aktuariellt utfall.",
           kind=OperationKind.WRITE)
def register_dataset(ctx: OperationContext, data: DatasetInput) -> JsonResult:
    if ctx.actor.is_agent:
        raise AccessDeniedError("Observerat utfall registreras av människa eller en betrodd dataproducent")
    content = validated_dataset(data)
    session = ctx.require_session()
    if session.get(ActuarialDataset, data.id):
        raise ConflictError("Underlags-id finns redan; en rättelse får ett nytt versions-id")
    digest = vb.checksum(content)
    session.add(ActuarialDataset(id=data.id, kind=data.kind, title=data.title, content=content,
                               checksum=digest, created_by=ctx.actor.id))
    return JsonResult(payload={"id": data.id, "checksum": digest, "synthetic": data.synthetic})


class ValuationQuery(Strict):
    valuation_date: date
    basis_code: str | None = None
    curve_code: str | None = None


class SavedQuery(Strict):
    run_id: UUID | None = None
    valuation_date: date | None = None
    basis_code: str | None = None
    curve_code: str | None = None
    source_checksum: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def one_source(self):
        if (self.run_id is None) == (self.valuation_date is None):
            raise ValueError("Ange antingen sparad run_id eller valuation_date för ett skrivskyddat scenario")
        if self.run_id is not None and (self.basis_code is not None or self.curve_code is not None):
            raise ValueError("Ett sparat underlag använder sina egna versionerade grunder")
        return self


class ScenarioEffects(Strict):
    rate_shift_bp: float = Field(default=0, ge=-300, le=300)
    mortality_intensity_factor: float = Field(default=1, ge=.25, le=4)
    improvement_per_year: float | None = Field(default=None, ge=0, le=.04)
    expense_factor: float = Field(default=1, ge=0, le=5)
    expense_indexation: float | None = Field(default=None, ge=0, le=.1)


class ScenarioQuery(SavedQuery, ScenarioEffects):
    pass


class MonthChangeQuery(ScenarioEffects):
    journal_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


class ExperienceQuery(Strict):
    dataset_id: str
    basis_code: str | None = None
    prior_expected_deaths: float = Field(default=20, gt=0, le=10000)


class CurveQuery(Strict):
    basis_code: str
    birth_year: int = Field(ge=1900, le=2100)
    start_age: int = Field(default=50, ge=0, le=110)
    end_age: int = Field(default=110, ge=0, le=120)

    @model_validator(mode="after")
    def order(self):
        if self.end_age <= self.start_age:
            raise ValueError("Slutåldern ska vara större än startåldern")
        return self


class CompareQuery(Strict):
    previous_run_id: UUID
    current_run_id: UUID


ANALYSES = {
    "monthly_fta_change": (MonthChangeQuery, "Förklara en avstämd syntetisk premie-/garantimånad med strikt nollrest"),
    "valuation": (ValuationQuery, "Skrivskyddad FTA-provberäkning på aktuellt bestånd, alltid scenario"),
    "scenario": (ScenarioQuery, "Räkna om sparat utdrag med ändrad ränta, dödlighet eller kostnad"),
    "cashflows": (SavedQuery, "Projicera garantins och kostnadernas kassaflöden på ett sparat utdrag"),
    "experience": (ExperienceQuery, "Utfall mot förväntan för dödlighet, kostnader eller beteende"),
    "fit_mortality": (ExperienceQuery, "Skatta nivå och förbättring mot extern tabell med tidsvalidering"),
    "mortality_curve": (CurveQuery, "Dödsrisk och kohortöverlevnad ur versionerad grund"),
    "compare_valuations": (CompareQuery, "Jämför två värderingar; isolera grundeffekt och redovisa oförklarat"),
}


class AnalysisInput(Strict):
    analysis: Literal["valuation", "scenario", "cashflows", "experience", "fit_mortality", "mortality_curve", "compare_valuations", "monthly_fta_change"]
    parameters_json: str = Field(max_length=10000)


def _mortality(session, code):
    basis = session.scalar(select(ValuationBasis).where(ValuationBasis.code == code))
    if basis is None or basis.status != "adopted" or "mortality" not in basis.assumptions:
        raise NotFoundError("Välj en antagen dödlighetsgrund från antagandebiblioteket")
    vb.verify_checksum(basis)
    return basis, aa.MortalityBasis.from_assumptions(basis.assumptions["mortality"])


def _saved(session, run_id):
    run = session.get(ValuationRun, run_id)
    if run is None:
        raise NotFoundError("Värderingskörningen saknas")
    record = session.get(ValuationExtractRecord, run.extract_id)
    extract = ValuationExtract.model_validate(record.content)
    if (not run.checks_passed or not record.approved or extract.checksum != run.extract_checksum
            or record.checksum != extract.checksum):
        raise BlockedError("Värderingsunderlaget är inte godkänt eller innehållskontrollerat")
    # Kontrollera hela serialiserade utdraget med dess ursprungliga kontrollmetod.
    from services.valuation_extract import extract_checksum

    if extract_checksum(extract) != extract.checksum:
        raise BlockedError("Utdragets innehåll har ändrats")
    basis = session.scalar(select(ValuationBasis).where(ValuationBasis.code == run.basis_code))
    curve = session.scalar(select(ValuationBasis).where(ValuationBasis.code == run.curve_code))
    if basis is None or curve is None:
        raise BlockedError("Körningens grunder saknas")
    vb.verify_checksum(basis)
    vb.verify_checksum(curve)
    if basis.checksum != run.basis_checksum or curve.checksum != run.curve_checksum:
        raise BlockedError("Körningens grundversion stämmer inte")
    model = fv.ValuationModel.from_assumptions(basis.assumptions, curve.assumptions, float(run.tax_reduction))
    values = fv.value_policies(model, run.valuation_date, policy_inputs(extract))
    total = fv.totals(values)
    payload = fv.results_payload(values, total)
    payload["inputs"] = {"extract": extract.checksum, "basis": basis.checksum, "curve": curve.checksum,
                         "tax_reduction": str(run.tax_reduction)}
    # Postgres bevarar beloppet men kan ändra Decimalens presentationsskala.
    tax_strings = {str(run.tax_reduction), str(run.tax_reduction.normalize())}
    tax_strings.update(format(run.tax_reduction, f".{scale}f") for scale in range(13)
                       if Decimal(format(run.tax_reduction, f".{scale}f")) == run.tax_reduction)
    candidates = [{**payload, "inputs": {**payload["inputs"], "tax_reduction": value}} for value in tax_strings]
    if (not any(vb.checksum(p) == run.result_checksum for p in candidates) or total.fta != run.fta_sek
            or total.policies != run.policies or total.capital != run.capital_sek
            or total.expenses != run.expenses_sek or total.surplus != run.surplus_sek or total.deficit != run.deficit_sek):
        raise BlockedError("Källkörningens resultat kan inte återskapas på den sparade grunden")
    return run, extract, model


def _amounts(t):
    return {"fta_sek": float(t.fta), "capital_sek": float(t.capital), "expenses_sek": float(t.expenses),
            "surplus_sek": float(t.surplus), "deficit_sek": float(t.deficit)}


def _source(session, q):
    if q.run_id is not None:
        run, extract, model = _saved(session, q.run_id)
    else:
        c = compute_valuation(session, q.valuation_date, "scenario", basis_code=q.basis_code, curve_code=q.curve_code)
        if not c.checks_passed:
            raise BlockedError("Provvärderingens kontroller är underkända")
        basis = session.scalar(select(ValuationBasis).where(ValuationBasis.code == c.basis.code))
        curve = session.scalar(select(ValuationBasis).where(ValuationBasis.code == c.curve.code))
        model = fv.ValuationModel.from_assumptions(basis.assumptions, curve.assumptions, float(c.tax_reduction))
        run = SimpleNamespace(id="preview-"+c.result_checksum[:20], valuation_date=c.valuation_date,
            purpose="scenario", status="unsaved", policies=c.totals.policies, extract_checksum=c.extract.checksum,
            result_checksum=c.result_checksum, basis_checksum=c.basis.checksum, curve_checksum=c.curve.checksum,
            basis_code=c.basis.code, curve_code=c.curve.code)
        extract = c.extract
    if q.source_checksum is not None and q.source_checksum != extract.checksum:
        raise BlockedError("Beståndsunderlaget har ändrats sedan föregående analys; välj en ny bas")
    return run, extract, model


def _scenario_model(model, q):
    mortality = replace(model.mortality, improvement_per_year=(q.improvement_per_year
                          if q.improvement_per_year is not None else model.mortality.improvement_per_year))
    # Intensitetsmultiplikator: p' = p^f. Kan användas utan att ändra tabell eller historisk grund.
    if q.mortality_intensity_factor != 1:
        mortality = replace(mortality, intensity_factor=q.mortality_intensity_factor)
    curve = aa.DiscountCurve(tuple((t, r + q.rate_shift_bp / 10000) for t, r in model.curve.points),
                             model.curve.tax_reduction)
    expenses = replace(model.expenses, deferred_per_year=model.expenses.deferred_per_year*q.expense_factor,
                       payout_per_year=model.expenses.payout_per_year*q.expense_factor,
                       indexation=q.expense_indexation if q.expense_indexation is not None else model.expenses.indexation)
    return fv.ValuationModel(mortality, curve, expenses)


def _cashflows(run, extract, model):
    by_year = defaultdict(lambda: {"guarantee_sek": 0.0, "expenses_sek": 0.0, "present_value_sek": 0.0})
    grouped = defaultdict(lambda: [0.0, 0])
    for p in policy_inputs(extract):
        group = grouped[p.birth, p.plan_start]
        group[0] += float(p.guarantee)
        group[1] += 1
    for (birth, start), (guarantee, count) in grouped.items():
        month, weight = aa.first_month_after(run.valuation_date), 1.0
        for n in range(1, 2401):
            pension = weight * guarantee if month >= start else 0.0
            annual_cost = model.expenses.payout_per_year if month >= start else model.expenses.deferred_per_year
            cost = weight * count * annual_cost / 12 * (1+model.expenses.indexation)**(n/12)
            y = by_year[month.year]
            y["guarantee_sek"] += pension
            y["expenses_sek"] += cost
            y["present_value_sek"] += (pension+cost)*model.curve.factor(n)
            weight *= 1-aa.monthly_q(model.mortality, birth, month)
            month = aa.add_months(month, 1)
            if weight < 1e-25:
                break
    rows = [{"year": year, **{k: round(v, 2) for k, v in values.items()}} for year, values in sorted(by_year.items())]
    pv = sum(v["present_value_sek"] for v in by_year.values())
    check = fv.totals(fv.value_policies(model, run.valuation_date, policy_inputs(extract)))
    if abs(pv-float(check.fta)) > max(.01, len(extract.policies)*.000001):
        raise BlockedError("Kassaflödenas nuvärde stämmer inte av mot FTA; leveransen stoppas för granskning")
    return {"rows": rows, "projected_present_value_sek": round(pv, 2),
            "valuation_fta_sek": float(check.fta), "reconciliation_difference_sek": round(pv-float(check.fta), 2),
            "limitations": ["Avser redan intjänad garanti och driftkostnader; inga nya premier eller återbäringsutbetalningar.",
                             "Referensplanen är livsvarigt från 66. Ohanterade fall följer källkörningen."]}


@operation(name="perform_actuarial_analysis", description="Systemarbetarens aktuariella beräkningskärna; bara aggregat ut.",
           kind=OperationKind.COMPUTE)
def perform_analysis(ctx: OperationContext, data: AnalysisInput) -> JsonResult:
    if ctx.actor.is_agent:
        raise AccessDeniedError("Analysen körs av den avgränsade systemarbetaren, inte genom agentens databasroll")
    session = ctx.require_session()
    q = ANALYSES[data.analysis][0].model_validate_json(data.parameters_json)
    sources, limitations = [], []
    if data.analysis == "monthly_fta_change":
        from services.operations.premium_month import analyse_month

        payload, hidden = analyse_month(session, q)
        sources = payload["sources"]
        limitations = ["Syntetiskt månadsförsök med rekonstruerat S-04-IB; inga basvärderingar, tillgångar, ALM eller solvens.",
                       "Ändrade grunder här är scenarier och ändrar inte intjänade garantidelar."]
    elif data.analysis == "valuation":
        c = compute_valuation(session, q.valuation_date, "scenario", basis_code=q.basis_code, curve_code=q.curve_code)
        payload = {"rows": [{"label": "Scenario", **_amounts(c.totals)}], "policies": c.totals.policies,
                   "checks_passed": c.checks_passed,
                   "not_calculated": len(c.extract.not_calculated) if len(c.extract.not_calculated) not in range(1, 10) else None}
        sources = [c.extract.checksum, c.basis.checksum, c.curve.checksum, c.code_version]
        hidden = c.totals.policies not in (0,) and c.totals.policies < 10
        limitations = ["Rekonstruerat startbestånd S-04, skrivskyddat scenario. Ingen bas har skapats eller fastställts."]
    elif data.analysis in {"scenario", "cashflows"}:
        run, extract, model = _source(session, q)
        sources = [str(run.id), run.extract_checksum, run.result_checksum, run.basis_checksum, run.curve_checksum]
        hidden = 0 < run.policies < 10
        if data.analysis == "cashflows":
            payload = _cashflows(run, extract, model)
        else:
            scenario = _scenario_model(model, q)
            base = fv.totals(fv.value_policies(model, run.valuation_date, policy_inputs(extract)))
            changed = fv.totals(fv.value_policies(scenario, run.valuation_date, policy_inputs(extract)))
            payload = {"rows": [{"label": "Basunderlag", **_amounts(base)}, {"label": "Scenario", **_amounts(changed)}],
                       "delta_fta_sek": float(changed.fta-base.fta), "scenario": q.model_dump(mode="json"),
                       "base_status": run.status, "base_purpose": run.purpose}
        payload["valuation_date"] = run.valuation_date.isoformat()
        payload["extract_checksum"] = run.extract_checksum
        payload["basis_code"], payload["curve_code"] = run.basis_code, run.curve_code
        limitations = ["Samma oförändrade utdrag som källkörningen. Scenariot blir aldrig en fastställd bas."]
    elif data.analysis in {"experience", "fit_mortality"}:
        dataset = session.get(ActuarialDataset, q.dataset_id)
        if dataset is None:
            raise NotFoundError("Erfarenhetsunderlaget saknas; använd katalogen för databehov och importkontrakt")
        if vb.checksum(dataset.content) != dataset.checksum:
            raise BlockedError("Erfarenhetsunderlagets kontrollsumma stämmer inte")
        rows, kind = dataset.content["rows"], dataset.kind
        sources = [dataset.id, dataset.checksum, dataset.content["source_ref"]]
        if kind == "mortality":
            basis, mortality = _mortality(session, q.basis_code)
            sources += [basis.code, basis.checksum]
            payload = (fit_mortality(rows, mortality) if data.analysis == "fit_mortality"
                       else mortality_experience(rows, mortality, q.prior_expected_deaths))
        elif data.analysis == "fit_mortality":
            raise ValueError("Dödlighetsmodellering kräver ett dödlighetsunderlag")
        else:
            payload = expense_experience(rows) if kind == "expenses" else behavior_experience(rows)
        payload["synthetic"] = dataset.content["synthetic"]
        payload["data_definition"] = dataset.content["definition"]
        limitations = ["Syntetiskt utfall verifierar analyskedjan, inte verkliga antaganden."] if payload["synthetic"] else []
        hidden = False  # varje statistikfunktion tillämpar sitt eget härledningsskydd
    elif data.analysis == "mortality_curve":
        basis, mortality = _mortality(session, q.basis_code)
        survival, rows = 1.0, []
        for age in range(q.start_age, q.end_age+1):
            risk = aa.annual_q(mortality, age, q.birth_year+age, q.birth_year)
            rows.append({"age": age, "year": q.birth_year+age, "death_probability": risk, "survival": survival})
            survival *= 1-risk
        payload = {"rows": rows, "birth_year": q.birth_year, "conditional_on_survival_to_age": q.start_age}
        sources, hidden = [basis.code, basis.checksum, aa.TABLE_SHA256], False
        limitations = ["Modellkurva, inte observerat utfall eller konfidensintervall."]
    else:
        previous, _old_extract, old_model = _saved(session, q.previous_run_id)
        current, new_extract, _new_model = _saved(session, q.current_run_id)
        if previous.valuation_date >= current.valuation_date:
            raise ValueError("Jämförelsen kräver två värderingar i tidsordning")
        constant = fv.totals(fv.value_policies(old_model, current.valuation_date, policy_inputs(new_extract))).fta
        basis_effect = current.fta_sek-constant
        unexplained = constant-previous.fta_sek
        payload = {"rows": [{"label": "Ingående FTA", "fta_sek": float(previous.fta_sek)},
                            {"label": "Bestånd, tid och ej separerade rörelser", "fta_sek": float(unexplained)},
                            {"label": "Ändrade grunder", "fta_sek": float(basis_effect)},
                            {"label": "Utgående FTA", "fta_sek": float(current.fta_sek)}],
                   "unexplained_sek": float(unexplained),
                   "status": fv.unexplained_status(unexplained, current.fta_sek)}
        sources = [str(previous.id), previous.result_checksum, str(current.id), current.result_checksum]
        hidden = any(0 < n < 10 for n in (previous.policies, current.policies))
        limitations = ["Delanalys: premier, utbetalningar, dödsfall och planändringar är ännu inte separerade.",
                      "Oförklarad rörelse redovisas öppet och kräver mänsklig granskning över avtalad tröskel."]
    if hidden:
        payload = {"rows": [], "status": "suppressed", "reason": "Småcellsskydd; belopp och härledda mått dolda"}
    import hashlib
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    files = (root / "analytics/actuarial_experience.py", Path(__file__), root / "skills/calculation/actuarial_annuity.py",
             root / "skills/calculation/fta_valuation.py", root / "services/premium_month_analysis.py",
             root / "services/operations/premium_month.py", root / "skills/calculation/premium_origin_ledger.py")
    code_hash = hashlib.sha256(b"".join(p.read_bytes().replace(b"\r\n", b"\n") for p in files)).hexdigest()
    payload = {**payload, "analysis": data.analysis, "sources": sources, "code_checksum": code_hash,
               "parameters": q.model_dump(mode="json"),
               "limitations": [*payload.get("limitations", []), *limitations],
               "scenario_only": data.analysis in {"valuation", "scenario", "monthly_fta_change"}}
    return JsonResult(payload=payload)
