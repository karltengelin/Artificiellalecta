"""Schemalägga och dra tillbaka produktparametrar (Fas 3c 3c-P2, B-035, tjänstelager.md §9.4).

Överlappskontrollen, retroaktivitetsspärren, värdekontrollerna, agentens förslag via
godkännandekön och att premieberäkningen följer den nya versionen från dess månad.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from models import BaseAmount, ProductParameter
from services import (
    AccessDeniedError,
    Actor,
    AgentAccess,
    OperationContext,
    ProductRuleCatalog,
    ServiceLayer,
)
from services.errors import (
    BlockedError,
    ConflictError,
    InvalidInputError,
    NotFoundError,
)
from services.operations import common
from services.parameters import premium_parameters

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

TODAY = date(2026, 11, 15)  # PR-ITP1 v1.0 gäller – agenter får föreslå
HUMAN = OperationContext(actor=Actor.human("karl"), reason="Fiktiv avtalsändring K-SIM-ITP-2027")
AGENT = OperationContext(
    actor=Actor.agent("compliance_agent", team="compliance"), reason="Godkänd tolkning", run_id="run-p2"
)
APPROVER = OperationContext(actor=Actor.human("karl"))


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(common, "today", lambda: TODAY)


@pytest.fixture
def service(insurance_db):
    return ServiceLayer(session_factory=insurance_db.session_factory, rules=ProductRuleCatalog(today=TODAY))


def change(**overrides) -> dict:
    return {
        "key": "premium_age_end", "value": "67", "valid_from": "2027-01-01", "rule_version": "1.1",
        "source_ref": "K-SIM-ITP-2027", "decision_ref": "B-035 demo", **overrides,
    }


def versions(db, key="premium_age_end") -> list[tuple]:
    with db.session_factory() as s:
        rows = s.scalars(select(ProductParameter).where(ProductParameter.key == key).order_by(ProductParameter.valid_from))
        return [(r.valid_from, r.valid_to, r.value, r.status) for r in rows]


class TestSchemalagga:
    def test_ny_version_avslutar_den_foregaende(self, service, insurance_db):
        out = service.execute("schedule_product_parameter_change", HUMAN, change()).output
        assert (out.value, out.rule_id, out.rule_version) == (Decimal("67"), "PR-ITP1-013", "1.1")
        assert (out.previous_value, out.previous_valid_to) == (Decimal("66"), date(2026, 12, 31))
        assert versions(insurance_db) == [
            (date(2023, 1, 1), date(2026, 12, 31), Decimal("66"), "valid"),
            (date(2027, 1, 1), None, Decimal("67"), "valid"),
        ]
        with insurance_db.session_factory() as s:
            assert premium_parameters(s, date(2026, 12, 1)).age_end == 66
            assert premium_parameters(s, date(2027, 1, 1)).age_end == 67
            created_by = s.scalar(select(ProductParameter.created_by).where(ProductParameter.valid_from == date(2027, 1, 1)))
        assert created_by == "karl"

    def test_aldrig_retroaktivt_eller_innevarande_manad(self, service):
        for month in ("2026-11-01", "2026-10-01"):
            with pytest.raises(BlockedError, match="tidigast 2026-12-01"):
                service.execute("schedule_product_parameter_change", HUMAN, change(valid_from=month))
        assert service.execute("schedule_product_parameter_change", HUMAN, change(valid_from="2026-12-01")).output

    def test_giltighet_maste_vara_manadsforsta(self, service):
        with pytest.raises(InvalidInputError):
            service.execute("schedule_product_parameter_change", HUMAN, change(valid_from="2027-01-15"))

    def test_bara_en_kommande_version_at_gangen(self, service):
        service.execute("schedule_product_parameter_change", HUMAN, change())
        with pytest.raises(ConflictError, match="senare version.*dra tillbaka"):
            service.execute("schedule_product_parameter_change", HUMAN, change(value="68", valid_from="2026-12-01"))
        with pytest.raises(ConflictError, match="redan en version"):
            service.execute("schedule_product_parameter_change", HUMAN, change(value="68"))
        # efter 2027-01-01 avslutas 67 när 68 läggs till
        service.execute("schedule_product_parameter_change", HUMAN, change(value="68", valid_from="2028-01-01"))

    def test_samma_varde_ar_ingen_andring(self, service):
        with pytest.raises(ConflictError, match="ingen ändring"):
            service.execute("schedule_product_parameter_change", HUMAN, change(value="66"))

    @pytest.mark.parametrize("key,value,message", [
        ("premium_age_end", "66.5", "hela år"),
        ("premium_age_end", "95", "hela år"),
        ("premium_age_end", "25", "premieåldern inte ihop"),
        ("premium_rate_low", "4.5", "andel mellan 0 och 1"),
        ("premium_breakpoint_low_ibb", "30", "brytpunkterna inte ihop"),
        ("premium_breakpoint_high_ibb", "0", "positivt antal IBB"),
    ])
    def test_orimliga_varden_stoppas(self, service, key, value, message):
        with pytest.raises(BlockedError, match=message):
            service.execute("schedule_product_parameter_change", HUMAN, change(key=key, value=value))

    def test_okand_parameter_nekas(self, service):
        with pytest.raises(InvalidInputError):
            service.execute("schedule_product_parameter_change", HUMAN, change(key="pension_age"))

    def test_regel_foljer_parametern(self, service):
        out = service.execute(
            "schedule_product_parameter_change", HUMAN, change(key="premium_rate_low", value="0.05")
        ).output
        assert out.rule_id == "PR-ITP1-001"


class TestDraTillbaka:
    def test_kommande_version_dras_tillbaka_och_foregaende_galler_igen(self, service, insurance_db):
        service.execute("schedule_product_parameter_change", HUMAN, change())
        out = service.execute(
            "withdraw_product_parameter_change", HUMAN, {"key": "premium_age_end", "valid_from": "2027-01-01"}
        ).output
        assert (out.previous_value, out.previous_valid_to) == (Decimal("66"), None)
        assert versions(insurance_db) == [
            (date(2023, 1, 1), None, Decimal("66"), "valid"),
            (date(2027, 1, 1), None, Decimal("67"), "withdrawn"),
        ]
        with insurance_db.session_factory() as s:
            assert premium_parameters(s, date(2027, 6, 1)).age_end == 66
        # samma giltighetsdag kan inte återanvändas efter återkallelse (unik nyckel och dag)
        with pytest.raises(ConflictError, match="återkallad"):
            service.execute("schedule_product_parameter_change", HUMAN, change())
        assert service.execute("schedule_product_parameter_change", HUMAN, change(valid_from="2027-02-01")).output

    def test_gallande_version_kan_inte_dras_tillbaka(self, service):
        with pytest.raises(BlockedError, match="redan börjat gälla"):
            service.execute("withdraw_product_parameter_change", HUMAN,
                            {"key": "premium_age_end", "valid_from": "2023-01-01"})

    def test_okand_version(self, service):
        with pytest.raises(NotFoundError):
            service.execute("withdraw_product_parameter_change", HUMAN,
                            {"key": "premium_age_end", "valid_from": "2027-01-01"})

    def test_senaste_versionen_dras_tillbaka_forst(self, service):
        service.execute("schedule_product_parameter_change", HUMAN, change())
        service.execute("schedule_product_parameter_change", HUMAN, change(value="68", valid_from="2028-01-01"))
        with pytest.raises(ConflictError, match="senare version"):
            service.execute("withdraw_product_parameter_change", HUMAN,
                            {"key": "premium_age_end", "valid_from": "2027-01-01"})


class TestAgenter:
    def test_niva_i_registret_och_efter_giltighetsdagen(self, service, insurance_db):
        assert service.decision("schedule_product_parameter_change").effective is AgentAccess.APPROVAL
        assert service.decision("withdraw_product_parameter_change").effective is AgentAccess.HUMAN_ONLY
        before = ServiceLayer(session_factory=insurance_db.session_factory, rules=ProductRuleCatalog(today=date(2026, 10, 25)))
        assert before.decision("schedule_product_parameter_change").effective is AgentAccess.HUMAN_ONLY

    def test_agentens_forslag_galler_forst_efter_godkannande(self, service, insurance_db):
        result = service.execute("schedule_product_parameter_change", AGENT, change())
        assert result.status.value == "pending_approval" and result.approval_id
        assert [v[0] for v in versions(insurance_db)] == [date(2023, 1, 1)]  # ingenting ändrat än

        done = service.approve(result.approval_id, APPROVER, note="Grind 2 godkänd")
        assert done.output.valid_from == date(2027, 1, 1)
        with insurance_db.session_factory() as s:
            row = s.scalar(select(ProductParameter).where(ProductParameter.valid_from == date(2027, 1, 1)))
        # Handläggaren verkställer; förslagsställaren står i godkännandekön och händelseloggen
        assert row.created_by == "karl"
        assert service.approvals.get(result.approval_id).proposed_by == "compliance_agent"

    def test_agenten_kan_inte_dra_tillbaka(self, service):
        service.execute("schedule_product_parameter_change", HUMAN, change())
        with pytest.raises(AccessDeniedError):
            service.execute("withdraw_product_parameter_change", AGENT,
                            {"key": "premium_age_end", "valid_from": "2027-01-01"})


def test_forhandsberakningen_foljer_den_schemalagda_versionen(service, insurance_db):
    with insurance_db.session_factory() as s:
        s.add(BaseAmount(year=2027, income_base_amount_sek=Decimal("85000")))
        s.commit()
    preview = {"monthly_salary_sek": "40000", "birth_date": "1961-03-15", "period_month": "2027-06-01"}
    assert service.execute("calculate_premium_preview", HUMAN, preview).output.total_premium_sek == Decimal("0.00")
    service.execute("schedule_product_parameter_change", HUMAN, change())
    out = service.execute("calculate_premium_preview", HUMAN, preview).output
    assert out.total_premium_sek == Decimal("1800.00")
    assert out.calculation_basis["age_window"] == [25, 67]
