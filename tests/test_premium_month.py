"""P6-MANAD-001: källkontrakt, mottagning, ursprungsspår och oberoende månadsfacit."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select

from models import (
    Base,
    BaseAmount,
    Employer,
    InsuredPerson,
    Policy,
    PolicyState,
    PremiumTransaction,
)
from services import (
    Actor,
    OperationContext,
    ProductRuleCatalog,
    ServiceLayer,
    parameters,
)
from services import valuation_bases as vb
from services.db import session_factory_for
from services.errors import AccessDeniedError, BlockedError, ConflictError
from services.premium_month_inputs import (
    InvoiceInput,
    MonthInputs,
    ReceiptInput,
    allocate_receipt,
    extended_returns,
    inputs_checksum,
    receipt_key,
)
from services.premium_month_preparation import bound_source, prepare_inputs
from services.valuation_extract import build_extract
from skills.calculation.premium_origin_ledger import (
    Origin,
    reconstruct_origins,
    roll_origins,
)
from tests.conftest import add_retirement_benefit


@pytest.fixture
def month_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'month.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = session_factory_for(engine)
    with factory() as s:
        parameters.add_missing_defaults(s)
        vb.add_missing_defaults(s)
        s.add(BaseAmount(year=2026, income_base_amount_sek=Decimal(83400)))
        employer = Employer(org_number="5560000001", name="Syntetiskt bolag", affiliation_date=date(2020, 1, 1))
        s.add(employer)
        s.flush()
        for n in range(12):
            person = InsuredPerson(personal_id_number=f"198001{n+1:02}1234", first_name="Test", last_name=str(n),
                employer_id=employer.id, employment_start_date=date(2020, 1, 1), itp1_start_date=date(2020, 1, 1),
                status="active")
            s.add(person)
            s.flush()
            policy = Policy(policy_number=f"SYN-{n:03}", insured_person_id=person.id,
                            start_date=date(2020, 1, 1), signed_date=date(2020, 1, 1))
            s.add(policy)
            s.flush()
            benefit = add_retirement_benefit(s, policy.id, date(2020, 1, 1))
            s.add(PolicyState(policy_id=policy.id, state="premium_paying", valid_from=date(2020, 1, 1)))
            s.flush()
            for month, amount in ((1, "10000.00"), (2, "5000.00")):
                s.add(PremiumTransaction(benefit_id=benefit.id, period_month=date(2023, month, 1),
                    transaction_type="premium", amount_sek=Decimal(amount), status="paid", paid_date=date(2023, month, 15)))
    with factory() as s:
        opening = build_extract(s, date(2026, 10, 31))
        package = prepare_inputs(s, "november-test", opening.checksum)
    yield SimpleNamespace(engine=engine, factory=factory, package=package)
    engine.dispose()


def receipt(invoice_id="invoice-1", amount="333.33", **changes):
    body = {"event_id": "event-1", "payment_reference": "reference-1", "payer_id": "payer-1",
        "received_date": "2026-11-15", "currency": "SEK", "gross_sek": amount,
        "external_deduction_sek": "0.00", "net_sek": amount, "invoice_id": invoice_id, **changes}
    return ReceiptInput.model_validate({**body, "source": bound_source("bank", body["event_id"], body)})


def invoice():
    body = {"id": "invoice-1", "payer_id": "payer-1", "lines": [
        {"id": key, "benefit_id": key, "policy_id": "p", "period_month": "2025-12-01", "due_sek": amount,
         "calculation_basis": {"ibb_year": 2025}} for key, amount in (("a", "600.00"), ("b", "400.00"))]}
    return InvoiceInput.model_validate({**body, "source": bound_source("employer", "invoice-1", body)})


def test_preparation_freezes_history_and_does_not_write(month_db):
    from models import ValuationBasis, ValuationRun

    p = month_db.package
    assert p.checksum == inputs_checksum(p)
    assert len(p.invoices) == len(p.receipts) == len(p.opening.policies) == 12
    assert {r.value_date for r in p.receipts} == {date(2026, 11, 30)}
    avk = extended_returns(p)
    old = next(b.assumptions for b in p.bases if b.code == "AVK-SIM-2026-01")
    assert avk["months"][:-1] == old["months"]
    assert avk["months"][-1] == {"month": "2026-11-01", "rate": "0.002"}
    with month_db.factory() as s:
        assert not list(s.scalars(select(ValuationRun)))
        assert "AVK-SIM-2026-02" not in set(s.scalars(select(ValuationBasis.code)))
        count = len(list(s.scalars(select(PremiumTransaction))))
        assert count == 24


def test_receipt_partial_overpayment_and_payer_mismatch():
    shares, rest = allocate_receipt(invoice(), receipt(), {})
    assert shares == {"a": Decimal("200.00"), "b": Decimal("133.33")}
    assert rest == 0
    shares, rest = allocate_receipt(invoice(), receipt(amount="1000.00"), shares)
    assert shares == {"a": Decimal("400.00"), "b": Decimal("266.67")}
    assert rest == Decimal("333.33")
    assert allocate_receipt(invoice(), receipt(payer_id="other"), {}) == ({}, Decimal("333.33"))


def test_source_tampering_amount_validation_and_transport_idempotency():
    original = receipt()
    body = original.model_dump(mode="json")
    body["net_sek"] = "300.00"
    with pytest.raises(ValueError):
        ReceiptInput.model_validate(body)
    body = original.model_dump(mode="json")
    body["source"]["payload"]["payment_reference"] = "changed"
    with pytest.raises(ValueError):
        ReceiptInput.model_validate(body)
    alternate = ReceiptInput.model_validate({**original.model_dump(mode="json"), "delivery_ref": "another-file"})
    assert receipt_key("scenario", alternate) == receipt_key("scenario", original)
    assert original.economic_content() == alternate.economic_content()
    with pytest.raises(ValueError):
        receipt(amount="1.001")


def test_modified_opening_basis_parameter_and_population_stop(month_db):
    p = month_db.package
    for mutate in (
        lambda d: d["opening"]["policies"][0].update(capital="1.00"),
        lambda d: d["bases"][0]["assumptions"].update(synthetic=False),
        lambda d: d["parameters"][0].update(value="0.1"),
        lambda d: d.update(expected_opening_checksum="0" * 64),
        lambda d: d["invoices"][0]["lines"][0].update(policy_id="outside"),
    ):
        body = p.model_dump(mode="json")
        mutate(body)
        with pytest.raises(ValueError):
            MonthInputs.model_validate(body)
    with month_db.factory() as s, pytest.raises(ValueError):
        prepare_inputs(s, "different", "0" * 64)


HUMAN = OperationContext(actor=Actor.human("karl"), reason="Godkänt syntetiskt månadsförsök")


def month_service(db):
    return ServiceLayer(session_factory=db.factory, rules=ProductRuleCatalog(today=date(2026, 11, 3)))


def call(service, name, data):
    return service.execute(name, HUMAN, data).output.payload


def open_package(db):
    service = month_service(db)
    p = db.package
    call(service, "open_premium_month", {"inputs_json": p.model_dump_json(), "reviewed_checksum": p.checksum})
    return service


def receive_all(service, p):
    for r in sorted(p.receipts, key=lambda r: (r.received_date, receipt_key(p.scenario_id, r))):
        call(service, "receive_premium_payment", {"journal_id": p.scenario_id, "receipt": r.model_dump(mode="json")})


def adopt_returns(service, p):
    service.execute("propose_valuation_basis", HUMAN, {"code": "AVK-SIM-2026-02", "title": "Syntetisk novemberbana",
        "assumptions": extended_returns(p), "source_refs": p.checksum, "supersedes_code": "AVK-SIM-2026-01"})
    service.execute("adopt_valuation_basis", HUMAN, {"code": "AVK-SIM-2026-02", "valid_from": "2026-11-01",
        "decision_ref": "P6-MANAD-001 D5"})


def test_origins_preserve_policy_rounding_and_hand_calculated_month(month_db):
    origins, digest = reconstruct_origins(month_db.package.opening)
    assert len(origins) == 24 and len(digest) == 64
    # Avgiften ska rundas per försäkring, inte två gånger på de enskilda ursprungen.
    old = [Origin("a", "p", Decimal("50000.00")), Origin("b", "p", Decimal("50000.00"))]
    result, entries, closed = roll_origins(date(2026, 11, 1), Decimal("0.01"), old,
        [Origin("new", "p", Decimal("1000.00"))], fee_rate=Decimal("0.002"), tax_rate=Decimal("0.00354"))
    assert closed.total("closing") == Decimal("101953.83")
    assert sum((x.capital for x in result), Decimal(0)) == Decimal("101953.83")
    assert sum((Decimal(e["amount"]) for e in entries if e["kind"] == "fee"), Decimal(0)) == Decimal("-16.67")
    assert next(x for x in result if x.id == "new").capital == 1000
    loss, _, _ = roll_origins(date(2026, 11, 1), Decimal(-1), old, [],
                             fee_rate=Decimal("0.002"), tax_rate=Decimal("0.00354"))
    assert all(x.capital == 0 for x in loss)
    with pytest.raises(ValueError):
        roll_origins(date(2026, 11, 1), Decimal(0), old, [old[0]], fee_rate=Decimal(0), tax_rate=Decimal(0))


def test_full_month_independent_capital_bridge_review_and_idempotence(month_db):
    from models import PremiumMonthClose, PremiumReceipt, ValuationRun

    p = month_db.package
    service = open_package(month_db)
    receive_all(service, p)
    # Releverans är samma ekonomiska händelse, även från en annan transportfil.
    r = p.receipts[0].model_dump(mode="json")
    r["delivery_ref"] = "second-file"
    assert call(service, "receive_premium_payment", {"journal_id": p.scenario_id, "receipt": r})["reused"]
    with pytest.raises(BlockedError):
        call(service, "close_premium_month", {"journal_id": p.scenario_id})  # saknad november-AVK
    adopt_returns(service, p)
    result = call(service, "close_premium_month", {"journal_id": p.scenario_id})
    assert result["state"] == "review_required"
    assert call(service, "close_premium_month", {"journal_id": p.scenario_id}) == result
    with month_db.factory() as s:
        closed = s.scalar(select(PremiumMonthClose))
        content = closed.content
        steps = content["analysis"]["steps"]
        assert Decimal(content["analysis"]["unexplained_sek"]) == 0
        ib = Decimal(content["analysis"]["opening"]["fta_sek"])
        ub = Decimal(content["analysis"]["closing"]["fta_sek"])
        assert ib + sum((Decimal(x["reported_change_sek"]) for x in steps), Decimal(0)) == ub
        assert steps[0]["reported_change_sek"] == "24300.00"
        capital = content["capital_movements"]
        assert (Decimal(capital["opening"]) + Decimal(capital["returns"]) - Decimal(capital["fees"])
                - Decimal(capital["taxes"]) + Decimal(capital["premiums"])) == Decimal(capital["closing"])
        assert len(list(s.scalars(select(PremiumReceipt)))) == 12
        assert len(list(s.scalars(select(ValuationRun)))) == 2
        assert all(r.purpose == "scenario" and r.status == "draft" for r in s.scalars(select(ValuationRun)))
        assert len(list(s.scalars(select(PremiumTransaction)))) == 24  # historiken betalmarkeras inte igen
    with pytest.raises(ConflictError):
        call(service, "approve_premium_month", {"journal_id": p.scenario_id, "reviewed_checksum": "0" * 64})
    with pytest.raises(AccessDeniedError):
        service.execute("approve_premium_month", OperationContext(actor=Actor.system("worker"), reason="Försök"),
                        {"journal_id": p.scenario_id, "reviewed_checksum": result["review_checksum"]})
    approved = call(service, "approve_premium_month", {"journal_id": p.scenario_id,
                                                       "reviewed_checksum": result["review_checksum"]})
    assert approved["state"] == "approved_analysis"
    analysis_results = {}
    for label, effects in (("base", {}), ("rate", {"rate_shift_bp": 50}), ("cost", {"expense_factor": 1.1}),
                            ("both", {"rate_shift_bp": 50, "expense_factor": 1.1})):
        import json

        analysis_results[label] = service.execute("perform_actuarial_analysis", HUMAN,
            {"analysis": "monthly_fta_change", "parameters_json": json.dumps({"journal_id": p.scenario_id, **effects})}).output.payload
    assert Decimal(analysis_results["rate"]["steps"][6]["exact_change_sek"]) < 0
    assert Decimal(analysis_results["cost"]["steps"][7]["exact_change_sek"]) > 0
    assert Decimal(analysis_results["base"]["steps"][6]["exact_change_sek"]) == 0
    assert all(Decimal(a["unexplained_sek"]) == 0 for a in analysis_results.values())
    assert "policy_id" not in str(analysis_results)


def test_pending_receipt_proposal_has_no_effect_until_approved(month_db):
    from models import PremiumReceipt

    service = open_package(month_db)
    p = month_db.package
    first = min(p.receipts, key=lambda r: (r.received_date, receipt_key(p.scenario_id, r)))
    proposal = service.execute("receive_premium_payment", OperationContext(actor=Actor.agent("test-agent"),
        reason="Verifierat syntetiskt underlag"), {"journal_id": p.scenario_id, "receipt": first.model_dump(mode="json")})
    assert proposal.pending
    with month_db.factory() as s:
        assert not list(s.scalars(select(PremiumReceipt)))
    service.approve(proposal.approval_id, HUMAN)
    with month_db.factory() as s:
        assert len(list(s.scalars(select(PremiumReceipt)))) == 1


def test_tiny_unexplained_delta_stops_analysis(month_db):
    from services.operations.premium_month import _model
    from services.premium_month_analysis import change_analysis
    from services.valuation import policy_inputs
    from skills.calculation import fta_valuation as fv

    p = month_db.package
    with month_db.factory() as s:
        model = _model(s, p.opening_basis_code, p.opening_curve_code, Decimal("0.00354"))
    total = fv.totals(fv.value_policies(model, p.opening.valuation_date, policy_inputs(p.opening)))
    for residual in (Decimal("0.01"), Decimal("0.000001")):
        with pytest.raises(ValueError):
            change_analysis(p.opening, p.opening, model, model, premium_sek=Decimal(0),
                            expected_opening=total.fta, expected_closing=total.fta+residual, sources={})


def test_existing_flow_engine_binds_human_month_review(month_db):
    from agents.flows import FlowEngine
    from agents.flows.definitions.premium_month_review import (
        premium_month_review_definition,
    )

    service = open_package(month_db)
    p = month_db.package
    receive_all(service, p)
    adopt_returns(service, p)
    call(service, "close_premium_month", {"journal_id": p.scenario_id})
    engine = FlowEngine(month_db.factory, [premium_month_review_definition()], trusted=service)
    actor = Actor.human("karl")
    flow = engine.start("premium_month_review", {"journal_id": p.scenario_id}, actor=actor)
    flow = engine.run_next(flow.flow_id, expected_version=flow.version, actor=actor)
    assert flow.status == "waiting_gate"
    flow = engine.decide_gate(flow.flow_id, expected_version=flow.version, actor=actor,
                             decision="approved", seen_hash=flow.gate_hashes["review"])
    flow = engine.run_next(flow.flow_id, expected_version=flow.version, actor=actor)
    assert flow.status == "completed"
    assert call(service, "get_premium_month", {"journal_id": p.scenario_id})["state"] == "approved_analysis"


def test_receipt_and_guarantee_rollback_with_event_log_failure(month_db):
    from models import PremiumReceipt

    service = open_package(month_db)
    previous_log = service.events
    class FailingLog:
        def record(self, event, session=None):
            raise RuntimeError("synthetic log failure")
    service.events = FailingLog()
    p = month_db.package
    first = min(p.receipts, key=lambda r: (r.received_date, receipt_key(p.scenario_id, r)))
    with pytest.raises(RuntimeError, match="synthetic log failure"):
        call(service, "receive_premium_payment", {"journal_id": p.scenario_id, "receipt": first.model_dump(mode="json")})
    service.events = previous_log
    with month_db.factory() as s:
        assert not list(s.scalars(select(PremiumReceipt)))
    assert not call(service, "receive_premium_payment", {"journal_id": p.scenario_id,
                    "receipt": first.model_dump(mode="json")})["reused"]


def test_single_contributor_is_hidden_and_sources_are_human_only(month_db):
    import json

    p = month_db.package
    body = p.model_dump(mode="json")
    body.update(receipts=body["receipts"][:1], checksum="")
    initial = MonthInputs.model_validate(body)
    month_db.package = MonthInputs.model_validate({**initial.model_dump(mode="json"), "checksum": inputs_checksum(initial)})
    p = month_db.package
    service = open_package(month_db)
    receive_all(service, p)
    adopt_returns(service, p)
    result = call(service, "close_premium_month", {"journal_id": p.scenario_id})
    payload = service.execute("perform_actuarial_analysis", HUMAN,
        {"analysis": "monthly_fta_change", "parameters_json": json.dumps({"journal_id": p.scenario_id})}).output.payload
    assert payload["status"] == "suppressed" and payload["rows"] == []
    assert "closing" not in payload and "steps" not in payload
    inspected = call(service, "get_premium_month", {"journal_id": p.scenario_id, "include_sources": True})
    assert inspected["sources"]["closing"]["entries"]
    with pytest.raises(AccessDeniedError):
        service.execute("get_premium_month", OperationContext(actor=Actor.system("worker")),
                        {"journal_id": p.scenario_id, "include_sources": True})
    # Ändrat kvitto efter stängningen ogiltigförklarar ett äldre granskningsunderlag.
    from models import PremiumReceipt

    with month_db.factory() as s:
        row = s.scalar(select(PremiumReceipt))
        row.content = {**row.content, "unallocated_sek": "0.01"}
        row.checksum = vb.checksum(row.content)
    with pytest.raises(BlockedError):
        call(service, "approve_premium_month", {"journal_id": p.scenario_id,
                                                "reviewed_checksum": result["review_checksum"]})


def test_existing_dialogue_catalog_analysis_chart_and_report(month_db):
    import json

    from agents.actuarial_workbench import Workbench, WorkbenchInput
    from models import ActuarialConversation, ActuarialTurn, ValuationBasis

    p = month_db.package
    service = open_package(month_db)
    receive_all(service, p)
    adopt_returns(service, p)
    result = call(service, "close_premium_month", {"journal_id": p.scenario_id})
    with month_db.factory() as s:
        s.add(ActuarialConversation(id="month-dialogue", title="Månadsuppföljning", created_by="karl"))
        s.flush()
        s.add(ActuarialTurn(id="month-turn", conversation_id="month-dialogue", submission_key="turn-1",
            instruction="Förklara den avstämda månaden", status="running", submitted_by="karl", run_id="month-run"))
    bench = Workbench(service, service, "month-dialogue")
    def invoke(action, name="", args=None):
        return bench.invoke("aktuarie", "month-run", WorkbenchInput(action=action, name=name,
            arguments_json=json.dumps(args or {}))).payload
    catalog = invoke("catalog")
    assert any(a["name"] == "monthly_fta_change" for a in catalog["analyses"])
    assert catalog["premium_months"][0]["journal_id"] == p.scenario_id
    analysis = invoke("analyze", "monthly_fta_change", {"journal_id": p.scenario_id})
    chart = invoke("chart", args={"analysis_id": analysis["id"], "title": "FTA-förändring", "kind": "bar",
                                  "x": "label", "y": "fta_sek", "unit": "SEK"})
    report = invoke("report", args={"title": "Månadsuppföljning", "conclusion": "Månaden är avstämd som scenario.",
        "analysis_ids": [analysis["id"]], "chart_ids": [chart["id"]]})
    assert report["kind"] == "report" and "Ingående FTA" in report["content"]["markdown"]
    assert "policy_id" not in json.dumps(report)
    # Även underliggande grund måste vara oförändrad vid mänskligt godkännande.
    with month_db.factory() as s:
        basis = s.scalar(select(ValuationBasis).where(ValuationBasis.code == "SIM-V-2026-01"))
        basis.assumptions = {**basis.assumptions, "option_adjustment": "changed"}
    with pytest.raises(BlockedError):
        call(service, "approve_premium_month", {"journal_id": p.scenario_id,
                                                "reviewed_checksum": result["review_checksum"]})


@pytest.mark.postgres
def test_premium_journal_postgres_migration_and_concurrent_receipt(month_db):
    import os
    from concurrent.futures import ThreadPoolExecutor
    from dataclasses import replace
    from threading import Barrier

    from sqlalchemy import inspect
    from sqlalchemy.exc import DBAPIError

    from models import PremiumReceipt
    from tests.test_services_postgres import TEST_URL, isolated_schema
    from utils.agent_roles import AKTUARIE
    from utils.migration_premium_journal import MODELS, TABLES, migrate_premium_journal

    if not TEST_URL:
        pytest.skip("Isolerad Postgres saknas")
    with isolated_schema() as db:
        Base.metadata.create_all(db.engine, tables=[t for t in Base.metadata.sorted_tables if t.name not in TABLES])
        dry = migrate_premium_journal(db.engine)
        assert not dry.applied and not set(TABLES) & set(inspect(db.engine).get_table_names())
        done = migrate_premium_journal(db.engine, dry_run=False)
        assert done.applied and done.row_counts == dry.row_counts
        assert migrate_premium_journal(db.engine, dry_run=False).already_applied
        for model in MODELS:
            actual = {c["name"] for c in inspect(db.engine).get_columns(model.__tablename__)}
            assert actual == {c.name for c in model.__table__.columns}
        with db.session_factory() as s:
            vb.add_missing_defaults(s)
            parameters.add_missing_defaults(s)
        pg = SimpleNamespace(factory=db.session_factory, package=month_db.package)
        service = open_package(pg)
        p = pg.package
        first = min(p.receipts, key=lambda r: (r.received_date, receipt_key(p.scenario_id, r)))
        barrier = Barrier(2)
        def receive(_):
            barrier.wait(timeout=10)
            return call(service, "receive_premium_payment", {"journal_id": p.scenario_id,
                                                            "receipt": first.model_dump(mode="json")})
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(receive, (1, 2)))
        assert sorted(o["reused"] for o in outcomes) == [False, True]
        with db.session_factory() as s:
            assert len(list(s.scalars(select(PremiumReceipt)))) == 1
        role_url = os.environ.get("SERVICES_TEST_AKTUARIE_POSTGRES_URL") or os.environ.get("SERVICES_TEST_AGENT_POSTGRES_URL")
        assert role_url and role_url != os.environ.get("AGENT_AKTUARIE_DATABASE_URL")
        role_engine = create_engine(role_url, connect_args={"options": f"-csearch_path={db.name}"})
        try:
            with role_engine.connect() as conn:
                login = conn.exec_driver_sql("SELECT current_user").scalar_one()
            with db.engine.begin() as conn:
                for sql in replace(AKTUARIE, role=login).statements(db.name):
                    conn.exec_driver_sql(sql)
            for table in TABLES:
                with pytest.raises(DBAPIError), role_engine.begin() as conn:
                    conn.exec_driver_sql(f"SELECT * FROM {table}")
        finally:
            role_engine.dispose()


def test_origin_calculation_can_be_imported_without_the_service_layer():
    import os
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "-c",
        "import sys; import skills.calculation.premium_origin_ledger; assert 'services' not in sys.modules"],
        cwd=root, env={**os.environ, "PYTHONPATH": str(root / "src"), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr
